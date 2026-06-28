# AlphaForage — Autonomous Investment Intelligence Platform

> Think Perplexity + Bloomberg + Cursor for Finance — built for the Wizard Hackathon.

12 AI agents run in parallel, debate each other when they disagree, generate probabilistic scenario simulations, extract knowledge graphs, and stream every step live to the browser. All backed by real-time web research from You.com and Tavily. Not a broker, not a trading app — pure autonomous research infrastructure.

---

## What's Inside

```
Backend   FastAPI monolith · SQLite · in-process TTL cache · real-time SSE via asyncio.Queue
Frontend  React 18 + Vite · Zustand · dark-mode · live agent activity panel
Research  You.com (primary) + Tavily (cross-validation) → 12 agents → debate → scenarios → graph
```

---

## Architecture

```
app/
  main.py                   FastAPI app — mounts all routers, initialises DB
  core/
    config.py               Single settings class (reads .env)
    database.py             SQLite async via SQLAlchemy + aiosqlite
    cache.py                In-process TTL dict (replaces Redis)
    security.py             JWT creation + bcrypt password hashing
  models/
    user.py                 User + RefreshToken ORM models
    workspace.py            Workspace + WorkspaceResearch ORM models
  providers/
    market.py               Polygon.io + Finnhub — quotes, candles, fundamentals, news
    youcom.py               You.com Web Search API (api.you.com/v1/search) — primary research
    tavily.py               Tavily Search API — cross-validation layer
    evidence.py             Merges You.com + Tavily into unified evidence chain
  agents/
    state.py                AgentState dataclass — carries everything through the pipeline
    base.py                 llm_json() helper + shared market data fetchers
    agents.py               All 12 agents (see below)
    supervisor.py           Full pipeline: intent → evidence → agents → debate → scenarios → graph → synthesis
    debate.py               2-round structured debate engine with neutral moderator
    scenarios.py            Probabilistic scenario simulation (5 futures per analysis)
    graph.py                Knowledge graph extraction (entities + relationships)
  routers/
    auth.py                 /api/v1/auth
    market.py               /api/v1/market
    intelligence.py         /api/v1/intelligence  — real-time SSE research
    workspaces.py           /api/v1/workspaces    — Living Research Workspaces
    screener.py             /api/v1/screener

web/
  src/
    pages/
      Landing.jsx           Marketing page — 12-agent grid, sponsor section, demo flow
      Research.jsx          Chat interface — live agent panel, debate, scenarios, graph
      Workspaces.jsx        Workspace list + template workspaces + create modal
      WorkspaceDetail.jsx   Full workspace view — agents, event log, debate, scenarios, graph
      Screener.jsx          Natural-language stock screener
      pages.jsx             Market watchlist, Portfolio P&L, Earnings calendar
    store/index.js          Zustand stores — handles all SSE event types in real time
    lib/api.js              SSE streaming client + REST api helpers
```

---

## The 12-Agent AI Team

| Agent | Role | Signal type |
|---|---|---|
| **Technical Analyst** | RSI-14, SMA-20/50/200, golden cross, support/resistance | bullish / bearish / neutral |
| **Fundamental Analyst** | P/E, margins, earnings quality, balance sheet health | bullish / bearish / neutral |
| **Sentiment Analyst** | News headlines → sentiment score, key catalysts | bullish / bearish / neutral |
| **Valuation Expert** | DCF, comparables, fair-value range, margin of safety | bullish / bearish / neutral |
| **Risk Manager** | Annualised volatility, max drawdown, beta, VaR | bullish / bearish / neutral |
| **Macro Economist** | Rate environment, inflation trend, economic cycle phase | bullish / bearish / neutral |
| **Growth Investor** | TAM expansion, revenue acceleration, R&D reinvestment | bullish / bearish / neutral |
| **Value Investor** | Intrinsic value, owner earnings, moat durability | bullish / bearish / neutral |
| **Quant Researcher** | Statistical factors, momentum, mean-reversion signals | bullish / bearish / neutral |
| **Industry Specialist** | Sector-specific dynamics, competitive positioning | bullish / bearish / neutral |
| **Short Seller** | Red flags, accounting risks, downside catalysts | bullish / bearish / neutral |
| **Devil's Advocate** | Challenges the consensus — runs last with all outputs visible | bullish / bearish / neutral |

