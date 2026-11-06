"""Inventory: checks stock by SKU and size, spots shortfalls, and finds the vendor that can restock."""

from backend.agents.base import AgentSpec

SPEC = AgentSpec(
    name="inventory",
    role="back room and shelves: hard yes/no on stock by SKU and size, low-stock flags, shortfalls, restock vendors",
    tools=frozenset({"check_stock", "list_inventory", "check_shortfall", "fulfill_from_stock",
                     "list_vendors", "get_pricing", "list_purchase_orders",
                     "plan_restock", "receive_purchase_order", "list_stock_movements"}),
)
