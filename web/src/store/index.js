import { create } from 'zustand'
import { streamResearch, workspaceApi, api } from '../lib/api.js'

let msgId = 0
const uid = () => `m${++msgId}`

// ── Research store (legacy chat interface) ─────────────────────────────────────

export const useResearchStore = create((set, get) => ({
  messages: [],
  agentStates: {},
  isStreaming: false,
  depth: 'full',

  setDepth: (d) => set({ depth: d }),
  clearMessages: () => set({ messages: [], agentStates: {} }),

  sendQuery: async (query) => {
    if (get().isStreaming) return
    const { depth } = get()

    const userMsg = { id: uid(), role: 'user', text: query }
    const aiId = uid()
    const aiMsg = { id: aiId, role: 'ai', text: 'Routing to agents…', streaming: true, tickers: [], analysis: null }

    set(s => ({ messages: [...s.messages, userMsg, aiMsg], agentStates: {}, isStreaming: true }))

    const patch = (updater) => set(s => ({
      messages: s.messages.map(m => m.id === aiId ? { ...m, ...updater(m) } : m),
    }))

    try {
      for await (const event of streamResearch(query, depth)) {
        if (event.type === 'intent_parsed') {
          patch(m => ({
            tickers: event.tickers || m.tickers,
            text: `Intent: ${event.intent} — activating ${(event.agents || []).length} agents…`,
          }))
        }
        if (event.type === 'evidence_searching') {
          patch(() => ({ text: 'Searching You.com + Tavily for evidence…' }))
        }
        if (event.type === 'evidence_gathered') {
          patch(() => ({
            text: `Evidence gathered: ${event.total_sources} sources (You.com: ${event.you_com_count}, Tavily: ${event.tavily_count})`,
          }))
        }
        if (event.type === 'agent_start') {
          set(s => ({
            agentStates: {
              ...s.agentStates,
              [event.agent]: {
                status: 'thinking',
                signal: null,
                confidence: null,
                display_name: event.display_name || event.agent,
              },
            },
          }))
        }
        if (event.type === 'agent_complete') {
          set(s => ({
            agentStates: {
              ...s.agentStates,
              [event.agent]: {
                ...s.agentStates[event.agent],
                status: 'done',
                signal: event.signal,
                confidence: event.confidence,
                key_finding: event.key_finding,
              },
            },
          }))
        }
        if (event.type === 'debate_starting') {
          patch(() => ({ text: `Debate: ${event.bull} (bull) vs ${event.bear} (bear)…` }))
        }
        if (event.type === 'debate_complete') {
          patch(() => ({
            text: `Debate complete — winner: ${event.winner}. "${event.key_insight}"`,
          }))
        }
        if (event.type === 'scenarios_generating') {
          patch(() => ({ text: 'Generating scenario simulations…' }))
        }
        if (event.type === 'scenarios_generated') {
          patch(() => ({ text: `${event.count} scenarios generated. Building knowledge graph…` }))
        }
        if (event.type === 'graph_building') {
          patch(() => ({ text: 'Extracting knowledge graph from evidence…' }))
        }
        if (event.type === 'graph_built') {
          patch(() => ({
            text: `Knowledge graph: ${event.nodes} nodes, ${event.edges} edges. Synthesizing thesis…`,
          }))
        }
        if (event.type === 'synthesizing') {
          patch(() => ({ text: 'Synthesizing institutional investment thesis…' }))
        }
        if (event.type === 'synthesis_complete') {
          patch(() => ({ text: 'Analysis complete. Preparing results…' }))
        }
        if (event.type === 'result') {
          set(s => {
            const next = { ...s.agentStates }
            Object.entries(event.agent_outputs || {}).forEach(([name, out]) => {
              if (next[name]) next[name] = { ...next[name], confidence: out.confidence }
            })
            return { agentStates: next }
          })
          patch(() => ({
            text: event.explanation || event.recommendation || 'Analysis complete.',
            streaming: false,
            tickers: event.tickers || [],
            analysis: {
              confidence: event.confidence,
              confidence_breakdown: event.confidence_breakdown,
              recommendation: event.recommendation,
              explanation: event.explanation,
              bull_case: event.bull_case,
              bear_case: event.bear_case,
              key_risks: event.key_risks,
              invalidation_conditions: event.invalidation_conditions,
              known_unknowns: event.known_unknowns,
              agents_activated: event.agents_activated,
              evidence: event.evidence,
              debate: event.debate,
              scenarios: event.scenarios,
              knowledge_graph: event.knowledge_graph,
            },
          }))
        }
        if (event.type === 'error') {
          patch(() => ({ text: `Error: ${event.message}`, streaming: false }))
        }
      }
    } catch (err) {
      patch(() => ({ text: `Connection error: ${err.message}. Is the API running on :8000?`, streaming: false }))
    }

    set({ isStreaming: false })
  },
}))

