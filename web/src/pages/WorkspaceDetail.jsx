import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Send, Loader2, Zap, CheckCircle, Clock, AlertCircle, ChevronDown, ChevronUp, History } from 'lucide-react'
import { useWorkspaceStore } from '../store/index.js'
import { workspaceApi } from '../lib/api.js'
import { LIFECYCLE_META, CHANGE_TYPE_META, CLAIM_STATUS_META } from '../lib/thesisConstants.js'

const SIGNAL_COLOR = { bullish: 'var(--bull)', bearish: 'var(--bear)', neutral: 'var(--muted)', active: 'var(--accent2)' }
const SIGNAL_BG   = { bullish: 'rgba(0,203,169,0.1)', bearish: 'rgba(255,107,107,0.1)', neutral: 'rgba(255,255,255,0.04)', active: 'rgba(108,92,231,0.1)' }

export default function WorkspaceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { agentStates, isStreaming, currentResult, streamLog, streamResearch } = useWorkspaceStore()

  const [workspace, setWorkspace] = useState(null)
  const [query, setQuery] = useState('')
  const [activeTab, setActiveTab] = useState('agents')
  const [expandedSection, setExpandedSection] = useState(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    workspaceApi.get(id).then(ws => {
      setWorkspace(ws)
      // Auto-run research on first open if no prior history
      if (!ws.research_history?.length && !isStreaming) {
        const tickers = ws.tracked_tickers ? JSON.parse(ws.tracked_tickers) : []
        const tickerStr = tickers.length > 0 ? ` for ${tickers.join(', ')}` : ''
        const desc = ws.description ? `: ${ws.description}` : ''
        const autoQuery = tickers.length > 0
          ? `Comprehensive stock analysis and investment thesis${tickerStr} — ${ws.title}${desc}`
          : `Comprehensive investment analysis and institutional thesis for ${ws.title}${desc}. Analyze growth prospects, risks, valuation, market dynamics, and generate bull/bear cases.`
        streamResearch(id, autoQuery, 'full').then(() => {
          workspaceApi.get(id).then(setWorkspace).catch(() => {})
        })
      }
    }).catch(console.error)
  }, [id])

  async function handleSubmit(e, overrideQuery) {
    e?.preventDefault()
    const q = overrideQuery || query.trim() || (workspace ? `Analyze the ${workspace.title} investment thesis` : 'Analyze this workspace')
    setQuery('')
    await streamResearch(id, q, 'full')
    // Refresh workspace after research
    workspaceApi.get(id).then(setWorkspace).catch(() => {})
  }

  const agents = Object.entries(agentStates)
  const doneAgents = agents.filter(([, s]) => s.status === 'done')
  const thinkingAgents = agents.filter(([, s]) => s.status === 'thinking')
  const result = currentResult

  const recentEvents = streamLog.slice(-6).reverse()

  function toggle(key) {
    setExpandedSection(s => s === key ? null : key)
  }

  if (!workspace && !isStreaming) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)' }}>
        <Loader2 size={24} style={{ animation: 'spin 0.7s linear infinite' }} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Topbar */}
      <div style={{ height: '52px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 20px', gap: '12px', background: 'var(--surface)', flexShrink: 0 }}>
        <button onClick={() => navigate('/app/workspaces')}
          style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '5px 10px', borderRadius: '7px', border: 'none', background: 'transparent', color: 'var(--muted)', cursor: 'pointer', fontSize: '12px', transition: 'color 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}>
          <ArrowLeft size={14} /> Workspaces
        </button>
        <div style={{ width: '1px', height: '16px', background: 'var(--border)' }} />
        {workspace && <span style={{ fontSize: '18px' }}>{workspace.icon}</span>}
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '14px', fontWeight: 600, flex: 1 }}>
          {workspace?.title || 'Loading…'}
        </span>
        {workspace?.confidence > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', padding: '4px 10px', borderRadius: '20px', background: workspace.confidence >= 0.75 ? 'rgba(0,203,169,0.12)' : 'rgba(253,203,110,0.12)', color: workspace.confidence >= 0.75 ? 'var(--bull)' : 'var(--warn)', border: `1px solid ${workspace.confidence >= 0.75 ? 'rgba(0,203,169,0.25)' : 'rgba(253,203,110,0.25)'}` }}>
            {Math.round(workspace.confidence * 100)}% confidence
          </span>
        )}
        {isStreaming && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--accent2)' }}>
            <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite' }} />
            Researching…
          </div>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left: Agent Observability + Query */}
        <div style={{ width: '320px', flexShrink: 0, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Agent panel tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
            {[['agents', 'Agents'], ['log', 'Event Log']].map(([key, label]) => (
              <button key={key} onClick={() => setActiveTab(key)}
                style={{ flex: 1, padding: '10px', background: activeTab === key ? 'var(--surface2)' : 'transparent', border: 'none', borderBottom: `2px solid ${activeTab === key ? 'var(--accent)' : 'transparent'}`, color: activeTab === key ? 'var(--text)' : 'var(--muted)', fontSize: '12px', fontWeight: activeTab === key ? 600 : 400, cursor: 'pointer', transition: 'all 0.15s' }}>
                {label}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
            {activeTab === 'agents' && (
              <AgentPanel agents={agentStates} isStreaming={isStreaming} />
            )}
            {activeTab === 'log' && (
              <EventLog events={streamLog} />
            )}
          </div>

          {/* Query input */}
          <div style={{ borderTop: '1px solid var(--border)', padding: '12px', flexShrink: 0, background: 'var(--surface)' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
              <textarea
                ref={textareaRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() } }}
                disabled={isStreaming}
                placeholder={`Research ${workspace?.title || 'this workspace'}…`}
                rows={2}
                style={{ flex: 1, background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: '8px', padding: '8px 12px', color: 'var(--text)', fontSize: '12px', resize: 'none', outline: 'none', fontFamily: 'var(--font-body)', lineHeight: 1.5, transition: 'border-color 0.15s' }}
                onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                onBlur={e => e.target.style.borderColor = 'var(--border2)'}
              />
              <button onClick={handleSubmit} disabled={isStreaming}
                style={{ width: '36px', height: '36px', borderRadius: '8px', border: 'none', background: isStreaming ? 'var(--dim)' : 'var(--accent)', color: '#fff', cursor: isStreaming ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'background 0.15s' }}>
                {isStreaming ? <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Send size={14} />}
              </button>
            </div>
            <div style={{ fontSize: '10px', color: 'var(--muted)', marginTop: '5px', textAlign: 'center' }}>Enter to research · Shift+Enter for new line</div>
          </div>
        </div>

        {/* Right: Results */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {!result && !isStreaming && (
            <EmptyState workspace={workspace} onStart={handleSubmit} />
          )}

          {(result || isStreaming) && (
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

              {/* Evidence banner */}
              {(result?.evidence || isStreaming) && (
                <EvidenceBanner evidence={result?.evidence} isStreaming={isStreaming} streamLog={streamLog} />
              )}

              {/* Thesis summary */}
              {result && (
                <ThesisSummary result={result} />
              )}

              {/* Living Thesis — persistent intelligence layer, always visible once a thesis exists */}
              {workspace?.thesis_version_count > 0 && (
                <LivingThesisPanel
                  workspaceId={id}
                  versionCount={workspace.thesis_version_count}
                  lifecycleStage={workspace.thesis_lifecycle_stage}
                  convictionScore={workspace.conviction_score}
                  thesisSignal={workspace.thesis_signal}
                />
              )}

              {/* Debate */}
              {result?.debate?.debate_occurred && (
                <CollapsibleSection title="Agent Debate" icon="⚔️" expanded={expandedSection === 'debate'} onToggle={() => toggle('debate')}>
                  <DebateView debate={result.debate} />
                </CollapsibleSection>
              )}

              {/* Scenarios */}
              {result?.scenarios?.length > 0 && (
                <CollapsibleSection title="Scenario Simulation" icon="🎭" expanded={expandedSection === 'scenarios'} onToggle={() => toggle('scenarios')}>
                  <ScenariosView scenarios={result.scenarios} />
                </CollapsibleSection>
              )}

              {/* Knowledge Graph */}
              {result?.knowledge_graph?.nodes?.length > 0 && (
                <CollapsibleSection title="Knowledge Graph" icon="🕸️" expanded={expandedSection === 'graph'} onToggle={() => toggle('graph')}>
                  <GraphView graph={result.knowledge_graph} />
                </CollapsibleSection>
              )}

              {/* Agent outputs detail */}
              {result?.agent_outputs && Object.keys(result.agent_outputs).length > 0 && (
                <CollapsibleSection title="Agent Reports" icon="🧠" expanded={expandedSection === 'outputs'} onToggle={() => toggle('outputs')}>
                  <AgentOutputs outputs={result.agent_outputs} />
                </CollapsibleSection>
              )}

            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function AgentPanel({ agents, isStreaming }) {
  const entries = Object.entries(agents)
  if (entries.length === 0 && !isStreaming) {
    return <div style={{ fontSize: '12px', color: 'var(--muted)', textAlign: 'center', padding: '24px 0' }}>No agents active yet.<br />Run a research query.</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {entries.map(([name, state]) => {
        const sc = SIGNAL_COLOR[state.signal] || SIGNAL_COLOR.neutral
        const sb = SIGNAL_BG[state.signal] || SIGNAL_BG.neutral
        const isDone = state.status === 'done'
        const isThinking = state.status === 'thinking'

        return (
          <div key={name}
            style={{ background: isDone ? sb : isThinking ? 'rgba(108,92,231,0.07)' : 'var(--surface2)', border: `1px solid ${isDone ? sc + '44' : isThinking ? 'rgba(108,92,231,0.25)' : 'var(--border)'}`, borderRadius: '9px', padding: '10px 12px', transition: 'all 0.3s' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: isDone && state.key_finding ? '6px' : 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                {isDone ? <CheckCircle size={11} style={{ color: sc, flexShrink: 0 }} /> :
                  isThinking ? <div style={{ display: 'flex', gap: '2px' }}>{[0, 1, 2].map(d => <span key={d} style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--accent)', animation: `dotPulse 1.2s ${d * 0.2}s infinite` }} />)}</div> :
                  <Clock size={11} style={{ color: 'var(--muted)', flexShrink: 0 }} />}
                <span style={{ fontSize: '11px', fontWeight: 500, color: isDone ? 'var(--text)' : isThinking ? 'var(--accent2)' : 'var(--muted)' }}>
                  {state.display_name || name}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {isDone && state.signal && (
                  <span style={{ fontSize: '8px', padding: '1px 5px', borderRadius: '3px', fontWeight: 700, textTransform: 'uppercase', background: SIGNAL_BG[state.signal], color: sc, border: `1px solid ${sc}44` }}>
                    {state.signal}
                  </span>
                )}
                {isDone && state.confidence != null && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--muted)' }}>
                    {Math.round(state.confidence * 100)}%
                  </span>
                )}
              </div>
            </div>
            {isDone && state.key_finding && (
              <div style={{ fontSize: '10px', color: 'var(--muted)', lineHeight: 1.5, paddingLeft: '18px' }}>
                {state.key_finding}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function EventLog({ events }) {
  if (events.length === 0) return (
    <div style={{ fontSize: '12px', color: 'var(--muted)', textAlign: 'center', padding: '24px 0' }}>Events will appear here during research.</div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {events.map((ev, i) => (
        <div key={i} style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--muted)', padding: '5px 8px', borderRadius: '6px', background: 'var(--surface2)', borderLeft: `2px solid ${ev.type === 'agent_complete' ? 'var(--bull)' : ev.type === 'error' ? 'var(--bear)' : ev.type === 'debate_complete' ? 'var(--warn)' : 'var(--accent)'}` }}>
          <span style={{ color: 'var(--accent2)' }}>{ev.type}</span>
          {ev.agent && <span style={{ color: 'var(--text)', marginLeft: '4px' }}>← {ev.display_name || ev.agent}</span>}
          {ev.signal && <span style={{ color: SIGNAL_COLOR[ev.signal] || 'var(--muted)', marginLeft: '4px' }}>[{ev.signal}]</span>}
          {ev.message && <span style={{ marginLeft: '4px' }}>{ev.message.slice(0, 60)}</span>}
          {ev.total_sources != null && <span style={{ marginLeft: '4px' }}>{ev.total_sources} sources</span>}
        </div>
      ))}
    </div>
  )
}

function EvidenceBanner({ evidence, isStreaming, streamLog }) {
  const searchingEvent = streamLog.find(e => e.type === 'evidence_searching')
  const gatheredEvent = streamLog.find(e => e.type === 'evidence_gathered')

  if (!evidence && !searchingEvent) return null

  const youCount = evidence?.you_com?.count ?? gatheredEvent?.you_com_count ?? 0
  const tavCount = evidence?.tavily?.count ?? gatheredEvent?.tavily_count ?? 0
  const coverage = evidence?.coverage ?? gatheredEvent?.coverage ?? 'searching…'
  const youAvail = evidence?.you_com?.available ?? (gatheredEvent?.you_com_available || youCount > 0)
  const tavAvail = evidence?.tavily?.available ?? (gatheredEvent?.tavily_available || tavCount > 0)

  return (
    <div style={{ background: 'rgba(0,203,169,0.05)', border: '1px solid rgba(0,203,169,0.2)', borderRadius: '12px', padding: '14px 18px', display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
      <div style={{ fontSize: '11px', color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: 'var(--bull)', display: 'inline-block', animation: gatheredEvent ? 'none' : 'pulse 1.5s infinite', boxShadow: '0 0 6px var(--bull)' }} />
        {gatheredEvent ? 'Evidence gathered' : 'Searching…'}
      </div>
      {[
        { label: 'You.com', count: youCount, available: youAvail, color: '#00cba9' },
        { label: 'Tavily', count: tavCount, available: tavAvail, color: '#a29bfe' },
      ].map(s => (
        <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: s.color }}>{s.label}</span>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>{s.available ? (s.count > 0 ? `${s.count} sources` : 'searching…') : 'no key'}</span>
        </div>
      ))}
      {gatheredEvent && (
        <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '4px', background: 'rgba(0,203,169,0.1)', color: 'var(--bull)', border: '1px solid rgba(0,203,169,0.2)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
          {coverage}
        </span>
      )}
    </div>
  )
}

function ThesisSummary({ result }) {
  const conf = result.confidence ?? 0
  const confColor = conf >= 0.75 ? 'var(--bull)' : conf >= 0.55 ? 'var(--warn)' : 'var(--bear)'

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border2)', borderRadius: '14px', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Investment Thesis</div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '16px', fontWeight: 700 }}>{result.recommendation}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '28px', fontWeight: 700, color: confColor, lineHeight: 1 }}>{Math.round(conf * 100)}%</div>
            <div style={{ fontSize: '10px', color: 'var(--muted)', marginTop: '2px' }}>confidence</div>
          </div>
        </div>
      </div>

      {/* Confidence breakdown */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface2)' }}>
        <div style={{ height: '6px', background: 'var(--dim)', borderRadius: '3px', overflow: 'hidden', marginBottom: '10px' }}>
          <div style={{ height: '100%', width: `${conf * 100}%`, background: `linear-gradient(90deg, ${confColor}, var(--accent2))`, borderRadius: '3px', transition: 'width 0.8s ease' }} />
        </div>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          {Object.entries(result.confidence_breakdown || {}).filter(([k]) => k !== 'overall').map(([k, v]) => (
            <div key={k} style={{ fontSize: '10px', color: 'var(--muted)' }}>
              <span style={{ textTransform: 'capitalize', marginRight: '4px' }}>{k.replace('_', ' ')}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{typeof v === 'number' ? `${Math.round(v * 100)}%` : v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Explanation */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: 1.65 }}>{result.explanation}</div>
      </div>

      {/* Bull / Bear */}
      <div style={{ padding: '18px 20px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        {[
          { label: 'Bull Case', data: result.bull_case, color: 'var(--bull)', bg: 'rgba(0,203,169,0.06)', border: 'rgba(0,203,169,0.2)' },
          { label: 'Bear Case', data: result.bear_case, color: 'var(--bear)', bg: 'rgba(255,107,107,0.06)', border: 'rgba(255,107,107,0.2)' },
        ].map(({ label, data, color, bg, border }) => data && (
          <div key={label} style={{ background: bg, border: `1px solid ${border}`, borderRadius: '10px', padding: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', color, letterSpacing: '0.5px' }}>{label}</span>
              {data.probability != null && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color }}>{Math.round(data.probability * 100)}%</span>}
            </div>
            {data.summary && <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.55, marginBottom: '10px' }}>{data.summary}</div>}
            {data.key_points?.map((pt, i) => (
              <div key={i} style={{ fontSize: '11px', color: 'var(--muted)', padding: '3px 0', display: 'flex', gap: '6px' }}>
                <span style={{ color, flexShrink: 0 }}>·</span>{pt}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Risks */}
      {result.key_risks?.length > 0 && (
        <div style={{ padding: '0 20px 18px' }}>
          <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px', fontWeight: 600 }}>Key Risks</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {result.key_risks.map((r, i) => (
              <div key={i} style={{ fontSize: '12px', color: 'var(--muted)', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                <AlertCircle size={11} style={{ color: 'var(--warn)', flexShrink: 0, marginTop: '2px' }} />{r}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Living Thesis ─────────────────────────────────────────────────────────────
// The persistent intelligence layer: how the thesis has evolved across
// research runs, not just what it says right now (that's ThesisSummary above).

function LivingThesisPanel({ workspaceId, versionCount, lifecycleStage, convictionScore, thesisSignal }) {
  const [versions, setVersions] = useState([])
  const [history, setHistory] = useState([])
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedVersionId, setSelectedVersionId] = useState(null)
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [claimsFilter, setClaimsFilter] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      workspaceApi.getThesisVersions(workspaceId),
      workspaceApi.getConfidenceHistory(workspaceId),
      workspaceApi.getThesisClaims(workspaceId),
    ]).then(([v, h, c]) => {
      if (cancelled) return
      setVersions(v)
      setHistory(h)
      setClaims(c)
      setSelectedVersionId(null)
      setSelectedDetail(null)
    }).catch(console.error).finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [workspaceId, versionCount])

  async function selectVersion(versionId) {
    if (selectedVersionId === versionId) {
      setSelectedVersionId(null)
      setSelectedDetail(null)
      return
    }
    setSelectedVersionId(versionId)
    try {
      const detail = await workspaceApi.getThesisVersion(workspaceId, versionId)
      setSelectedDetail(detail)
    } catch (err) {
      console.error(err)
    }
  }

  const lm = LIFECYCLE_META[lifecycleStage] || LIFECYCLE_META.forming
  const convColor = convictionScore >= 0.75 ? 'var(--bull)' : convictionScore >= 0.5 ? 'var(--warn)' : 'var(--muted)'

  const claimCounts = claims.reduce((acc, c) => { acc[c.status] = (acc[c.status] || 0) + 1; return acc }, {})
  const visibleClaims = claimsFilter ? claims.filter(c => c.status === claimsFilter) : []

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border2)', borderRadius: '14px', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
        <History size={15} style={{ color: 'var(--accent2)' }} />
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '13px', fontWeight: 700, flex: 1 }}>Living Thesis</span>

        <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', padding: '3px 10px', borderRadius: '20px', background: `${lm.color}18`, color: lm.color, border: `1px solid ${lm.color}44`, fontWeight: 600 }}>
          {lm.icon} {lm.label}
        </span>

        <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
          v{versionCount} · <span style={{ color: SIGNAL_COLOR[thesisSignal] || 'var(--muted)', fontWeight: 600, textTransform: 'capitalize' }}>{thesisSignal}</span>
        </span>

        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '16px', fontWeight: 700, color: convColor, lineHeight: 1 }}>{Math.round((convictionScore || 0) * 100)}%</div>
          <div style={{ fontSize: '9px', color: 'var(--muted)' }}>conviction</div>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--muted)', fontSize: '12px' }}>
          <Loader2 size={16} style={{ animation: 'spin 0.7s linear infinite' }} />
        </div>
      ) : (
        <>
          {/* Conviction sparkline */}
          {history.length > 1 && (
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px', fontWeight: 600 }}>Conviction Over Time</div>
              <Sparkline
                data={history.map((h, i) => ({ value: h.conviction_score, label: `v${i + 1}`, signal: h.signal }))}
                color={lm.color}
              />
            </div>
          )}

          {/* Version timeline */}
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px', fontWeight: 600 }}>Version History</div>
            <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
              {versions.map(v => {
                const ct = CHANGE_TYPE_META[v.change_type]
                const isSelected = selectedVersionId === v.id
                const sc = SIGNAL_COLOR[v.signal] || 'var(--muted)'
                return (
                  <button key={v.id} onClick={() => selectVersion(v.id)}
                    style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '4px', padding: '8px 12px', borderRadius: '9px', border: `1px solid ${isSelected ? sc : 'var(--border)'}`, background: isSelected ? `${sc}14` : 'var(--surface2)', cursor: 'pointer', minWidth: '78px', textAlign: 'left', transition: 'all 0.15s' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: sc, flexShrink: 0 }} />
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700 }}>v{v.version_number}</span>
                    </div>
                    <span style={{ fontSize: '9px', color: ct?.color || 'var(--muted)', fontWeight: 600 }}>{ct?.label || 'Initial'}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--muted)' }}>{Math.round(v.conviction_score * 100)}%</span>
                  </button>
                )
              })}
            </div>

            {selectedDetail && (
              <VersionDiffCard version={selectedDetail} />
            )}
          </div>

          {/* Claims tracker */}
          {claims.length > 0 && (
            <div style={{ padding: '16px 20px' }}>
              <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px', fontWeight: 600 }}>Claim Tracker · {claims.length} tracked</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {Object.entries(CLAIM_STATUS_META).filter(([status]) => claimCounts[status]).map(([status, meta]) => (
                  <button key={status} onClick={() => setClaimsFilter(f => f === status ? null : status)}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '5px 12px', borderRadius: '20px', border: `1px solid ${claimsFilter === status ? meta.color : `${meta.color}33`}`, background: claimsFilter === status ? `${meta.color}18` : 'transparent', color: meta.color, fontSize: '11px', fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s' }}>
                    {meta.label} <span style={{ fontFamily: 'var(--font-mono)' }}>{claimCounts[status]}</span>
                  </button>
                ))}
              </div>

              {claimsFilter && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '12px' }}>
                  {visibleClaims.map(c => (
                    <div key={c.id} style={{ fontSize: '12px', color: 'var(--muted)', display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '8px 10px', background: 'var(--surface2)', borderRadius: '8px', border: '1px solid var(--border)' }}>
                      <span style={{ fontSize: '9px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: 'var(--accent2)', textTransform: 'uppercase', fontWeight: 700, flexShrink: 0 }}>{c.claim_type.replace(/_/g, ' ')}</span>
                      <span style={{ flex: 1 }}>{c.claim_text}</span>
                      <span style={{ fontSize: '10px', color: 'var(--muted)', flexShrink: 0 }}>×{c.appearance_count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function VersionDiffCard({ version }) {
  const diff = version.diff
  if (!diff) {
    return (
      <div style={{ marginTop: '12px', fontSize: '12px', color: 'var(--muted)', fontStyle: 'italic' }}>
        Initial version — no prior thesis to compare against.
      </div>
    )
  }

  const sections = [
    ['Key Risks', diff.key_risks],
    ['Assumptions', diff.key_assumptions],
    ['Invalidation Conditions', diff.invalidation_conditions],
    ['Bull Points', diff.bull_points],
    ['Bear Points', diff.bear_points],
  ].filter(([, d]) => d && (d.added.length || d.removed.length))

  return (
    <div style={{ marginTop: '12px', padding: '14px', background: 'var(--surface2)', borderRadius: '10px', border: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', gap: '16px', marginBottom: sections.length ? '12px' : 0, flexWrap: 'wrap' }}>
        <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
          Signal: <span style={{ color: SIGNAL_COLOR[diff.previous_signal], fontWeight: 600 }}>{diff.previous_signal}</span>
          {diff.signal_changed && <> → <span style={{ color: SIGNAL_COLOR[diff.new_signal], fontWeight: 600 }}>{diff.new_signal}</span></>}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
          Conviction Δ <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: diff.conviction_delta >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
            {diff.conviction_delta >= 0 ? '+' : ''}{Math.round(diff.conviction_delta * 100)}%
          </span>
        </div>
      </div>
      {sections.map(([label, d]) => (
        <div key={label} style={{ marginBottom: '8px' }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>{label}</div>
          {d.added.map((t, i) => (
            <div key={`a${i}`} style={{ fontSize: '11px', color: 'var(--bull)', paddingLeft: '10px' }}>+ {t}</div>
          ))}
          {d.removed.map((t, i) => (
            <div key={`r${i}`} style={{ fontSize: '11px', color: 'var(--bear)', paddingLeft: '10px', textDecoration: 'line-through', opacity: 0.7 }}>− {t}</div>
          ))}
        </div>
      ))}
      {!sections.length && (
        <div style={{ fontSize: '11px', color: 'var(--muted)', fontStyle: 'italic' }}>No structural changes — thesis content held steady.</div>
      )}
    </div>
  )
}

function Sparkline({ data, color = 'var(--accent2)', height = 48 }) {
  const [hoverIdx, setHoverIdx] = useState(null)
  const svgRef = useRef(null)

  if (!data.length) return null
  const values = data.map(d => d.value)
  const min = Math.min(...values), max = Math.max(...values)
  const range = max - min || 1
  const padY = 6
  const width = 100 // percentage-based viewBox; scales with container via preserveAspectRatio=none

  const points = data.map((d, i) => ({
    x: data.length === 1 ? width / 2 : (i / (data.length - 1)) * width,
    y: padY + (1 - (d.value - min) / range) * (height - padY * 2),
    ...d,
  }))

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ')
  const last = points[points.length - 1]
  const hovered = hoverIdx != null ? points[hoverIdx] : null

  function handleMove(e) {
    const rect = svgRef.current.getBoundingClientRect()
    const relX = ((e.clientX - rect.left) / rect.width) * width
    let nearest = 0
    let best = Infinity
    points.forEach((p, i) => {
      const dist = Math.abs(p.x - relX)
      if (dist < best) { best = dist; nearest = i }
    })
    setHoverIdx(nearest)
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ width: '100%', height: `${height}px`, display: 'block', cursor: 'crosshair' }}
        onMouseMove={handleMove} onMouseLeave={() => setHoverIdx(null)}>
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {hovered && (
          <line x1={hovered.x} x2={hovered.x} y1={padY} y2={height - padY} stroke={color} strokeWidth="1" strokeOpacity="0.35" vectorEffect="non-scaling-stroke" />
        )}
        <circle cx={last.x} cy={last.y} r="2.5" fill={color} />
        {hovered && (
          <circle cx={hovered.x} cy={hovered.y} r="3" fill={color} stroke="var(--surface)" strokeWidth="1.5" />
        )}
      </svg>
      {/* Direct end-label — only the latest value, not every point */}
      <div style={{ position: 'absolute', top: 0, right: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 700, color }}>
        {Math.round(last.value * 100)}%
      </div>
      {hovered && (
        <div style={{ position: 'absolute', bottom: '-2px', left: `${hovered.x}%`, transform: 'translateX(-50%)', fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--muted)', background: 'var(--surface2)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
          {hovered.label} · {Math.round(hovered.value * 100)}%
        </div>
      )}
    </div>
  )
}

function DebateView({ debate }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', gap: '10px', fontSize: '12px', color: 'var(--muted)' }}>
        <span style={{ padding: '3px 10px', borderRadius: '5px', background: 'rgba(0,203,169,0.1)', color: 'var(--bull)', border: '1px solid rgba(0,203,169,0.2)', fontWeight: 600 }}>▲ {debate.participants?.bull}</span>
        <span style={{ padding: '3px 10px', borderRadius: '5px', background: 'rgba(255,107,107,0.1)', color: 'var(--bear)', border: '1px solid rgba(255,107,107,0.2)', fontWeight: 600 }}>▼ {debate.participants?.bear}</span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '10px', padding: '3px 8px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: debate.debate_winner === 'bull' ? 'var(--bull)' : debate.debate_winner === 'bear' ? 'var(--bear)' : 'var(--muted)' }}>
          {debate.debate_winner === 'draw' ? 'No clear winner' : `${debate.debate_winner} prevailed`}
        </span>
      </div>

      {debate.rounds?.map(round => (
        <div key={round.round} style={{ background: 'var(--surface2)', borderRadius: '10px', padding: '14px', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px', fontWeight: 600 }}>
            Round {round.round} — {round.type}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div style={{ background: 'rgba(0,203,169,0.06)', borderRadius: '8px', padding: '12px', border: '1px solid rgba(0,203,169,0.2)' }}>
              <div style={{ fontSize: '10px', color: 'var(--bull)', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>▲ {round.bull?.agent?.replace(/_/g,' ')}</div>
              <div style={{ fontSize: '12px', color: '#d4f1ea', lineHeight: 1.65 }}>{round.bull?.argument || round.bull?.key_point}</div>
              {round.bull?.key_point && round.bull?.argument && (
                <div style={{ fontSize: '11px', color: 'rgba(0,203,169,0.75)', marginTop: '7px', fontStyle: 'italic' }}>Strongest point: {round.bull.key_point}</div>
              )}
              {round.bull?.concession && <div style={{ fontSize: '11px', color: 'var(--warn)', marginTop: '6px', fontStyle: 'italic' }}>Concedes: {round.bull.concession}</div>}
            </div>
            <div style={{ background: 'rgba(255,107,107,0.06)', borderRadius: '8px', padding: '12px', border: '1px solid rgba(255,107,107,0.2)' }}>
              <div style={{ fontSize: '10px', color: 'var(--bear)', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>▼ {round.bear?.agent?.replace(/_/g,' ')}</div>
              <div style={{ fontSize: '12px', color: '#fde8e8', lineHeight: 1.65 }}>{round.bear?.argument || round.bear?.key_point}</div>
              {round.bear?.key_point && round.bear?.argument && (
                <div style={{ fontSize: '11px', color: 'rgba(255,107,107,0.75)', marginTop: '7px', fontStyle: 'italic' }}>Strongest point: {round.bear.key_point}</div>
              )}
              {round.bear?.concession && <div style={{ fontSize: '11px', color: 'var(--warn)', marginTop: '6px', fontStyle: 'italic' }}>Concedes: {round.bear.concession}</div>}
            </div>
          </div>
        </div>
      ))}

      {debate.moderator_conclusion && (
        <div style={{ background: 'rgba(108,92,231,0.07)', border: '1px solid rgba(108,92,231,0.2)', borderRadius: '10px', padding: '14px' }}>
          <div style={{ fontSize: '10px', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>Moderator Conclusion</div>
          <div style={{ fontSize: '13px', color: '#e0d9ff', lineHeight: 1.65 }}>{debate.moderator_conclusion}</div>
          {debate.key_insight && (
            <div style={{ marginTop: '10px', padding: '7px 10px', background: 'rgba(253,203,110,0.08)', borderRadius: '6px', borderLeft: '2px solid var(--warn)' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--warn)', marginRight: '6px' }}>KEY INSIGHT</span>
              <span style={{ fontSize: '11px', color: '#fef3d0' }}>{debate.key_insight}</span>
            </div>
          )}
          {debate.residual_uncertainty && (
            <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginTop: '8px', fontStyle: 'italic' }}>Open question: {debate.residual_uncertainty}</div>
          )}
        </div>
      )}
    </div>
  )
}

function ScenariosView({ scenarios }) {
  const total = scenarios.reduce((a, s) => a + (s.probability || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {scenarios.map(s => (
        <div key={s.name}
          style={{ background: 'var(--surface2)', border: `1px solid ${s.color}33`, borderRadius: '12px', padding: '16px', transition: 'all 0.2s' }}
          onMouseEnter={e => e.currentTarget.style.borderColor = s.color + '66'}
          onMouseLeave={e => e.currentTarget.style.borderColor = s.color + '33'}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: s.color, boxShadow: `0 0 8px ${s.color}88`, flexShrink: 0 }} />
              <span style={{ fontFamily: 'var(--font-display)', fontSize: '13px', fontWeight: 600 }}>{s.name}</span>
            </div>
            <div style={{ display: 'flex', align: 'center', gap: '12px' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: s.color }}>{s.estimated_upside_pct >= 0 ? '+' : ''}{s.estimated_upside_pct?.toFixed(0) ?? '?'}%</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}>{Math.round((s.probability || 0) * 100)}% prob</span>
            </div>
          </div>

          {/* Probability bar */}
          <div style={{ height: '4px', background: 'var(--dim)', borderRadius: '2px', overflow: 'hidden', marginBottom: '10px' }}>
            <div style={{ height: '100%', width: `${((s.probability || 0) / Math.max(total, 1)) * 100}%`, background: s.color, borderRadius: '2px', transition: 'width 0.5s ease' }} />
          </div>

          <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.55, marginBottom: '8px' }}>{s.summary}</div>

          {s.key_assumptions?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
              {s.key_assumptions.slice(0, 3).map((a, i) => (
                <span key={i} style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '4px', background: `${s.color}11`, color: s.color, border: `1px solid ${s.color}22` }}>{a}</span>
              ))}
            </div>
          )}

          {s.investment_implication && (
            <div style={{ fontSize: '11px', color: 'var(--accent2)', marginTop: '8px', fontStyle: 'italic' }}>→ {s.investment_implication}</div>
          )}
        </div>
      ))}
    </div>
  )
}

function GraphView({ graph }) {
  const typeColors = { company: '#6c5ce7', technology: '#00cba9', sector: '#fdcb6e', macro: '#fd79a8', country: '#74b9ff', person: '#a29bfe', product: '#55efc4', concept: '#b2bec3' }

  const nodesByType = {}
  graph.nodes.forEach(n => {
    const t = n.type || 'concept'
    if (!nodesByType[t]) nodesByType[t] = []
    nodesByType[t].push(n)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Node groups */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {Object.entries(nodesByType).map(([type, nodes]) => (
          <div key={type}>
            <div style={{ fontSize: '10px', color: typeColors[type] || 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600, marginBottom: '6px' }}>{type}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {nodes.map(n => (
                <div key={n.id}
                  title={n.description}
                  style={{ padding: '5px 12px', borderRadius: '20px', background: `${typeColors[type] || '#b2bec3'}15`, border: `1px solid ${typeColors[type] || '#b2bec3'}33`, color: typeColors[type] || 'var(--muted)', fontSize: '12px', fontWeight: 500, cursor: 'default' }}>
                  {n.label}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Key relationships */}
      {graph.edges.length > 0 && (
        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600, marginBottom: '8px' }}>Key Relationships</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {graph.edges.slice(0, 10).map((e, i) => {
              const sourceNode = graph.nodes.find(n => n.id === e.source)
              const targetNode = graph.nodes.find(n => n.id === e.target)
              if (!sourceNode || !targetNode) return null
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--muted)', padding: '4px 0' }}>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{sourceNode.label}</span>
                  <span style={{ color: 'var(--accent2)', fontStyle: 'italic' }}>→ {e.relationship} →</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{targetNode.label}</span>
                  <div style={{ height: '2px', flex: 1, background: `rgba(108,92,231,${e.strength || 0.5})`, borderRadius: '1px', maxWidth: '60px' }} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function AgentOutputs({ outputs }) {
  const [expanded, setExpanded] = useState(null)
  const SIGNAL_COL = { bullish: 'var(--bull)', bearish: 'var(--bear)', neutral: 'var(--muted)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {Object.entries(outputs).map(([name, out]) => {
        const isOpen = expanded === name
        const sc = SIGNAL_COL[out.signal] || 'var(--muted)'
        return (
          <div key={name}
            style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: '10px', overflow: 'hidden' }}>
            <div
              style={{ display: 'flex', alignItems: 'center', padding: '12px 14px', cursor: 'pointer', gap: '10px' }}
              onClick={() => setExpanded(isOpen ? null : name)}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '2px' }}>{name.replace(/_/g, ' ')}</div>
                {out.key_finding && <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{out.key_finding}</div>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {out.signal && <span style={{ fontSize: '9px', padding: '2px 6px', borderRadius: '3px', fontWeight: 700, textTransform: 'uppercase', background: SIGNAL_BG[out.signal] || 'rgba(255,255,255,0.04)', color: sc, border: `1px solid ${sc}44` }}>{out.signal}</span>}
                {out.confidence != null && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--muted)' }}>{Math.round(out.confidence * 100)}%</span>}
                {isOpen ? <ChevronUp size={13} style={{ color: 'var(--muted)' }} /> : <ChevronDown size={13} style={{ color: 'var(--muted)' }} />}
              </div>
            </div>
            {isOpen && out.data && (
              <div style={{ padding: '0 14px 14px', borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px', marginTop: '12px' }}>
                  {Object.entries(out.data).filter(([k, v]) => v != null && typeof v !== 'object').slice(0, 8).map(([k, v]) => (
                    <div key={k} style={{ background: 'var(--surface)', borderRadius: '7px', padding: '8px 10px', border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: '9px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>{k.replace(/_/g, ' ')}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 500 }}>{typeof v === 'number' ? v.toFixed(2) : String(v)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function CollapsibleSection({ title, icon, children, expanded, onToggle }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px', overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '10px', padding: '14px 18px', background: 'transparent', border: 'none', cursor: 'pointer', transition: 'background 0.15s', textAlign: 'left' }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
        <span style={{ fontSize: '16px' }}>{icon}</span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '14px', fontWeight: 600, flex: 1, color: 'var(--text)' }}>{title}</span>
        {expanded ? <ChevronUp size={16} style={{ color: 'var(--muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--muted)' }} />}
      </button>
      {expanded && (
        <div style={{ padding: '0 18px 18px', borderTop: '1px solid var(--border)' }}>
          <div style={{ paddingTop: '14px' }}>{children}</div>
        </div>
      )}
    </div>
  )
}

function EmptyState({ workspace, onStart }) {
  const queries = workspace ? [
    `Analyze the ${workspace.title} investment thesis`,
    `What are the key risks in ${workspace.title}?`,
    `Compare the bull and bear case for ${workspace.tracked_tickers?.join(', ') || 'these positions'}`,
    `What macro tailwinds support ${workspace.title}?`,
  ] : []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 40px', textAlign: 'center' }}>
      <div style={{ fontSize: '48px', marginBottom: '16px' }}>{workspace?.icon || '📊'}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>
        {workspace ? workspace.title : 'Research Workspace'}
      </div>
      <div style={{ fontSize: '14px', color: 'var(--muted)', marginBottom: '32px', maxWidth: '360px', lineHeight: 1.6 }}>
        {workspace?.description || 'Run a query to start your research. 12 agents will activate in parallel.'}
      </div>
      {queries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', maxWidth: '400px' }}>
          {queries.map(q => (
            <button key={q} onClick={() => onStart(null, q)}
              style={{ padding: '10px 16px', borderRadius: '10px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--muted)', fontSize: '12px', cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(108,92,231,0.4)'; e.currentTarget.style.color = 'var(--text)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--muted)' }}>
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
