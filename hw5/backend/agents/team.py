"""The Campus Customs team: builds the five PydanticAI agents and runs the delegation loop.

Full connectivity: every agent has `delegate(to, task)`, which can run ANY teammate, the Boss included.
The loop is bounded by MAX_DEPTH (chain length), MAX_DELEGATIONS and MAX_TICKET_TOKENS (per ticket
run), RUN_LIMITS (model requests, tool calls and tokens per agent run) and MAX_OUTPUT_TOKENS.

Each agent runs through `run_agent`, which walks PydanticAI's loop node by node (`agent.iter`) so that
every model request and response is written to output/audit_trail.json next to the tool calls.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from pydantic_ai import Agent, RunContext

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.agents.base import AgentSpec, build_instructions
from backend.agents.config import (MAX_DELEGATIONS, MAX_DEPTH, MAX_OUTPUT_TOKENS, MAX_TICKET_TOKENS, MODEL_NAME,
                                   RUN_LIMITS, build_model)
from backend.agents.tools import _short, emit, toolset_for
from backend.models import AGENT_NAMES, AgentName, BossDecision, TeamDeps

TEAM: dict[str, AgentSpec] = {m.SPEC.name: m.SPEC for m in (boss, inventory, accounting, facilities, customer_service)}
assert tuple(TEAM) == AGENT_NAMES


async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
    """Ask a teammate to do part of the work and return their reply.

    Args:
        to: Teammate to delegate to: boss, inventory, accounting, facilities or customer_service.
        task: A self-contained instruction with the ticket id, SKUs, sizes, quantities and amounts they need.
    """
    d = ctx.deps
    if to == d.agent:
        return "You cannot delegate to yourself. Do it with your own tools."
    if to not in TEAM:
        return f"Unknown teammate '{to}'. Choose one of: {', '.join(TEAM)}."
    if d.depth >= MAX_DEPTH:
        return f"Delegation chain too deep ({' → '.join(d.chain)}). Finish with what you have."
    if d.budget["delegations"] >= MAX_DELEGATIONS:
        return "The delegation budget for this ticket is used up. Finish with what you have."
    if d.budget["tokens"] >= MAX_TICKET_TOKENS:
        return f"The token budget for this ticket ({MAX_TICKET_TOKENS:,}) is used up. Finish with what you have."
    d.budget["delegations"] += 1

    emit(d.run_id, d.ticket_id, d.agent, "delegate", _deps=d, to=to, task=task)
    child = TeamDeps(agent=to, ticket_id=d.ticket_id, run_id=d.run_id, depth=d.depth + 1,
                     chain=[*d.chain, to], budget=d.budget)
    prompt = f"Ticket #{d.ticket_id}. {d.agent} asks you (delegation chain: {' → '.join(child.chain)}):\n\n{task}"
    try:
        out = await run_agent(to, prompt, child)
    except Exception as exc:  # includes UsageLimitExceeded: report it, don't crash the caller
        emit(d.run_id, d.ticket_id, to, "error", _deps=child, message=f"{type(exc).__name__}: {exc}")
        return f"{to} failed: {type(exc).__name__}: {exc}"
    reply = f"{out.decision}\n{out.summary}" if isinstance(out, BossDecision) else str(out)
    emit(d.run_id, d.ticket_id, to, "reply", _deps=child, to=d.agent, text=reply)
    return reply


async def run_agent(name: str, prompt: str, deps: TeamDeps) -> Any:
    """One agent loop. Audits every model request/response; tool calls are audited by the MCP hook."""
    emit(deps.run_id, deps.ticket_id, name, "agent_started", _deps=deps, _feed=False, model=MODEL_NAME, prompt=prompt)
    async with build_agent(name).iter(prompt, deps=deps, usage_limits=RUN_LIMITS) as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                parts = [{"kind": p.part_kind, **({"tool": p.tool_name} if hasattr(p, "tool_name") else {})}
                         for p in node.request.parts]
                emit(deps.run_id, deps.ticket_id, name, "model_request", _deps=deps, _feed=False, parts=parts)
            elif Agent.is_call_tools_node(node):
                r = node.model_response
                tokens = (r.usage.input_tokens or 0) + (r.usage.output_tokens or 0)
                deps.budget["tokens"] += tokens
                emit(deps.run_id, deps.ticket_id, name, "model_response", _deps=deps, _feed=False,
                     model=r.model_name, finish_reason=r.finish_reason,
                     input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
                     ticket_tokens_so_far=deps.budget["tokens"],
                     tool_calls=[{"tool": p.tool_name, "args": p.args_as_dict()} for p in r.parts if p.part_kind == "tool-call"],
                     text=_short(" ".join(p.content for p in r.parts if p.part_kind == "text"), 800))
        output = run.result.output
        usage = run.usage()
    emit(deps.run_id, deps.ticket_id, name, "agent_finished", _deps=deps, _feed=False,
         requests=usage.requests, tool_calls=usage.tool_calls, input_tokens=usage.input_tokens,
         output_tokens=usage.output_tokens,
         output=output.model_dump() if isinstance(output, BossDecision) else _short(str(output), 1500))
    return output


@cache
def build_agent(name: str) -> Agent[TeamDeps, Any]:
    spec = TEAM[name]
    return Agent(
        build_model(),                       # gpt-6-luna via Portkey, shared by all five
        name=spec.name,
        deps_type=TeamDeps,
        output_type=spec.output_type,
        instructions=build_instructions(spec, TEAM),
        toolsets=[toolset_for(spec.tools)],  # MCP tools for this role
        tools=[delegate],                    # full connectivity
        retries=2,
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS},
    )


async def work_ticket(ticket_id: int, run_id: str, human_note: str | None = None) -> BossDecision:
    """Run the team on one ticket: the Boss starts, delegates as needed, and returns the final call."""
    deps = TeamDeps(agent="boss", ticket_id=ticket_id, run_id=run_id, chain=["boss"])
    prompt = f"New work on ticket #{ticket_id}. Read it with get_ticket, coordinate the team, and make the final call."
    if human_note:
        prompt += f"\n\nNote from the human manager: {human_note}"
    emit(run_id, ticket_id, "boss", "run_started", _deps=deps, prompt=prompt)
    output = await run_agent("boss", prompt, deps)
    emit(run_id, ticket_id, "boss", "decision", _deps=deps, ticket_tokens=deps.budget["tokens"],
         delegations=deps.budget["delegations"], **output.model_dump())
    return output
