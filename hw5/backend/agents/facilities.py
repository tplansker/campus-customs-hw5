"""Facilities: handles the shop space: leases, rent and landlord notices."""

from backend.agents.base import AgentSpec

SPEC = AgentSpec(
    name="facilities",
    role="the physical store: repairs, safety, security, and the lease/rent for the Chapel Street space",
    tools=frozenset({"list_leases", "get_lease", "get_cash_position", "add_ticket_note"}),
)
