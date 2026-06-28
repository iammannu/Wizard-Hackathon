"""
Base helpers for all agents.
Direct calls to provider functions — no inter-service HTTP.
"""
import json
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.providers import market as mkt

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


# Re-export market data helpers for agents to import from one place
get_quote = mkt.get_quote
get_candles = mkt.get_candles
get_news = mkt.get_news
get_fundamentals = mkt.get_fundamentals
get_analyst = mkt.get_analyst
