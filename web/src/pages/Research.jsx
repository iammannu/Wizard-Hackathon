import React, { useRef, useEffect, useState } from 'react'
import {
  Send, BrainCircuit, Loader2, TrendingUp, TrendingDown,
  AlertTriangle, Zap, Swords, BarChart2, Network,
  ChevronDown, ChevronUp,
} from 'lucide-react'
import { useResearchStore } from '../store/index.js'
import styles from './Research.module.css'

const EXAMPLES = [
  { icon: '📈', text: 'Is NVDA a good long-term buy at current prices?' },
  { icon: '⚖️', text: 'Compare Apple vs Microsoft for the next 3 years' },
  { icon: '🔍', text: "Analyze Tesla's bull and bear case in detail" },
  { icon: '🌍', text: 'What happens to tech stocks if Fed cuts rates 100bps?' },
  { icon: '💊', text: 'Best healthcare stocks with low P/E under 20' },
  { icon: '⚡', text: 'Undervalued AI companies with strong balance sheets' },
]

const AGENT_META = {
  technical:           { label: 'Technical',           desc: 'TA indicators & chart patterns' },
  fundamental:         { label: 'Fundamental',         desc: 'Financials & earnings quality' },
  sentiment:           { label: 'Sentiment',           desc: 'News & market sentiment' },
  valuation:           { label: 'Valuation',           desc: 'DCF & comparable analysis' },
  risk:                { label: 'Risk',                desc: 'Volatility & drawdown metrics' },
  macro:               { label: 'Macro',               desc: 'Macroeconomic environment' },
  growth_investor:     { label: 'Growth Investor',     desc: 'Long-term growth potential' },
  value_investor:      { label: 'Value Investor',      desc: 'Margin of safety & intrinsic value' },
  quant_researcher:    { label: 'Quant Researcher',    desc: 'Statistical & factor models' },
  industry_specialist: { label: 'Industry Specialist', desc: 'Sector-specific deep dive' },
  short_seller:        { label: 'Short Seller',        desc: 'Downside risks & red flags' },
  devils_advocate:     { label: "Devil's Advocate",    desc: 'Challenges the consensus view' },
}

const SCENARIO_COLORS = {
  bull: 'var(--bull)',
  bear: 'var(--bear)',
  base: 'var(--accent2)',
  black_swan: '#fd79a8',
  tail_risk: '#fd79a8',
}

