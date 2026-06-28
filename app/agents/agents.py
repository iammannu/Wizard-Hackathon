"""
All sub-agents — original 6 preserved, 6 new added for institutional depth.
Each agent: fetch data → LLM analysis → return structured output.
Pattern: {"signal": "bullish"|"bearish"|"neutral", "confidence": 0-1, "key_finding": str, "data": dict}
"""
import asyncio
import json
import math
from app.agents.state import AgentState
from app.agents.base import llm_json, get_quote, get_candles, get_fundamentals, get_analyst, get_news


# ── Shared technical indicators ───────────────────────────────────────────────

def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)


def _sma(closes: list[float], period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    return round(sum(closes[-period:]) / period, 4)


def _volatility(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return round(math.sqrt(variance) * math.sqrt(252) * 100, 2)


def _max_drawdown(closes: list[float]) -> float:
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for p in closes:
        if p > peak:
            peak = p
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd
    return round(-max_dd * 100, 2)


def _momentum(closes: list[float], period: int = 20) -> float:
    """Price momentum: % change over period."""
    if len(closes) < period + 1:
        return 0.0
    return round((closes[-1] - closes[-period-1]) / closes[-period-1] * 100, 2)


# ── Original 6 agents ─────────────────────────────────────────────────────────

async def technical_agent(state: AgentState) -> dict:
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    candles = await get_candles(ticker, "1d", 60)
    closes = [c["close"] for c in candles if c.get("close")]

    rsi = _rsi(closes)
    sma20, sma50, sma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
    price = closes[-1] if closes else 0

    indicators = {
        "rsi_14": rsi, "sma_20": sma20, "sma_50": sma50, "sma_200": sma200,
        "price": price, "above_sma50": price > sma50, "golden_cross": sma50 > sma200,
        "momentum_20d": _momentum(closes, 20),
    }

    result = await llm_json(
        system="""You are a technical analysis agent. Analyze indicators and return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","trend":"uptrend"|"downtrend"|"sideways","key_levels":{"support":number,"resistance":number},"signals":[]}""",
        user=f"Ticker: {ticker}\nIndicators: {json.dumps(indicators)}",
        fast=True,
    )
    result["data"] = indicators
    return result or {"signal": "neutral", "confidence": 0.5, "key_finding": f"RSI={rsi}", "data": indicators}


async def fundamental_agent(state: AgentState) -> dict:
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    fundamentals, analyst = await asyncio.gather(
        get_fundamentals(ticker), get_analyst(ticker), return_exceptions=True
    )
    if isinstance(fundamentals, Exception): fundamentals = {}
    if isinstance(analyst, Exception): analyst = {}

    result = await llm_json(
        system="""You are a fundamental analysis agent. Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","quality_score":0-10,"growth_trajectory":"accelerating"|"decelerating"|"stable"|"declining","balance_sheet_health":"strong"|"adequate"|"concerning"|"weak","earnings_quality":"high"|"medium"|"low","red_flags":[],"data":{}}""",
        user=f"Ticker: {ticker}\nRatios: {json.dumps(fundamentals or {})}\nAnalyst: {json.dumps(analyst or {})}",
    )
    result["data"] = {**(fundamentals or {}), "analyst": analyst}
    return result


async def sentiment_agent(state: AgentState) -> dict:
    ticker = state.tickers[0] if state.tickers else None
    news_items = await get_news(ticker, 10) if ticker else []
    news_text = "\n".join(f"- {n.get('title','')}" for n in news_items[:6])

    evidence_snippet = ""
    if state.evidence:
        you_results = state.evidence.get("you_com", {}).get("results", [])
        evidence_snippet = "\n".join(r.get("snippet", "")[:150] for r in you_results[:3])

    result = await llm_json(
        system="""You are a sentiment analysis agent. Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","overall_sentiment":-1.0_to_1.0,"sentiment_trend":"improving"|"deteriorating"|"stable","news_summary":"2-3 sentences","key_catalysts":[],"risk_events":[]}""",
        user=f"Ticker: {ticker or 'N/A'}\nNews:\n{news_text or 'No news'}\nExternal research:\n{evidence_snippet or 'None'}",
        fast=True,
    )
    result["data"] = {"news_count": len(news_items)}
    return result


async def valuation_agent(state: AgentState) -> dict:
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    fundamentals, quote = await asyncio.gather(
        get_fundamentals(ticker), get_quote(ticker), return_exceptions=True
    )
    if isinstance(fundamentals, Exception): fundamentals = {}
    if isinstance(quote, Exception): quote = {}
    price = (quote or {}).get("price", 0)

    result = await llm_json(
        system="""You are a valuation agent. Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","fair_value_range":{"bear":number,"base":number,"bull":number},"current_premium_discount":number,"valuation_method":"string","margin_of_safety":number,"is_undervalued":boolean,"valuation_commentary":"2-3 sentences"}""",
        user=f"Ticker: {ticker}\nPrice: {price}\nRatios: {json.dumps(fundamentals or {})}",
    )
    result["data"] = {"price": price}
    return result


async def risk_agent(state: AgentState) -> dict:
    ticker = state.tickers[0] if state.tickers else None
    closes = []
    fundamentals = {}
    if ticker:
        candles, fund = await asyncio.gather(
            get_candles(ticker, "1d", 252), get_fundamentals(ticker), return_exceptions=True
        )
        closes = [c["close"] for c in (candles if isinstance(candles, list) else []) if c.get("close")]
        fundamentals = fund if isinstance(fund, dict) else {}

    vol = _volatility(closes)
    mdd = _max_drawdown(closes)
    beta = (fundamentals or {}).get("beta", 1.0) or 1.0

    risk_data = {"annual_volatility_pct": vol, "max_drawdown_pct": mdd, "beta": beta,
                 "debt_to_equity": (fundamentals or {}).get("debt_to_equity"),
                 "current_ratio": (fundamentals or {}).get("current_ratio")}

    result = await llm_json(
        system="""You are a risk analysis agent. Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","risk_level":"low"|"medium"|"high"|"very_high","var_1d_pct":number,"key_risks":[],"risk_mitigants":[]}""",
        user=f"Ticker: {ticker or 'N/A'}\nRisk Metrics: {json.dumps(risk_data)}",
        fast=True,
    )
    result["data"] = risk_data
    return result


async def macro_agent(state: AgentState) -> dict:
    evidence_snippet = ""
    if state.evidence:
        tav_answers = state.evidence.get("tavily", {}).get("answers", [])
        evidence_snippet = "\n".join(a.get("answer", "")[:200] for a in tav_answers[:2])

    result = await llm_json(
        system="""You are a macro analyst. Assess the macroeconomic environment relevant to this query. Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","rate_environment":"rising"|"falling"|"stable","inflation_trend":"rising"|"falling"|"stable","economic_cycle":"expansion"|"peak"|"contraction"|"trough","key_risks":[],"sector_impacts":{}}""",
        user=f"Query: {state.query}\nTickers: {state.tickers}\nExternal macro context:\n{evidence_snippet or 'None'}",
        fast=True,
    )
    return result


# ── New 6 agents ──────────────────────────────────────────────────────────────

async def growth_investor_agent(state: AgentState) -> dict:
    """Growth investor: TAM, revenue acceleration, market share, R&D moat."""
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    fundamentals = await get_fundamentals(ticker)
    if not isinstance(fundamentals, dict): fundamentals = {}

    evidence_snippet = ""
    if state.evidence:
        you_results = state.evidence.get("you_com", {}).get("results", [])
        evidence_snippet = " ".join(r.get("snippet", "")[:120] for r in you_results[:3])

    result = await llm_json(
        system="""You are a growth-focused investor (think Cathie Wood, Bill Miller).
Assess the stock through a pure growth lens: TAM expansion, revenue acceleration, market share gains, R&D pipeline, and competitive moat from technology.
Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence from growth perspective","tam_opportunity":"large"|"medium"|"small","revenue_acceleration":"accelerating"|"stable"|"decelerating","market_share_trajectory":"gaining"|"stable"|"losing","growth_moat":"strong"|"moderate"|"weak","growth_catalysts":["catalyst1","catalyst2"],"growth_risks":["risk1"]}""",
        user=f"Ticker: {ticker}\nFinancials: {json.dumps(fundamentals)}\nResearch context: {evidence_snippet}",
        fast=True,
    )
    result["data"] = {"ticker": ticker}
    return result


async def value_investor_agent(state: AgentState) -> dict:
    """Value investor: intrinsic value, margin of safety, earnings power, owner earnings."""
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    fundamentals, quote = await asyncio.gather(
        get_fundamentals(ticker), get_quote(ticker), return_exceptions=True
    )
    if isinstance(fundamentals, Exception): fundamentals = {}
    if isinstance(quote, Exception): quote = {}

    result = await llm_json(
        system="""You are a deep value investor (think Warren Buffett, Charlie Munger, Seth Klarman).
Assess intrinsic value, business quality, competitive moat width, and margin of safety.
Never chase momentum — only buy with meaningful margin of safety.
Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","intrinsic_value_estimate":number,"margin_of_safety_pct":number,"moat_width":"wide"|"narrow"|"none","business_quality":"excellent"|"good"|"fair"|"poor","owner_earnings_quality":"high"|"medium"|"low","value_catalysts":["catalyst1"],"value_risks":["risk1"]}""",
        user=f"Ticker: {ticker}\nPrice: {(quote or {}).get('price', 0)}\nRatios: {json.dumps(fundamentals)}",
        fast=True,
    )
    result["data"] = {"price": (quote or {}).get("price", 0)}
    return result


async def quant_researcher_agent(state: AgentState) -> dict:
    """Quant researcher: momentum factors, statistical patterns, factor scores."""
    ticker = state.tickers[0] if state.tickers else None
    if not ticker:
        return {"signal": "neutral", "confidence": 0.3, "key_finding": "No ticker", "data": {}}

    candles = await get_candles(ticker, "1d", 120)
    if isinstance(candles, Exception): candles = []
    closes = [c["close"] for c in (candles or []) if c.get("close")]

    rsi = _rsi(closes)
    mom_20 = _momentum(closes, 20)
    mom_60 = _momentum(closes, 60)
    vol = _volatility(closes)
    sma50, sma200 = _sma(closes, 50), _sma(closes, 200)
    price = closes[-1] if closes else 0

    # Simple momentum z-score
    returns_20 = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(max(1, len(closes)-20), len(closes))]
    avg_ret = sum(returns_20) / len(returns_20) if returns_20 else 0
    sharpe_approx = round(avg_ret / max(_volatility(closes[-20:]) / 252**0.5, 0.001), 2) if len(closes) >= 20 else 0

    quant_data = {
        "rsi_14": rsi,
        "momentum_20d_pct": mom_20,
        "momentum_60d_pct": mom_60,
        "annual_vol_pct": vol,
        "sma50": sma50,
        "sma200": sma200,
        "price_vs_sma50_pct": round((price - sma50) / max(sma50, 1) * 100, 2) if sma50 else 0,
        "golden_cross": sma50 > sma200,
        "sharpe_approx_20d": sharpe_approx,
    }

    result = await llm_json(
        system="""You are a quantitative researcher analyzing statistical price signals and factor exposures.
Assess momentum quality, trend strength, mean-reversion probability, and factor tilts.
Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","momentum_quality":"strong"|"moderate"|"weak"|"negative","trend_strength":"strong"|"moderate"|"weak","mean_reversion_risk":"high"|"medium"|"low","factor_tilts":["momentum","quality","value","low_vol"],"quant_signals":["signal1","signal2"]}""",
        user=f"Ticker: {ticker}\nQuant metrics: {json.dumps(quant_data)}",
        fast=True,
    )
    result["data"] = quant_data
    return result


async def industry_specialist_agent(state: AgentState) -> dict:
    """Industry specialist: competitive dynamics, industry structure, secular trends."""
    ticker = state.tickers[0] if state.tickers else None

    fundamentals = {}
    if ticker:
        f = await get_fundamentals(ticker)
        if isinstance(f, dict): fundamentals = f

    evidence_snippet = ""
    if state.evidence:
        tav_answers = state.evidence.get("tavily", {}).get("answers", [])
        you_results = state.evidence.get("you_com", {}).get("results", [])
        evidence_snippet = " ".join(a.get("answer", "")[:150] for a in tav_answers[:2])
        evidence_snippet += " ".join(r.get("snippet", "")[:100] for r in you_results[:2])

    result = await llm_json(
        system="""You are a former McKinsey industry expert and sector specialist.
Analyze competitive dynamics, Porter's Five Forces, industry lifecycle, and secular trends affecting this investment.
Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"1 sentence","industry_lifecycle":"emerging"|"growth"|"mature"|"declining","competitive_intensity":"high"|"medium"|"low","barriers_to_entry":"high"|"medium"|"low","secular_tailwinds":["trend1","trend2"],"structural_headwinds":["headwind1"],"positioning":"leader"|"challenger"|"niche"|"commodity"}""",
        user=f"Ticker: {ticker or 'N/A'}\nQuery: {state.query}\nIndustry context: {evidence_snippet[:600]}",
        fast=True,
    )
    result["data"] = {"ticker": ticker}
    return result


async def short_seller_agent(state: AgentState) -> dict:
    """Short seller: overvaluation, accounting concerns, structural challenges, red flags."""
    ticker = state.tickers[0] if state.tickers else None

    fundamentals = {}
    news_items = []
    if ticker:
        f, n = await asyncio.gather(get_fundamentals(ticker), get_news(ticker, 8), return_exceptions=True)
        if isinstance(f, dict): fundamentals = f
        if isinstance(n, list): news_items = n

    news_text = "\n".join(f"- {n.get('title','')}" for n in news_items[:5])
    evidence_snippet = ""
    if state.evidence:
        you_results = state.evidence.get("you_com", {}).get("results", [])
        evidence_snippet = " ".join(r.get("snippet", "")[:120] for r in you_results[:3])

    result = await llm_json(
        system="""You are an experienced short seller (think Jim Chanos, Carson Block).
Find the bear case: overvaluation, accounting red flags, competitive threats, management issues, structural decline.
Be specific and data-driven. Challenge the bull consensus aggressively.
Return JSON:
{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"most important bear thesis point","overvaluation_concern":"high"|"medium"|"low","accounting_red_flags":["flag1"],"competitive_threats":["threat1","threat2"],"management_concerns":["concern1"],"short_catalysts":["catalyst1","catalyst2"],"bear_thesis_summary":"2-3 sentences"}""",
        user=f"Ticker: {ticker or 'N/A'}\nRatios: {json.dumps(fundamentals)}\nNews: {news_text}\nContext: {evidence_snippet[:400]}",
        fast=True,
    )
    result["data"] = {"ticker": ticker}
    return result


async def devils_advocate_agent(state: AgentState) -> dict:
    """Devil's advocate: challenges the consensus, questions assumptions, surfaces hidden risks."""
    # Build summary of other agents' signals
    agent_signals = {}
    for name in ["technical", "fundamental", "sentiment", "valuation", "risk", "macro",
                 "growth_investor", "value_investor", "quant_researcher", "industry_specialist", "short_seller"]:
        out = getattr(state, f"{name}_output", None)
        if out:
            agent_signals[name] = {"signal": out.get("signal"), "key_finding": out.get("key_finding", "")}

    consensus_signals = [v["signal"] for v in agent_signals.values() if v.get("signal")]
    dominant = max(set(consensus_signals), key=consensus_signals.count) if consensus_signals else "neutral"

    result = await llm_json(
        system=f"""You are the devil's advocate on an investment committee.
The current consensus is {dominant}. Your job is to challenge this consensus.
Question every assumption. Surface the risks everyone is ignoring. Be intellectually honest but contrarian.
Return JSON:
{{"signal":"bullish"|"bearish"|"neutral","confidence":0-1,"key_finding":"the most dangerous assumption being made","consensus_flaw":"what the consensus is missing","hidden_risks":["risk1","risk2","risk3"],"ignored_scenarios":["scenario1","scenario2"],"most_dangerous_assumption":"1 sentence","contrarian_view":"2-3 sentences"}}""",
        user=f"Query: {state.query}\nTickers: {state.tickers}\nAgent consensus:\n{json.dumps(agent_signals, indent=2)[:600]}",
        fast=True,
    )
    result["data"] = {"consensus": dominant, "agents_surveyed": len(agent_signals)}
    return result
