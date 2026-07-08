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
import logging
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def get_client(fast: bool = False) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_model(fast: bool = False) -> str:
    return settings.fast_model if fast else settings.default_model


async def llm_json(system: str, user: str, fast: bool = False) -> dict:
    """Call OpenAI and parse JSON response.

    Every caller (12 agents, debate, scenarios, knowledge graph, synthesis)
    treats a failure here identically to "the model legitimately returned an
    empty object" — an empty dict. That ambiguity is exactly what let a
    silently-broken OpenAI call (bad key, no access to the configured model,
    quota exhaustion, timeout) masquerade as a healthy-but-boring research
    result in production: every stage downstream degrades gracefully instead
    of surfacing an error. Logging the real exception here (with enough
    context to tell which call site failed) is what makes that failure mode
    diagnosable from `docker logs` instead of invisible.
    """
    model = get_model(fast)
    client = get_client(fast)
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(
            "llm_json call failed model=%s call=%r: %s: %s",
            model, system.strip().splitlines()[0][:80], type(e).__name__, e,
            exc_info=True,
        )
        return {}
