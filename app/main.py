"""
AlphaForage — Autonomous Investment Intelligence Platform.

Monolith FastAPI app. One process handles:
  - Market data (Polygon + Finnhub)
  - 12-agent AI research pipeline
  - Agent debate + scenario simulation + knowledge graph
  - Living Research Workspaces
  - Evidence layer (You.com + Tavily)
  - JWT auth + SQLite storage
  - SSE streaming

Deployed on InsForge infrastructure. AI inference via Nebius GPU cluster (future).
"""
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
from app.routers import auth, market, intelligence, screener
from app.routers import workspaces
from app.routers import documents, retrieval
from app.routers import memory as memory_router
from app.routers import monitoring as monitoring_router
from app.routers import portfolio as portfolio_router
from app.core.database import init_db
from app.models import workspace as _workspace_models  # ensure tables created
from app.documents.embeddings import queue as embedding_queue
from app.monitoring import scheduler as monitoring_scheduler
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AlphaForage — Autonomous Investment Intelligence",
    version="2.0.0",
    docs_url="/docs",
    description="12-agent AI research pipeline with You.com + Tavily evidence, debate engine, and living workspaces.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(intelligence.router)
app.include_router(screener.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(retrieval.router)
app.include_router(memory_router.router)
app.include_router(monitoring_router.router)
app.include_router(portfolio_router.router)
app.include_router(portfolio_router.watchlist_router)


@app.on_event("startup")
async def startup():
    await init_db()
    app.state.embedding_worker_task = asyncio.create_task(embedding_queue.worker_loop())
    app.state.monitoring_scheduler_task = asyncio.create_task(monitoring_scheduler.scheduler_loop())
    print("[alphaforage v2] Autonomous Investment Intelligence Platform ready")
    print(f"[alphaforage v2] API docs available at /docs (environment={settings.environment})")


@app.on_event("shutdown")
async def shutdown():
    for attr in ("embedding_worker_task", "monitoring_scheduler_task"):
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "agents": 12,
        "features": ["workspaces", "debate", "scenarios", "knowledge_graph", "you.com", "tavily", "document_intelligence", "evidence_engine", "ai_memory", "monitoring_alerts", "portfolio_intelligence"],
    }
