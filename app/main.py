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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, market, intelligence, screener
from app.routers import workspaces
from app.core.database import init_db
from app.models import workspace as _workspace_models  # ensure tables created

app = FastAPI(
    title="AlphaForage — Autonomous Investment Intelligence",
    version="2.0.0",
    docs_url="/docs",
    description="12-agent AI research pipeline with You.com + Tavily evidence, debate engine, and living workspaces.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(intelligence.router)
app.include_router(screener.router)
app.include_router(workspaces.router)


@app.on_event("startup")
async def startup():
    await init_db()
    print("[alphaforage v2] Autonomous Investment Intelligence Platform ready")
    print("[alphaforage v2] http://localhost:8000/docs")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "agents": 12,
        "features": ["workspaces", "debate", "scenarios", "knowledge_graph", "you.com", "tavily"],
    }
