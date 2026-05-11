import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { sessionApi, eventApi, clipApi } from '../../lib/api'
import { Clock, Shield, AlertTriangle, CheckCircle, Eye, EyeOff, Smartphone, Users, Camera, MonitorOff, AlertCircle, X } from 'lucide-react'

const BUFFER_DURATION = 30 // seconds
const CHUNK_INTERVAL = 1000 // ms

// Map detection event types to human-friendly alert configs
const ALERT_CONFIG = {
  tab_switch: {
    label: 'Tab Switch Detected',
    description: 'You switched away from the exam tab. Stay focused.',
    icon: MonitorOff,
    color: 'amber',
  },
  window_blur: {
    label: 'Window Focus Lost',
    description: 'The exam window lost focus. Please return to the exam.',
    icon: MonitorOff,
    color: 'amber',
  },
  fullscreen_exit: {
    label: 'Fullscreen Exited',
    description: 'You exited fullscreen mode. Please stay in fullscreen.',
    icon: MonitorOff,
    color: 'amber',
  },
  phone_detected: {
    label: 'Mobile Device Detected',
    description: 'A mobile phone was detected in camera view. Please remove it.',
    icon: Smartphone,
    color: 'red',
  },
  multiple_persons: {
    label: 'Multiple Persons Detected',
    description: 'More than one person detected in the frame. Only the student should be visible.',
    icon: Users,
    color: 'red',
  },
  no_face: {
    label: 'No Face Detected',
    description: 'Your face is not visible. Please position yourself in front of the camera.',
    icon: EyeOff,
    color: 'amber',
  },
  identity_mismatch: {
    label: 'Identity Mismatch',
    description: 'The detected face does not match the reference. Please stay in frame.',
    icon: AlertCircle,
    color: 'red',
  },
  gaze_anomaly: {
    label: 'Gaze Anomaly Detected',
    description: 'Sustained off-screen gaze detected. Please keep your eyes on the screen.',
    icon: Eye,
    color: 'amber',
  },
  background_change: {
    label: 'Background Change Detected',
    description: 'Your background has changed significantly. Please stay in the same position.',
    icon: Camera,
    color: 'amber',
  },
  composite_critical: {
    label: 'Critical Alert',
    description: 'Multiple anomalies detected simultaneously. This has been escalated for review.',
    icon: AlertCircle,
    color: 'red',
  },
}

function getAlertConfig(eventType) {
  // Normalize: the event_type might be PHONE_DETECTED or phone_detected
  const key = eventType.toLowerCase()
  return ALERT_CONFIG[key] || {
    label: eventType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    description: 'A proctoring event has been detected.',
    icon: AlertTriangle,
    color: 'amber',
  }
}

