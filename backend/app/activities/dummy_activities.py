from typing import Any

from temporalio import activity


@activity.defn
async def dummy_agent_activity(context: dict[str, Any]) -> dict[str, Any]:
    """Phase-1 stand-in for the future Gemini agent activity.

    Activities are allowed to perform I/O. For Phase 1 we only print a message
    and return deterministic-looking demo data. The workflow itself owns and
    mutates the durable in-memory timeline/state.
    """
    trigger = context.get("trigger", "unknown")
    order_id = context.get("order_id", "unknown")
    event = context.get("event")

    print(
        f"[dummy_agent_activity] order={order_id} trigger={trigger} event={event}",
        flush=True,
    )

    summary = f"Dummy supervisor handled trigger '{trigger}'."
    if event:
        summary += f" Event type: {event.get('type', 'unknown')}."

    return {
        "summary": summary,
        "memory_summary": f"Latest handled trigger: {trigger}.",
        "key_facts": {
            "last_trigger": trigger,
            "last_event_type": event.get("type") if event else None,
        },
    }


@activity.defn
async def dummy_log_activity(message: str) -> str:
    """Simple console logger activity used to prove Activity execution."""
    print(f"[dummy_log_activity] {message}", flush=True)
    return message
