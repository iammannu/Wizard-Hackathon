import React, { useState, useEffect } from 'react'
import { BarChart2, Loader2, Briefcase, Calendar } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useResearchStore } from '../store/index.js'
import useIsMobile from '../lib/useIsMobile.js'

// ── Shared styles ──────────────────────────────────────────────────────
const S = {
  topbar: { height:'52px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 28px', gap:'12px', background:'var(--surface)', flexShrink:0 },
  topbarTitle: { fontFamily:'var(--font-display)', fontSize:'15px', fontWeight:600, flex:1 },
  badge: { fontSize:'10px', padding:'3px 10px', borderRadius:'20px', background:'rgba(108,92,231,0.12)', color:'var(--accent2)', border:'1px solid rgba(108,92,231,0.22)', fontFamily:'var(--font-mono)' },
  sectionTitle: { fontFamily:'var(--font-display)', fontSize:'15px', fontWeight:600, marginBottom:'14px' },
  mCard: { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'12px', padding:'16px', cursor:'pointer', transition:'border-color 0.15s' },
  mCardTicker: { fontFamily:'var(--font-mono)', fontSize:'11px', color:'var(--muted)', marginBottom:'6px' },
  mCardPrice: { fontFamily:'var(--font-display)', fontSize:'22px', fontWeight:700, marginBottom:'4px' },
  mCardChange: { fontFamily:'var(--font-mono)', fontSize:'12px', fontWeight:500 },
  input: { background:'var(--surface2)', border:'1px solid var(--border2)', borderRadius:'10px', padding:'11px 16px', color:'var(--text)', fontSize:'14px', outline:'none', width:'160px' },
  modeBtn: { padding:'10px 16px', borderRadius:'9px', border:'1px solid var(--border2)', background:'transparent', color:'var(--muted)', fontSize:'13px', cursor:'pointer', transition:'all 0.15s' },
  modeBtnActive: { background:'var(--accent)', color:'#fff', border:'1px solid var(--accent)' },
  fetchBtn: { padding:'10px 20px', borderRadius:'9px', border:'1px solid var(--border2)', background:'var(--surface2)', color:'var(--text)', fontSize:'13px', cursor:'pointer', transition:'all 0.15s' },
  dataItem: { padding:'14px', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'10px' },
  dataLabel: { fontSize:'10px', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'6px' },
  dataVal: { fontFamily:'var(--font-mono)', fontSize:'15px', fontWeight:500 },
  sumCard: { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'12px', padding:'18px' },
  sumLabel: { fontSize:'11px', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'8px' },
  sumVal: { fontFamily:'var(--font-display)', fontSize:'26px', fontWeight:700 },
  ghostBtn: { padding:'8px 16px', borderRadius:'8px', border:'1px solid var(--border2)', background:'transparent', color:'var(--muted)', fontSize:'12px', cursor:'pointer' },
}

// ── Market page ────────────────────────────────────────────────────────
const WATCHLIST = ['AAPL','MSFT','NVDA','GOOGL','META','TSLA']

