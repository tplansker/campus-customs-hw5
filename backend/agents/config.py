"""Model and loop settings shared by the whole team.

Every agent is built from the same model: gpt-6-luna, called through Portkey with PORTKEY_API_KEY.
The name is read once from OPENAI_MODEL (default gpt-6-luna); any other value is refused.
"""

from __future__ import annotations

import os
from functools import cache

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from openai import AsyncOpenAI
from pydantic_ai import UsageLimits
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import shared.db  # noqa: F401  (loads .env files before the settings below are read)

REQUIRED_MODEL = "gpt-6-luna"
MODEL_NAME = os.getenv("OPENAI_MODEL", REQUIRED_MODEL).strip()
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp")

# Agent-loop limits.
MAX_DEPTH = 3            # delegation chain: boss (0) -> a (1) -> b (2) -> c (3)
MAX_DELEGATIONS = 16     # total delegations in one ticket run, across all agents
MAX_TICKET_TOKENS = 400_000   # token budget for one ticket run, all agents together
# Per single agent run: model requests, tool calls and tokens.
RUN_LIMITS = UsageLimits(request_limit=20, tool_calls_limit=30, total_tokens_limit=150_000)
MAX_OUTPUT_TOKENS = 4_000     # cap on each model response (reasoning tokens count toward it)


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to HW5/.env (see .env.example).")
    return key


@cache
def build_model() -> OpenAIResponsesModel:
    """The one model every agent shares: gpt-6-luna via Portkey."""
    if MODEL_NAME != REQUIRED_MODEL:
        raise RuntimeError(f"OPENAI_MODEL is '{MODEL_NAME}', but every Campus Customs agent must use {REQUIRED_MODEL}.")
    key = require_api_key()
    client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=key, default_headers={"x-portkey-api-key": key})
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
