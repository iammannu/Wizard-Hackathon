# AlphaForage — simplified monolith

## What This Is
An AI-native financial research platform. NOT a broker, NOT a trading app.
Think: Perplexity + Bloomberg + Cursor for Finance.

## What Changed (and Why)
The original was a 6-service microservices monorepo with Nginx, Redis, TimescaleDB, Pinecone, and LangGraph.
That's great architecture at scale — but overkill before you have users.

This version collapses everything into **one FastAPI app** with **SQLite** and an **in-process cache**.
The AI core (multi-agent analysis, SSE streaming, bull/bear duality, confidence scoring) is 100% intact.

**Before → After:**
- 6 Docker services → 1 (+ frontend)
- Redis → in-process TTL dict (`app/core/cache.py`)
- TimescaleDB → SQLite (swap to Postgres: change `DATABASE_URL` in `.env`)
- Pinecone RAG → removed (add back when you have real docs to index)
- LangGraph → plain `asyncio.gather` pipeline
- nginx gateway → not needed for single service
- Turbo monorepo → not needed

## Architecture
```
app/
  main.py               FastAPI app, mounts all routers
  core/
    config.py           Single settings file
    database.py         SQLite async (SQLAlchemy)
    cache.py            In-process TTL cache (replaces Redis)
    security.py         JWT auth helpers
  models/user.py        User + RefreshToken
  providers/market.py   Polygon + Finnhub (direct, no wrapper service)
  agents/
    state.py            AgentState dataclass
    base.py             LLM + market data helpers
    agents.py           All 6 agents: technical, fundamental, sentiment, valuation, risk, macro
    supervisor.py       Orchestration: intent → agents → synthesis (replaces LangGraph)
  routers/
    auth.py             /api/v1/auth — register, login, me
    market.py           /api/v1/market — quotes, candles, fundamentals, news
    intelligence.py     /api/v1/intelligence — SSE research, sync research, compare
    screener.py         /api/v1/screener — NL stock screener

apps/web/               Next.js frontend (unchanged)
```

## Getting Started
```bash
cp .env.example .env
# Add POLYGON_API_KEY, FINNHUB_API_KEY, OPENAI_API_KEY, SECRET_KEY

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/web && pnpm install && pnpm dev
```

Or with Docker:
```bash
docker-compose up
```

## Key Design Decisions (preserved from v1)
- **Multi-agent** — technical, fundamental, sentiment, valuation, risk, macro
- **SSE streaming** — agent thinking streamed to frontend in real-time
- **Bull/Bear duality** — every analysis forces both cases
- **Calibrated confidence** — weighted by agent, penalized for conflicts
- **Intent routing** — LLM classifies query → activates relevant agents only

## When to Graduate from This
- **Add Redis** when you have multiple workers or need shared cache: swap `app/core/cache.py`
- **Switch to Postgres** when SQLite becomes a bottleneck: change `DATABASE_URL`
- **Add Pinecone RAG** when you have real SEC filings/news to index: add back `rag-service` logic
- **Split services** when independent scaling matters: the agent code is already modular

## Adding a New Agent
1. Add your async function to `app/agents/agents.py` — same pattern as the others
2. Add to `AGENT_FN` and `INTENT_TO_AGENTS` in `app/agents/supervisor.py`
3. Add the output field to `AgentState` in `app/agents/state.py`
