from typing import Any

from temporalio import activity

from app.tools.registry import BUSINESS_ACTIONS, validate_tool_args


@activity.defn
async def execute_tool_activity(data: dict[str, Any]) -> dict[str, Any]:
    tool_name = data["tool"]
    ok, validated = validate_tool_args(tool_name, data.get("args", {}))
    if not ok:
        raise ValueError(f"Invalid args for {tool_name}: {validated}")

    args = validated
    run_id = data.get("run_id", "unknown")
    order_id = data.get("order_id", "unknown")

    if tool_name == "message_fulfillment_team":
        summary = f"Fulfillment team message: {args['message']}"
        result = {}
    elif tool_name == "message_payments_team":
        summary = f"Payments team message: {args['message']}"
        result = {}
    elif tool_name == "message_logistics_team":
        summary = f"Logistics team message: {args['message']}"
        result = {}
    elif tool_name == "message_customer":
        summary = f"Customer message: {args['message']}"
        result = {}
    elif tool_name == "create_internal_note":
        summary = f"Internal note: {args['note']}"
        result = {}
    elif tool_name == "schedule_next_wake_up":
        summary = f"Next wake explicitly scheduled for {args['at']}"
        result = {"next_wake_at": args["at"]}
    else:
        raise ValueError(f"Unknown tool: {tool_name}")

    print(
        f"[tool] run={run_id} order={order_id} tool={tool_name} args={args}",
        flush=True,
    )

    return {
        "ok": True,
        "tool": tool_name,
        "args": args,
        "summary": summary,
        "is_business_action": tool_name in BUSINESS_ACTIONS,
        **result,
    }