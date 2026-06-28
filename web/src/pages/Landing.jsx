import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const AGENTS = [
  { name: 'Research Coordinator', role: 'Orchestrates the team', signal: 'active', color: '#a29bfe' },
  { name: 'Technical Analyst',    role: 'Price action & momentum', signal: 'bullish', color: '#00cba9' },
  { name: 'Fundamental Analyst',  role: 'Earnings & balance sheet', signal: 'bullish', color: '#00cba9' },
  { name: 'Valuation Expert',     role: 'Intrinsic value & margin of safety', signal: 'neutral', color: '#fdcb6e' },
  { name: 'Sentiment Analyst',    role: 'News flow & catalysts', signal: 'bullish', color: '#00cba9' },
  { name: 'Macro Economist',      role: 'Rate env & economic cycle', signal: 'neutral', color: '#fdcb6e' },
  { name: 'Growth Investor',      role: 'TAM & disruption thesis', signal: 'bullish', color: '#00cba9' },
  { name: 'Value Investor',       role: 'Owner earnings & moat width', signal: 'neutral', color: '#fdcb6e' },
  { name: 'Quant Researcher',     role: 'Factor analysis & momentum', signal: 'bullish', color: '#00cba9' },
  { name: 'Industry Specialist',  role: "Porter's Five Forces", signal: 'bullish', color: '#00cba9' },
  { name: 'Short Seller',         role: 'Bear thesis & red flags', signal: 'bearish', color: '#ff6b6b' },
  { name: "Devil's Advocate",     role: 'Challenges consensus', signal: 'neutral', color: '#fdcb6e' },
]

const WORKSPACES = [
  { icon: '⚡', title: 'AI Infrastructure', tickers: ['NVDA', 'MSFT', 'GOOGL'], confidence: 0.82 },
  { icon: '⚛️', title: 'Nuclear Energy Renaissance', tickers: ['CEG', 'CCJ', 'VST'], confidence: 0.74 },
  { icon: '🤖', title: 'Humanoid Robotics', tickers: ['TSLA', 'NVDA', 'AMZN'], confidence: 0.67 },
  { icon: '💊', title: 'Healthcare AI', tickers: ['LLY', 'ISRG', 'VEEV'], confidence: 0.71 },
]

const FEATURES = [
  { icon: '🧠', title: 'Living Research Workspaces', desc: 'Persistent investment theses that evolve over time. Return days later and find your thesis updated with new evidence.' },
  { icon: '⚔️', title: 'Agent Debate Engine',        desc: 'Bull and bear agents argue live. Growth Investor vs Short Seller. Devil\'s Advocate challenges every consensus.' },
  { icon: '🌐', title: 'You.com Research Engine',    desc: 'Every workspace searches You.com for breaking news, earnings coverage, and market intelligence in real time.' },
  { icon: '✅', title: 'Tavily Cross-Validation',    desc: 'Tavily independently validates every finding. Confidence rises when sources agree; falls when they conflict.' },
  { icon: '🎭', title: 'Scenario Simulation',        desc: 'Bull / Base / Bear / Structural Breakout / Black Swan — five probabilistic futures, not a single prediction.' },
  { icon: '🕸️', title: 'Living Knowledge Graph',     desc: 'Automatically maps relationships: companies, suppliers, technologies, regulators, macroeconomic forces.' },
]

const SCENARIOS = [
  { name: 'Bull Case', prob: '35%', color: '#00cba9', upside: '+82%', note: 'AI supercycle continues through 2027' },
  { name: 'Base Case', prob: '42%', color: '#a29bfe', upside: '+28%', note: 'Steady growth, rate normalization' },
  { name: 'Bear Case', prob: '17%', color: '#ff6b6b', upside: '−24%', note: 'Capex slowdown from hyperscalers' },
  { name: 'Black Swan', prob: '6%', color: '#fd79a8', upside: '−61%', note: 'Export restrictions + supply chain shock' },
]

