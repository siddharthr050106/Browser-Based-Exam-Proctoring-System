import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { sessionApi, eventApi, clipApi, flApi } from '../../lib/api'
import { initGearManager, stopGearManager, getCurrentGear, getGearConfig, onGearChange, getFrameCaptureIntervalMs, GEARS } from '../../lib/gearManager'
import { initHeartbeat, stopHeartbeat, reportEvent, reportGaze, getTrustScore } from '../../lib/heartbeatService'
import { initOfflineBuffer, stopOfflineBuffer, enterGear4, exitGear4, isSuspended } from '../../lib/offlineBuffer'
import { initVideoBuffer, stopVideoBuffer, captureAndUpload, recordWarningClip } from '../../lib/videoBuffer'
import { Clock, Shield, AlertTriangle, CheckCircle, Eye, EyeOff, Smartphone, Users, Camera, MonitorOff, AlertCircle, X, ShieldAlert, Wifi, WifiOff, Volume2 } from 'lucide-react'

const BUFFER_DURATION = 30 // seconds

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
  proctor_warning: {
    label: 'Proctor Warning',
    description: 'The proctor has issued a warning. A recording is being captured.',
    icon: ShieldAlert,
    color: 'red',
  },
  multiple_speakers: {
    label: 'Multiple Speakers Detected',
    description: 'Multiple voices detected. Only the student should be audible.',
    icon: Volume2,
    color: 'amber',
  },
}

function getAlertConfig(eventType) {
  const key = eventType.toLowerCase()
  return ALERT_CONFIG[key] || {
    label: eventType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    description: 'A proctoring event has been detected.',
    icon: AlertTriangle,
    color: 'amber',
  }
}

// ── Gear Badge Component ──
function GearBadge({ gear }) {
  const config = GEARS[gear]
  if (!config) return null
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full font-medium border flex items-center gap-1"
      style={{
        backgroundColor: `${config.color}20`,
        color: config.color,
        borderColor: `${config.color}40`,
      }}
    >
      {gear === 4 ? <WifiOff className="w-3 h-3" /> : <Wifi className="w-3 h-3" />}
      Gear {gear}
    </span>
  )
}

