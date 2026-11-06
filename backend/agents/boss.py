"""Boss: reads each ticket, decides who works on it, and makes the final call."""

from backend.agents.base import AgentSpec
from backend.models import BossDecision

SPEC = AgentSpec(
    name="boss",
    role="runs the floor: triages each ticket, routes work to the right specialist, and makes the final call",
    tools=frozenset({"list_approvals", "get_cash_position", "list_vendors", "add_ticket_note"}),
    output_type=BossDecision,
)