export function Market() {
  const [quotes, setQuotes] = useState({})
  const [ticker, setTicker] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('quote')

  useEffect(() => {
    WATCHLIST.forEach(async t => {
      try { const d = await api.quote(t); setQuotes(q => ({ ...q, [t]: d })) } catch {}
    })
  }, [])

  async function fetchDetail() {
    const t = ticker.trim().toUpperCase()
    if (!t) return
    setLoading(true); setDetail(null)
    try {
      const d = mode === 'quote' ? await api.quote(t) : await api.fundamentals(t)
      setDetail({ ...d, _ticker: t, _mode: mode })
    } catch (err) { setDetail({ _error: err.message }) }
    setLoading(false)
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <div style={S.topbar}>
        <BarChart2 size={16} style={{ color:'var(--accent2)' }} />
        <span style={S.topbarTitle}>Market Data</span>
        <span style={S.badge}>Polygon · Finnhub</span>
      </div>
      <div style={{ flex:1, overflowY:'auto', padding:'28px' }}>
        <div style={S.sectionTitle}>Watchlist</div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(160px,1fr))', gap:'10px', marginBottom:'32px' }}>
          {WATCHLIST.map(t => {
            const d = quotes[t]
            const up = d ? (d.change_pct ?? 0) >= 0 : null
            return (
              <div key={t} style={S.mCard} onClick={() => { setTicker(t); setMode('quote') }}>
                <div style={S.mCardTicker}>{t}</div>
                <div style={{ ...S.mCardPrice, color: d ? 'var(--text)' : 'var(--muted)' }}>
                  {d ? '$' + (d.price ?? 0).toFixed(2) : '—'}
                </div>
                {d && (
                  <div style={{ ...S.mCardChange, color: up ? 'var(--bull)' : 'var(--bear)' }}>
                    {up ? '▲' : '▼'} {Math.abs(d.change_pct ?? 0).toFixed(2)}%
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div style={S.sectionTitle}>Lookup</div>
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'14px', padding:'24px' }}>
          <div style={{ display:'flex', gap:'10px', marginBottom:'16px', flexWrap:'wrap' }}>
            <input
              style={S.input}
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && fetchDetail()}
              placeholder="AAPL"
            />
            {['quote','fundamentals'].map(m => (
              <button key={m} style={{ ...S.modeBtn, ...(mode===m ? S.modeBtnActive : {}) }} onClick={() => setMode(m)}>
                {m.charAt(0).toUpperCase()+m.slice(1)}
              </button>
            ))}
            <button style={S.fetchBtn} onClick={fetchDetail} disabled={!ticker.trim() || loading}>
              {loading ? <Loader2 size={13} style={{ animation:'spin 0.7s linear infinite' }} /> : 'Fetch'}
            </button>
          </div>

          {detail && !detail._error && detail._mode === 'quote' && <QuoteDetail d={detail} />}
          {detail && !detail._error && detail._mode === 'fundamentals' && <FundamentalsDetail d={detail} />}
          {detail?._error && <div style={{ color:'var(--bear)', fontSize:'13px', padding:'12px 0' }}>Error: {detail._error}</div>}
        </div>
      </div>
    </div>
  )
}

function QuoteDetail({ d }) {
  const up = (d.change_pct ?? 0) >= 0
  const isMobile = useIsMobile()
  return (
    <div style={{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:'12px', padding:'20px' }}>
      <div style={{ display:'flex', alignItems:'baseline', gap:'14px', marginBottom:'20px', flexWrap:'wrap' }}>
        <span style={{ fontFamily:'var(--font-display)', fontSize:'26px', fontWeight:700 }}>{d._ticker}</span>
        <span style={{ fontFamily:'var(--font-mono)', fontSize:'28px', fontWeight:500 }}>${(d.price??0).toFixed(2)}</span>
        <span style={{ fontFamily:'var(--font-mono)', fontSize:'14px', color: up?'var(--bull)':'var(--bear)' }}>
          {up?'▲':'▼'} ${Math.abs(d.change??0).toFixed(2)} ({Math.abs(d.change_pct??0).toFixed(2)}%)
        </span>
      </div>
      <div style={{ display:'grid', gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : 'repeat(4,1fr)', gap:'12px' }}>
        {[['Open','$'+(d.open??0).toFixed(2)],['High','$'+(d.high??0).toFixed(2)],['Low','$'+(d.low??0).toFixed(2)],['Volume',(d.volume??0).toLocaleString()]].map(([k,v]) => (
          <div key={k} style={S.dataItem}><div style={S.dataLabel}>{k}</div><div style={S.dataVal}>{v}</div></div>
        ))}
      </div>
    </div>
  )
}

function FundamentalsDetail({ d }) {
  const isMobile = useIsMobile()
  const rows = [
    ['P/E Ratio', d.pe_ratio?.toFixed(1)],
    ['P/S Ratio', d.ps_ratio?.toFixed(1)],
    ['EV/EBITDA', d.ev_ebitda?.toFixed(1)],
    ['Gross Margin', d.gross_margin != null ? d.gross_margin.toFixed(1)+'%' : null],
    ['Net Margin', d.net_margin != null ? d.net_margin.toFixed(1)+'%' : null],
    ['ROE', d.roe != null ? d.roe.toFixed(1)+'%' : null],
    ['Rev Growth', d.revenue_growth_yoy != null ? d.revenue_growth_yoy.toFixed(1)+'%' : null],
    ['Beta', d.beta?.toFixed(2)],
    ['D/E Ratio', d.debt_to_equity?.toFixed(2)],
    ['52W High', d['52w_high'] ? '$'+d['52w_high'].toFixed(2) : null],
    ['52W Low',  d['52w_low']  ? '$'+d['52w_low'].toFixed(2)  : null],
    ['Current Ratio', d.current_ratio?.toFixed(2)],
  ].filter(([, v]) => v != null)

  return (
    <div style={{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:'12px', padding:'20px' }}>
      <div style={{ fontFamily:'var(--font-display)', fontSize:'18px', fontWeight:600, marginBottom:'16px' }}>{d._ticker} — Fundamentals</div>
      <div style={{ display:'grid', gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : 'repeat(4,1fr)', gap:'10px' }}>
        {rows.map(([k,v]) => (
          <div key={k} style={S.dataItem}><div style={S.dataLabel}>{k}</div><div style={S.dataVal}>{v}</div></div>
        ))}
      </div>
    </div>
  )
}

// ── Portfolio page ─────────────────────────────────────────────────────
const POSITIONS = [
  { ticker:'AAPL', shares:10, avgCost:180, name:'Apple Inc.' },
  { ticker:'MSFT', shares:5,  avgCost:380, name:'Microsoft Corp.' },
  { ticker:'NVDA', shares:3,  avgCost:500, name:'NVIDIA Corp.' },
]

export function Portfolio() {
  const [quotes, setQuotes] = useState({})
  const sendQuery = useResearchStore(s => s.sendQuery)
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  useEffect(() => {
    POSITIONS.forEach(async p => {
      try { const d = await api.quote(p.ticker); setQuotes(q => ({ ...q, [p.ticker]: d })) } catch {}
    })
  }, [])

  const rows = POSITIONS.map(p => {
    const d = quotes[p.ticker]
    const price  = d?.price ?? 0
    const value  = price * p.shares
    const cost   = p.avgCost * p.shares
    const pnl    = value - cost
    const pnlPct = cost > 0 ? pnl / cost * 100 : 0
    return { ...p, price, value, pnl, pnlPct, up: pnl >= 0, chgPct: d?.change_pct ?? 0 }
  })

  const totalValue = rows.reduce((a, r) => a + r.value, 0)
  const totalCost  = rows.reduce((a, r) => a + r.avgCost * r.shares, 0)
  const totalPnl   = totalValue - totalCost
  const best       = [...rows].sort((a, b) => b.chgPct - a.chgPct)[0]

  function goResearch(ticker) {
    sendQuery(`Analyze ${ticker}`)
    navigate('/app/research')
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <div style={S.topbar}>
        <Briefcase size={16} style={{ color:'var(--accent2)' }} />
        <span style={S.topbarTitle}>Portfolio</span>
        <button style={S.ghostBtn}>+ Add Position</button>
      </div>
      <div style={{ flex:1, overflowY:'auto', padding:'28px' }}>
        {/* Summary cards */}
        <div style={{ display:'grid', gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : 'repeat(4,1fr)', gap:'12px', marginBottom:'28px' }}>
          {[
            { label:'Total Value',  val:'$'+totalValue.toFixed(0), sub: (totalPnl>=0?'+':'-')+'$'+Math.abs(totalPnl).toFixed(0), color:'var(--text)' },
            { label:'Total P&L',    val:(totalPnl>=0?'+':'-')+'$'+Math.abs(totalPnl).toFixed(0), sub:(totalPnl/Math.max(totalCost,1)*100).toFixed(1)+'%', color:totalPnl>=0?'var(--bull)':'var(--bear)' },
            { label:'Positions',    val:POSITIONS.length, sub:'stocks held', color:'var(--text)' },
            { label:'Best Today',   val:best?(best.chgPct>=0?'+':'')+best.chgPct.toFixed(2)+'%':'—', sub:best?.ticker??'', color:(best?.chgPct??0)>=0?'var(--bull)':'var(--bear)' },
          ].map(({ label, val, sub, color }) => (
            <div key={label} style={S.sumCard}>
              <div style={S.sumLabel}>{label}</div>
              <div style={{ ...S.sumVal, color }}>{val}</div>
              <div style={{ fontSize:'11px', color:'var(--muted)', fontFamily:'var(--font-mono)', marginTop:'4px' }}>{sub}</div>
            </div>
          ))}
        </div>

        {/* Positions table */}
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'14px', overflow:'hidden' }}>
          <div style={{ padding:'16px 20px', borderBottom:'1px solid var(--border)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <span style={{ fontFamily:'var(--font-display)', fontSize:'15px', fontWeight:600 }}>Positions</span>
            <span style={{ fontSize:'12px', color:'var(--muted)' }}>Click any row for AI research</span>
          </div>
          <div style={{ overflowX: isMobile ? 'auto' : undefined }}>
          <table style={{ width:'100%', minWidth: isMobile ? '640px' : undefined, borderCollapse:'collapse', fontSize:'13px' }}>
            <thead>
              <tr>
                {['Ticker','Name','Shares','Avg Cost','Price','Value','P&L','P&L %',''].map(h => (
                  <th key={h} style={{ padding:'10px 16px', textAlign:'left', fontSize:'10px', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', borderBottom:'1px solid var(--border)', fontWeight:500, background:'var(--surface2)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.ticker} style={{ cursor:'pointer' }} onClick={() => goResearch(r.ticker)}>
                  {[
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontWeight:500, color:'var(--accent2)', borderBottom:'1px solid var(--border)' }}>{r.ticker}</td>,
                    <td style={{ padding:'13px 16px', borderBottom:'1px solid var(--border)' }}>{r.name}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:'var(--muted)', borderBottom:'1px solid var(--border)' }}>{r.shares}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:'var(--muted)', borderBottom:'1px solid var(--border)' }}>${r.avgCost}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:'var(--muted)', borderBottom:'1px solid var(--border)' }}>{r.price ? '$'+r.price.toFixed(2) : '—'}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:'var(--muted)', borderBottom:'1px solid var(--border)' }}>{r.value ? '$'+r.value.toFixed(0) : '—'}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:r.up?'var(--bull)':'var(--bear)', borderBottom:'1px solid var(--border)' }}>{r.up?'+':'-'}${Math.abs(r.pnl).toFixed(0)}</td>,
                    <td style={{ padding:'13px 16px', fontFamily:'var(--font-mono)', fontSize:'12px', color:r.up?'var(--bull)':'var(--bear)', borderBottom:'1px solid var(--border)' }}>{r.up?'+':''}{r.pnlPct.toFixed(1)}%</td>,
                    <td style={{ padding:'13px 16px', borderBottom:'1px solid var(--border)' }}>
                      <button style={{ padding:'6px 12px', borderRadius:'7px', border:'1px solid rgba(108,92,231,0.2)', background:'rgba(108,92,231,0.07)', color:'var(--accent2)', fontSize:'11px', cursor:'pointer' }}
                        onClick={e => { e.stopPropagation(); goResearch(r.ticker) }}>
                        Research →
                      </button>
                    </td>,
                  ]}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Events page ────────────────────────────────────────────────────────