export default function ExamSession() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const timerRef = useRef(null)
  const [timeLeft, setTimeLeft] = useState(3600)
  const [status, setStatus] = useState('active')
  const [monitorStatus, setMonitorStatus] = useState('green')
  const [eventCount, setEventCount] = useState({ info: 0, warning: 0, flag: 0, critical: 0 })
  const [stream, setStream] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [detectionReady, setDetectionReady] = useState(false)
  const [warningActive, setWarningActive] = useState(false)
  const [warningMessage, setWarningMessage] = useState('')
  const [terminated, setTerminated] = useState(false)
  const [terminationReason, setTerminationReason] = useState('')
  const studentWsRef = useRef(null)
  const streamRef = useRef(null)

  // ── New: Gear / Heartbeat / Offline state ──
  const [currentGear, setCurrentGear] = useState(1)
  const [trustScore, setTrustScore] = useState(1.0)
  const [examSuspended, setExamSuspended] = useState(false)
  const [sidecarOnline, setSidecarOnline] = useState(false)
  const [audioActive, setAudioActive] = useState(false)
  const audioWsRef = useRef(null)
  const audioContextRef = useRef(null)

  // Keep streamRef synced
  useEffect(() => { streamRef.current = stream }, [stream])

  // ── Resolve sidecar/API URLs ──
  const getSidecarUrl = useCallback(() => {
    // In Electron, use IPC config. In browser dev, Vite proxy handles it.
    if (window.bezpElectron) {
      return `http://127.0.0.1:8765`
    }
    return '' // Vite proxy handles /detect/* → localhost:8765
  }, [])

  const getRemoteApiUrl = useCallback(() => {
    if (window.bezpElectron) {
      return window.bezpElectron.getConfig?.()?.remoteApiUrl || 'http://localhost:8000'
    }
    return '' // Vite proxy handles /api/* → localhost:8000
  }, [])

  // ── Alert Toast System (unchanged) ──
  const addAlert = useCallback((eventType, tier) => {
    const config = getAlertConfig(eventType)
    const id = Date.now() + '-' + Math.random().toString(36).slice(2)
    const alert = { id, eventType, tier, ...config, timestamp: Date.now() }

    setAlerts(prev => {
      const updated = [alert, ...prev].slice(0, 5)
      return updated
    })

    const dismissMs = tier === 'flag' || tier === 'critical' ? 15000 : 8000
    setTimeout(() => {
      setAlerts(prev => prev.filter(a => a.id !== id))
    }, dismissMs)
  }, [])

  const dismissAlert = useCallback((id) => {
    setAlerts(prev => prev.filter(a => a.id !== id))
  }, [])

  // ── 1. Initialize Gear Manager, Heartbeat, Offline Buffer ──
  useEffect(() => {
    const remoteUrl = getRemoteApiUrl()

    initGearManager(remoteUrl)
    initHeartbeat(sessionId, remoteUrl, (signal, action) => {
      // Callback when an event is routed
      console.debug(`[Heartbeat] ${signal.event_type} → ${action}`)
    })
    initOfflineBuffer(
      remoteUrl,
      // onSuspend: 5 min Gear 4 → lock the UI
      () => {
        setExamSuspended(true)
        console.warn('[ExamSession] Exam SUSPENDED — 5 min in Gear 4')
      },
      // onResume: network recovered
      () => {
        setExamSuspended(false)
        console.log('[ExamSession] Exam RESUMED — network recovered')
      }
    )

    // Listen for gear changes
    const unsub = onGearChange((newGear, oldGear) => {
      setCurrentGear(newGear)
      if (newGear === 4) enterGear4()
      else if (oldGear === 4) exitGear4()
    })

    // Trust score polling
    const trustInterval = setInterval(() => {
      setTrustScore(getTrustScore())
    }, 2000)

    return () => {
      unsub()
      clearInterval(trustInterval)
      stopGearManager()
      stopHeartbeat()
      stopOfflineBuffer()
    }
  }, [sessionId])

  // ── 2. Setup webcam + video buffer ──
  useEffect(() => {
    let mediaStream
    async function setup() {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 360 } },
          audio: true,
        })
        setStream(mediaStream)
        if (videoRef.current) videoRef.current.srcObject = mediaStream
        // Initialize the rolling 30s video buffer
        initVideoBuffer(mediaStream, sessionId, getRemoteApiUrl())
      } catch (err) {
        console.warn('Combined media request failed, attempting video-only...', err)
        try {
          mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 360 } },
          })
          setStream(mediaStream)
          if (videoRef.current) videoRef.current.srcObject = mediaStream
          initVideoBuffer(mediaStream, sessionId, getRemoteApiUrl())
        } catch (camErr) {
          console.error('Failed to access camera', camErr)
        }
      }
    }
    setup()

    // Enable kiosk mode in Electron
    if (window.bezpElectron) {
      window.bezpElectron.startKiosk()
    }

    return () => {
      if (mediaStream) mediaStream.getTracks().forEach(t => t.stop())
      stopVideoBuffer()
    }
  }, [])

  // ── 3. Timer ──
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

  // ── 4. Browser event listeners (tab switch, blur, fullscreen) ──
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) handleBrowserEvent('tab_switch')
    }
    const handleBlur = () => handleBrowserEvent('window_blur')
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) handleBrowserEvent('fullscreen_exit')
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

  // ── 5. Student WebSocket — receive proctor commands ──
  useEffect(() => {
    const wsBase = window.bezpElectron
      ? getRemoteApiUrl().replace('http', 'ws')
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`

    const ws = new WebSocket(`${wsBase}/ws/student/${sessionId}`)
    studentWsRef.current = ws

    ws.onopen = () => console.log('[StudentWS] Connected')

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data)

        if (data.type === 'proctor_warning') {
          setWarningActive(true)
          setWarningMessage(data.message || 'You have received a warning from the proctor.')
          setMonitorStatus('red')
          addAlert('proctor_warning', 'critical')

          // Record 30-second post-warning clip using the video buffer
          recordWarningClip().then(async (clipBlob) => {
            try {
              await clipApi.uploadWarning(sessionId, clipBlob)
              console.log('[StudentWS] 30s post-warning clip uploaded')
            } catch (err) {
              console.error('Warning clip upload failed:', err)
            }
          }).catch(err => {
            console.error('Failed to record warning clip:', err)
          })

          setTimeout(() => setWarningActive(false), 15000)
        }

        if (data.type === 'session_terminated') {
          setTerminated(true)
          setTerminationReason(data.reason || 'Your exam has been terminated by the proctor.')
          setStatus('terminated')
          clearInterval(timerRef.current)
          if (stream) stream.getTracks().forEach(t => t.stop())
        }
      } catch (e) {
        console.error('[StudentWS] Parse error:', e)
      }
    }

    ws.onclose = () => {
      console.log('[StudentWS] Disconnected')
      setTimeout(() => {
        if (status === 'active') {
          const reconnect = new WebSocket(`${wsBase}/ws/student/${sessionId}`)
          studentWsRef.current = reconnect
        }
      }, 3000)
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN) ws.close(1000)
    }
  }, [sessionId])

  // ── 6. Frame capture → LOCAL SIDECAR (gear-controlled FPS) ──
  useEffect(() => {
    if (!stream || !videoRef.current) return

    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const ctx = canvas.getContext('2d')
    let isFirstFrame = true
    let captureTimer = null

    function scheduleCaptureLoop() {
      const intervalMs = getFrameCaptureIntervalMs()
      if (intervalMs === Infinity) {
        // Gear 4: no frame capture
        return
      }

      captureTimer = setTimeout(async () => {
        if (!videoRef.current || status !== 'active') {
          scheduleCaptureLoop()
          return
        }

        ctx.drawImage(videoRef.current, 0, 0, 640, 480)
        const dataUrl = canvas.toDataURL('image/jpeg', 0.7)
        const base64 = dataUrl.split(',')[1]

        try {
          // POST to LOCAL SIDECAR (localhost:8765) — frame never leaves this device
          const res = await fetch(`${getSidecarUrl()}/detect/frame`, {
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
            setSidecarOnline(true)
            isFirstFrame = false
          }

          const data = await res.json()

          // Process detection signals
          if (data.signals && data.signals.length > 0) {
            for (const sig of data.signals) {
              // Update local counter
              setEventCount(c => ({
                ...c,
                [sig.tier]: (c[sig.tier] || 0) + 1,
              }))

              // Show alert toast
              addAlert(sig.event_type, sig.tier)

              // Route through heartbeat service (gear-aware send/bundle/drop/buffer)
              reportEvent(sig)

              // Update monitor status
              if (sig.tier === 'flag' || sig.tier === 'critical') {
                setMonitorStatus('red')
                // Capture and upload 30s clip for FLAG/CRITICAL
                if (sig.requires_clip) {
                  captureAndUpload(sig.event_type).catch(console.error)
                }
              } else if (sig.tier === 'warning') {
                setMonitorStatus(prev => prev === 'red' ? 'red' : 'yellow')
              }
            }
            setTimeout(() => setMonitorStatus('green'), 10000)
          }

          // Report gaze data to heartbeat service (gear-aware)
          if (data.gaze) {
            reportGaze(data.gaze)
          }

        } catch (err) {
          setSidecarOnline(false)
          console.debug('Sidecar detection skipped:', err.message)
        }

        scheduleCaptureLoop()
      }, intervalMs)
    }

    scheduleCaptureLoop()

    return () => {
      if (captureTimer) clearTimeout(captureTimer)
    }
  }, [stream, status, sessionId, addAlert])

  // ── 7. Audio capture → Sidecar WebSocket ──
  useEffect(() => {
    if (!stream) return

    // Check if the stream has audio tracks
    const audioTracks = stream.getAudioTracks()
    if (audioTracks.length === 0) {
      console.warn('[Audio] No audio tracks available')
      return
    }

    const wsUrl = window.bezpElectron
      ? `ws://127.0.0.1:8765/ws/audio/${sessionId}`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/audio/${sessionId}`

    let ws
    try {
      ws = new WebSocket(wsUrl)
      audioWsRef.current = ws
    } catch (err) {
      console.warn('[Audio] WebSocket connection failed:', err)
      return
    }

    ws.onopen = () => {
      setAudioActive(true)
      console.log('[Audio] WebSocket connected')

      // Use AudioContext to extract PCM from the media stream
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 })
        audioContextRef.current = audioCtx
        const source = audioCtx.createMediaStreamSource(stream)
        const processor = audioCtx.createScriptProcessor(4096, 1, 1)

        let chunkBuffer = []
        const SAMPLES_PER_CHUNK = 16000 * 3 // 3 seconds at 16kHz

        processor.onaudioprocess = (e) => {
          if (getCurrentGear() >= 3) return // Gear 3-4: pause audio streaming

          const input = e.inputBuffer.getChannelData(0)
          // Convert float32 to int16
          const int16 = new Int16Array(input.length)
          for (let i = 0; i < input.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, Math.round(input[i] * 32767)))
          }
          chunkBuffer.push(...int16)

          if (chunkBuffer.length >= SAMPLES_PER_CHUNK) {
            const chunk = new Int16Array(chunkBuffer.splice(0, SAMPLES_PER_CHUNK))
            // Convert to base64 and send
            const bytes = new Uint8Array(chunk.buffer)
            const base64 = btoa(String.fromCharCode(...bytes))

            if (ws.readyState === WebSocket.OPEN) {
              ws.send(base64)
            }
          }
        }

        source.connect(processor)
        processor.connect(audioCtx.destination)
      } catch (err) {
        console.error('[Audio] AudioContext setup failed:', err)
      }
    }

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data)
        if (data.flag) {
          // Audio detection flagged something
          addAlert(data.flag.event_type, data.flag.tier)
          reportEvent(data.flag)
          setEventCount(c => ({
            ...c,
            [data.flag.tier]: (c[data.flag.tier] || 0) + 1,
          }))
        }
      } catch {}
    }

    ws.onclose = () => {
      setAudioActive(false)
      console.log('[Audio] WebSocket disconnected')
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN) ws.close()
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {})
      }
    }
  }, [stream, sessionId])

  // ── Handle browser events → sidecar + heartbeat ──
  async function handleBrowserEvent(eventType) {
    try {
      // Send to local sidecar for rule engine processing
      const res = await fetch(`${getSidecarUrl()}/detect/browser-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, event_type: eventType }),
      })
      const data = await res.json()

      setEventCount(c => ({ ...c, [data.tier]: (c[data.tier] || 0) + 1 }))
      addAlert(eventType, data.tier)

      // Route through heartbeat (gear-aware)
      reportEvent({
        event_type: data.event_type,
        tier: data.tier,
        confidence: data.confidence,
        metadata: data.metadata,
        requires_clip: data.requires_clip,
      })

      if (data.tier === 'flag' || data.tier === 'critical') {
        setMonitorStatus('red')
        if (data.requires_clip) {
          captureAndUpload(eventType).catch(console.error)
        }
      } else if (data.tier === 'warning') {
        setMonitorStatus(prev => prev === 'red' ? 'red' : 'yellow')
      }

      setTimeout(() => setMonitorStatus('green'), 10000)
    } catch (err) {
      // Sidecar offline — route directly through heartbeat
      reportEvent({
        event_type: eventType,
        tier: 'warning',
        confidence: 1.0,
        metadata: { source: 'browser_event' },
        requires_clip: false,
      })
      console.error('Browser event to sidecar failed, sent via heartbeat:', err)
    }
  }

  // ── End exam ──
  async function handleEndExam() {
    clearInterval(timerRef.current)
    setStatus('completed')

    // Disable kiosk mode
    if (window.bezpElectron) {
      window.bezpElectron.stopKiosk()
    }

    try {
      // Clean up sidecar session and collect FL parameters
      const sidecarRes = await fetch(`${getSidecarUrl()}/detect/end-session/${sessionId}`, { method: 'POST' }).catch(() => null)
      if (sidecarRes && sidecarRes.ok) {
        try {
          const sidecarData = await sidecarRes.json()
          if ((sidecarData.fl_boundary_params && sidecarData.fl_boundary_params.length > 0) || 
              (sidecarData.fl_audio_params && sidecarData.fl_audio_params.length > 0)) {
            await flApi.contribute({
              session_id: sessionId,
              fl_boundary_params: sidecarData.fl_boundary_params || [],
              fl_audio_params: sidecarData.fl_audio_params || []
            })
            console.log('[ExamSession] Federated Learning contribution submitted')
          }
        } catch (err) {
          console.error('[ExamSession] Failed to submit FL contribution', err)
        }
      }

      await sessionApi.end(sessionId)
      if (stream) stream.getTracks().forEach(t => t.stop())
      stopVideoBuffer()
      stopHeartbeat()
      stopGearManager()
      stopOfflineBuffer()
      if (audioWsRef.current?.readyState === WebSocket.OPEN) audioWsRef.current.close()
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

      {/* ── TERMINATION SCREEN ── */}
      {terminated && (
        <div className="fixed inset-0 z-[100] bg-surface-950 flex items-center justify-center">
          <div className="text-center max-w-lg p-8">
            <div className="w-20 h-20 rounded-full bg-red-500/20 flex items-center justify-center mx-auto mb-6">
              <AlertCircle className="w-10 h-10 text-red-400" />
            </div>
            <h1 className="text-3xl font-bold text-red-400 mb-4">Exam Terminated</h1>
            <p className="text-surface-300 mb-2">Your exam has been terminated by the proctor.</p>
            <div className="glass p-4 rounded-xl mt-4 mb-8">
              <p className="text-sm text-surface-400"><span className="font-semibold text-surface-300">Reason:</span> {terminationReason}</p>
            </div>
            <button
              onClick={() => navigate('/student/results')}
              className="px-8 py-3 bg-surface-800 text-surface-300 rounded-xl hover:bg-surface-700 transition-colors"
            >
              Return to Dashboard
            </button>
          </div>
        </div>
      )}

      {/* ── EXAM SUSPENDED OVERLAY (5 min Gear 4) ── */}
      {examSuspended && !terminated && (
        <div className="fixed inset-0 z-[95] bg-surface-950/90 backdrop-blur-lg flex items-center justify-center animate-fade-in">
          <div className="max-w-lg p-8 text-center">
            <div className="w-20 h-20 rounded-full bg-amber-500/20 border-2 border-amber-500/40 flex items-center justify-center mx-auto mb-6">
              <WifiOff className="w-10 h-10 text-amber-400 animate-pulse" />
            </div>
            <h2 className="text-2xl font-bold text-amber-300 mb-3">Connection Lost — Exam Paused</h2>
            <p className="text-surface-300 mb-4">
              Your internet connection has been unstable for more than 5 minutes.
              The exam is paused until connectivity is restored.
            </p>
            <div className="glass p-4 rounded-xl border border-amber-500/30">
              <p className="text-xs text-amber-400/80">
                Your answers and progress have been saved locally.
                The exam will automatically resume when your connection recovers.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── PROCTOR WARNING OVERLAY ── */}
      {warningActive && !terminated && (
        <div className="fixed inset-0 z-[90] bg-red-950/70 backdrop-blur-sm flex items-center justify-center animate-fade-in">
          <div className="max-w-lg p-8 text-center">
            <div className="w-20 h-20 rounded-full bg-amber-500/20 border-2 border-amber-500/40 flex items-center justify-center mx-auto mb-6 animate-pulse">
              <AlertTriangle className="w-10 h-10 text-amber-400" />
            </div>
            <h2 className="text-2xl font-bold text-amber-300 mb-3">⚠ Proctor Warning</h2>
            <p className="text-surface-200 mb-6 leading-relaxed">{warningMessage}</p>
            <div className="glass p-4 rounded-xl border border-amber-500/30">
              <p className="text-xs text-amber-400/80">
                A 30-second recording is being captured. Please comply with the exam rules to continue.
              </p>
            </div>
            <button
              onClick={() => setWarningActive(false)}
              className="mt-6 px-6 py-2 bg-surface-800/80 text-surface-300 rounded-xl text-sm hover:bg-surface-700 transition-colors"
            >
              I Understand
            </button>
          </div>
        </div>
      )}

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
          {/* Gear indicator */}
          <GearBadge gear={currentGear} />
          {/* Audio indicator */}
          {audioActive && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-400 border border-violet-500/30">
              <Volume2 className="w-3 h-3 inline mr-1" />
              Audio
            </span>
          )}
        </div>

        <div className="flex items-center gap-6">
          {/* Trust Score */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-surface-500">Trust</span>
            <div className="w-16 h-2 bg-surface-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${trustScore * 100}%`,
                  backgroundColor: trustScore > 0.7 ? '#10b981' : trustScore > 0.4 ? '#f59e0b' : '#ef4444',
                }}
              />
            </div>
            <span className="text-xs font-mono text-surface-400">{(trustScore * 100).toFixed(0)}%</span>
          </div>

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
          {!sidecarOnline && detectionReady === false && (
            <div className="absolute top-1 right-1 px-1.5 py-0.5 bg-amber-900/80 rounded text-[10px] text-amber-400">
              Sidecar...
            </div>
          )}
          {monitorStatus === 'red' && (
            <div className="absolute inset-0 border-2 border-red-500 rounded-xl animate-pulse pointer-events-none" />
          )}
        </div>

        {/* Exam Questions Placeholder */}
        <div className={`glass p-8 space-y-8 ${examSuspended ? 'blur-lg pointer-events-none select-none' : ''}`}>
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
