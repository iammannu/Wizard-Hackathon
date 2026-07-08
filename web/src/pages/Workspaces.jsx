import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Loader2, Trash2, ChevronRight, Zap, TrendingUp } from 'lucide-react'
import { LIFECYCLE_META } from '../lib/thesisConstants.js'
import { useWorkspaceStore } from '../store/index.js'

const TEMPLATE_WORKSPACES = [
  { icon: '⚡', title: 'AI Infrastructure', description: 'NVIDIA, Microsoft, Google AI compute dominance', tracked_tickers: ['NVDA', 'MSFT', 'GOOGL'], tracked_themes: ['AI', 'semiconductors', 'cloud computing'] },
  { icon: '⚛️', title: 'Nuclear Energy Renaissance', description: 'Uranium miners, utilities, SMR developers', tracked_tickers: ['CEG', 'CCJ', 'VST'], tracked_themes: ['nuclear energy', 'clean power', 'energy transition'] },
  { icon: '🤖', title: 'Humanoid Robotics', description: 'AI embodiment, labor automation, NVIDIA ecosystem', tracked_tickers: ['TSLA', 'NVDA', 'AMZN'], tracked_themes: ['robotics', 'automation', 'AI hardware'] },
  { icon: '💊', title: 'Healthcare AI', description: 'GLP-1 drugs, surgical robots, AI diagnostics', tracked_tickers: ['LLY', 'ISRG', 'VEEV'], tracked_themes: ['biotech', 'medical AI', 'GLP-1'] },
  { icon: '🏭', title: 'India Manufacturing', description: 'Supply chain diversification from China', tracked_tickers: ['INFY', 'WIT', 'HDB'], tracked_themes: ['India', 'manufacturing', 'supply chain'] },
  { icon: '🚀', title: 'Space Economy', description: 'Satellite, launch, defense space systems', tracked_tickers: ['RKLB', 'SATS', 'MAXN'], tracked_themes: ['space', 'satellites', 'defense'] },
]

const ICONS = ['📊', '⚡', '🧠', '💰', '🌐', '🚀', '⚛️', '🤖', '💊', '🏭', '🔬', '📡', '⚙️', '🎯', '🌱']

