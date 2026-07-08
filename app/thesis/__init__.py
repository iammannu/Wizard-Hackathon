"""
Living Investment Thesis engine.

Deterministic, non-LLM logic that turns a completed AgentState (one research
run) into a versioned, auditable thesis record. Split into single-purpose
modules so each piece of reasoning can be tested and evolved independently:

  signal.py      — overall bullish/bearish/neutral call + conviction score
  comparator.py  — structured diff between two thesis versions
  lifecycle.py   — lifecycle_stage state machine
  claims.py      — atomic claim extraction + longitudinal tracking
  versioner.py   — orchestrates the above into a persisted ThesisVersion

Why deterministic: change detection and versioning run on every research
call. Routing them through an LLM would add cost and latency without adding
judgment — the inputs (signals, probabilities, confidence) are already
numeric. LLM calls stay in app/agents/ where semantic synthesis is the point.
"""
