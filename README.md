# AlphaForage — Autonomous Investment Intelligence Platform

> Think Perplexity + Bloomberg + Cursor for Finance.

12 AI agents run in parallel, debate each other when they disagree, generate probabilistic scenario simulations, extract knowledge graphs, and stream every step live to the browser. A Living Thesis engine versions every conclusion over time, a Document Intelligence layer ingests real SEC filings for grounded evidence, an AI Memory layer remembers facts and decisions across sessions, a Monitoring layer watches tracked tickers for real-world events, and a Portfolio Intelligence layer scores your actual holdings. Not a broker, not a trading app — pure autonomous research infrastructure.

---

## What's Inside

```
Backend      FastAPI monolith · SQLite · in-process TTL cache · real-time SSE via asyncio.Queue
Frontend     React 18 + Vite · Zustand · dark-mode · live agent activity panel
Research     You.com + Tavily → 12 agents → debate → scenarios → graph → Living Thesis
Documents    SEC EDGAR ingestion → chunking → embeddings → hybrid retrieval → Evidence Engine
Memory       Cross-session facts, beliefs & decisions, extracted and consolidated per research run
Monitoring   6 background watchers (filings, earnings, news, insiders, price, analyst ratings) → alerts
Portfolio    Real holdings, P&L, health scoring, daily summaries, watchlists
```

---

## Website Sections

The sidebar has six tabs, grouped as **Platform → Research → Portfolio**. Here's what each one actually does today:

| Section | Route | What it does | Data |
|---|---|---|---|
| **Workspaces** | `/app/workspaces` | Create a persistent research thesis around a set of tickers/themes (e.g. "AI Infrastructure — NVDA, MSFT, GOOGL"). Opening one auto-runs the full 12-agent pipeline; every later query re-runs it and **versions the thesis** — you see what changed, why, and whether conviction went up or down. | Live — real agent runs, persisted to SQLite |
| **Research** | `/app/research` | Freeform chat interface into the same 12-agent pipeline, outside any workspace context. Streams agent activity, debate rounds, scenarios, and the knowledge graph live via SSE as they're generated. | Live |
| **Screener** | `/app/screener` | Natural-language stock screener — type "profitable tech with revenue growth over 15%" and an LLM translates it into precise numeric filters (P/E, margins, growth, beta, D/E, ROE) run against the market data providers. | Live |
| **Market** | `/app/market` | Quote watchlist (AAPL, MSFT, NVDA, GOOGL, META, TSLA) plus a ticker lookup for quotes or fundamentals (P/E, margins, beta, 52-week range, etc.). | Live — Polygon/Finnhub |
| **Portfolio** | `/app/portfolio` | Positions table with live prices and P&L, one click into AI research per holding. **Currently renders a hardcoded demo portfolio (AAPL/MSFT/NVDA)** — the real backend (buy/sell, cost basis, health scoring, daily summaries, watchlists) already exists under `/api/v1/portfolio` and `/api/v1/watchlists` but isn't wired to this page yet. See [Portfolio Intelligence](#portfolio-intelligence) below. | Demo UI / live backend API |
| **Events** | `/app/events` | Calendar of upcoming earnings, Fed meetings, and macro data releases, with one-click "Analyze impact" into Research. **Currently a hardcoded event list** — the real Monitoring backend (SEC filings, earnings, news, insider trades, price moves, analyst rating changes, polled on a schedule with a persisted `Alert` feed) already exists under `/api/v1/monitoring` but isn't wired to this page yet. See [Monitoring & Alerts](#monitoring--alerts) below. | Demo UI / live backend API |

The **Landing page** (`/`) is the marketing/demo surface: the 12-agent roster, sample workspaces, feature highlights (Living Workspaces, Debate Engine, You.com/Tavily research, Scenario Simulation, Knowledge Graph), and a sample bull/bear/scenario breakdown — all illustrative content that links into the real app.

