"""What defines an agent, and how its instructions are assembled from backend/prompts/."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@dataclass(frozen=True)
class AgentSpec:
    name: str                 # also the prompt file name: backend/prompts/<name>.md
    role: str                 # one line for the team roster every agent sees
    tools: frozenset[str]     # role-specific MCP tools (the shared ones are added automatically)
    output_type: Any = str    # the Boss returns a BossDecision; specialists reply in text


def build_instructions(spec: AgentSpec, team: dict[str, AgentSpec]) -> str:
    roster = "\n".join(f"- **{s.name}**: {s.role}" for s in team.values())
    shared = (PROMPTS_DIR / "_team_rules.md").read_text(encoding="utf-8").replace("{team_roster}", roster)
    own = (PROMPTS_DIR / f"{spec.name}.md").read_text(encoding="utf-8")
    return f"{shared}\n\n{own}"
