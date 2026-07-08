"""
Shared OpenAI JSON-mode helper.

Lives in app/core/ (not app/agents/base.py, where it originated) so lower
layers — app/documents/evidence/ as of Milestone 2 — can call it without
creating a layering inversion (app/documents/ depending on app/agents/).
app/agents/base.py re-exports these same names, so every existing
`from app.agents.base import llm_json` caller (all 12 agents,
app/agents/supervisor.py, debate.py, scenarios.py, graph.py,
app/routers/screener.py) is unaffected.
"""
import json
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()


def get_client(fast: bool = False) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_model(fast: bool = False) -> str:
    return settings.fast_model if fast else settings.default_model


async def llm_json(system: str, user: str, fast: bool = False) -> dict:
    """Call OpenAI and parse JSON response."""
    client = get_client(fast)
    try:
        resp = await client.chat.completions.create(
            model=get_model(fast),
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[llm_json error]: {e}")
        return {}
