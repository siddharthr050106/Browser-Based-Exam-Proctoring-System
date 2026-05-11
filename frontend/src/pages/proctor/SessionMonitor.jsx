import { useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventApi, sessionApi } from '../../lib/api'
import { useProctorStore } from '../../stores/proctorStore'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { ArrowLeft, Pause, Play, Download, Video, AlertTriangle, Clock } from 'lucide-react'
import { format } from 'date-fns'

const tierBadgeClass = {
  info: 'tier-info',
  warning: 'tier-warning',
  flag: 'tier-flag',
  critical: 'tier-critical',
}

export default function SessionMonitor() {
  const { sessionId } = useParams()
  const { connectToSession, events: wsEvents, sendCommand, wsConnections } = useProctorStore()

  // Check if WebSocket is connected
  const ws = wsConnections[sessionId]
  const wsConnected = ws && ws.readyState === WebSocket.OPEN

  // Fetch session details
  const { data: session } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => sessionApi.get(sessionId),
    refetchInterval: 5000,
  })

  // Fetch historical events — poll every 5s for reliability
  const { data: eventsData } = useQuery({
    queryKey: ['events', sessionId],
    queryFn: () => eventApi.listForSession(sessionId),
    refetchInterval: 5000,
  })

  // Fetch gaze snapshots for chart
  const { data: gazeData } = useQuery({
    queryKey: ['gaze', sessionId],
    queryFn: () => eventApi.gazeSnapshots(sessionId),
    refetchInterval: 5000,
  })

  // Connect WebSocket
  useEffect(() => {
    connectToSession(sessionId)
  }, [sessionId])

  const allEvents = [
    ...(wsEvents[sessionId] || []),
    ...(eventsData?.events || []),
  ]
  // Deduplicate by id
  const uniqueEvents = Array.from(
    new Map(allEvents.map(e => [e.id || e.timestamp, e])).values()
  ).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

  const gazeChartData = (gazeData || []).map((s, i) => ({
    idx: i,
    yaw: s.head_yaw || 0,
    pitch: s.head_pitch || 0,
    score: (s.anomaly_score || 0) * 100,
  }))

  const handlePause = () => sendCommand(sessionId, 'pause_session')
  const handleResume = () => sendCommand(sessionId, 'resume_session')

  const exportCSV = () => {
    const headers = 'event_type,tier,confidence,timestamp\n'
    const rows = uniqueEvents.map(e =>
      `${e.event_type},${e.tier},${e.confidence || ''},${e.timestamp}`
    ).join('\n')
    const blob = new Blob([headers + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `session_${sessionId.slice(0, 8)}_events.csv`
    a.click()
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/proctor" className="glass-light p-2 rounded-xl hover:bg-surface-700 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold">Session Monitor</h1>
            <div className="flex items-center gap-2">
              <p className="text-xs text-surface-500 font-mono">{sessionId}</p>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                wsConnected
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                  : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
              }`}>
                {wsConnected ? '● Live' : '○ Polling'}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={handlePause} className="glass-light px-3 py-2 text-sm hover:bg-amber-600/20 transition-colors flex items-center gap-1.5 rounded-xl">
            <Pause className="w-4 h-4" /> Pause
          </button>
          <button onClick={handleResume} className="glass-light px-3 py-2 text-sm hover:bg-emerald-600/20 transition-colors flex items-center gap-1.5 rounded-xl">
            <Play className="w-4 h-4" /> Resume
          </button>
          <button onClick={exportCSV} className="glass-light px-3 py-2 text-sm hover:bg-primary-600/20 transition-colors flex items-center gap-1.5 rounded-xl">
            <Download className="w-4 h-4" /> CSV
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="glass-light p-4 text-center">
          <p className="text-2xl font-bold">{uniqueEvents.length}</p>
          <p className="text-xs text-surface-500">Total Events</p>
        </div>
        <div className="glass-light p-4 text-center">
          <p className="text-2xl font-bold text-danger">{uniqueEvents.filter(e => e.tier === 'flag' || e.tier === 'critical').length}</p>
          <p className="text-xs text-surface-500">Flags</p>
        </div>
        <div className="glass-light p-4 text-center">
          <p className="text-2xl font-bold text-amber-400">{uniqueEvents.filter(e => e.tier === 'warning').length}</p>
          <p className="text-xs text-surface-500">Warnings</p>
        </div>
        <div className="glass-light p-4 text-center">
          <p className="text-2xl font-bold text-surface-300">{session?.status || '—'}</p>
          <p className="text-xs text-surface-500">Status</p>
        </div>
      </div>

      {/* Gaze Timeline Chart */}
      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">Gaze Timeline</h2>
        {gazeChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={gazeChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="idx" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px' }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Line type="monotone" dataKey="yaw" stroke="#818cf8" strokeWidth={2} dot={false} name="Yaw °" />
              <Line type="monotone" dataKey="pitch" stroke="#34d399" strokeWidth={2} dot={false} name="Pitch °" />
              <Line type="monotone" dataKey="score" stroke="#f87171" strokeWidth={2} dot={false} name="Anomaly %" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-center text-surface-500 py-8">No gaze data available yet.</p>
        )}
      </div>

      {/* Event Feed */}
      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">Event Feed</h2>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {uniqueEvents.length === 0 ? (
            <p className="text-center text-surface-500 py-8">No events recorded.</p>
          ) : uniqueEvents.map((event, i) => (
            <div
              key={event.id || i}
              className={`glass-light p-3 flex items-center justify-between animate-slide-in`}
            >
              <div className="flex items-center gap-3">
                <span className={`${tierBadgeClass[event.tier]} px-2.5 py-1 rounded-full text-xs font-semibold uppercase`}>
                  {event.tier}
                </span>
                <div>
                  <p className="text-sm font-medium">{event.event_type?.replace(/_/g, ' ')}</p>
                  <p className="text-xs text-surface-500">
                    {event.timestamp ? format(new Date(event.timestamp), 'HH:mm:ss') : ''}
                    {event.confidence ? ` • conf: ${(event.confidence * 100).toFixed(0)}%` : ''}
                  </p>
                </div>
              </div>
              {event.clip_url && (
                <Link
                  to={`/proctor/clip/${event.id}`}
                  className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors"
                >
                  <Video className="w-3.5 h-3.5" /> View Clip
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
