"""Accounting: watches cash and invoices, checks margins, prepares payments and POs for human approval."""

from backend.agents.base import AgentSpec

SPEC = AgentSpec(
    name="accounting",
    role="cash flow, invoices and disputes: verifies the ledger, checks margins, prepares payments and POs for human approval",
    tools=frozenset({"get_cash_position", "list_invoices", "list_payments", "get_pricing", "calculate_margin",
                     "list_vendors", "request_payment", "request_purchase_order", "request_discount",
                     "list_approvals", "list_purchase_orders",
                     "get_invoice", "plan_restock", "price_for_margin"}),
)