> Devil's Advocate always runs after all others so it can challenge the emerging consensus.

---

## Full Pipeline

```
User query
    │
    ▼
Intent Parser          classifies into 8 intents via GPT-4o-mini
    │
    ▼
Evidence Gathering     You.com + Tavily in parallel
    │                  → merged evidence chain with confidence boost
    ▼
12 Agents              all run in parallel via asyncio.gather
    │                  each emits agent_complete the moment it finishes (real-time SSE)
    ▼
Agent Debate           triggered when bull/bear conflict exists + depth="full"
    │                  2 rounds: opening arguments → rebuttals → moderator conclusion
    ▼
Scenario Simulation    5 probabilistic futures (bull, bear, base, tail risk, black swan)
    │                  each with probability, upside/downside %, time horizon
    ▼
Knowledge Graph        8-14 nodes (company, tech, sector, macro, country, person, product)
    │                  8-14 edges (relationships between entities)
    ▼
Synthesis              Research Director LLM synthesises all outputs into
                       institutional investment thesis:
                       recommendation · explanation · bull/bear cases ·
                       key risks · invalidation conditions · known unknowns
```

### Intent → Agent Mapping

| Intent | Agents activated |
|---|---|
| `stock_analysis` | technical, fundamental, sentiment, risk, valuation, growth_investor, value_investor, quant_researcher, industry_specialist, short_seller, devils_advocate |
| `comparison` | fundamental, valuation, risk, technical, growth_investor, value_investor |
| `screener` | fundamental, technical, risk, quant_researcher |
| `macro_query` | macro, sentiment, industry_specialist |
| `portfolio_check` | risk, macro, quant_researcher, value_investor |
| `scenario_analysis` | macro, risk, industry_specialist, devils_advocate |
| `event_impact` | macro, sentiment, risk, industry_specialist |
| `general` | fundamental, sentiment, macro |

Pass `depth: "quick"` to use only the first 3 agents for that intent (faster, lower cost).

---

## Real-Time SSE Architecture

The streaming is genuinely real-time — events are pushed to the client the moment they happen, not batched at the end.

```
Intelligence router
    │
    ├── asyncio.Queue()
    ├── asyncio.create_task(run_research(..., on_event=queue.put))
    │       │
    │       └── supervisor.py emits each event immediately via on_event callback:
    │               intent_parsed → evidence_searching → evidence_gathered →
    │               agent_start (×N) → agent_complete (as each finishes) →
    │               debate_starting → debate_complete →
    │               scenarios_generating → scenarios_generated →
    │               graph_building → graph_built →
    │               synthesizing → synthesis_complete
    │
    └── SSE generator drains queue and yields events as they arrive
```

Events are also stored in `state.stream_events` for backwards-compatible sync callers.

---

## Living Research Workspaces

Persistent investment theses that accumulate research over time.

```
POST /api/v1/workspaces                          create workspace
GET  /api/v1/workspaces                          list all active
GET  /api/v1/workspaces/{id}                     detail + research history (latest 10)
PATCH /api/v1/workspaces/{id}                    update title/tickers/themes/icon
DELETE /api/v1/workspaces/{id}                   archive (soft delete)

POST /api/v1/workspaces/{id}/research            SSE streaming research (real-time)
POST /api/v1/workspaces/{id}/research/sync       sync research (single JSON response)
GET  /api/v1/workspaces/{id}/history             full research history (latest 20)
```

Each workspace tracks `tracked_tickers`, `tracked_sectors`, `tracked_themes`. Research results are persisted to SQLite and the workspace confidence + thesis are updated after every run. Opening a workspace with no history auto-triggers an initial analysis.

---

## Sponsor Integrations

| Sponsor | Role | Endpoint |
|---|---|---|
| **You.com** | Primary web research engine | `api.you.com/v1/search` |
| **Tavily** | Cross-validation + AI answer layer | Tavily Search API |
| **InsForge** | Deployment infrastructure | Agent services + API hosting |
| **Nebius** | GPU inference | Future large reasoning models |

You.com and Tavily run in parallel for every research query. Results are merged into a unified evidence chain that feeds all 12 agents. Confidence score gets a boost when both sources agree.

---

## API Reference

### Auth

