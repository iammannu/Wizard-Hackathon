from typing import Optional
from dataclasses import dataclass, field


@dataclass
class AgentState:
    # Input
    query: str = ""
    depth: str = "full"       # "quick" | "full"
    workspace_id: Optional[str] = None

    # Parsed
    intent: str = "general"
    tickers: list[str] = field(default_factory=list)
    timeframe: str = "general"
    active_agents: list[str] = field(default_factory=list)

    # Research evidence (You.com + Tavily)
    evidence: Optional[dict] = None

    # AI Memory (Milestone 3) — recalled once per run, before agents execute,
    # via app.memory.service.recall_for_agent(). {"workspace": MemoryPack-as-dict,
    # "company": {ticker: MemoryPack-as-dict}} — see app/agents/supervisor.py's
    # gather_memory() step. None until that step runs or when nothing relevant
    # is on file yet.
    memory_context: Optional[dict] = None

    # Original 6 agent outputs
    technical_output: Optional[dict] = None
    fundamental_output: Optional[dict] = None
    sentiment_output: Optional[dict] = None
    macro_output: Optional[dict] = None
    risk_output: Optional[dict] = None
    valuation_output: Optional[dict] = None

    # New 6 agent outputs
    growth_investor_output: Optional[dict] = None
    value_investor_output: Optional[dict] = None
    quant_researcher_output: Optional[dict] = None
    industry_specialist_output: Optional[dict] = None
    short_seller_output: Optional[dict] = None
    devils_advocate_output: Optional[dict] = None

    # Agent debate transcript
    debate: Optional[dict] = None

    # Scenario simulation
    scenarios: list[dict] = field(default_factory=list)

    # Knowledge graph
    knowledge_graph: Optional[dict] = None

    # Synthesis
    conflicts: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    confidence_breakdown: dict = field(default_factory=dict)
    evidence_chain: list[dict] = field(default_factory=list)
    bull_case: Optional[dict] = None
    bear_case: Optional[dict] = None
    recommendation: str = ""
    explanation: str = ""
    key_risks: list[str] = field(default_factory=list)
    key_assumptions: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    known_unknowns: list[str] = field(default_factory=list)

    # Streaming
    stream_events: list[dict] = field(default_factory=list)