---

## Architecture

```
app/
  main.py                     FastAPI app — mounts all routers, starts the embedding
                               worker + monitoring scheduler as background tasks
  core/
    config.py                 Single settings class (reads .env) — model choice,
                               thresholds, health-score weights, monitor poll intervals
    database.py                SQLite async via SQLAlchemy + aiosqlite
    cache.py                   In-process TTL dict (replaces Redis)
    security.py                JWT creation + bcrypt password hashing
    llm.py                     Shared llm_json() + OpenAI client (used by agents,
                               evidence synthesis, memory extraction, portfolio AI)
  models/
    user.py                    User + RefreshToken
    workspace.py                Workspace + WorkspaceResearch
    thesis.py                   ThesisVersion + ConfidenceSnapshot + ThesisClaim
    memory.py                   ConversationMemory + WorkspaceMemory + CompanyMemory + ThesisMemory
    monitoring.py               MonitoringJob + Alert
    portfolio.py                Portfolio + PortfolioHolding + PortfolioActivity + HoldingSnapshot + Watchlist
  providers/
    market.py                  Polygon.io + Finnhub — quotes, candles, fundamentals, news, analyst, insiders
    youcom.py                   You.com Web Search API — primary research
    tavily.py                   Tavily Search API — cross-validation
    evidence.py                 Merges You.com + Tavily into a unified web-evidence chain
  agents/
    state.py                    AgentState — carries query, evidence, memory context, outputs
    base.py                     llm_json() + market helpers + search_evidence() + recall_memory()
    agents.py                   All 12 agents
    supervisor.py                Pipeline: intent → memory recall → evidence → agents →
                                 debate → scenarios → graph → synthesis
    debate.py                    2-round structured debate engine
    scenarios.py                 5-scenario probabilistic simulation
    graph.py                     Knowledge graph extraction
  thesis/
    versioner.py                 Creates a new ThesisVersion after each research run
    comparator.py                 Classifies what changed vs. the prior version
    lifecycle.py                  forming → established → evolving → challenged → invalidated
    signal.py, claims.py          Directional signal + atomic claim extraction/tracking
  documents/                     Document Intelligence — see dedicated section below
    providers/sec_edgar.py        SEC EDGAR ingestion (no API key, rate-limited, compliant UA)
    parsers/, chunking/           HTML section parsing + token-aware chunking
    embeddings/                   Pluggable embedding providers + async embed queue/worker
    indexing/                     Document + chunk metadata index
    retrieval/                    Hybrid (BM25+vector) search, MMR rerank, 5 pluggable vector stores
    evidence/                     Evidence Engine 2.0 — scoring, dedup, conflict detection, claims
  memory/                        AI Memory — see dedicated section below
    extractor.py, consolidator.py, retriever.py, service.py
  monitoring/                    Monitoring & Alerts — see dedicated section below
    providers/                    6 monitor types (filing, earnings, news, insider, price, analyst)
    scheduler.py, alert_service.py, registry.py
  portfolio/                     Portfolio Intelligence — see dedicated section below
    service.py, intelligence.py, summary.py
  routers/
    auth.py                      /api/v1/auth
    market.py                    /api/v1/market
    intelligence.py               /api/v1/intelligence  — real-time SSE research
    workspaces.py                 /api/v1/workspaces    — Living Research Workspaces + Thesis
    screener.py                   /api/v1/screener
    documents.py                  /api/v1/documents     — embedding trigger + document search
    retrieval.py                  /api/v1/retrieval     — agent-facing evidence query
    memory.py                     /api/v1/memory        — recall + inspection
    monitoring.py                 /api/v1/monitoring    — alerts + job control
    portfolio.py                  /api/v1/portfolio, /api/v1/watchlists

web/
  src/
    pages/
      Landing.jsx                Marketing page — 12-agent grid, sample workspaces, feature highlights
      Research.jsx                Chat interface — live agent panel, debate, scenarios, graph
      Workspaces.jsx               Workspace list + template workspaces + create modal
      WorkspaceDetail.jsx          Full workspace view — agents, event log, debate, scenarios,
                                   graph, Living Thesis timeline/claims/confidence sparkline
      Screener.jsx                 Natural-language stock screener
      pages.jsx                    Market watchlist, demo Portfolio table, demo Events calendar
    store/index.js                Zustand stores — handles all SSE event types in real time
    lib/api.js                    SSE streaming client + REST api helpers
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
Memory Recall          pulls relevant facts/beliefs/decisions from prior sessions
    │                  for this workspace and/or ticker (AI Memory layer)
    ▼
Evidence Gathering     You.com + Tavily in parallel
    │                  → merged evidence chain with confidence boost
    ▼
12 Agents              all run in parallel via asyncio.gather, each with
    │                  memory context injected into its prompt
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
    │                  institutional investment thesis: recommendation ·
    │                  explanation · bull/bear cases · key risks ·
    │                  invalidation conditions · known unknowns
    ▼
Thesis Versioning      (workspace runs only) diffs against the prior thesis,
    │                  classifies the change, updates lifecycle stage
    ▼
Memory Consolidation   extracts durable facts/beliefs/decisions from this run,
                       reinforces or contradicts existing memory, promotes
                       confirmed beliefs into cross-session CompanyMemory
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
Intelligence / Workspace router
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

Workspace research additionally emits a `thesis_version` event once the run is persisted and versioned.

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

### Living Thesis — versioning, lifecycle, claims

Every workspace research run doesn't just overwrite the old conclusion — it **versions** it, so you can see the thesis evolve.

```
GET /api/v1/workspaces/{id}/thesis                        current thesis + lifecycle stage + conviction score
GET /api/v1/workspaces/{id}/thesis/versions               version history (lightweight, for a timeline view)
GET /api/v1/workspaces/{id}/thesis/versions/{version_id}  full detail of one version, incl. diff from prior
GET /api/v1/workspaces/{id}/thesis/confidence-history     time series of confidence/conviction (sparkline)
GET /api/v1/workspaces/{id}/thesis/claims                 atomic claims, filterable by status
```

- **Versioning** (`app/thesis/versioner.py`) — after each run, compares the new thesis to the last one and classifies the change (reinforced, evolved, challenged, invalidated).
- **Lifecycle** (`app/thesis/lifecycle.py`) — a small state machine: `forming → established → evolving → challenged → invalidated`. A thesis only becomes "established" after surviving enough consecutive versions, so one good run after a challenge doesn't instantly relabel a shaky thesis.
- **Claims** (`app/thesis/claims.py`) — individual assertions (e.g. "gross margin expansion continues") are tracked atomically across versions with their own status: `active → strengthened / weakened → confirmed / refuted`.
- **Confidence snapshots** — every version records a point-in-time confidence score, rendered as a sparkline in the workspace UI.

---

## Document Intelligence & Evidence Engine

Real primary-source documents (SEC filings today), turned into grounded, cited evidence — not just web search snippets.

```
Ingestion    app/documents/providers/sec_edgar.py
             Ticker → CIK resolution and filing discovery/fetch directly against
             SEC EDGAR's public JSON APIs. No API key. Rate-limited (~10 req/sec)
             and sends the SEC-required descriptive User-Agent on every request.
                 │
                 ▼