```
POST /api/v1/auth/register   { name, email, password }  →  { access_token, user }
POST /api/v1/auth/login      { email, password }         →  { access_token, user }
GET  /api/v1/auth/me                                     →  user profile
```

### Market Data

```
GET /api/v1/market/stocks/{ticker}               →  quote (price, OHLCV, change %)
GET /api/v1/market/stocks/{ticker}/candles       →  OHLCV candle array
GET /api/v1/market/stocks/{ticker}/fundamentals  →  P/E, margins, beta, debt/equity, EPS
GET /api/v1/market/stocks/{ticker}/analyst       →  analyst ratings (buy/hold/sell counts)
GET /api/v1/market/stocks/{ticker}/news          →  recent headlines
```

### Intelligence (SSE)

```
POST /api/v1/intelligence/research
     Body: { query: string, tickers?: string[], depth?: "quick" | "full" }
     Response: text/event-stream

SSE event sequence:
  session_start         { session_id }
  intent_parsed         { intent, tickers, agents }
  evidence_searching    { message }
  evidence_gathered     { you_com_count, tavily_count, total_sources, coverage }
  agent_start           { agent, display_name }          — one per agent
  agent_complete        { agent, signal, confidence, key_finding }  — fires immediately
  debate_starting       { bull, bear }                   — only when conflict detected
  debate_complete       { winner, key_insight, rounds }
  scenarios_generating  {}
  scenarios_generated   { count }
  graph_building        {}
  graph_built           { nodes, edges }
  synthesizing          {}
  synthesis_complete    { confidence }
  result                { full analysis payload — see below }
  complete              { session_id }
  error                 { message }

POST /api/v1/intelligence/research/sync   →  same payload as result event, in one shot
POST /api/v1/intelligence/compare         ?tickers[]=AAPL&tickers[]=MSFT
```

**Full result payload**

```json
{
  "intent": "stock_analysis",
  "tickers": ["NVDA"],
  "agents_activated": ["technical", "fundamental", "sentiment", "..."],
  "confidence": 0.81,
  "confidence_breakdown": {
    "data_quality": 0.83,
    "signal_agreement": 0.75,
    "evidence_boost": 0.09,
    "overall": 0.81
  },
  "conflicts": [],
  "recommendation": "...",
  "explanation": "...",
  "bull_case": { "summary": "...", "key_points": ["..."], "probability": 0.68 },
  "bear_case": { "summary": "...", "key_points": ["..."], "probability": 0.32 },
  "key_risks": ["..."],
  "invalidation_conditions": ["..."],
  "known_unknowns": ["..."],
  "agent_outputs": { "technical": { "signal": "bullish", "confidence": 0.78, "key_finding": "...", "data": {} } },
  "evidence": {
    "you_com": { "available": true, "count": 6, "results": [] },
    "tavily":  { "available": true, "count": 3, "answers": [], "results": [] },
    "total_sources": 9,
    "coverage": "strong"
  },
  "debate": {
    "debate_occurred": true,
    "participants": { "bull": "growth_investor", "bear": "short_seller" },
    "rounds": [{ "round_type": "opening", "arguments": { "bull": "...", "bear": "..." } }],
    "moderator_conclusion": "...",
    "debate_winner": "bull",
    "key_insight": "..."
  },
  "scenarios": [
    {
      "name": "AI Supercycle Continues",
      "type": "bull",
      "probability": 0.35,
      "estimated_upside_pct": 45,
      "time_horizon": "12-18 months",
      "summary": "...",
      "key_assumptions": ["..."],
      "key_catalysts": ["..."],
      "investment_implication": "..."
    }
  ],
  "knowledge_graph": {
    "nodes": [{ "id": "NVDA", "label": "NVIDIA", "type": "company", "color": "#6c5ce7" }],
    "edges": [{ "source": "NVDA", "target": "AI", "label": "leads", "weight": 0.95 }],
    "node_count": 10,
    "edge_count": 12
  }
}
```

### Screener

```
POST /api/v1/screener/screen
     Body: { query: "Profitable tech with revenue growth over 15%", limit?: 20 }
     →  { filters_applied, explanation, results[], count }

Filterable: pe_ratio, ps_ratio, net_margin, revenue_growth, beta, debt_to_equity, roe
```

