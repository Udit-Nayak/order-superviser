import json
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError
from temporalio import activity

from app.agent_models import AgentAction, AgentDecision, FinalSummaryOutput, MemoryUpdate
from app.config import settings
from app.tools.registry import TOOL_REGISTRY, enabled_tool_specs, validate_tool_args


SUPPORTED_EVENTS = {
    "order_created",
    "payment_confirmed",
    "payment_failed",
    "shipment_created",
    "shipment_delayed",
    "delivered",
    "customer_message_received",
    "refund_requested",
    "order_state_changed",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _model_and_temperature(supervisor_config: dict[str, Any]) -> tuple[str, float | None]:
    llm = supervisor_config.get("model_config") or {}
    model = llm.get("model") or settings.gemini_model
    temperature = llm.get("temperature", 0.2)
    # Gemini 3.5/3.6 deprecate legacy sampling controls; omit temperature there.
    if str(model).startswith("gemini-3"):
        temperature = None
    return str(model), temperature


async def _generate_structured(
    *,
    model: str,
    prompt: str,
    schema: type,
    temperature: float | None,
) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing in .env")

    kwargs: dict[str, Any] = {
        "response_mime_type": "application/json",
        "response_json_schema": schema.model_json_schema(),
    }
    # if temperature is not None:
    #     kwargs["temperature"] = temperature

    async with genai.Client(api_key=settings.gemini_api_key).aio as client:
        response = await client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**kwargs),
        )
    return response.text or ""


def _safe_fallback(context: dict[str, Any], warning: str) -> dict[str, Any]:
    default_seconds = int(context.get("default_wake_seconds", 3600))
    wake = _utc_now() + timedelta(seconds=default_seconds)
    return {
        "reasoning": "Safe fallback: no external action taken.",
        "actions": [],
        "memory_update": {
            "summary": context.get("memory_summary", ""),
            "key_facts": context.get("key_facts", {}),
        },
        "next_wake_at": wake.isoformat(),
        "close_workflow": False,
        "warnings": [warning],
        "fallback": True,
    }


@activity.defn
async def classify_event_activity(data: dict[str, Any]) -> dict[str, Any]:
    event = data.get("event") or {}
    event_type = str(event.get("type", "unknown"))
    important = event_type in SUPPORTED_EVENTS
    return {
        "important": important,
        "event_type": event_type,
        "reason": (
            "supported order lifecycle event"
            if important
            else "unsupported event logged without AI wake"
        ),
    }