const EVENTS = [
  { date:'May 28', type:'Earnings', ticker:'NVDA', color:'var(--accent)', desc:'NVIDIA Q1 FY2026 — Consensus EPS $0.89. Watch data center revenue guidance and Blackwell ramp.' },
  { date:'May 29', type:'Fed',      ticker:'FOMC', color:'var(--warn)',   desc:'FOMC meeting minutes. Markets pricing 2 cuts in 2026. Watch for tone shift on inflation timeline.' },
  { date:'Jun 4',  type:'Earnings', ticker:'AAPL', color:'var(--accent)', desc:'Apple Q2 FY2026 — Services revenue and Vision Pro adoption are the key metrics.' },
  { date:'Jun 11', type:'Data',     ticker:'CPI',  color:'var(--bull)',   desc:'May CPI report. YoY expected at 3.1%. Core CPI watch for Fed rate-cut trajectory.' },
  { date:'Jun 18', type:'Earnings', ticker:'MSFT', color:'var(--accent)', desc:'Microsoft Q4 FY2026 — Azure growth and Copilot monetization are key focus areas.' },
  { date:'Jun 25', type:'Data',     ticker:'PCE',  color:'var(--bull)',   desc:"Core PCE deflator — Fed's preferred inflation measure. Critical for rate-cut timing." },
]