export function Landing() {
  const navigate = useNavigate()
  const [activeAgent, setActiveAgent] = useState(0)
  const [ticker, setTicker] = useState(0)

  useEffect(() => {
    const t1 = setInterval(() => setActiveAgent(a => (a + 1) % AGENTS.length), 1800)
    const t2 = setInterval(() => setTicker(t => (t + 1) % 3), 3000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  return (
    <div style={{ minHeight: '100vh', overflowX: 'hidden', background: 'var(--bg)' }}>

      {/* ── Nav ── */}
      <nav style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100, height: '64px', display: 'flex', alignItems: 'center', padding: '0 48px', gap: '32px', background: 'rgba(7,7,13,0.9)', backdropFilter: 'blur(20px)', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }} onClick={() => navigate('/')}>
          <div style={{ width: '30px', height: '30px', background: 'linear-gradient(135deg, var(--accent), var(--accent2))', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '15px', fontWeight: 800, color: '#fff', boxShadow: '0 0 20px rgba(108,92,231,0.4)' }}>α</div>
          <span>AlphaForage</span>
          <span style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '4px', background: 'rgba(108,92,231,0.15)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.25)', fontFamily: 'var(--font-mono)', letterSpacing: '0.5px' }}>v2.0</span>
        </div>
        <div style={{ display: 'flex', gap: '28px', marginLeft: 'auto', alignItems: 'center' }}>
          {[['Workspaces', '/app/workspaces'], ['Research', '/app/research'], ['Screener', '/app/screener']].map(([l, p]) => (
            <span key={l} style={{ fontSize: '14px', color: 'var(--muted)', cursor: 'pointer', transition: 'color 0.15s' }}
              onMouseEnter={e => e.target.style.color = 'var(--text)'}
              onMouseLeave={e => e.target.style.color = 'var(--muted)'}
              onClick={() => navigate(p)}>{l}</span>
          ))}
          <button onClick={() => navigate('/app/workspaces')}
            style={{ marginLeft: '12px', padding: '9px 22px', borderRadius: '10px', border: 'none', background: 'linear-gradient(135deg, var(--accent), #8b5cf6)', color: '#fff', fontSize: '13px', fontWeight: 600, cursor: 'pointer', boxShadow: '0 4px 20px rgba(108,92,231,0.35)', transition: 'all 0.2s' }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 6px 28px rgba(108,92,231,0.5)' }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(108,92,231,0.35)' }}>
            Open Platform →
          </button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '120px 24px 80px', position: 'relative', overflow: 'hidden' }}>
        {/* Background orbs */}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
          <div style={{ position: 'absolute', width: '800px', height: '800px', borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(108,92,231,0.15) 0%, transparent 70%)', top: '40%', left: '50%', transform: 'translate(-50%,-50%)' }} />
          <div style={{ position: 'absolute', width: '400px', height: '400px', borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(0,203,169,0.08) 0%, transparent 70%)', top: '20%', right: '10%' }} />
          <div style={{ position: 'absolute', width: '300px', height: '300px', borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(253,121,168,0.07) 0%, transparent 70%)', bottom: '20%', left: '10%' }} />
        </div>

        <div style={{ position: 'relative', maxWidth: '900px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', border: '1px solid rgba(108,92,231,0.35)', background: 'rgba(108,92,231,0.1)', padding: '7px 16px', borderRadius: '100px', fontSize: '12px', color: 'var(--accent2)', fontWeight: 500, marginBottom: '32px', backdropFilter: 'blur(10px)' }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: 'var(--bull)', display: 'inline-block', animation: 'pulse 2s infinite', boxShadow: '0 0 8px var(--bull)' }} />
            12 AI Agents · You.com + Tavily Research · Live Debate · Scenario Simulation
          </div>

          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(48px,7vw,90px)', fontWeight: 800, lineHeight: 1.0, letterSpacing: '-3px', marginBottom: '24px' }}>
            The Autonomous<br />
            <span style={{ background: 'linear-gradient(135deg, var(--accent2), #e879f9, #38bdf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              Investment Intelligence
            </span>
            <br />Platform
          </h1>

          <p style={{ fontSize: '18px', color: 'var(--muted)', maxWidth: '560px', lineHeight: 1.7, marginBottom: '48px', fontWeight: 300, margin: '0 auto 48px' }}>
            Not another chatbot. Not another screener. A team of 12 institutional analysts working autonomously — researching, debating, and updating your investment thesis continuously.
          </p>

          <div style={{ display: 'flex', gap: '14px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button onClick={() => navigate('/app/workspaces')}
              style={{ padding: '16px 36px', borderRadius: '12px', border: 'none', background: 'linear-gradient(135deg, var(--accent), #8b5cf6)', color: '#fff', fontSize: '15px', fontWeight: 600, cursor: 'pointer', boxShadow: '0 4px 24px rgba(108,92,231,0.4)', transition: 'all 0.25s' }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 8px 36px rgba(108,92,231,0.55)' }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 24px rgba(108,92,231,0.4)' }}>
              Create Your First Workspace →
            </button>
            <button onClick={() => navigate('/app/research')}
              style={{ padding: '15px 28px', borderRadius: '12px', border: '1px solid var(--border2)', background: 'rgba(255,255,255,0.04)', color: 'var(--text)', fontSize: '15px', cursor: 'pointer', backdropFilter: 'blur(10px)', transition: 'all 0.2s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.08)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}>
              Try Quick Research
            </button>
          </div>

          {/* Stats */}
          <div style={{ display: 'flex', gap: '48px', justifyContent: 'center', marginTop: '64px', flexWrap: 'wrap' }}>
            {[['12', 'AI Agents'], ['2', 'Research Engines'], ['5', 'Scenarios Generated'], ['∞', 'Memory Horizon']].map(([n, l]) => (
              <div key={l} style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: '36px', fontWeight: 800, background: 'linear-gradient(135deg, var(--accent2), #e879f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>{n}</div>
                <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px', letterSpacing: '0.5px' }}>{l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Agent Team ── */}
      <section style={{ padding: '80px 48px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ fontSize: '11px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--accent2)', fontWeight: 600, marginBottom: '12px' }}>Your Research Team</div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px,4vw,52px)', fontWeight: 800, letterSpacing: '-2px', marginBottom: '8px' }}>12 specialists. One platform.</h2>
        <p style={{ color: 'var(--muted)', fontSize: '15px', marginBottom: '40px', maxWidth: '500px' }}>All run in parallel. All stream their reasoning live. The Supervisor synthesizes conflicts into a single institutional thesis.</p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '10px' }}>
          {AGENTS.map((agent, i) => {
            const isActive = activeAgent === i
            return (
              <div key={agent.name}
                style={{ background: isActive ? 'rgba(108,92,231,0.12)' : 'var(--surface)', border: `1px solid ${isActive ? 'rgba(108,92,231,0.4)' : 'var(--border)'}`, borderRadius: '12px', padding: '16px', transition: 'all 0.4s', transform: isActive ? 'translateY(-2px)' : 'none', boxShadow: isActive ? '0 8px 32px rgba(108,92,231,0.15)' : 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: isActive ? 'var(--text)' : 'var(--text)' }}>{agent.name}</span>
                  {isActive && (
                    <span style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
                      {[0, 1, 2].map(d => (
                        <span key={d} style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--accent)', animation: `dotPulse 1.2s ${d * 0.2}s infinite` }} />
                      ))}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '10px' }}>{agent.role}</div>
                {isActive && (
                  <span style={{ fontSize: '9px', padding: '2px 7px', borderRadius: '4px', fontWeight: 600, textTransform: 'uppercase', background: agent.signal === 'bullish' ? 'rgba(0,203,169,0.15)' : agent.signal === 'bearish' ? 'rgba(255,107,107,0.15)' : 'rgba(255,255,255,0.07)', color: agent.signal === 'bullish' ? 'var(--bull)' : agent.signal === 'bearish' ? 'var(--bear)' : 'var(--muted)', border: `1px solid ${agent.signal === 'bullish' ? 'rgba(0,203,169,0.25)' : agent.signal === 'bearish' ? 'rgba(255,107,107,0.25)' : 'var(--border)'}` }}>
                    {agent.signal}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Workspaces Demo ── */}
      <section style={{ padding: '80px 48px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ fontSize: '11px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--accent2)', fontWeight: 600, marginBottom: '12px' }}>Living Research Workspaces</div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px,4vw,52px)', fontWeight: 800, letterSpacing: '-2px', marginBottom: '8px' }}>Your thesis. Evolving forever.</h2>
        <p style={{ color: 'var(--muted)', fontSize: '15px', marginBottom: '40px', maxWidth: '520px' }}>Create a workspace for any investment theme. AI researches continuously. Return tomorrow and find it updated.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {WORKSPACES.map(ws => (
            <div key={ws.title}
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px', padding: '22px', cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(108,92,231,0.4)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none' }}
              onClick={() => navigate('/app/workspaces')}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                <span style={{ fontSize: '24px' }}>{ws.icon}</span>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: '15px', fontWeight: 600 }}>{ws.title}</span>
              </div>
              <div style={{ display: 'flex', gap: '6px', marginBottom: '14px', flexWrap: 'wrap' }}>
                {ws.tickers.map(t => (
                  <span key={t} style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', padding: '3px 8px', borderRadius: '5px', background: 'rgba(108,92,231,0.1)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.2)' }}>{t}</span>
                ))}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Confidence</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: ws.confidence >= 0.75 ? 'var(--bull)' : ws.confidence >= 0.6 ? 'var(--warn)' : 'var(--muted)' }}>
                  {Math.round(ws.confidence * 100)}%
                </span>
              </div>
              <div style={{ height: '4px', background: 'var(--dim)', borderRadius: '2px', marginTop: '6px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${ws.confidence * 100}%`, background: ws.confidence >= 0.75 ? 'linear-gradient(90deg, var(--bull), #38bdf8)' : 'linear-gradient(90deg, var(--warn), var(--accent2))', borderRadius: '2px', transition: 'width 0.8s ease' }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ── */}
      <section style={{ padding: '80px 48px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ fontSize: '11px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--accent2)', fontWeight: 600, marginBottom: '12px' }}>Platform Capabilities</div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px,4vw,52px)', fontWeight: 800, letterSpacing: '-2px', marginBottom: '48px' }}>Built for institutional depth.</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1px', background: 'var(--border)', border: '1px solid var(--border)', borderRadius: '16px', overflow: 'hidden' }}>
          {FEATURES.map(f => (
            <div key={f.title}
              style={{ background: 'var(--surface)', padding: '32px', transition: 'background 0.2s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'var(--surface)'}>
              <div style={{ fontSize: '28px', marginBottom: '16px' }}>{f.icon}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>{f.title}</div>
              <div style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: 1.65 }}>{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Scenario Simulation ── */}
      <section style={{ padding: '80px 48px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '40px', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '11px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--accent2)', fontWeight: 600, marginBottom: '12px' }}>Scenario Simulation Engine</div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(28px,3.5vw,44px)', fontWeight: 800, letterSpacing: '-1.5px', marginBottom: '16px' }}>Five futures.<br />Not one prediction.</h2>
            <p style={{ color: 'var(--muted)', fontSize: '15px', lineHeight: 1.7, marginBottom: '24px' }}>
              AlphaForage never predicts the future. Instead, it generates calibrated probabilistic scenarios — Bull, Base, Bear, Structural Breakout, and Black Swan — each with explicit assumptions and catalysts.
            </p>
            <p style={{ color: 'var(--muted)', fontSize: '15px', lineHeight: 1.7 }}>
              Probabilities update as new evidence arrives. The scenarios you see today reflect today's evidence.
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {SCENARIOS.map(s => (
              <div key={s.name}
                style={{ background: 'var(--surface)', border: `1px solid ${s.color}33`, borderRadius: '12px', padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: s.color, boxShadow: `0 0 8px ${s.color}88`, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '2px' }}>{s.name}</div>
                  <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{s.note}</div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', fontWeight: 500, color: s.color }}>{s.upside}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--muted)' }}>{s.prob}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Sponsor section ── */}
      <section style={{ padding: '64px 48px', maxWidth: '1200px', margin: '0 auto', borderTop: '1px solid var(--border)' }}>
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div style={{ fontSize: '11px', letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600, marginBottom: '8px' }}>Powered By</div>
          <p style={{ color: 'var(--muted)', fontSize: '14px' }}>Deeply integrated sponsor technologies — not just logos</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          {[
            { name: 'You.com', desc: 'Primary research engine. Every workspace searches You.com for live intelligence.', color: '#00cba9' },
            { name: 'Tavily',  desc: 'Cross-validation layer. AI answers that verify or challenge You.com findings.', color: '#a29bfe' },
            { name: 'InsForge', desc: 'Infrastructure platform. Agent services, API hosting, and model gateway.', color: '#fdcb6e' },
            { name: 'Nebius',  desc: 'GPU inference cluster. Larger reasoning models run on Nebius infrastructure.', color: '#fd79a8' },
          ].map(s => (
            <div key={s.name}
              style={{ background: 'var(--surface)', border: `1px solid ${s.color}22`, borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '15px', fontWeight: 700, color: s.color, marginBottom: '8px' }}>{s.name}</div>
              <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ padding: '120px 24px', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
          <div style={{ position: 'absolute', width: '600px', height: '400px', borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(108,92,231,0.2), transparent 70%)', top: '50%', left: '50%', transform: 'translate(-50%,-50%)' }} />
        </div>
        <div style={{ position: 'relative' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(40px,5vw,72px)', fontWeight: 800, letterSpacing: '-2.5px', lineHeight: 1.0, marginBottom: '20px' }}>
            Your first workspace<br />
            <span style={{ background: 'linear-gradient(135deg, var(--accent2), #e879f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              takes 30 seconds.
            </span>
          </h2>
          <p style={{ fontSize: '17px', color: 'var(--muted)', marginBottom: '40px', fontWeight: 300 }}>
            Name your thesis. Add tickers. Watch 12 agents research it live.
          </p>
          <button onClick={() => navigate('/app/workspaces')}
            style={{ padding: '18px 44px', borderRadius: '14px', border: 'none', background: 'linear-gradient(135deg, var(--accent), #8b5cf6)', color: '#fff', fontSize: '16px', fontWeight: 600, cursor: 'pointer', boxShadow: '0 6px 32px rgba(108,92,231,0.45)', transition: 'all 0.25s' }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 10px 40px rgba(108,92,231,0.6)' }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 6px 32px rgba(108,92,231,0.45)' }}>
            Open AlphaForage →
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer style={{ borderTop: '1px solid var(--border)', padding: '48px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ width: '24px', height: '24px', background: 'linear-gradient(135deg, var(--accent), var(--accent2))', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', color: '#fff', fontWeight: 800 }}>α</div>
          AlphaForage v2.0
        </div>
        <div style={{ display: 'flex', gap: '32px', fontSize: '13px', color: 'var(--muted)' }}>
          <span>Deployed on InsForge</span>
          <span>AI via Nebius GPU Cluster</span>
          <span>Research: You.com + Tavily</span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--dim)' }}>
          Market data by Polygon.io & Finnhub. AI analysis is not financial advice.
        </div>
      </footer>
    </div>
  )
}
