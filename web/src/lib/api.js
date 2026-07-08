// Production-safe API origin resolution: an explicit VITE_API_URL (baked in
// at build time) wins when set — needed the moment the frontend is served
// from a different origin than the backend (e.g. a static host + a
// separately-deployed API). Falling back to window.location.origin keeps
// today's same-origin-behind-a-proxy behavior working with zero config,
// both in the Vite dev server (proxied to the backend, see vite.config.js)
// and in a same-origin production deployment.
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? window.location.origin
const BASE = `${API_BASE_URL}/api`

async function get(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function post(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function patch(path, body) {
  const r = await fetch(BASE + path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function del(path) {
  const r = await fetch(BASE + path, { method: 'DELETE' })
  if (!r.ok && r.status !== 204) throw new Error(`${r.status} ${r.statusText}`)
}

// ── SSE streaming helper ───────────────────────────────────────────────────────

export async function* streamSSE(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try { yield JSON.parse(line.slice(6)) } catch {}
    }
  }
}

// Legacy alias used by Research.jsx
export async function* streamResearch(query, depth = 'full') {
  yield* streamSSE('/v1/intelligence/research', { query, depth })
}

// ── Market API ─────────────────────────────────────────────────────────────────

export const api = {
  // /health is served at the API root, not under /api/v1 — hits
  // API_BASE_URL directly rather than going through BASE.
  health:       ()              => fetch(`${API_BASE_URL}/health`).then(r => {
                                      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
                                      return r.json()
                                    }),
  quote:        (ticker)       => get(`/v1/market/stocks/${ticker}`),
  candles:      (ticker, n=60) => get(`/v1/market/stocks/${ticker}/candles?limit=${n}`),
  fundamentals: (ticker)       => get(`/v1/market/stocks/${ticker}/fundamentals`),
  analyst:      (ticker)       => get(`/v1/market/stocks/${ticker}/analyst`),
  news:         (ticker, n=10) => get(`/v1/market/stocks/${ticker}/news?limit=${n}`),
  screen:       (query, limit=20) => post('/v1/screener/screen', { query, limit }),
  researchSync: (query, depth='full') => post('/v1/intelligence/research/sync', { query, depth }),
  compare:      (tickers, query='Compare these stocks') =>
                  fetch(BASE + '/v1/intelligence/compare?' + new URLSearchParams({ query }), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(tickers),
                  }).then(r => r.json()),
}

// ── Workspace API ──────────────────────────────────────────────────────────────

export const workspaceApi = {
  list:   ()             => get('/v1/workspaces'),
  get:    (id)           => get(`/v1/workspaces/${id}`),
  create: (body)         => post('/v1/workspaces', body),
  update: (id, body)     => patch(`/v1/workspaces/${id}`, body),
  delete: (id)           => del(`/v1/workspaces/${id}`),
  history: (id)          => get(`/v1/workspaces/${id}/history`),

  researchSync: (id, query, depth='full') =>
    post(`/v1/workspaces/${id}/research/sync`, { query, depth }),

  // SSE streaming research within workspace
  streamResearch: (id, query, depth='full') =>
    streamSSE(`/v1/workspaces/${id}/research`, { query, depth }),

  // Living Thesis
  getThesis:            (id)         => get(`/v1/workspaces/${id}/thesis`),
  getThesisVersions:    (id)         => get(`/v1/workspaces/${id}/thesis/versions`),
  getThesisVersion:     (id, vId)    => get(`/v1/workspaces/${id}/thesis/versions/${vId}`),
  getConfidenceHistory: (id)         => get(`/v1/workspaces/${id}/thesis/confidence-history`),
  getThesisClaims:      (id, status) => get(`/v1/workspaces/${id}/thesis/claims${status ? `?status=${status}` : ''}`),
}