export function Events() {
  const sendQuery = useResearchStore(s => s.sendQuery)
  const navigate = useNavigate()

  function analyze(ev) {
    sendQuery(`Analyze the upcoming ${ev.ticker} ${ev.type.toLowerCase()} event and its market impact`)
    navigate('/app/research')
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}>
      <div style={S.topbar}>
        <Calendar size={16} style={{ color:'var(--accent2)' }} />
        <span style={S.topbarTitle}>Upcoming Events</span>
        <span style={S.badge}>Earnings · Fed · Data</span>
      </div>
      <div style={{ flex:1, overflowY:'auto', padding:'28px' }}>
        <p style={{ color:'var(--muted)', fontSize:'13px', marginBottom:'24px' }}>
          Key earnings, macro data, and Fed events — one-click AI impact analysis.
        </p>
        <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
          {EVENTS.map(ev => (
            <div key={ev.ticker+ev.date}
              style={{ display:'flex', gap:'16px', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'12px', padding:'18px 20px', cursor:'pointer', transition:'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border2)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
              onClick={() => analyze(ev)}
            >
              <div style={{ width:'52px', textAlign:'center', flexShrink:0 }}>
                <div style={{ fontFamily:'var(--font-display)', fontSize:'22px', fontWeight:700, lineHeight:1 }}>{ev.date.split(' ')[1]}</div>
                <div style={{ fontSize:'10px', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginTop:'2px' }}>{ev.date.split(' ')[0]}</div>
              </div>
              <div style={{ width:'1px', background:'var(--border)', flexShrink:0 }} />
              <div style={{ flex:1 }}>
                <div style={{ display:'flex', alignItems:'center', gap:'10px', marginBottom:'6px' }}>
                  <span style={{ fontSize:'10px', padding:'2px 8px', borderRadius:'4px', fontWeight:600, textTransform:'uppercase', background:ev.color+'22', color:ev.color }}>{ev.type}</span>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:'13px', fontWeight:500, color:'var(--accent2)' }}>{ev.ticker}</span>
                </div>
                <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.55 }}>{ev.desc}</div>
              </div>
              <button
                style={{ alignSelf:'center', flexShrink:0, padding:'7px 14px', borderRadius:'7px', border:'1px solid rgba(108,92,231,0.2)', background:'rgba(108,92,231,0.07)', color:'var(--accent2)', fontSize:'11px', cursor:'pointer' }}
                onClick={e => { e.stopPropagation(); analyze(ev) }}
              >
                Analyze →
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// Landing page moved to Landing.jsx
function _LandingLegacy_unused() {
  const navigate = useNavigate()

  return (
    <div style={{ minHeight:'100vh', overflowX:'hidden' }}>
      {/* Nav */}
      <nav style={{ position:'fixed', top:0, left:0, right:0, zIndex:100, height:'64px', display:'flex', alignItems:'center', padding:'0 48px', gap:'32px', background:'rgba(7,7,13,0.88)', backdropFilter:'blur(16px)', borderBottom:'1px solid var(--border)' }}>
        <div style={{ fontFamily:'var(--font-display)', fontSize:'18px', fontWeight:700, display:'flex', alignItems:'center', gap:'9px', cursor:'pointer' }}>
          <div style={{ width:'28px', height:'28px', background:'var(--accent)', borderRadius:'7px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:'14px', fontWeight:800, color:'#fff' }}>α</div>
          AlphaForage
        </div>
        <div style={{ display:'flex', gap:'28px', marginLeft:'auto', alignItems:'center' }}>
          {['Research','Screener','Portfolio'].map(l => (
            <span key={l} style={{ fontSize:'14px', color:'var(--muted)', cursor:'pointer', transition:'color 0.15s' }}
              onMouseEnter={e => e.target.style.color='var(--text)'}
              onMouseLeave={e => e.target.style.color='var(--muted)'}
              onClick={() => navigate(`/app/${l.toLowerCase()}`)}>
              {l}
            </span>
          ))}
          <button onClick={() => navigate('/app')}
            style={{ marginLeft:'12px', padding:'9px 20px', borderRadius:'9px', border:'none', background:'var(--accent)', color:'#fff', fontSize:'13px', fontWeight:500, cursor:'pointer', transition:'all 0.2s' }}
            onMouseEnter={e => e.currentTarget.style.background='var(--accent2)'}
            onMouseLeave={e => e.currentTarget.style.background='var(--accent)'}>
            Launch App →
          </button>
        </div>
      </nav>

      {/* Hero */}
      <div style={{ minHeight:'100vh', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', textAlign:'center', padding:'120px 24px 80px', position:'relative', overflow:'hidden' }}>
        <div style={{ position:'absolute', width:'700px', height:'700px', borderRadius:'50%', background:'radial-gradient(ellipse,rgba(108,92,231,0.18) 0%,transparent 70%)', top:'50%', left:'50%', transform:'translate(-50%,-55%)', pointerEvents:'none' }} />
        <div style={{ display:'inline-flex', alignItems:'center', gap:'8px', border:'1px solid rgba(108,92,231,0.3)', background:'rgba(108,92,231,0.08)', padding:'6px 14px', borderRadius:'100px', fontSize:'12px', color:'var(--accent2)', fontWeight:500, marginBottom:'28px', position:'relative' }}>
          <span style={{ width:'6px', height:'6px', borderRadius:'50%', background:'var(--bull)', display:'inline-block', animation:'pulse 2s infinite' }} />
          7-Agent AI · Real Market Data · SSE Streaming
        </div>
        <h1 style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontSize:'clamp(52px,7vw,96px)', fontWeight:800, lineHeight:1.0, letterSpacing:'-3px', maxWidth:'960px', marginBottom:'28px', position:'relative' }}>
        Institutional research.<br/><span style={{ color:'var(--accent2)' }}>Finally democratized.</span>
        </h1>
        <p style={{ fontSize:'18px', color:'var(--muted)', maxWidth:'500px', lineHeight:1.7, marginBottom:'44px', fontWeight:300, position:'relative' }}>
          Multi-agent AI runs technical, fundamental, sentiment, valuation, risk and macro analysis in parallel. Hedge-fund-grade research in seconds.
        </p>
        <div style={{ display:'flex', gap:'14px', marginBottom:'64px', position:'relative', flexWrap:'wrap', justifyContent:'center' }}>
          <button onClick={() => navigate('/app')}
            style={{ padding:'15px 32px', borderRadius:'12px', border:'none', background:'var(--accent)', color:'#fff', fontSize:'15px', fontWeight:500, cursor:'pointer', transition:'all 0.2s' }}
            onMouseEnter={e => { e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.background='var(--accent2)' }}
            onMouseLeave={e => { e.currentTarget.style.transform='none'; e.currentTarget.style.background='var(--accent)' }}>
            Start Researching →
          </button>
          <button onClick={() => navigate('/app/screener')}
            style={{ padding:'14px 28px', borderRadius:'12px', border:'1px solid var(--border2)', background:'transparent', color:'var(--text)', fontSize:'15px', cursor:'pointer', transition:'all 0.2s' }}
            onMouseEnter={e => e.currentTarget.style.background='var(--surface2)'}
            onMouseLeave={e => e.currentTarget.style.background='transparent'}>
            Try Screener
          </button>
        </div>
        <div style={{ display:'flex', gap:'48px', justifyContent:'center', position:'relative', flexWrap:'wrap' }}>
          {[['7','AI Agents'],['<15s','Full Analysis'],['100%','Real Data'],['0','Black Boxes']].map(([n,l]) => (
            <div key={l} style={{ textAlign:'center' }}>
              <div style={{ fontFamily:'var(--font-display)', fontSize:'32px', fontWeight:700, color:'var(--accent2)' }}>{n}</div>
              <div style={{ fontSize:'13px', color:'var(--muted)', marginTop:'2px' }}>{l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Features grid */}
      <div style={{ padding:'80px 48px', maxWidth:'1100px', margin:'0 auto' }}>
        <div style={{ fontSize:'11px', letterSpacing:'1.5px', textTransform:'uppercase', color:'var(--accent2)', fontWeight:600, marginBottom:'14px' }}>What AlphaForage does</div>
        <h2 style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontSize:'clamp(36px,4vw,58px)', fontWeight:800, letterSpacing:'-1.5px', marginBottom:'48px' }}>Every angle. One platform.</h2>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'1px', background:'var(--border)', border:'1px solid var(--border)', borderRadius:'16px', overflow:'hidden' }}>
          {[
            ['📡','Live Market Data','Real-time quotes, OHLCV candles, and news from Polygon.io and Finnhub.'],
            ['🧠','7-Agent AI Research','Technical, fundamental, sentiment, valuation, risk, macro — all parallel via SSE.'],
            ['⚖️','Bull & Bear Duality','Every analysis forces both cases with probabilities and invalidation conditions.'],
            ['📊','Calibrated Confidence','0–1 confidence score weighted by agent reliability, penalized for conflicts.'],
            ['🔍','NL Screener','Describe what you want in plain English — translated to precise filters instantly.'],
            ['💼','Portfolio Intelligence','Track positions, see live P&L, one-click into AI analysis per holding.'],
          ].map(([icon, title, desc]) => (
            <div key={title}
              style={{ background:'var(--surface)', padding:'32px', transition:'background 0.2s', cursor:'default' }}
              onMouseEnter={e => e.currentTarget.style.background='var(--surface2)'}
              onMouseLeave={e => e.currentTarget.style.background='var(--surface)'}>
              <div style={{ fontSize:'26px', marginBottom:'16px' }}>{icon}</div>
              <div style={{ fontFamily:'var(--font-display)', fontSize:'16px', fontWeight:600, marginBottom:'8px' }}>{title}</div>
              <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.65 }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>


      {/* HOW IT WORKS — Bento */}
      <div style={{ padding:'80px 48px', maxWidth:'1100px', margin:'0 auto' }}>
        <div style={{ fontSize:'11px', letterSpacing:'1.5px', textTransform:'uppercase', color:'var(--accent2)', fontWeight:600, marginBottom:'14px' }}>How it works</div>
        <h2 style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'clamp(36px,4vw,56px)', fontWeight:800, letterSpacing:'-1.5px', marginBottom:'56px' }}>Research that thinks<br/>while you read.</h2>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(12,1fr)', gap:'12px' }}>

          {/* Agent pipeline — span 5 */}
          <div style={{ gridColumn:'span 5', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'16px', padding:'28px' }}>
            <div style={{ fontSize:'10px', letterSpacing:'1px', textTransform:'uppercase', color:'var(--muted)', fontWeight:600, marginBottom:'10px' }}>Multi-agent pipeline</div>
            <div style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'20px', fontWeight:700, letterSpacing:'-0.5px', marginBottom:'8px' }}>7 specialists. One answer.</div>
            <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.6, marginBottom:'20px' }}>Agents activate in parallel, stream results live, and a supervisor synthesizes conflicts.</div>
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              {[
                { n:'Technical',   s:'bullish', c:'82%' },
                { n:'Fundamental', s:'bullish', c:'85%' },
                { n:'Sentiment',   s:'neutral', c:'61%' },
                { n:'Valuation',   s:'bearish', c:'70%' },
                { n:'Risk',        s:'neutral', c:'74%' },
              ].map(a => (
                <div key={a.n} style={{ display:'flex', alignItems:'center', gap:'10px', padding:'8px 12px', borderRadius:'8px', border:'1px solid var(--border)', background: a.s==='bullish'?'rgba(0,203,169,0.05)':a.s==='bearish'?'rgba(255,107,107,0.04)':'var(--surface2)', borderColor: a.s==='bullish'?'rgba(0,203,169,0.22)':a.s==='bearish'?'rgba(255,107,107,0.2)':'var(--border)' }}>
                  <span style={{ fontSize:'12px', fontWeight:500, flex:1 }}>{a.n}</span>
                  <span style={{ fontSize:'9px', padding:'2px 6px', borderRadius:'4px', fontWeight:600, textTransform:'uppercase', background: a.s==='bullish'?'rgba(0,203,169,0.12)':a.s==='bearish'?'rgba(255,107,107,0.12)':'rgba(255,255,255,0.05)', color: a.s==='bullish'?'var(--bull)':a.s==='bearish'?'var(--bear)':'var(--muted)' }}>{a.s}</span>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:'10px', color:'var(--muted)' }}>{a.c}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Confidence — span 7 */}
          <div style={{ gridColumn:'span 7', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'16px', padding:'28px' }}>
            <div style={{ fontSize:'10px', letterSpacing:'1px', textTransform:'uppercase', color:'var(--muted)', fontWeight:600, marginBottom:'10px' }}>Confidence scoring</div>
            <div style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'20px', fontWeight:700, letterSpacing:'-0.5px', marginBottom:'8px' }}>Never guess how sure the AI is.</div>
            <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.6, marginBottom:'20px' }}>Weighted by agent reliability, adjusted for signal conflicts.</div>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:'8px' }}>
              <span style={{ fontSize:'13px', color:'var(--muted)' }}>Overall confidence</span>
              <span style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'32px', fontWeight:800, color:'var(--bull)' }}>76%</span>
            </div>
            <div style={{ height:'6px', background:'var(--dim)', borderRadius:'3px', overflow:'hidden', marginBottom:'16px' }}>
              <div style={{ height:'100%', width:'76%', background:'linear-gradient(90deg,var(--bull),var(--accent2))', borderRadius:'3px' }} />
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'10px' }}>
              {[['79%','Data quality','var(--bull)'],['62%','Signal agreement','var(--warn)'],['84%','Retrieval','var(--bull)']].map(([v,k,c]) => (
                <div key={k} style={{ textAlign:'center', padding:'12px', background:'var(--surface2)', borderRadius:'9px', border:'1px solid var(--border)' }}>
                  <div style={{ fontFamily:'var(--font-mono)', fontSize:'15px', fontWeight:500, color:c }}>{v}</div>
                  <div style={{ fontSize:'11px', color:'var(--muted)', marginTop:'3px' }}>{k}</div>
                </div>
              ))}
            </div>
          </div>

          {/* NL Screener — span 7 */}
          <div style={{ gridColumn:'span 7', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'16px', padding:'28px' }}>
            <div style={{ fontSize:'10px', letterSpacing:'1px', textTransform:'uppercase', color:'var(--muted)', fontWeight:600, marginBottom:'10px' }}>Natural language screener</div>
            <div style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'20px', fontWeight:700, letterSpacing:'-0.5px', marginBottom:'8px' }}>Plain English → instant shortlist.</div>
            <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.6, marginBottom:'16px' }}>No filter menus. No dropdowns. Just describe what you want.</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:'6px', marginBottom:'16px' }}>
              {['Profitable tech, revenue growth >15%','Low P/E healthcare stocks','High ROE, low debt','Momentum plays with RSI <70'].map(q => (
                <span key={q} style={{ padding:'5px 12px', borderRadius:'100px', background:'rgba(108,92,231,0.1)', border:'1px solid rgba(108,92,231,0.2)', color:'var(--accent2)', fontSize:'11px', cursor:'pointer' }}>{q}</span>
              ))}
            </div>
            {[['NVDA','Technology','P/E 50','+122% growth','var(--bull)'],['MSFT','Technology','P/E 32','+16% growth','var(--bull)'],['META','Comm. Svcs','P/E 24','+22% growth','var(--bull)']].map(([t,s,pe,g,c]) => (
              <div key={t} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 0', borderBottom:'1px solid var(--border)', fontSize:'12px' }}>
                <span style={{ fontFamily:'var(--font-mono)', fontWeight:500, color:'var(--accent2)', width:'56px' }}>{t}</span>
                <span style={{ color:'var(--muted)', flex:1 }}>{s}</span>
                <span style={{ color:'var(--muted)', width:'56px', textAlign:'right' }}>{pe}</span>
                <span style={{ color:c, width:'96px', textAlign:'right', fontFamily:'var(--font-mono)', fontSize:'11px' }}>{g}</span>
              </div>
            ))}
          </div>

          {/* Bull Bear — span 5 */}
          <div style={{ gridColumn:'span 5', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'16px', padding:'28px' }}>
            <div style={{ fontSize:'10px', letterSpacing:'1px', textTransform:'uppercase', color:'var(--muted)', fontWeight:600, marginBottom:'10px' }}>Duality by design</div>
            <div style={{ fontFamily:"'Plus Jakarta Sans', sans-serif", fontSize:'20px', fontWeight:700, letterSpacing:'-0.5px', marginBottom:'8px' }}>Both sides. Always.</div>
            <div style={{ fontSize:'13px', color:'var(--muted)', lineHeight:1.6, marginBottom:'20px' }}>Every analysis forces bull and bear cases. Never one-sided conviction.</div>
            <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
              <div style={{ background:'rgba(0,203,169,0.06)', border:'1px solid rgba(0,203,169,0.2)', borderRadius:'11px', padding:'16px' }}>
                <div style={{ display:'flex', alignItems:'center', marginBottom:'8px' }}>
                  <span style={{ fontSize:'10px', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.5px', color:'var(--bull)' }}>▲ Bull Case</span>
                  <span style={{ marginLeft:'auto', fontFamily:'var(--font-mono)', fontSize:'11px', color:'rgba(0,203,169,0.6)' }}>72%</span>
                </div>
                <div style={{ fontSize:'12px', color:'var(--muted)', lineHeight:1.55 }}>AI infrastructure supercycle has years of runway. NVIDIA's CUDA moat is nearly impossible to replicate.</div>
              </div>
              <div style={{ background:'rgba(255,107,107,0.06)', border:'1px solid rgba(255,107,107,0.2)', borderRadius:'11px', padding:'16px' }}>
                <div style={{ display:'flex', alignItems:'center', marginBottom:'8px' }}>
                  <span style={{ fontSize:'10px', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.5px', color:'var(--bear)' }}>▼ Bear Case</span>
                  <span style={{ marginLeft:'auto', fontFamily:'var(--font-mono)', fontSize:'11px', color:'rgba(255,107,107,0.6)' }}>28%</span>
                </div>
                <div style={{ fontSize:'12px', color:'var(--muted)', lineHeight:1.55 }}>P/E of 50 leaves no margin for error. Any capex slowdown from hyperscalers would compress multiples rapidly.</div>
              </div>
            </div>
          </div>

        </div>
      </div>
      {/* CTA */}
      <div style={{ padding:'120px 24px', textAlign:'center', position:'relative', overflow:'hidden' }}>
        <div style={{ position:'absolute', width:'600px', height:'400px', borderRadius:'50%', background:'radial-gradient(ellipse,rgba(108,92,231,0.2),transparent 70%)', top:'50%', left:'50%', transform:'translate(-50%,-50%)', pointerEvents:'none' }} />
        <h2 style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontSize:'clamp(44px,5vw,80px)', fontWeight:800, letterSpacing:'-2.5px', lineHeight:1.0, marginBottom:'20px', position:'relative' }}>
          Stop guessing.<br/>Start researching.
        </h2>
        <p style={{ fontSize:'17px', color:'var(--muted)', marginBottom:'40px', fontWeight:300, position:'relative' }}>
          Your API is running. Open the app and run your first analysis.
        </p>
        <button onClick={() => navigate('/app')}
          style={{ padding:'16px 40px', borderRadius:'12px', border:'none', background:'var(--accent)', color:'#fff', fontSize:'16px', fontWeight:500, cursor:'pointer', position:'relative', transition:'all 0.2s' }}
          onMouseEnter={e => { e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.background='var(--accent2)' }}
          onMouseLeave={e => { e.currentTarget.style.transform='none'; e.currentTarget.style.background='var(--accent)' }}>
          Open AlphaForage →
        </button>
      </div>

      {/* Footer */}
      <footer style={{ borderTop:'1px solid var(--border)', padding:'48px', display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:'16px' }}>
        <div style={{ fontFamily:'var(--font-display)', fontSize:'16px', fontWeight:700, display:'flex', alignItems:'center', gap:'8px' }}>
          <div style={{ width:'24px', height:'24px', background:'var(--accent)', borderRadius:'6px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:'12px', color:'#fff', fontWeight:800 }}>α</div>
          AlphaForage
        </div>
        <div style={{ fontSize:'11px', color:'var(--dim)', maxWidth:'500px', lineHeight:1.5 }}>
          Market data by Polygon.io & Finnhub. AI analysis is not financial advice. For research purposes only.
        </div>
      </footer>
    </div>
  )
}