---

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required
SECRET_KEY=<32+ random chars>
POLYGON_API_KEY=<polygon.io — free tier works>
FINNHUB_API_KEY=<finnhub.io — free tier works>
OPENAI_API_KEY=<platform.openai.com>

# Sponsor integrations (research engines)
YOUCOM_API_KEY=<api.you.com — get from you.com developer portal>
TAVILY_API_KEY=<tavily.com — get from app.tavily.com>

# Optional
DEFAULT_MODEL=gpt-4o
FAST_MODEL=gpt-4o-mini
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/alphaforage
```

> You.com key: sign up at [api.you.com](https://api.you.com), key format is `ydc-sk-...`
> Tavily key: sign up at [app.tavily.com](https://app.tavily.com), key format is `tvly-...`
> Both degrade gracefully if missing — the pipeline still runs, just without external evidence.

### 2. Backend

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 3. Frontend

```bash
cd web
pnpm install      # or npm install
pnpm dev          # http://localhost:3000
```

> Vite proxies `/api` → `http://localhost:8000` automatically.

### Docker (both at once)

```bash
docker-compose up
```

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| API framework | FastAPI 0.115 | async throughout |
| Database | SQLite + aiosqlite | change `DATABASE_URL` for Postgres |
| Cache | In-process TTL dict | replace `app/core/cache.py` with Redis for multi-worker |
| Auth | JWT (python-jose) + bcrypt | 24h access tokens |
| Market data | Polygon.io + Finnhub | direct HTTP via httpx, cached in TTL dict |
| Research | You.com + Tavily | parallel evidence gathering, merged confidence boost |
| AI inference | OpenAI GPT-4o / GPT-4o-mini | all agents call `llm_json()` with `response_format=json_object` |
| Streaming | asyncio.Queue + SSE | genuine real-time, not batch-at-end |
| Frontend | React 18 + Vite 6 | Zustand, Recharts, Lucide, CSS Modules |
| Deployment | Docker (single container) | InsForge for agent services, Nebius for GPU inference |

---

## Adding a New Agent

1. Write `async def my_agent(state: AgentState) -> dict` in [app/agents/agents.py](app/agents/agents.py)
   — must return `{ "signal": "bullish"|"bearish"|"neutral", "confidence": 0-1, "key_finding": str, "data": dict }`
2. Register in [app/agents/supervisor.py](app/agents/supervisor.py):
   - Add to `AGENT_FN`
   - Add to `AGENT_DISPLAY_NAMES`
   - Add to relevant intents in `INTENT_TO_AGENTS`
   - Add a weight in `AGENT_WEIGHTS` if needed
3. Add `my_output: Optional[dict] = None` to `AgentState` in [app/agents/state.py](app/agents/state.py)

The agent will automatically be picked up by the debate engine, scenario generator, and knowledge graph extractor.

---

## Scaling Path

| When | What to do |
|---|---|
| Multiple workers / shared cache | Replace `app/core/cache.py` with Redis (`aioredis`) |
| SQLite bottleneck | Set `DATABASE_URL=postgresql+asyncpg://...` in `.env` |
| Real document RAG | Add Pinecone / pgvector ingestion pipeline for SEC filings |
| Independent agent scaling | Agent code is modular — split into microservices when needed |
| GPU inference | Wire Nebius cluster into `app/agents/base.py` `llm_json()` |

---

## Demo Flow (Hackathon)

1. Open [http://localhost:3000](http://localhost:3000) — Landing page shows 12-agent team + sponsor integrations
2. Click **Launch App** → **Workspaces** → create "NVDA — AI Infrastructure Play"
3. Watch workspace auto-run: You.com + Tavily gather evidence, 12 agents stream live one-by-one
4. Agents disagree → Debate Engine fires — Growth Investor vs Short Seller, 2 rounds, moderator concludes
5. 5 scenario simulations generated with probabilities and upside/downside %
6. Knowledge graph built: NVDA → CUDA → AI industry → Jensen Huang → ...
7. Research Director synthesises institutional investment thesis
8. Open **Research Chat** → ask "What if NVDA loses its CUDA moat?" → full pipeline reruns

---

## Disclaimer

Market data by Polygon.io & Finnhub. Web research by You.com & Tavily. AI analysis by OpenAI. Nothing here is financial advice. For research and educational purposes only.
