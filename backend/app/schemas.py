from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.tools.registry import BUSINESS_ACTIONS, TOOL_REGISTRY


class SupervisorModelSettings(BaseModel):
    model: str = Field(default="gemini-3.6-flash", min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class CreateSupervisorRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    base_instruction: str = Field(min_length=1)
    tools_enabled: list[str] = Field(default_factory=lambda: sorted(BUSINESS_ACTIONS))
    llm_config: SupervisorModelSettings = Field(
        default_factory=SupervisorModelSettings,
        alias="model_config",
    )

    @field_validator("tools_enabled")
    @classmethod
    def validate_tools(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(TOOL_REGISTRY))
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class StartRunRequest(BaseModel):
    order_id: str = Field(min_length=1)
    supervisor_id: UUID


class IncomingOrderRequest(BaseModel):
    order_id: str = Field(min_length=1)
    supervisor_id: UUID


class OrderEventRequest(BaseModel):
    type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    instruction: str | None = None


class InstructionRequest(BaseModel):
    text: str = Field(min_length=1)


class HumanActionRequest(BaseModel):
    text: str = Field(min_length=1)


class ExternalOrderStatePatch(BaseModel):
    """Changes the demo external-system source of truth, then wakes Temporal.

    This is what the right panel should call. It simulates a payment gateway,
    warehouse, courier, or post-delivery service changing the real order state.
    """

    payment_status: Literal["pending", "failed", "confirmed"] | None = None
    shipment_status: Literal[
        "not_created", "created", "in_transit", "delayed", "delivered"
    ] | None = None
    delivery_status: Literal["pending", "delivered"] | None = None
    additional_delay_hours: float | None = Field(default=None, ge=0.0, le=10_000.0)
    latest_eta: datetime | None = None
    refund_status: Literal["none", "requested", "resolved"] | None = None
    customer_message: str | None = Field(default=None, max_length=5000)
    instruction: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def require_change(self) -> "ExternalOrderStatePatch":
        values = self.model_dump(exclude_none=True)
        values.pop("instruction", None)
        if not values:
            raise ValueError("Provide at least one external order-state change")
        return self


WorkflowBlockType = Literal[
    "order_created",
    "payment",
    "shipment",
    "in_transit",
    "delivered",
    "post_delivery",
]


class WorkflowBlock(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    block_type: WorkflowBlockType
    label: str = Field(min_length=1, max_length=200)
    wait_seconds: int = Field(default=0, ge=0, le=86_400)
    instruction: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SaveWorkflowTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    supervisor_id: UUID
    blocks: list[WorkflowBlock] = Field(min_length=1)
    active: bool = True


# Existing Phase-4 scenario schema is kept so old CLI scenarios still work.
class ScenarioEvent(BaseModel):
    type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioCondition(BaseModel):
    event_type_equals: str = Field(min_length=1)


class ScenarioStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event: ScenarioEvent | None = None
    instruction: str | None = Field(default=None, min_length=1)
    wait: float | None = Field(default=None, ge=0.0, le=3600.0)
    condition: ScenarioCondition | None = Field(default=None, alias="if")
    then: list["ScenarioStep"] = Field(default_factory=list)
    wait_after: float | None = Field(default=None, ge=0.0, le=3600.0)

    @model_validator(mode="after")
    def validate_kind(self) -> "ScenarioStep":
        kinds = [
            self.event is not None,
            self.instruction is not None,
            self.wait is not None,
            self.condition is not None,
        ]
        if sum(kinds) != 1:
            raise ValueError("Scenario step must contain exactly one step kind")
        if self.condition is not None and not self.then:
            raise ValueError("An if step requires nested then steps")
        return self


class ScenarioDefinition(BaseModel):
    supervisor: CreateSupervisorRequest
    order_id: str = Field(min_length=1)
    default_wake_seconds: int = Field(default=60, ge=5, le=86_400)
    steps: list[ScenarioStep] = Field(min_length=1)


ScenarioStep.model_rebuild()