@activity.defn
async def run_agent_activity(context: dict[str, Any]) -> dict[str, Any]:
    supervisor = context.get("supervisor_config") or {}
    enabled_tools = list(supervisor.get("tools_enabled") or [])
    model, temperature = _model_and_temperature(supervisor)

    prompt_payload = {
        "base_instruction": supervisor.get("base_instruction", "Supervise this order."),
        "active_run_instructions": context.get("instructions", []),
        "memory_summary": context.get("memory_summary", ""),
        "key_facts": context.get("key_facts", {}),
        "recent_timeline": list(context.get("timeline", []))[-20:],
        "trigger": context.get("trigger"),
        "triggering_event": context.get("event"),
        "external_order_state": context.get("external_state", {}),
        "actions_already_taken_this_wake": context.get("already_executed_actions", []),
        "current_workflow_block": context.get("current_block"),
        "block_instruction": context.get("block_instruction", ""),
        "available_tools": enabled_tool_specs(enabled_tools),
    }

    prompt = (
        "You are the long-running AI supervisor for one commerce order.\n"
        "Decide whether action is needed now, update compact memory, and choose a next wake time.\n"
        "Only request tools that appear in available_tools. Keep reasoning short and operational.\n"
        "Treat the current workflow block and its block_instruction as the active policy for this stage.\n"
        "The Temporal workflow owns lifecycle transitions and completion; do not try to close the workflow yourself.\n"
        "The external_order_state is the factual source of truth. Never invent payment/shipment/delivery state.\n"
        "Do not repeat a tool listed in actions_already_taken_this_wake.\n"
        "When shipment_delayed or payment_failed occurs, follow the supervisor/run instructions closely; "
        "if they require escalation or review, call the corresponding enabled tool immediately.\n"
        "Return only data matching the response schema.\n\n"
        f"CONTEXT:\n{json.dumps(prompt_payload, ensure_ascii=False, default=str)}"
    )

    parse_errors: list[str] = []
    decision: AgentDecision | None = None

    for attempt in range(2):
        if settings.phase2_force_bad_gemini_json:
            raw = "{ intentionally malformed phase2 test json"
        else:
            strict_suffix = (
                "\n\nSTRICT RETRY: Return valid JSON only and exactly match the schema."
                if attempt == 1
                else ""
            )
            raw = await _generate_structured(
                model=model,
                prompt=prompt + strict_suffix,
                schema=AgentDecision,
                temperature=temperature,
            )
        try:
            decision = AgentDecision.model_validate_json(raw)
            break
        except (ValidationError, ValueError) as exc:
            parse_errors.append(f"attempt {attempt + 1}: {exc}")

    if decision is None:
        return _safe_fallback(
            context,
            "Gemini returned malformed/invalid structured output twice; safe fallback decision used.",
        )

    actions = [action.model_dump(mode="json", exclude_none=True) for action in decision.actions]

    # Deterministic Phase-2 test hook. Leave blank in normal use.
    if settings.phase2_test_force_disallowed_tool:
        actions.append(
            {
                "tool": settings.phase2_test_force_disallowed_tool,
                "args": {"reason": "Phase 2 disallowed-tool verification"},
            }
        )

    warnings: list[str] = []
    filtered_actions: list[dict[str, Any]] = []
    already_taken = set(context.get("already_executed_actions") or [])
    for action in actions:
        tool_name = action["tool"]
        args = action.get("args") or {}
        if tool_name in already_taken:
            warnings.append(
                f"Dropped duplicate tool action '{tool_name}' because the workflow already executed it in this wake."
            )
            continue
        if tool_name not in enabled_tools:
            warnings.append(
                f"Dropped disallowed tool action '{tool_name}' because it is not enabled for this supervisor."
            )
            continue
        if tool_name not in TOOL_REGISTRY:
            warnings.append(f"Dropped unknown tool action '{tool_name}'.")
            continue
        valid, normalized_or_error = validate_tool_args(tool_name, args)
        if not valid:
            warnings.append(
                f"Dropped tool action '{tool_name}' because its arguments were invalid: {normalized_or_error}"
            )
            continue
        filtered_actions.append({"tool": tool_name, "args": normalized_or_error})

    next_wake = _parse_iso(decision.next_wake_at)
    # Completion belongs to the Temporal state machine, so even if Gemini asks
    # to close we still require a valid future monitoring wake until the
    # deterministic lifecycle itself reaches a terminal state.
    if next_wake is None or next_wake <= _utc_now():
        next_wake = _utc_now() + timedelta(
            seconds=int(context.get("default_wake_seconds", 3600))
        )
        warnings.append("Missing/past next_wake_at replaced with the configured block poll interval.")

    if decision.close_workflow:
        warnings.append(
            "Agent requested close_workflow, but lifecycle completion is owned by the deterministic Temporal state machine."
        )

    result = decision.model_dump(mode="json", exclude_none=True)
    result["actions"] = filtered_actions
    result["close_workflow"] = False
    result["next_wake_at"] = next_wake.isoformat()
    result["warnings"] = warnings
    result["fallback"] = False
    return result


@activity.defn
async def run_final_summary_activity(context: dict[str, Any]) -> dict[str, Any]:
    supervisor = context.get("supervisor_config") or {}
    model, temperature = _model_and_temperature(supervisor)
    prompt = (
        "Produce the final structured summary for this completed/terminated order-supervisor run. "
        "Be concise and concrete. Return only schema-compatible JSON.\n\n"
        f"Order ID: {context.get('order_id')}\n"
        f"Base instruction: {supervisor.get('base_instruction', '')}\n"
        f"Run instructions: {json.dumps(context.get('instructions', []), ensure_ascii=False)}\n"
        f"Memory: {context.get('memory_summary', '')}\n"
        f"Key facts: {json.dumps(context.get('key_facts', {}), ensure_ascii=False, default=str)}\n"
        f"Timeline: {json.dumps(context.get('timeline', []), ensure_ascii=False, default=str)}"
    )

    for attempt in range(2):
        if settings.phase2_force_bad_gemini_json:
            raw = "{ malformed final summary test"
        else:
            raw = await _generate_structured(
                model=model,
                prompt=prompt
                + ("\nSTRICT RETRY: valid JSON only." if attempt == 1 else ""),
                schema=FinalSummaryOutput,
                temperature=temperature,
            )
        try:
            return FinalSummaryOutput.model_validate_json(raw).model_dump(mode="json")
        except (ValidationError, ValueError):
            pass

    actions = [
        item["summary"]
        for item in context.get("timeline", [])
        if item.get("type") == "tool_call"
    ]
    return FinalSummaryOutput(
        summary=context.get("memory_summary")
        or f"Order supervisor run for {context.get('order_id')} ended.",
        actions_taken=actions,
        key_learnings=["Gemini final-summary parsing failed; fallback summary was generated."],
        recommendations=["Review the timeline for full operational details."],
    ).model_dump(mode="json")
