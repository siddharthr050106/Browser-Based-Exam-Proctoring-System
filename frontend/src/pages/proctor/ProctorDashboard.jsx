import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { sessionApi, eventApi } from '../../lib/api'
import { useProctorStore } from '../../stores/proctorStore'
import { Eye, AlertTriangle, Wifi, Users, Activity } from 'lucide-react'

const tierColors = {
  tier_1: 'text-emerald-400',
  tier_2: 'text-primary-400',
  tier_3: 'text-amber-400',
  tier_4: 'text-danger',
}

export default function ProctorDashboard() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['active-sessions'],
    queryFn: sessionApi.listActive,
    refetchInterval: 5000, // Poll every 5 seconds
  })
  const { connectToSession, events: wsEvents } = useProctorStore()
  const sessions = data?.sessions || []

  // Fetch events for all active sessions via REST (fallback for WS)
  const sessionIds = sessions.map(s => s.id)
  const { data: allEventsData } = useQuery({
    queryKey: ['all-session-events', ...sessionIds],
    queryFn: async () => {
      const results = {}
      for (const id of sessionIds) {
        try {
          const res = await eventApi.listForSession(id)
          results[id] = res?.events || []
        } catch { results[id] = [] }
      }
      return results
    },
    refetchInterval: 5000,
    enabled: sessionIds.length > 0,
  })

  // Auto-connect WebSocket to all active sessions
  useEffect(() => {
    sessions.forEach(s => connectToSession(s.id))
  }, [sessions.length])

  // Merge WS + REST events per session
  const getMergedEvents = (sessionId) => {
    const ws = wsEvents[sessionId] || []
    const rest = (allEventsData && allEventsData[sessionId]) || []
    const all = [...ws, ...rest]
    return Array.from(new Map(all.map(e => [e.id || e.timestamp, e])).values())
  }

  const getSessionFlagCount = (sessionId) => {
    const merged = getMergedEvents(sessionId)
    return merged.filter(e => e.tier === 'flag' || e.tier === 'critical').length
  }

  const getSessionStatus = (sessionId) => {
    const flags = getSessionFlagCount(sessionId)
    if (flags > 2) return 'red'
    if (flags > 0) return 'yellow'
    return 'green'
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <Eye className="w-7 h-7 text-emerald-400" /> Live Monitoring
          </h1>
          <p className="text-surface-400 mt-1">
            Real-time event monitoring — no video streamed, only detection metadata.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="glass-light px-4 py-2 flex items-center gap-2">
            <Users className="w-4 h-4 text-primary-400" />
            <span className="text-sm font-medium">{sessions.length} Active</span>
          </div>
          <button onClick={() => refetch()} className="glass-light px-4 py-2 text-sm hover:bg-surface-700 transition-colors rounded-xl">
            Refresh
          </button>
        </div>
      </div>

      {/* Session Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="glass p-12 text-center">
          <Activity className="w-12 h-12 text-surface-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-surface-300">No Active Sessions</h3>
          <p className="text-surface-500 mt-1">Sessions will appear here when students start their exams.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sessions.map((session) => {
            const statusColor = getSessionStatus(session.id)
            const flagCount = getSessionFlagCount(session.id)
            const sessionEvents = getMergedEvents(session.id)
            const latestEvent = sessionEvents.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0]

            return (
              <Link
                key={session.id}
                to={`/proctor/session/${session.id}`}
                className="glass-light p-5 hover:bg-surface-800/60 transition-all duration-200 group hover:scale-[1.01] block"
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`status-dot ${statusColor}`} />
                    <span className="text-sm font-medium">
                      Session
                    </span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    session.status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-surface-700 text-surface-400'
                  }`}>
                    {session.status}
                  </span>
                </div>

                {/* Student Info */}
                <div className="mb-3">
                  <p className="text-xs text-surface-500 font-mono truncate">ID: {session.id.slice(0, 8)}...</p>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="bg-surface-900/50 rounded-lg p-2 text-center">
                    <p className={`text-lg font-bold ${flagCount > 0 ? 'text-danger' : 'text-surface-300'}`}>{flagCount}</p>
                    <p className="text-xs text-surface-500">Flags</p>
                  </div>
                  <div className="bg-surface-900/50 rounded-lg p-2 text-center">
                    <p className="text-lg font-bold text-surface-300">{sessionEvents.length}</p>
                    <p className="text-xs text-surface-500">Events</p>
                  </div>
                </div>

                {/* Network Tier */}
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1 text-surface-500">
                    <Wifi className={`w-3.5 h-3.5 ${tierColors[session.network_tier] || 'text-surface-500'}`} />
                    {session.network_tier?.replace('_', ' ')}
                  </span>
                  {latestEvent && (
                    <span className={`tier-${latestEvent.tier} px-2 py-0.5 rounded-full text-xs font-medium`}>
                      {latestEvent.event_type?.replace('_', ' ')}
                    </span>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
