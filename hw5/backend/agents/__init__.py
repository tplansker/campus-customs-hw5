"""Campus Customs agent team: boss, inventory, accounting, facilities, customer_service."""

from backend.agents.config import MCP_URL, MODEL_NAME
from backend.agents.team import TEAM, build_agent, work_ticket
from backend.agents.tools import emit, mcp_toolset

__all__ = ["MCP_URL", "MODEL_NAME", "TEAM", "build_agent", "work_ticket", "emit", "mcp_toolset"]
