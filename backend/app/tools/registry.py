from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class TeamMessageArgs(BaseModel):
    message: str = Field(min_length=1)


class CustomerMessageArgs(BaseModel):
    message: str = Field(min_length=1)


class InternalNoteArgs(BaseModel):
    note: str = Field(min_length=1)


class ScheduleNextWakeArgs(BaseModel):
    at: datetime


# Exact required business actions from the assignment.
BUSINESS_ACTIONS = {
    "message_fulfillment_team",
    "message_payments_team",
    "message_logistics_team",
    "message_customer",
    "create_internal_note",
}

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "message_fulfillment_team": {
        "description": "Create an activity representing a message to the fulfillment team.",
        "args_model": TeamMessageArgs,
        "kind": "business_action",
    },
    "message_payments_team": {
        "description": "Create an activity representing a message to the payments team.",
        "args_model": TeamMessageArgs,
        "kind": "business_action",
    },
    "message_logistics_team": {
        "description": "Create an activity representing a message to the logistics team.",
        "args_model": TeamMessageArgs,
        "kind": "business_action",
    },
    "message_customer": {
        "description": "Create an activity representing a message to the customer.",
        "args_model": CustomerMessageArgs,
        "kind": "business_action",
    },
    "create_internal_note": {
        "description": "Create an internal activity/note for the current order run.",
        "args_model": InternalNoteArgs,
        "kind": "business_action",
    },
    # Runtime capability: assignment allows sleep/wake as a tool or workflow method.
    "schedule_next_wake_up": {
        "description": "Runtime capability to set the next durable wake time.",
        "args_model": ScheduleNextWakeArgs,
        "kind": "runtime",
    },
}


def enabled_tool_specs(tool_names: list[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in tool_names:
        item = TOOL_REGISTRY.get(name)
        if not item:
            continue
        specs.append(
            {
                "name": name,
                "description": item["description"],
                "args_schema": item["args_model"].model_json_schema(),
                "kind": item["kind"],
            }
        )
    return specs


def validate_tool_args(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[bool, dict[str, Any] | str]:
    item = TOOL_REGISTRY.get(tool_name)
    if not item:
        return False, f"Unknown tool: {tool_name}"
    try:
        model = item["args_model"].model_validate(args)
    except ValidationError as exc:
        return False, exc.errors(include_url=False).__repr__()
    return True, model.model_dump(mode="json")