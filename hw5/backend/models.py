"""Data types for the Campus Customs agent team and its API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- the team

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

EventKind = Literal["run_started", "tool_call", "tool_result", "delegate", "reply", "decision", "error", "human"]
TicketStatus = Literal["open", "in_progress", "awaiting_approval", "needs_human", "resolved"]


@dataclass
class TeamDeps:
    """Per-run context handed to every agent (PydanticAI `deps`).

    A delegation makes a child copy (`depth + 1`, `chain` extended) that shares the same
    `budget` dict, so the delegation limit counts across the whole ticket run.
    """

    agent: AgentName
    ticket_id: int
    run_id: str
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    budget: dict[str, int] = field(default_factory=lambda: {"delegations": 0, "tokens": 0})
    step: int = 0  # agent-loop step counter for this one agent run (audit trail)


class BossDecision(BaseModel):
    """The Boss's structured final call on a ticket."""

    outcome: Literal["resolved", "awaiting_approval", "needs_human"] = Field(
        description="awaiting_approval if any approval request exists for the ticket; needs_human if a person "
                    "must decide or supply information; resolved if nothing is left to do.")
    decision: str = Field(description="The final call in one or two sentences.")
    summary: str = Field(description="What each teammate did, with approval / message IDs.")


# ---------------------------------------------------------------- API request bodies

class RunRequest(BaseModel):
    note: str | None = Field(None, description="Optional guidance from the human manager for the Boss.")


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = ""


class MessageAction(BaseModel):
    action: Literal["approve", "discard"]
    body: str | None = Field(None, description="Edited draft text to keep (drafts are never emailed).")