export default function Research() {
  const { messages, agentStates, isStreaming, depth, setDepth, sendQuery, clearMessages } = useResearchStore()
  const [query, setQuery] = useState('')
  const textareaRef = useRef(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const q = query.trim()
    if (!q || isStreaming) return
    setQuery('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    sendQuery(q)
  }

  function autoResize(e) {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
  }

  const hasAgents = Object.keys(agentStates).length > 0

  return (
    <div className={styles.page}>
      {/* Topbar */}
      <div className={styles.topbar}>
        <BrainCircuit size={16} className={styles.topbarIcon} />
        <span className={styles.topbarTitle}>Research Chat</span>
        <div className={styles.depthToggle}>
          {['quick', 'full'].map(d => (
            <button
              key={d}
              className={`${styles.depthBtn} ${depth === d ? styles.depthActive : ''}`}
              onClick={() => setDepth(d)}
            >
              {d === 'quick' ? <Zap size={11} /> : null}
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>
        <span className={styles.badge}>
          {isStreaming ? 'Analyzing…' : '12 agents ready'}
        </span>
        {messages.length > 0 && (
          <button className={styles.clearBtn} onClick={clearMessages}>Clear</button>
        )}
      </div>

      <div className={styles.body}>
        {/* Chat column */}
        <div className={styles.chatCol}>
          <div className={styles.messages}>
            {messages.length === 0 ? (
              <EmptyState onExample={(q) => { setQuery(q); textareaRef.current?.focus() }} />
            ) : (
              messages.map(msg => (
                msg.role === 'user'
                  ? <UserMessage key={msg.id} text={msg.text} />
                  : <AiMessage key={msg.id} msg={msg} />
              ))
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className={styles.inputBar}>
            <div className={styles.inputWrap}>
              <textarea
                ref={textareaRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                onInput={autoResize}
                placeholder="Analyze AAPL · Compare MSFT vs GOOGL · What if Fed cuts 100bps…"
                className={styles.textarea}
                rows={1}
                disabled={isStreaming}
              />
              <button
                className={styles.sendBtn}
                onClick={submit}
                disabled={!query.trim() || isStreaming}
              >
                {isStreaming
                  ? <Loader2 size={14} className={styles.spinning} />
                  : <Send size={14} />}
              </button>
            </div>
            <p className={styles.inputHint}>
              Enter to send · Shift+Enter for newline · AI analysis is not financial advice
            </p>
          </div>
        </div>

        {/* Agent panel */}
        {hasAgents && (
          <aside className={styles.agentPanel}>
            <div className={styles.agentPanelHeader}>
              <div className={styles.agentPanelTitle}>Agent Activity</div>
              <div className={styles.agentPanelSub}>Real-time reasoning</div>
            </div>
            <div className={styles.agentList}>
              {Object.entries(agentStates).map(([name, state]) => (
                <AgentCard key={name} name={name} state={state} />
              ))}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}

function EmptyState({ onExample }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}><BrainCircuit size={26} /></div>
      <h2 className={styles.emptyTitle}>What do you want to research?</h2>
      <p className={styles.emptySub}>
        12 AI agents run in parallel — technical, fundamental, sentiment, valuation, risk, macro,
        growth investor, value investor, quant researcher, industry specialist, short seller &amp;
        devil's advocate. Streamed live with confidence scoring, debate engine, scenario simulations
        and knowledge graph.
      </p>
      <div className={styles.exampleGrid}>
        {EXAMPLES.map(ex => (
          <button key={ex.text} className={styles.exampleBtn} onClick={() => onExample(ex.text)}>
            <span className={styles.exampleIcon}>{ex.icon}</span>
            <span>{ex.text}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function UserMessage({ text }) {
  return (
    <div className={styles.userRow}>
      <div className={styles.userBubble}>{text}</div>
    </div>
  )
}

function Collapsible({ title, icon, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ marginTop: '10px', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '10px', overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: '6px',
          padding: '8px 12px', background: 'rgba(255,255,255,0.03)',
          border: 'none', cursor: 'pointer', color: 'var(--text)', fontSize: '12px', fontWeight: 600,
        }}
      >
        {icon}
        <span style={{ flex: 1, textAlign: 'left' }}>{title}</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && <div style={{ padding: '10px 12px' }}>{children}</div>}
    </div>
  )
}

function AiMessage({ msg }) {
  const { text, streaming, tickers, analysis } = msg
  const conf = analysis?.confidence ?? null
  const pct = conf !== null ? Math.round(conf * 100) : null
  const confColor = conf >= 0.7 ? 'var(--bull)' : conf >= 0.4 ? 'var(--warn)' : 'var(--bear)'
  const bd = analysis?.confidence_breakdown ?? {}
  const bdKeys = Object.keys(bd).filter(k => k !== 'overall')

  return (
    <div className={styles.aiRow}>
      <div className={styles.aiAvatar}>α</div>
      <div className={styles.aiContent}>
        {tickers?.length > 0 && (
          <div className={styles.tickers}>
            {tickers.map(t => <span key={t} className={styles.tickerChip}>{t}</span>)}
          </div>
        )}

        <div className={styles.aiBubble}>
          {text}
          {streaming && <span className={styles.cursor} />}
        </div>

        {!streaming && analysis && (
          <>
            {/* Confidence */}
            {conf !== null && (
              <div className={styles.confCard}>
                <div className={styles.confHeader}>
                  <span className={styles.confLabel}>AI Confidence</span>
                  <span className={styles.confPct} style={{ color: confColor }}>{pct}%</span>
                </div>
                <div className={styles.confTrack}>
                  <div
                    className={styles.confFill}
                    style={{ width: `${pct}%`, background: confColor }}
                  />
                </div>
                {bdKeys.length > 0 && (
                  <div className={styles.confBreakdown}>
                    {bdKeys.map(k => (
                      <div key={k} className={styles.confBdItem}>
                        <div className={styles.confBdVal}>{Math.round(bd[k] * 100)}%</div>
                        <div className={styles.confBdKey}>{k.replace(/_/g, ' ')}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Recommendation */}
            {analysis.recommendation && (
              <div className={styles.recCard}>
                <div className={styles.recLabel}>Recommendation</div>
                <div className={styles.recText}>{analysis.recommendation}</div>
              </div>
            )}

            {/* Bull / Bear */}
            {(analysis.bull_case || analysis.bear_case) && (
              <div className={styles.bbGrid}>
                <BullBearCard type="bull" data={analysis.bull_case} />
                <BullBearCard type="bear" data={analysis.bear_case} />
              </div>
            )}

            {/* Key risks */}
            {analysis.key_risks?.length > 0 && (
              <div className={styles.risksCard}>
                <div className={styles.risksLabel}><AlertTriangle size={11} /> Key Risks</div>
                {analysis.key_risks.map((r, i) => (
                  <div key={i} className={styles.riskItem}>
                    <span className={styles.riskBullet}>▸</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Debate */}
            {analysis.debate?.debate_occurred && (
              <Collapsible
                title={`Agent Debate — Winner: ${analysis.debate.debate_winner ?? 'draw'}`}
                icon={<Swords size={13} style={{ color: 'var(--warn)' }} />}
                defaultOpen={false}
              >
                <DebateView debate={analysis.debate} />
              </Collapsible>
            )}

            {/* Scenarios */}
            {analysis.scenarios?.length > 0 && (
              <Collapsible
                title={`Scenario Simulations (${analysis.scenarios.length})`}
                icon={<BarChart2 size={13} style={{ color: 'var(--accent2)' }} />}
                defaultOpen={false}
              >
                <ScenariosView scenarios={analysis.scenarios} />
              </Collapsible>
            )}

            {/* Knowledge graph */}
            {analysis.knowledge_graph?.nodes?.length > 0 && (
              <Collapsible
                title={`Knowledge Graph — ${analysis.knowledge_graph.node_count} nodes, ${analysis.knowledge_graph.edge_count} edges`}
                icon={<Network size={13} style={{ color: 'var(--accent)' }} />}
                defaultOpen={false}
              >
                <GraphView graph={analysis.knowledge_graph} />
              </Collapsible>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function BullBearCard({ type, data }) {
  if (!data) return null
  const bull = type === 'bull'
  return (
    <div className={bull ? styles.bullCard : styles.bearCard}>
      <div className={styles.bbHeader}>
        {bull
          ? <><TrendingUp size={11} /><span className={styles.bullLabel}>Bull Case</span></>
          : <><TrendingDown size={11} /><span className={styles.bearLabel}>Bear Case</span></>}
        <span className={bull ? styles.bullProb : styles.bearProb}>
          {Math.round((data.probability ?? 0) * 100)}%
        </span>
      </div>
      <p className={styles.bbSummary}>{data.summary}</p>
      <ul className={styles.bbPoints}>
        {(data.key_points ?? []).map((pt, i) => (
          <li key={i} className={styles.bbPoint}>
            <span className={bull ? styles.bullDot : styles.bearDot}>{bull ? '+' : '−'}</span>
            <span>{pt}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DebateView({ debate }) {
  if (!debate?.debate_occurred) return null
  const { participants = {}, rounds = [], moderator_conclusion, key_insight, residual_uncertainty, debate_winner } = debate

  const bullAgent = participants.bull
  const bearAgent = participants.bear

  return (
    <div style={{ fontSize: '12px' }}>
      {/* Participants */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <div style={{ padding: '4px 12px', borderRadius: '20px', fontSize: '11px', fontWeight: 700, background: 'rgba(0,203,169,0.12)', color: 'var(--bull)', border: '1px solid rgba(0,203,169,0.25)' }}>
          ▲ {bullAgent?.replace(/_/g, ' ')} — BULL
        </div>
        <div style={{ padding: '4px 12px', borderRadius: '20px', fontSize: '11px', fontWeight: 700, background: 'rgba(255,107,107,0.12)', color: 'var(--bear)', border: '1px solid rgba(255,107,107,0.25)' }}>
          ▼ {bearAgent?.replace(/_/g, ' ')} — BEAR
        </div>
      </div>

      {/* Rounds */}
      {rounds.map((round, i) => (
        <div key={i} style={{ marginBottom: '10px', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.07)' }}>
          {/* Round header */}
          <div style={{ padding: '6px 12px', background: 'rgba(108,92,231,0.15)', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
            <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--accent2)', letterSpacing: '0.8px', textTransform: 'uppercase' }}>
              Round {round.round} — {round.type === 'opening' ? 'Opening Arguments' : 'Rebuttals'}
            </span>
          </div>

          {/* Bull argument */}
          {round.bull?.argument && (
            <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(0,203,169,0.04)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '5px' }}>
                <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--bull)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  ▲ {round.bull.agent?.replace(/_/g, ' ')}
                </span>
                <span style={{ fontSize: '9px', color: 'rgba(0,203,169,0.5)', padding: '1px 6px', borderRadius: '3px', background: 'rgba(0,203,169,0.1)' }}>BULL</span>
              </div>
              <p style={{ margin: 0, color: '#d4f1ea', lineHeight: 1.6, fontSize: '12px' }}>{round.bull.argument}</p>
              {round.bull.key_point && (
                <div style={{ marginTop: '5px', fontSize: '11px', color: 'rgba(0,203,169,0.7)', fontStyle: 'italic' }}>
                  Key point: {round.bull.key_point}
                </div>
              )}
              {round.bull.concession && (
                <div style={{ marginTop: '5px', fontSize: '11px', color: 'var(--warn)', fontStyle: 'italic' }}>
                  Concedes: {round.bull.concession}
                </div>
              )}
            </div>
          )}

          {/* Bear argument */}
          {round.bear?.argument && (
            <div style={{ padding: '10px 12px', background: 'rgba(255,107,107,0.04)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '5px' }}>
                <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--bear)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  ▼ {round.bear.agent?.replace(/_/g, ' ')}
                </span>
                <span style={{ fontSize: '9px', color: 'rgba(255,107,107,0.5)', padding: '1px 6px', borderRadius: '3px', background: 'rgba(255,107,107,0.1)' }}>BEAR</span>
              </div>
              <p style={{ margin: 0, color: '#fde8e8', lineHeight: 1.6, fontSize: '12px' }}>{round.bear.argument}</p>
              {round.bear.key_point && (
                <div style={{ marginTop: '5px', fontSize: '11px', color: 'rgba(255,107,107,0.7)', fontStyle: 'italic' }}>
                  Key point: {round.bear.key_point}
                </div>
              )}
              {round.bear.concession && (
                <div style={{ marginTop: '5px', fontSize: '11px', color: 'var(--warn)', fontStyle: 'italic' }}>
                  Concedes: {round.bear.concession}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* Moderator conclusion */}
      {moderator_conclusion && (
        <div style={{ padding: '10px 14px', background: 'rgba(108,92,231,0.1)', borderRadius: '8px', borderLeft: '3px solid var(--accent)', marginBottom: '8px' }}>
          <div style={{ fontSize: '10px', color: 'var(--accent2)', fontWeight: 700, marginBottom: '5px', letterSpacing: '0.5px' }}>
            MODERATOR CONCLUSION
            {debate_winner && debate_winner !== 'draw' && (
              <span style={{ marginLeft: '8px', padding: '1px 7px', borderRadius: '3px', background: debate_winner === 'bull' ? 'rgba(0,203,169,0.15)' : 'rgba(255,107,107,0.15)', color: debate_winner === 'bull' ? 'var(--bull)' : 'var(--bear)', fontSize: '9px' }}>
                {debate_winner.toUpperCase()} WINS
              </span>
            )}
          </div>
          <p style={{ margin: 0, color: '#e0d9ff', lineHeight: 1.6, fontSize: '12px' }}>{moderator_conclusion}</p>
        </div>
      )}

      {key_insight && (
        <div style={{ padding: '7px 12px', background: 'rgba(253,203,110,0.07)', borderRadius: '6px', borderLeft: '2px solid var(--warn)' }}>
          <span style={{ fontSize: '10px', fontWeight: 700, color: 'var(--warn)', marginRight: '6px' }}>KEY INSIGHT</span>
          <span style={{ fontSize: '11px', color: '#fef3d0', lineHeight: 1.5 }}>{key_insight}</span>
        </div>
      )}

      {residual_uncertainty && (
        <div style={{ marginTop: '6px', fontSize: '11px', color: 'rgba(255,255,255,0.45)', fontStyle: 'italic', padding: '0 4px' }}>
          Open question: {residual_uncertainty}
        </div>
      )}
    </div>
  )
}

function ScenariosView({ scenarios }) {
  if (!scenarios?.length) return null
  const total = scenarios.reduce((s, sc) => s + (sc.probability || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {scenarios.map((sc, i) => {
        const color = SCENARIO_COLORS[sc.type] || 'var(--accent2)'
        const pct = total > 0 ? Math.round((sc.probability / total) * 100) : 0
        const upside = sc.estimated_upside_pct
        return (
          <div key={i} style={{
            padding: '9px 11px', borderRadius: '8px', border: `1px solid ${color}22`,
            background: `${color}08`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color }}>{sc.name}</span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {upside != null && (
                  <span style={{
                    fontSize: '11px', fontWeight: 700,
                    color: upside >= 0 ? 'var(--bull)' : 'var(--bear)',
                  }}>
                    {upside >= 0 ? '+' : ''}{upside}%
                  </span>
                )}
                <span style={{ fontSize: '11px', color: 'var(--dim)' }}>{pct}% prob</span>
              </div>
            </div>
            <div style={{ height: '3px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', marginBottom: '6px' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: '2px' }} />
            </div>
            <p style={{ fontSize: '11px', color: 'var(--dim)', lineHeight: 1.5, margin: 0 }}>{sc.summary}</p>
            {sc.time_horizon && (
              <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--dim)' }}>
                Horizon: {sc.time_horizon}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const NODE_COLORS = {
  company: '#6c5ce7',
  technology: '#00cba9',
  sector: '#fdcb6e',
  macro: '#74b9ff',
  country: '#a29bfe',
  person: '#fd79a8',
  product: '#55efc4',
  concept: '#81ecec',
}

function GraphView({ graph }) {
  if (!graph?.nodes?.length) return null

  return (
    <div style={{ fontSize: '12px' }}>
      {/* Nodes */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginBottom: '10px' }}>
        {graph.nodes.map((node) => {
          const color = NODE_COLORS[node.type] || 'var(--accent2)'
          return (
            <div key={node.id} style={{
              padding: '3px 9px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
              background: `${color}18`, color, border: `1px solid ${color}30`,
            }}>
              {node.label}
            </div>
          )
        })}
      </div>

      {/* Edges */}
      {graph.edges?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {graph.edges.slice(0, 10).map((edge, i) => {
            const sourceNode = graph.nodes.find(n => n.id === edge.source)
            const targetNode = graph.nodes.find(n => n.id === edge.target)
            if (!sourceNode || !targetNode) return null
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '5px', color: 'var(--dim)', fontSize: '11px' }}>
                <span style={{ color: NODE_COLORS[sourceNode.type] || 'var(--accent2)', fontWeight: 600 }}>
                  {sourceNode.label}
                </span>
                <span style={{ color: 'var(--dim)' }}>→ {edge.label} →</span>
                <span style={{ color: NODE_COLORS[targetNode.type] || 'var(--accent2)', fontWeight: 600 }}>
                  {targetNode.label}
                </span>
              </div>
            )
          })}
          {graph.edges.length > 10 && (
            <div style={{ color: 'var(--dim)', fontSize: '11px' }}>
              +{graph.edges.length - 10} more relationships
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AgentCard({ name, state }) {
  const meta = AGENT_META[name] || { label: name, desc: '' }
  const cls = state.status === 'thinking' ? styles.agentThinking
            : state.signal === 'bullish'  ? styles.agentBull
            : state.signal === 'bearish'  ? styles.agentBear
            : styles.agentDone

  const confColor = state.confidence != null
    ? (state.confidence >= 0.7 ? 'var(--bull)' : state.confidence >= 0.4 ? 'var(--warn)' : 'var(--bear)')
    : 'var(--dim)'

  return (
    <div className={`${styles.agentCard} ${cls}`}>
      <div className={styles.agentRow}>
        {state.status === 'thinking'
          ? <div className={styles.spinner} />
          : <span className={styles.agentCheck}>✓</span>}
        <span className={styles.agentName}>{meta.label}</span>
        {state.signal && (
          <span className={
            state.signal === 'bullish' ? styles.sigBull
            : state.signal === 'bearish' ? styles.sigBear
            : styles.sigNeu
          }>{state.signal}</span>
        )}
      </div>
      <div className={styles.agentDesc}>{meta.desc}</div>
      {state.status === 'thinking' && (
        <div className={styles.dots}>
          <div className={styles.dot} /><div className={styles.dot} /><div className={styles.dot} />
        </div>
      )}
      {state.confidence != null && (
        <div className={styles.agentConfBar}>
          <div className={styles.agentConfFill} style={{ width: `${Math.round(state.confidence * 100)}%`, background: confColor }} />
        </div>
      )}
    </div>
  )
}