export default function ExamSession() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const [timeLeft, setTimeLeft] = useState(3600)
  const [status, setStatus] = useState('active')
  const [monitorStatus, setMonitorStatus] = useState('green')
  const [eventCount, setEventCount] = useState({ info: 0, warning: 0, flag: 0, critical: 0 })
  const [stream, setStream] = useState(null)
  const [alerts, setAlerts] = useState([]) // Active alert toasts
  const [detectionReady, setDetectionReady] = useState(false)

  // ── Add alert toast ──
  const addAlert = useCallback((eventType, tier) => {
    const config = getAlertConfig(eventType)
    const id = Date.now() + '-' + Math.random().toString(36).slice(2)
    const alert = { id, eventType, tier, ...config, timestamp: Date.now() }

    setAlerts(prev => {
      // Keep only last 5 alerts
      const updated = [alert, ...prev].slice(0, 5)
      return updated
    })

    // Auto-dismiss after duration based on tier
    const dismissMs = tier === 'flag' || tier === 'critical' ? 15000 : 8000
    setTimeout(() => {
      setAlerts(prev => prev.filter(a => a.id !== id))
    }, dismissMs)
  }, [])

  const dismissAlert = useCallback((id) => {
    setAlerts(prev => prev.filter(a => a.id !== id))
  }, [])

  // ── Setup webcam + MediaRecorder ring buffer ──
  useEffect(() => {
    let mediaStream
    async function setup() {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        setStream(mediaStream)
        if (videoRef.current) videoRef.current.srcObject = mediaStream
        startRecordingBuffer(mediaStream)
      } catch (err) {
        console.error('Failed to access media devices', err)
      }
    }
    setup()

    return () => {
      if (mediaStream) mediaStream.getTracks().forEach(t => t.stop())
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop()
      }
    }
  }, [])

  // ── Ring buffer for 30s clip upload ──
  function startRecordingBuffer(mediaStream) {
    try {
      const recorder = new MediaRecorder(mediaStream, { mimeType: 'video/webm' })
      recorderRef.current = recorder
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
          // Keep only last BUFFER_DURATION seconds worth of chunks
          const maxChunks = BUFFER_DURATION * (1000 / CHUNK_INTERVAL)
          if (chunksRef.current.length > maxChunks) {
            chunksRef.current = chunksRef.current.slice(-maxChunks)
          }
        }
      }
      recorder.start(CHUNK_INTERVAL)
    } catch (err) {
      console.warn('MediaRecorder not available:', err.message)
    }
  }

  // ── Timer ──
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimeLeft(t => {
        if (t <= 1) {
          handleEndExam()
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [])

  // ── Browser event listeners (tab switch, blur, fullscreen) ──
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) sendBrowserEvent('tab_switch')
    }
    const handleBlur = () => sendBrowserEvent('window_blur')
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) sendBrowserEvent('fullscreen_exit')
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('blur', handleBlur)
    document.addEventListener('fullscreenchange', handleFullscreenChange)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('blur', handleBlur)
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
    }
  }, [sessionId])

  // ── Frame capture → Detection Worker (~0.5fps to reduce CPU load) ──
  useEffect(() => {
    if (!stream || !videoRef.current) return

    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const ctx = canvas.getContext('2d')
    let isFirstFrame = true

    const captureInterval = setInterval(async () => {
      if (!videoRef.current || status !== 'active') return

      ctx.drawImage(videoRef.current, 0, 0, 640, 480)
      const dataUrl = canvas.toDataURL('image/jpeg', 0.7)
      const base64 = dataUrl.split(',')[1]

      try {
        const res = await fetch('/detect/frame', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            frame_base64: base64,
            is_first_frame: isFirstFrame,
          }),
        })
        
        if (isFirstFrame) {
          setDetectionReady(true)
          isFirstFrame = false
        }
        
        const data = await res.json()

        // Process detection signals
        if (data.signals && data.signals.length > 0) {
          for (const sig of data.signals) {
            // Update counter
            setEventCount(c => ({
              ...c,
              [sig.tier]: (c[sig.tier] || 0) + 1,
            }))

            // Show alert toast to student
            addAlert(sig.event_type, sig.tier)

            // Update monitor status
            if (sig.tier === 'flag' || sig.tier === 'critical') {
              setMonitorStatus('red')
              // Upload 30s clip for FLAG/CRITICAL events
              if (sig.requires_clip) {
                const clipBlob = new Blob(chunksRef.current, { type: 'video/webm' })
                if (clipBlob.size > 0) {
                  clipApi.upload(sessionId, 'auto-' + Date.now(), clipBlob).catch(console.error)
                }
              }
            } else if (sig.tier === 'warning') {
              setMonitorStatus(prev => prev === 'red' ? 'red' : 'yellow')
            }
          }
          // Reset monitor status after 10 seconds of no new flags
          setTimeout(() => setMonitorStatus('green'), 10000)
        }
      } catch (err) {
        // Detection worker may be offline — degrade gracefully
        console.debug('Frame detection skipped:', err.message)
      }
    }, 2000) // ~0.5fps = every 2 seconds (once per ~10 webcam frames)

    return () => clearInterval(captureInterval)
  }, [stream, status, sessionId, addAlert])

  // ── Send browser event to detection worker ──
  async function sendBrowserEvent(eventType) {
    try {
      const res = await fetch('/detect/browser-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, event_type: eventType }),
      })
      const data = await res.json()

      setEventCount(c => ({ ...c, [data.tier]: (c[data.tier] || 0) + 1 }))

      // Show alert toast for browser events
      addAlert(eventType, data.tier)

      if (data.tier === 'flag' || data.tier === 'critical') {
        setMonitorStatus('red')
        if (data.requires_clip) {
          const clipBlob = new Blob(chunksRef.current, { type: 'video/webm' })
          if (clipBlob.size > 0) {
            clipApi.upload(sessionId, 'browser-' + Date.now(), clipBlob).catch(console.error)
          }
        }
      } else if (data.tier === 'warning') {
        setMonitorStatus(prev => prev === 'red' ? 'red' : 'yellow')
      }

      setTimeout(() => setMonitorStatus('green'), 10000)
    } catch (err) {
      console.error('Failed to send browser event', err)
    }
  }

  // ── End exam ──
  async function handleEndExam() {
    clearInterval(timerRef.current)
    setStatus('completed')
    try {
      // Clean up detection pipeline
      await fetch(`/detect/end-session/${sessionId}`, { method: 'POST' }).catch(() => {})
      await sessionApi.end(sessionId)
      if (stream) stream.getTracks().forEach(t => t.stop())
      if (document.fullscreenElement) await document.exitFullscreen()
      navigate('/student/results')
    } catch (err) {
      console.error('Failed to end session', err)
    }
  }

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  }

  const totalFlags = eventCount.flag + eventCount.critical

  return (
    <div className="min-h-screen bg-surface-950 relative">
      {/* Top Bar */}
      <div className="fixed top-0 left-0 right-0 z-50 glass border-b border-surface-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Shield className="w-5 h-5 text-primary-400" />
          <span className="font-semibold">Proctored Exam</span>
          <div className={`w-3 h-3 rounded-full ${
            monitorStatus === 'green' ? 'bg-emerald-400 shadow-emerald-400/50' :
            monitorStatus === 'yellow' ? 'bg-amber-400 shadow-amber-400/50 animate-pulse' :
            'bg-red-500 shadow-red-500/50 animate-pulse'
          } shadow-lg`} />
          <span className="text-xs text-surface-400">
            {monitorStatus === 'green' ? 'Monitoring Active' :
             monitorStatus === 'yellow' ? 'Warning Active' :
             'Alert Triggered'}
          </span>
          {detectionReady && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              <Eye className="w-3 h-3 inline mr-1" />
              Detection Active
            </span>
          )}
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-lg font-mono">
            <Clock className="w-5 h-5 text-surface-400" />
            <span className={timeLeft < 300 ? 'text-danger animate-pulse' : ''}>{formatTime(timeLeft)}</span>
          </div>
          <button
            id="end-exam-btn"
            onClick={handleEndExam}
            className="px-4 py-2 bg-danger/20 text-danger rounded-lg text-sm font-medium hover:bg-danger/30 transition-colors border border-danger/30"
          >
            End Exam
          </button>
        </div>
      </div>

      {/* Alert Toasts — top-right, stacked */}
      <div className="fixed top-20 right-6 z-50 flex flex-col gap-3 w-96 pointer-events-none">
        {alerts.map((alert) => {
          const Icon = alert.icon
          const isRed = alert.color === 'red'
          return (
            <div
              key={alert.id}
              className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border backdrop-blur-xl shadow-2xl
                transition-all duration-300 alert-toast-enter
                ${isRed
                  ? 'bg-red-950/80 border-red-500/40 shadow-red-500/10'
                  : 'bg-amber-950/80 border-amber-500/40 shadow-amber-500/10'
                }`}
            >
              <div className={`p-2 rounded-lg ${isRed ? 'bg-red-500/20' : 'bg-amber-500/20'}`}>
                <Icon className={`w-5 h-5 ${isRed ? 'text-red-400' : 'text-amber-400'}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className={`text-sm font-semibold ${isRed ? 'text-red-300' : 'text-amber-300'}`}>
                    {alert.label}
                  </p>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full uppercase font-bold tracking-wider
                    ${alert.tier === 'critical' ? 'bg-red-500/30 text-red-300' :
                      alert.tier === 'flag' ? 'bg-red-500/20 text-red-400' :
                      alert.tier === 'warning' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-primary-500/20 text-primary-400'}`}>
                    {alert.tier}
                  </span>
                </div>
                <p className="text-xs text-surface-400 mt-1 leading-relaxed">{alert.description}</p>
              </div>
              <button
                onClick={() => dismissAlert(alert.id)}
                className="text-surface-500 hover:text-surface-300 transition-colors shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )
        })}
      </div>

      {/* Main Content */}
      <div className="pt-20 p-8 max-w-4xl mx-auto">
        {/* Webcam (small, bottom-right) */}
        <div className="fixed bottom-6 right-6 w-48 h-36 rounded-xl overflow-hidden glass border-2 border-surface-700 shadow-2xl z-40">
          <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
          <div className="absolute bottom-1 left-1 flex items-center gap-1 px-2 py-0.5 bg-surface-900/80 rounded text-xs">
            <div className={`w-2 h-2 rounded-full ${monitorStatus === 'green' ? 'bg-emerald-400' : monitorStatus === 'yellow' ? 'bg-amber-400' : 'bg-red-400'} animate-pulse`} />
            <span className="text-surface-300">Live</span>
          </div>
          {monitorStatus === 'red' && (
            <div className="absolute inset-0 border-2 border-red-500 rounded-xl animate-pulse pointer-events-none" />
          )}
        </div>

        {/* Exam Questions Placeholder */}
        <div className="glass p-8 space-y-8">
          <div className="text-center border-b border-surface-800 pb-6">
            <h2 className="text-xl font-semibold">Examination In Progress</h2>
            <p className="text-surface-400 mt-2 text-sm">
              Your session is being monitored locally. Stay focused and keep your camera visible.
            </p>
          </div>

          {/* Sample questions - these would come from the exam API */}
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="glass-light p-6 rounded-xl">
              <h3 className="font-medium mb-3">Question {i}</h3>
              <p className="text-surface-400 mb-4">This is a placeholder for exam question {i}. The actual questions will be loaded from the exam configuration.</p>
              <div className="space-y-2">
                {['A', 'B', 'C', 'D'].map(opt => (
                  <label key={opt} className="flex items-center gap-3 p-3 rounded-lg hover:bg-surface-800/50 cursor-pointer transition-colors">
                    <input type="radio" name={`q${i}`} className="w-4 h-4 accent-primary-500" />
                    <span className="text-sm">Option {opt}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}

          <button
            onClick={handleEndExam}
            className="w-full py-4 bg-gradient-to-r from-primary-600 to-primary-500 text-white font-semibold rounded-xl hover:from-primary-500 hover:to-primary-400 transition-all text-lg shadow-lg shadow-primary-600/20"
          >
            Submit Exam
          </button>
        </div>
      </div>

      {/* Event Summary (bottom-left) */}
      <div className="fixed bottom-6 left-6 glass p-4 text-xs space-y-2 z-40 rounded-xl min-w-[180px]">
        <div className="text-surface-500 font-semibold uppercase tracking-wider text-[10px] mb-2">Detection Events</div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary-400" />
          <span className="text-surface-400 flex-1">Info</span>
          <span className="text-surface-300 font-mono">{eventCount.info}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-surface-400 flex-1">Warnings</span>
          <span className="text-surface-300 font-mono">{eventCount.warning}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-400" />
          <span className="text-surface-400 flex-1">Flags</span>
          <span className="text-surface-300 font-mono">{eventCount.flag}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-600" />
          <span className="text-surface-400 flex-1">Critical</span>
          <span className="text-surface-300 font-mono">{eventCount.critical}</span>
        </div>
        {totalFlags > 0 && (
          <div className="mt-2 pt-2 border-t border-surface-700 text-amber-400 text-[10px]">
            <AlertTriangle className="w-3 h-3 inline mr-1" />
            {totalFlags} flag{totalFlags > 1 ? 's' : ''} recorded
          </div>
        )}
      </div>
    </div>
  )
}
