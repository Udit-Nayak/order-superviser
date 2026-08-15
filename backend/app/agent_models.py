from typing import Any

from pydantic import BaseModel, Field


class ToolArgs(BaseModel):
    message: str | None = None
    note: str | None = None
    reason: str | None = None
    at: str | None = None


class AgentAction(BaseModel):
    tool: str = Field(description="One enabled tool name exactly as provided.")
    args: ToolArgs = Field(default_factory=ToolArgs)


class MemoryUpdate(BaseModel):
    summary: str = Field(description="Compact rolling memory summary.")
    key_facts: dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    reasoning: str = Field(
        description="Short operational rationale. Do not include hidden chain-of-thought."
    )
    actions: list[AgentAction] = Field(default_factory=list)
    memory_update: MemoryUpdate
    next_wake_at: str | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp for the next review, or null when closing.",
    )
    close_workflow: bool = False


class FinalSummaryOutput(BaseModel):
    summary: str
    actions_taken: list[str] = Field(default_factory=list)
    key_learnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