Parsing      app/documents/parsers/html_sections.py — splits a filing into sections
                 │
                 ▼
Chunking     app/documents/chunking/chunker.py — token-aware chunks with content hashing
                 │
                 ▼
Embedding    app/documents/embeddings/ — async queue + worker (started at app boot),
             pluggable provider: OpenAI (default) · Voyage · local sentence-transformers
                 │
                 ▼
Indexing     app/documents/indexing/ — document + chunk metadata, ready for retrieval
                 │
                 ▼
Retrieval    app/documents/retrieval/ — hybrid search (BM25 keyword + vector similarity),
             MMR reranking for diversity, pluggable vector store:
             SQLite (default) · FAISS · Chroma · Pinecone · pgvector
                 │
                 ▼
Evidence     app/documents/evidence/ — scores, deduplicates, and detects conflicts between
Engine 2.0   chunks, synthesizes atomic claims via LLM, and packages everything into an
             EvidencePack: evidence + claims + citations + confidence + conflict summary
```

```
POST /api/v1/documents/{id}/embed     trigger (or queue) embedding for an ingested document
GET  /api/v1/documents/search         lightweight snippet search across ingested documents
POST /api/v1/retrieval/query          full EvidencePack for a query (the agent-facing endpoint)
```

`app.agents.base.search_evidence()` already wraps the retrieval service for agent use — the plumbing is fully built, but wiring the 12 agent prompts to call it (instead of relying only on You.com/Tavily web evidence) is planned future work, not yet live in the default pipeline.

---

## AI Memory

Persistent, cross-session research memory — so the platform doesn't re-derive the same facts every time you ask about a ticker.

| Layer | Scope | Example |
|---|---|---|
| `ConversationMemory` | Per workspace | What was asked and concluded in a specific research run |
| `WorkspaceMemory` | Per workspace | Facts, beliefs, decisions, open/resolved questions tied to that thesis |
| `CompanyMemory` | Cross-workspace, per ticker | Durable facts about a company confirmed across multiple workspaces |
| `ThesisMemory` | Per workspace | Confirmed/refuted beliefs promoted from thesis claims |

```
Extraction      app/memory/extractor.py — after each research run, an LLM call decides
                what's actually worth remembering (a durable, context-free sentence),
                not everything that was said
                    │
                    ▼
