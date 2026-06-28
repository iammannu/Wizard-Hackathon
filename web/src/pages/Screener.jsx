import React, { useState } from 'react'
import { Search, Loader2, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useResearchStore } from '../store/index.js'
import styles from './Screener.module.css'

const SUGGESTIONS = [
  'Profitable tech stocks, revenue growth > 15%',
  'Low P/E healthcare stocks under 20',
  'High ROE with low debt',
  'High beta momentum plays',
  'Dividend payers with yield above 2%',
]

export default function Screener() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const navigate = useNavigate()
  const sendQuery = useResearchStore(s => s.sendQuery)

  async function run() {
    const q = query.trim()
    if (!q || loading) return
    setLoading(true)
    setResult(null)
    try {
      const data = await api.screen(q)
      setResult(data)
    } catch (err) {
      setResult({ error: err.message })
    }
    setLoading(false)
  }

  function researchTicker(ticker) {
    sendQuery(`Analyze ${ticker}`)
    navigate('/app/research')
  }

  return (
    <div className={styles.page}>
      <div className={styles.topbar}>
        <Search size={16} className={styles.topbarIcon} />
        <span className={styles.topbarTitle}>Stock Screener</span>
        <span className={styles.badge}>NL → Filters</span>
      </div>

      <div className={styles.body}>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Find your next idea.</h1>
          <p className={styles.heroSub}>
            Describe what you're looking for in plain English. AlphaForage translates it to precise filters instantly.
          </p>
        </div>

        <div className={styles.inputRow}>
          <input
            className={styles.input}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && run()}
            placeholder="e.g. profitable tech stocks with revenue growth over 15% and low debt…"
          />
          <button className={styles.runBtn} onClick={run} disabled={!query.trim() || loading}>
            {loading ? <Loader2 size={14} className={styles.spinning} /> : <Search size={14} />}
            {loading ? 'Screening…' : 'Screen'}
          </button>
        </div>

        <div className={styles.suggestions}>
          {SUGGESTIONS.map(s => (
            <button key={s} className={styles.suggChip} onClick={() => { setQuery(s); }}>
              {s}
            </button>
          ))}
        </div>

        {result && !result.error && (
          <>
            {result.explanation && (
              <div className={styles.explanation}>{result.explanation}</div>
            )}
            {result.filters_applied?.length > 0 && (
              <div className={styles.filters}>
                {result.filters_applied.map((f, i) => (
                  <span key={i} className={styles.filterChip}>
                    {f.field} {f.operator} {f.value}
                  </span>
                ))}
              </div>
            )}
            <div className={styles.resultsHeader}>
              <span className={styles.count}>{result.results?.length ?? 0} stocks matched</span>
            </div>
            {result.results?.length > 0 ? (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Ticker</th><th>Name</th><th>Sector</th>
                      <th>P/E</th><th>Rev Growth</th><th>Net Margin</th><th>Beta</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.map(s => {
                      const growthUp = (s.revenue_growth ?? 0) > 0
                      return (
                        <tr key={s.ticker} onClick={() => researchTicker(s.ticker)}>
                          <td className={styles.ticker}>{s.ticker}</td>
                          <td>{s.name}</td>
                          <td><span className={styles.sectorBadge}>{s.sector}</span></td>
                          <td className={styles.num}>{s.pe_ratio != null ? s.pe_ratio.toFixed(1) : '—'}</td>
                          <td className={`${styles.num} ${growthUp ? styles.up : styles.down}`}>
                            {s.revenue_growth != null ? (s.revenue_growth * 100).toFixed(1) + '%' : '—'}
                          </td>
                          <td className={styles.num}>{s.net_margin != null ? (s.net_margin * 100).toFixed(1) + '%' : '—'}</td>
                          <td className={styles.num}>{s.beta != null ? s.beta.toFixed(2) : '—'}</td>
                          <td>
                            <button className={styles.researchBtn} onClick={e => { e.stopPropagation(); researchTicker(s.ticker) }}>
                              Research <ArrowRight size={11} />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={styles.noResults}>No stocks matched — try relaxing the criteria.</div>
            )}
          </>
        )}

        {result?.error && (
          <div className={styles.error}>Error: {result.error}</div>
        )}
      </div>
    </div>
  )
}
