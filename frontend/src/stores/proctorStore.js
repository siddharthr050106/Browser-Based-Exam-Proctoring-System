import { create } from 'zustand'

export const useProctorStore = create((set, get) => ({
  // Active sessions being monitored
  activeSessions: [],
  selectedSessionId: null,
  events: {},       // { sessionId: [events...] }
  gazeData: {},     // { sessionId: [snapshots...] }
  wsConnections: {}, // { sessionId: WebSocket }

  setActiveSessions: (sessions) => set({ activeSessions: sessions }),

  selectSession: (sessionId) => set({ selectedSessionId: sessionId }),

  addEvent: (sessionId, event) =>
    set((state) => ({
      events: {
        ...state.events,
        [sessionId]: [event, ...(state.events[sessionId] || [])].slice(0, 200),
      },
    })),

  addGazeSnapshot: (sessionId, snapshot) =>
    set((state) => ({
      gazeData: {
        ...state.gazeData,
        [sessionId]: [...(state.gazeData[sessionId] || []), snapshot].slice(-300),
      },
    })),

  // WebSocket management with auto-reconnect
  connectToSession: (sessionId) => {
    const existing = get().wsConnections[sessionId]
    if (existing && existing.readyState === WebSocket.OPEN) return
    // Clean up stale connections
    if (existing) {
      try { existing.close() } catch {}
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/proctor/${sessionId}`)

    ws.onopen = () => {
      console.log(`[ProctorWS] Connected to session ${sessionId.slice(0, 8)}`)
    }

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data)
        if (data.type === 'detection_event') {
          get().addEvent(sessionId, data.data)
        } else if (data.type === 'gaze_snapshot') {
          get().addGazeSnapshot(sessionId, data.data)
        }
      } catch (e) { /* ignore parse errors */ }
    }

    ws.onclose = (e) => {
      console.log(`[ProctorWS] Disconnected from ${sessionId.slice(0, 8)}, code=${e.code}`)
      set((state) => {
        const conns = { ...state.wsConnections }
        delete conns[sessionId]
        return { wsConnections: conns }
      })
      // Auto-reconnect after 3 seconds (unless intentionally closed)
      if (e.code !== 1000) {
        setTimeout(() => {
          console.log(`[ProctorWS] Reconnecting to ${sessionId.slice(0, 8)}...`)
          get().connectToSession(sessionId)
        }, 3000)
      }
    }

    ws.onerror = () => {
      console.warn(`[ProctorWS] Error on session ${sessionId.slice(0, 8)}`)
    }

    set((state) => ({
      wsConnections: { ...state.wsConnections, [sessionId]: ws },
    }))
  },

  disconnectFromSession: (sessionId) => {
    const ws = get().wsConnections[sessionId]
    if (ws) ws.close()
    set((state) => {
      const conns = { ...state.wsConnections }
      delete conns[sessionId]
      return { wsConnections: conns }
    })
  },

  sendCommand: (sessionId, action) => {
    const ws = get().wsConnections[sessionId]
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action }))
    }
  },
}))