Consolidation   app/memory/consolidator.py — embeds new candidates against existing
                memory: similarity ≥ 0.92 reinforces an existing item, 0.80–0.92 is
                checked for contradiction (one batched LLM call per session), below
                that it's inserted as new. Confirmed items roll up into CompanyMemory.
                    │
                    ▼
Recall          app/memory/retriever.py — semantic search over a workspace's or
                ticker's memory, called once per research run (before agents hit
                their LLMs) to inject relevant history into every agent's prompt
```

```
POST /api/v1/memory/recall                              semantic recall (same call agents make)
GET  /api/v1/memory/workspace/{id}                       workspace memory items
GET  /api/v1/memory/workspace/{id}/conversations         conversation memory
GET  /api/v1/memory/workspace/{id}/decisions             confirmed/refuted thesis memory
GET  /api/v1/memory/company/{ticker}                     cross-workspace company memory
```

Memory recall is fully wired into the research pipeline (`supervisor.py` calls it before agents run); the endpoints above exist to inspect and debug what's been remembered.

---

## Monitoring & Alerts

A background scheduler polls six independent monitors for every ticker the app currently cares about (every workspace's tracked tickers, plus portfolio holdings), and raises an `Alert` when something changes.

| Monitor | Checks | Default interval |
|---|---|---|
| **SEC Filing** | New 10-K/10-Q/8-K etc. via EDGAR | 6h |
| **Earnings** | Upcoming/reported earnings dates | 24h |
| **News** | Fresh headlines | 30m |
| **Insider Trading** | Form 4 buy/sell activity | 24h |
| **Price Movement** | Abnormal intraday/daily moves | 15m |
| **Analyst Rating** | Upgrades/downgrades, target changes | 12h |

```
GET  /api/v1/monitoring/alerts                list alerts (filterable by ticker/type/status)
GET  /api/v1/monitoring/alerts/{ticker}       alerts for one ticker
POST /api/v1/monitoring/alerts/{id}/read      mark read
POST /api/v1/monitoring/alerts/{id}/dismiss   dismiss
GET  /api/v1/monitoring/jobs                  list monitoring jobs + their schedule state
POST /api/v1/monitoring/jobs/sync             create jobs for every currently-tracked ticker
POST /api/v1/monitoring/jobs/run-now          force one full scheduler tick immediately
POST /api/v1/monitoring/jobs/{id}/run-now     force one specific job to run immediately
```

The scheduler runs as a background asyncio task started at app boot (`app/monitoring/scheduler.py`), ticking once a minute to check which jobs are due. This backend is fully functional but not yet surfaced in the frontend — the **Events** page still shows a static demo calendar.

---

## Portfolio Intelligence

Real portfolios and holdings — not the hardcoded demo table currently shown on the Portfolio page.

```
POST   /api/v1/portfolio                                    create portfolio
GET    /api/v1/portfolio                                    list portfolios
GET    /api/v1/portfolio/{id}?sync=true                     detail + holdings + allocation + concentration
PATCH  /api/v1/portfolio/{id}                                rename/update
DELETE /api/v1/portfolio/{id}                                archive
POST   /api/v1/portfolio/{id}/sync                           refresh market data for all holdings