export default function Workspaces() {
  const navigate = useNavigate()
  const { workspaces, loading, loadWorkspaces, createWorkspace, deleteWorkspace } = useWorkspaceStore()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', tracked_tickers: '', tracked_themes: '', icon: '📊' })
  const [creating, setCreating] = useState(false)

  useEffect(() => { loadWorkspaces() }, [])

  async function handleCreate(e) {
    e.preventDefault()
    if (!form.title.trim()) return
    setCreating(true)
    try {
      const ws = await createWorkspace({
        title: form.title.trim(),
        description: form.description.trim(),
        tracked_tickers: form.tracked_tickers.split(',').map(t => t.trim().toUpperCase()).filter(Boolean),
        tracked_themes: form.tracked_themes.split(',').map(t => t.trim().toLowerCase()).filter(Boolean),
        icon: form.icon,
      })
      setShowCreate(false)
      setForm({ title: '', description: '', tracked_tickers: '', tracked_themes: '', icon: '📊' })
      navigate(`/app/workspaces/${ws.id}`)
    } catch (err) {
      console.error(err)
    }
    setCreating(false)
  }

  async function useTemplate(tpl) {
    setCreating(true)
    try {
      const ws = await createWorkspace({ ...tpl, tracked_sectors: [] })
      navigate(`/app/workspaces/${ws.id}`)
    } catch {}
    setCreating(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Topbar */}
      <div style={{ height: '52px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 28px', gap: '12px', background: 'var(--surface)', flexShrink: 0 }}>
        <Zap size={16} style={{ color: 'var(--accent2)' }} />
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '15px', fontWeight: 600, flex: 1 }}>Research Workspaces</span>
        <span style={{ fontSize: '10px', padding: '3px 10px', borderRadius: '20px', background: 'rgba(108,92,231,0.12)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.22)', fontFamily: 'var(--font-mono)' }}>
          {workspaces.length} active
        </span>
        <button onClick={() => setShowCreate(true)}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px', borderRadius: '8px', border: 'none', background: 'var(--accent)', color: '#fff', fontSize: '12px', fontWeight: 500, cursor: 'pointer', transition: 'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--accent2)'}
          onMouseLeave={e => e.currentTarget.style.background = 'var(--accent)'}>
          <Plus size={13} /> New Workspace
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '28px' }}>

        {/* Existing workspaces */}
        {workspaces.length > 0 && (
          <div style={{ marginBottom: '36px' }}>
            <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '14px', fontWeight: 600 }}>Your Workspaces</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px' }}>
              {workspaces.map(ws => (
                <WorkspaceCard key={ws.id} ws={ws} onOpen={() => navigate(`/app/workspaces/${ws.id}`)} onDelete={() => deleteWorkspace(ws.id)} />
              ))}
            </div>
          </div>
        )}

        {/* Templates */}
        <div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '14px', fontWeight: 600 }}>
            {workspaces.length === 0 ? 'Start with a template' : 'Add from template'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px' }}>
            {TEMPLATE_WORKSPACES.map(tpl => (
              <div key={tpl.title}
                style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px', padding: '20px', cursor: 'pointer', transition: 'all 0.2s', position: 'relative', overflow: 'hidden' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(108,92,231,0.4)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none' }}
                onClick={() => useTemplate(tpl)}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '12px' }}>
                  <span style={{ fontSize: '28px', lineHeight: 1, flexShrink: 0 }}>{tpl.icon}</span>
                  <div>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>{tpl.title}</div>
                    <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.5 }}>{tpl.description}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {tpl.tracked_tickers.map(t => (
                    <span key={t} style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', padding: '2px 7px', borderRadius: '4px', background: 'rgba(108,92,231,0.1)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.2)' }}>{t}</span>
                  ))}
                </div>
                <div style={{ position: 'absolute', right: '16px', top: '50%', transform: 'translateY(-50%)', opacity: 0.4 }}>
                  <ChevronRight size={18} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200, padding: '20px' }}
          onClick={e => e.target === e.currentTarget && setShowCreate(false)}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border2)', borderRadius: '16px', padding: '32px', width: '100%', maxWidth: '480px', boxShadow: '0 20px 60px rgba(0,0,0,0.5)' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 700, marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>Create Research Workspace</span>
            </div>
            <form onSubmit={handleCreate}>
              {/* Icon picker */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: '8px' }}>Icon</label>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {ICONS.map(ic => (
                    <button key={ic} type="button" onClick={() => setForm(f => ({ ...f, icon: ic }))}
                      style={{ width: '34px', height: '34px', borderRadius: '8px', border: `2px solid ${form.icon === ic ? 'var(--accent)' : 'var(--border)'}`, background: form.icon === ic ? 'rgba(108,92,231,0.15)' : 'var(--surface2)', fontSize: '16px', cursor: 'pointer', transition: 'all 0.15s' }}>
                      {ic}
                    </button>
                  ))}
                </div>
              </div>

              {[
                { key: 'title', label: 'Workspace Title *', placeholder: 'e.g. AI Infrastructure', type: 'text' },
                { key: 'description', label: 'Description', placeholder: 'What investment thesis are you researching?', type: 'text' },
                { key: 'tracked_tickers', label: 'Tickers (comma-separated)', placeholder: 'NVDA, MSFT, GOOGL', type: 'text' },
                { key: 'tracked_themes', label: 'Themes (comma-separated)', placeholder: 'AI, semiconductors, cloud', type: 'text' },
              ].map(({ key, label, placeholder }) => (
                <div key={key} style={{ marginBottom: '16px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: '6px' }}>{label}</label>
                  <input
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    placeholder={placeholder}
                    required={key === 'title'}
                    style={{ width: '100%', background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: '9px', padding: '10px 14px', color: 'var(--text)', fontSize: '13px', outline: 'none', boxSizing: 'border-box', transition: 'border-color 0.15s' }}
                    onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                    onBlur={e => e.target.style.borderColor = 'var(--border2)'}
                  />
                </div>
              ))}

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '24px' }}>
                <button type="button" onClick={() => setShowCreate(false)}
                  style={{ padding: '10px 20px', borderRadius: '9px', border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', fontSize: '13px', cursor: 'pointer' }}>
                  Cancel
                </button>
                <button type="submit" disabled={creating || !form.title.trim()}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 24px', borderRadius: '9px', border: 'none', background: creating ? 'var(--dim)' : 'var(--accent)', color: '#fff', fontSize: '13px', fontWeight: 500, cursor: creating ? 'not-allowed' : 'pointer' }}>
                  {creating ? <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Zap size={14} />}
                  {creating ? 'Creating…' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function WorkspaceCard({ ws, onOpen, onDelete }) {
  const conf = ws.confidence
  const confColor = conf >= 0.75 ? 'var(--bull)' : conf >= 0.55 ? 'var(--warn)' : 'var(--muted)'

  return (
    <div
      style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px', padding: '20px', cursor: 'pointer', transition: 'all 0.2s', position: 'relative' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(108,92,231,0.4)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none' }}
      onClick={onOpen}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '24px' }}>{ws.icon}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '14px', fontWeight: 600 }}>{ws.title}</div>
            {ws.description && <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>{ws.description}</div>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {ws.thesis_version_count > 0 && (
            <span title={`Thesis: ${ws.thesis_lifecycle_stage}`} style={{ fontSize: '14px', lineHeight: 1 }}>
              {(LIFECYCLE_META[ws.thesis_lifecycle_stage] || LIFECYCLE_META.forming).icon}
            </span>
          )}
          <button onClick={e => { e.stopPropagation(); onDelete() }}
            style={{ padding: '4px', borderRadius: '6px', border: 'none', background: 'transparent', color: 'var(--muted)', cursor: 'pointer', opacity: 0.5, transition: 'opacity 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.opacity = 1}
            onMouseLeave={e => e.currentTarget.style.opacity = 0.5}>
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {ws.tracked_tickers?.length > 0 && (
        <div style={{ display: 'flex', gap: '5px', marginBottom: '12px', flexWrap: 'wrap' }}>
          {ws.tracked_tickers.slice(0, 4).map(t => (
            <span key={t} style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(108,92,231,0.1)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.18)' }}>{t}</span>
          ))}
        </div>
      )}

      {ws.thesis && (
        <div style={{ fontSize: '11px', color: 'var(--muted)', lineHeight: 1.5, marginBottom: '12px', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {ws.thesis}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Confidence</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: confColor }}>
            {conf > 0 ? `${Math.round(conf * 100)}%` : '—'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent2)', fontSize: '11px' }}>
          <TrendingUp size={12} />
          <span>Open →</span>
        </div>
      </div>

      {conf > 0 && (
        <div style={{ height: '3px', background: 'var(--dim)', borderRadius: '2px', marginTop: '8px', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${conf * 100}%`, background: conf >= 0.75 ? 'linear-gradient(90deg, var(--bull), #38bdf8)' : 'linear-gradient(90deg, var(--warn), var(--accent2))', borderRadius: '2px' }} />
        </div>
      )}
    </div>
  )
}
