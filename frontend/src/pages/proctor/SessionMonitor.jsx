import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { eventApi, sessionApi, clipApi } from '../../lib/api'
import { useProctorStore } from '../../stores/proctorStore'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { ArrowLeft, Pause, Play, Download, Video, AlertTriangle, Clock, ShieldAlert, ShieldOff, Check, MessageSquare, Eye, XCircle, Loader2 } from 'lucide-react'
import { format } from 'date-fns'

const tierBadgeClass = {
  info: 'tier-info',
  warning: 'tier-warning',
  flag: 'tier-flag',
  critical: 'tier-critical',
}

const FLAG_THRESHOLD = 3          // Flags needed to show warn button
const FLAG_WINDOW_MINUTES = 5     // Time window for flag counting

export default function SessionMonitor() {
  const { sessionId } = useParams()
  const { connectToSession, events: wsEvents, sendCommand, wsConnections } = useProctorStore()

  const [warningPending, setWarningPending] = useState(false)  // Warning sent, waiting for clip
  const [clipReady, setClipReady] = useState(false)             // Clip available for review
  const [clipUrl, setClipUrl] = useState(null)                  // URL of the warning clip
  const [showTerminateModal, setShowTerminateModal] = useState(false)
  const [terminateReason, setTerminateReason] = useState('')
  const [reviewVerdict, setReviewVerdict] = useState(null)      // After proctor reviews
  const [actionLoading, setActionLoading] = useState(false)

  // Check WebSocket
  const ws = wsConnections[sessionId]
  const wsConnected = ws && ws.readyState === WebSocket.OPEN

  // Fetch session details
  const { data: session, refetch: refetchSession } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => sessionApi.get(sessionId),
    refetchInterval: 5000,
  })

  // Fetch historical events
  const { data: eventsData } = useQuery({
    queryKey: ['events', sessionId],
    queryFn: () => eventApi.listForSession(sessionId),
    refetchInterval: 5000,
  })

  // Fetch gaze snapshots
  const { data: gazeData } = useQuery({
    queryKey: ['gaze', sessionId],
    queryFn: () => eventApi.gazeSnapshots(sessionId),
    refetchInterval: 5000,
  })

  useEffect(() => { connectToSession(sessionId) }, [sessionId])

  // Restore warning state from session data
  useEffect(() => {
    if (session?.warning_issued_at) {
      setWarningPending(true)
    }
  }, [session?.warning_issued_at])

  // Merge WS + REST events
  const allEvents = [
    ...(wsEvents[sessionId] || []),
    ...(eventsData?.events || []),
  ]
  const uniqueEvents = Array.from(
    new Map(allEvents.map(e => [e.id || e.timestamp, e])).values()
  ).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

  // Check for clip-available events (uploaded by student after warning)
  useEffect(() => {
    if (!warningPending) return
    const clipEvent = uniqueEvents.find(e =>
      e.clip_url && new Date(e.timestamp) > new Date(session?.warning_issued_at || 0)
    )
    if (clipEvent?.clip_url) {
      setClipReady(true)
      setClipUrl(clipEvent.clip_url)
    }
  }, [uniqueEvents, warningPending, session?.warning_issued_at])

  // Count recent flags
  const cutoff = Date.now() - FLAG_WINDOW_MINUTES * 60 * 1000
  const recentFlags = uniqueEvents.filter(e =>
    (e.tier === 'flag' || e.tier === 'critical') &&
    new Date(e.timestamp).getTime() > cutoff
  )
  const flagCount = recentFlags.length
  const totalFlags = uniqueEvents.filter(e => e.tier === 'flag' || e.tier === 'critical').length
  const showWarnButton = flagCount >= FLAG_THRESHOLD && !session?.warning_issued_at

  // Check if flags continue after warning
  const postWarningFlags = session?.warning_issued_at
    ? uniqueEvents.filter(e =>
        (e.tier === 'flag' || e.tier === 'critical') &&
        new Date(e.timestamp) > new Date(session.warning_issued_at)
      ).length
    : 0
  const showTerminateOption = session?.warning_issued_at && postWarningFlags >= 2 && reviewVerdict !== 'not_anomaly'

  const gazeChartData = (gazeData || []).map((s, i) => ({
    idx: i,
    yaw: s.head_yaw || 0,
    pitch: s.head_pitch || 0,
    score: (s.anomaly_score || 0) * 100,
  }))

  const handlePause = () => sendCommand(sessionId, 'pause_session')
  const handleResume = () => sendCommand(sessionId, 'resume_session')

  // ── Proctor Actions ──
  async function handleWarn() {
    setActionLoading(true)
    try {
      await sessionApi.warn(sessionId)
      setWarningPending(true)
      refetchSession()
    } catch (err) {
      console.error('Failed to issue warning:', err)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleReview(verdict, notes = '') {
    setActionLoading(true)
    try {
      await sessionApi.review(sessionId, verdict, notes)
      setReviewVerdict(verdict)
    } catch (err) {
      console.error('Failed to submit review:', err)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleTerminate() {
    if (!terminateReason.trim()) return
    setActionLoading(true)
    try {
      await sessionApi.terminate(sessionId, terminateReason)
      setShowTerminateModal(false)
      refetchSession()
    } catch (err) {
      console.error('Failed to terminate:', err)
    } finally {
      setActionLoading(false)
    }
  }

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
              {session?.status === 'terminated' && (
                <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-red-500/15 text-red-400 border border-red-500/30">
                  Terminated
                </span>
              )}
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
          <p className="text-2xl font-bold text-danger">{totalFlags}</p>
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

      {/* ── INTERVENTION PANEL ── */}
      {session?.status !== 'completed' && session?.status !== 'terminated' && (
        <div className={`glass p-6 border ${
          showTerminateOption ? 'border-red-500/40' :
          warningPending ? 'border-amber-500/30' :
          showWarnButton ? 'border-amber-500/20' :
          'border-surface-700'
        }`}>
          <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4" /> Proctor Intervention
          </h2>

          {/* Phase 1: Issue Warning */}
          {!session?.warning_issued_at && (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-surface-300">
                  {showWarnButton
                    ? <span className="text-amber-400 font-medium">⚠ {flagCount} flags in the last {FLAG_WINDOW_MINUTES} minutes</span>
                    : <span className="text-surface-500">{flagCount} flags in the last {FLAG_WINDOW_MINUTES} min (threshold: {FLAG_THRESHOLD})</span>
                  }
                </p>
              </div>
              <button
                onClick={handleWarn}
                disabled={!showWarnButton || actionLoading}
                className="px-4 py-2 rounded-xl text-sm font-medium flex items-center gap-2 transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30"
              >
                {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />}
                Issue Warning
              </button>
            </div>
          )}

          {/* Phase 2: Warning issued, waiting for clip */}
          {session?.warning_issued_at && !clipReady && !reviewVerdict && (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <p className="text-sm text-amber-400">
                  Warning issued at {format(new Date(session.warning_issued_at), 'HH:mm:ss')}
                </p>
              </div>
              <div className="flex items-center gap-3 glass-light p-4 rounded-xl">
                <Loader2 className="w-5 h-5 text-surface-400 animate-spin" />
                <div>
                  <p className="text-sm text-surface-300">Waiting for 30-second clip...</p>
                  <p className="text-xs text-surface-500">Student is recording 20s before + 10s after the warning</p>
                </div>
              </div>
            </div>
          )}

          {/* Phase 3: Clip ready — review */}
          {clipReady && !reviewVerdict && (
            <div className="space-y-4">
              <p className="text-sm text-emerald-400 flex items-center gap-2">
                <Video className="w-4 h-4" /> Warning clip available for review
              </p>

              {/* Video Player */}
              <div className="bg-surface-900 rounded-xl overflow-hidden">
                <video
                  src={clipUrl}
                  controls
                  className="w-full max-h-64 object-contain"
                  preload="metadata"
                />
              </div>

              {/* Verdict Buttons */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <button
                  onClick={() => handleReview('not_anomaly')}
                  disabled={actionLoading}
                  className="glass-light px-3 py-3 text-sm rounded-xl hover:bg-emerald-600/20 transition-colors flex flex-col items-center gap-1.5 border border-emerald-500/20"
                >
                  <Check className="w-5 h-5 text-emerald-400" />
                  <span className="text-emerald-400 font-medium">Not Anomaly</span>
                  <span className="text-[10px] text-surface-500">False positive</span>
                </button>

                <button
                  onClick={() => handleReview('add_note', prompt('Enter observation notes:') || '')}
                  disabled={actionLoading}
                  className="glass-light px-3 py-3 text-sm rounded-xl hover:bg-primary-600/20 transition-colors flex flex-col items-center gap-1.5 border border-primary-500/20"
                >
                  <MessageSquare className="w-5 h-5 text-primary-400" />
                  <span className="text-primary-400 font-medium">Add Note</span>
                  <span className="text-[10px] text-surface-500">Flag with notes</span>
                </button>

                <button
                  onClick={() => handleReview('continue_monitoring')}
                  disabled={actionLoading}
                  className="glass-light px-3 py-3 text-sm rounded-xl hover:bg-surface-600/30 transition-colors flex flex-col items-center gap-1.5 border border-surface-600/20"
                >
                  <Eye className="w-5 h-5 text-surface-400" />
                  <span className="text-surface-300 font-medium">Continue</span>
                  <span className="text-[10px] text-surface-500">Keep watching</span>
                </button>

                <button
                  onClick={() => setShowTerminateModal(true)}
                  disabled={actionLoading}
                  className="glass-light px-3 py-3 text-sm rounded-xl hover:bg-red-600/20 transition-colors flex flex-col items-center gap-1.5 border border-red-500/20"
                >
                  <ShieldOff className="w-5 h-5 text-red-400" />
                  <span className="text-red-400 font-medium">Terminate</span>
                  <span className="text-[10px] text-surface-500">End exam</span>
                </button>
              </div>
            </div>
          )}

          {/* Phase 4: Review submitted — post-warning monitoring */}
          {reviewVerdict && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <Check className="w-4 h-4 text-emerald-400" />
                <span className="text-surface-300">
                  Verdict: <span className="font-medium text-surface-100">{reviewVerdict.replace(/_/g, ' ')}</span>
                </span>
              </div>

              {/* Show terminate option if flags continue */}
              {showTerminateOption && (
                <div className="glass-light p-4 rounded-xl border border-red-500/30">
                  <p className="text-sm text-red-400 mb-3">
                    <AlertTriangle className="w-4 h-4 inline mr-1" />
                    {postWarningFlags} flags detected since the warning. Consider terminating.
                  </p>
                  <button
                    onClick={() => setShowTerminateModal(true)}
                    className="px-4 py-2 bg-red-500/20 text-red-400 rounded-xl text-sm font-medium hover:bg-red-500/30 transition-colors flex items-center gap-2 border border-red-500/30"
                  >
                    <ShieldOff className="w-4 h-4" /> Terminate Exam
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Terminate Modal */}
      {showTerminateModal && (
        <div className="fixed inset-0 z-50 bg-surface-950/80 backdrop-blur-sm flex items-center justify-center">
          <div className="glass p-8 max-w-md w-full mx-4 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
                <ShieldOff className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-red-400">Terminate Exam</h3>
                <p className="text-xs text-surface-500">This action cannot be undone</p>
              </div>
            </div>

            <div>
              <label className="block text-sm text-surface-400 mb-2">Reason for termination *</label>
              <textarea
                value={terminateReason}
                onChange={(e) => setTerminateReason(e.target.value)}
                rows={3}
                className="w-full bg-surface-800/50 border border-surface-700 rounded-xl p-3 text-sm text-surface-100 focus:outline-none focus:ring-2 focus:ring-red-500/50 resize-none"
                placeholder="e.g., Multiple unauthorized devices detected despite warning..."
              />
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowTerminateModal(false)}
                className="px-4 py-2 glass-light rounded-xl text-sm hover:bg-surface-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleTerminate}
                disabled={!terminateReason.trim() || actionLoading}
                className="px-4 py-2 bg-red-500/20 text-red-400 rounded-xl text-sm font-medium hover:bg-red-500/30 transition-colors border border-red-500/30 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldOff className="w-4 h-4" />}
                Terminate Session
              </button>
            </div>
          </div>
        </div>
      )}

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
                <a
                  href={event.clip_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors"
                >
                  <Video className="w-3.5 h-3.5" /> View Clip
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