GET    /api/v1/portfolio/{id}/holdings                       list holdings
POST   /api/v1/portfolio/{id}/holdings                       buy (adds to or opens a position)
POST   /api/v1/portfolio/{id}/holdings/import                bulk-import existing positions
POST   /api/v1/portfolio/{id}/holdings/{hid}/sell            sell (partial or full)
DELETE /api/v1/portfolio/{id}/holdings/{hid}                 close a position
GET    /api/v1/portfolio/{id}/holdings/{hid}/intelligence    per-holding AI intelligence (below)
GET    /api/v1/portfolio/{id}/activity                       buy/sell activity log

GET    /api/v1/portfolio/{id}/summary                        daily summary (below)
GET    /api/v1/portfolio/{id}/health                          portfolio-wide health rollup

POST   /api/v1/watchlists                                    create watchlist
GET    /api/v1/watchlists                                    list watchlists
GET    /api/v1/watchlists/{id}                                watchlist detail
PATCH  /api/v1/watchlists/{id}                                update name/tickers
DELETE /api/v1/watchlists/{id}                                delete
```

**Per-holding intelligence** composes every other subsystem into one view: latest evidence (Document Intelligence), open alerts (Monitoring), thesis status (Workspaces), recent SEC filings, earnings date, analyst rating changes, insider activity, a deterministic **risk score** (volatility, drawdown, beta), and an AI-generated sentiment score + summary — one LLM call per holding, cached and only refreshed when stale.

**Position Health Score** is a deterministic weighted blend of eight factors (evidence quality, alert severity, valuation, analyst revisions, earnings risk, insider activity, sentiment, thesis confidence) — a formula, not a model call, so it's fast, cheap, and reproducible.

**Daily Summary** rolls up biggest winners/losers, new alerts, thesis changes, and confidence changes across the whole portfolio, plus one shared "macro events" LLM call regardless of portfolio size.

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

> Workspaces/Thesis, Documents/Retrieval, Memory, Monitoring, and Portfolio/Watchlists each have their own endpoint reference in the dedicated sections above.

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

# Optional — Document Intelligence
SEC_EDGAR_USER_AGENT=<"YourApp your@email.com" — required by SEC EDGAR, not optional if you ingest filings>
EMBEDDING_PROVIDER=openai        # openai | voyage | local
VOYAGE_API_KEY=<only if EMBEDDING_PROVIDER=voyage>
VECTOR_STORE_PROVIDER=sqlite     # sqlite | faiss | chroma | pinecone | pgvector

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

### Docker (production build, both services)

`docker-compose.yml` builds production images for both services — the API
with plain `uvicorn` (no `--reload`) and the frontend as a static Vite build
served by nginx, which also reverse-proxies `/api` to the `api` container so
the browser only ever talks to one origin. There are no bind mounts, so
source edits require a rebuild:

```bash
docker-compose up --build
```

- Frontend: http://localhost (port 80, override with `WEB_PORT`)
- API: http://localhost:8000 (override with `API_PORT`)

For day-to-day local development, use steps 2–3 above instead (`--reload`
and Vite HMR) — this compose file is meant for a pre-deploy production
smoke test and for deployment itself (see `.env.production.example` /
`web/.env.production.example` for the env vars a real deployment needs).

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| API framework | FastAPI 0.115 | async throughout |
| Database | SQLite + aiosqlite | change `DATABASE_URL` for Postgres |
| Cache | In-process TTL dict | replace `app/core/cache.py` with Redis for multi-worker |
| Auth | JWT (python-jose) + bcrypt | 24h access tokens |
| Market data | Polygon.io + Finnhub | direct HTTP via httpx, cached in TTL dict |
| Web research | You.com + Tavily | parallel evidence gathering, merged confidence boost |
| Document ingestion | SEC EDGAR | no API key, rate-limited, compliant User-Agent |
| Embeddings | OpenAI / Voyage / local sentence-transformers | pluggable via `EMBEDDING_PROVIDER` |
| Vector store | SQLite / FAISS / Chroma / Pinecone / pgvector | pluggable via `VECTOR_STORE_PROVIDER` |
| AI inference | OpenAI GPT-4o / GPT-4o-mini | all agents + evidence + memory call `llm_json()` |
| Streaming | asyncio.Queue + SSE | genuine real-time, not batch-at-end |
| Background jobs | asyncio tasks at app boot | embedding worker + monitoring scheduler |
| Frontend | React 18 + Vite 6 | Zustand, Recharts, Lucide, CSS Modules |
| Deployment | Docker Compose (`api` + nginx-served frontend) | InsForge for agent services, Nebius for GPU inference |

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
| Larger document corpus | Switch `VECTOR_STORE_PROVIDER` to `pgvector` or `pinecone` |
| Wire Portfolio/Events into the UI | Point `web/src/pages/pages.jsx`'s Portfolio/Events at `/api/v1/portfolio` and `/api/v1/monitoring` instead of the hardcoded demo data |
| Wire document evidence into agent prompts | Call `app.agents.base.search_evidence()` from each agent, alongside the existing web evidence |
| Independent agent scaling | Agent code is modular — split into microservices when needed |
| GPU inference | Wire Nebius cluster into `app/core/llm.py`'s `llm_json()` |

---

## Demo Flow

1. Open [http://localhost:3000](http://localhost:3000) — Landing page shows the 12-agent team + sponsor integrations
2. Click **Launch App** → **Workspaces** → create "NVDA — AI Infrastructure Play"
3. Watch workspace auto-run: You.com + Tavily gather evidence, memory recall pulls anything known from prior sessions, 12 agents stream live one-by-one
4. Agents disagree → Debate Engine fires — Growth Investor vs Short Seller, 2 rounds, moderator concludes
5. 5 scenario simulations generated with probabilities and upside/downside %
6. Knowledge graph built: NVDA → CUDA → AI industry → Jensen Huang → ...
7. Research Director synthesises institutional investment thesis, which gets **versioned** into the workspace's Living Thesis (check the Thesis tab for lifecycle stage + confidence sparkline)
8. Open **Research Chat** → ask "What if NVDA loses its CUDA moat?" → full pipeline reruns
9. Hit `/docs` to explore the Document Intelligence, Memory, Monitoring, and Portfolio APIs directly — they're fully functional even though the corresponding frontend pages aren't wired up yet

---

## Disclaimer

Market data by Polygon.io & Finnhub. Web research by You.com & Tavily. Filing data by SEC EDGAR. AI analysis by OpenAI. Nothing here is financial advice. For research and educational purposes only.