// ── Market store ───────────────────────────────────────────────────────────────

export const useMarketStore = create((set, get) => ({
  cache: {},
  loading: {},

  fetch: async (ticker) => {
    if (get().loading[ticker]) return
    set(s => ({ loading: { ...s.loading, [ticker]: true } }))
    try {
      const data = await api.quote(ticker)
      set(s => ({ cache: { ...s.cache, [ticker]: data } }))
    } catch {}
    set(s => ({ loading: { ...s.loading, [ticker]: false } }))
  },
}))

// ── Workspace store ────────────────────────────────────────────────────────────

export const useWorkspaceStore = create((set, get) => ({
  workspaces: [],
  loading: false,
  error: null,

  // Active workspace research state
  activeWorkspaceId: null,
  agentStates: {},
  isStreaming: false,
  currentResult: null,
  streamLog: [],   // ordered list of all SSE events for the observability panel

  setActiveWorkspace: (id) => set({ activeWorkspaceId: id, agentStates: {}, currentResult: null, streamLog: [] }),

  loadWorkspaces: async () => {
    set({ loading: true, error: null })
    try {
      const data = await workspaceApi.list()
      set({ workspaces: data, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  createWorkspace: async (body) => {
    const ws = await workspaceApi.create(body)
    set(s => ({ workspaces: [ws, ...s.workspaces] }))
    return ws
  },

  deleteWorkspace: async (id) => {
    await workspaceApi.delete(id)
    set(s => ({ workspaces: s.workspaces.filter(w => w.id !== id) }))
  },

  // Stream research within a workspace
  streamResearch: async (workspaceId, query, depth = 'full') => {
    if (get().isStreaming) return
    set({ isStreaming: true, agentStates: {}, currentResult: null, streamLog: [], activeWorkspaceId: workspaceId })

    const addLog = (event) => set(s => ({ streamLog: [...s.streamLog, { ...event, _ts: Date.now() }] }))

    try {
      for await (const event of workspaceApi.streamResearch(workspaceId, query, depth)) {
        addLog(event)

        if (event.type === 'agent_start') {
          set(s => ({
            agentStates: {
              ...s.agentStates,
              [event.agent]: {
                status: 'thinking',
                signal: null,
                confidence: null,
                display_name: event.display_name || event.agent,
              },
            },
          }))
        }

        if (event.type === 'agent_complete') {
          set(s => ({
            agentStates: {
              ...s.agentStates,
              [event.agent]: {
                ...s.agentStates[event.agent],
                status: 'done',
                signal: event.signal,
                confidence: event.confidence,
                key_finding: event.key_finding,
              },
            },
          }))
        }

        if (event.type === 'result') {
          set({ currentResult: event })
          // Refresh workspace list so sidebar shows updated confidence/thesis
          get().loadWorkspaces()
        }
      }
    } catch (err) {
      addLog({ type: 'error', message: err.message })
    }

    set({ isStreaming: false })
  },
}))
