"""Customer Service: drafts messages for customers (drafts only, never sent)."""

from backend.agents.base import AgentSpec

SPEC = AgentSpec(
    name="customer_service",
    role="face of the shop: de-escalates and drafts plain-spoken replies using teammates' hard data (drafts only, never sent)",
    # No stock, pricing or cash tools: per its prompt it relies on Inventory and Accounting for hard data.
    tools=frozenset({"draft_customer_message", "list_approvals"}),
)
