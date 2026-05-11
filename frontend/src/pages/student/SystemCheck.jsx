import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { sessionApi } from '../../lib/api'
import { Camera, Mic, Monitor, CheckCircle, XCircle, ArrowRight, Loader2 } from 'lucide-react'

export default function SystemCheck() {
  const { examId } = useParams()
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const [checks, setChecks] = useState({
    camera: null,    // null = pending, true = pass, false = fail
    microphone: null,
    fullscreen: null,
    browser: null,
  })
  const [stream, setStream] = useState(null)
  const [starting, setStarting] = useState(false)

  const allPassed = Object.values(checks).every((v) => v === true)

  // Run checks on mount
  useEffect(() => {
    runChecks()
    return () => { if (stream) stream.getTracks().forEach((t) => t.stop()) }
  }, [])

  async function runChecks() {
    // Browser check
    const isChrome = /Chrome/.test(navigator.userAgent) && !/Edge/.test(navigator.userAgent)
    const isFirefox = /Firefox/.test(navigator.userAgent)
    setChecks((c) => ({ ...c, browser: isChrome || isFirefox || true }))

    // Fullscreen
    setChecks((c) => ({ ...c, fullscreen: !!document.fullscreenEnabled }))

    // Camera + Microphone
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      setStream(mediaStream)
      if (videoRef.current) videoRef.current.srcObject = mediaStream
      setChecks((c) => ({ ...c, camera: true, microphone: true }))
    } catch {
      setChecks((c) => ({
        ...c,
        camera: false,
        microphone: false,
      }))
    }
  }

  async function handleStartExam() {
    setStarting(true)
    try {
      const session = await sessionApi.start({
        student_id: user.id,
        exam_id: examId,
      })
      // Enter fullscreen
      try { await document.documentElement.requestFullscreen() } catch { /* ok */ }
      navigate(`/student/exam/${session.id}`)
    } catch (err) {
      alert('Failed to start session: ' + err.message)
    } finally {
      setStarting(false)
    }
  }

  const CheckItem = ({ label, icon: Icon, status }) => (
    <div className="glass-light p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
        status === true ? 'bg-emerald-500/10' : status === false ? 'bg-danger/10' : 'bg-surface-700/50'
      }`}>
        <Icon className={`w-5 h-5 ${
          status === true ? 'text-emerald-400' : status === false ? 'text-danger' : 'text-surface-500'
        }`} />
      </div>
      <div className="flex-1">
        <p className="font-medium">{label}</p>
        <p className="text-xs text-surface-500">
          {status === null ? 'Checking...' : status ? 'Ready' : 'Not available'}
        </p>
      </div>
      {status === true && <CheckCircle className="w-5 h-5 text-emerald-400" />}
      {status === false && <XCircle className="w-5 h-5 text-danger" />}
      {status === null && <Loader2 className="w-5 h-5 text-surface-500 animate-spin" />}
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Pre-Exam System Check</h1>
        <p className="text-surface-400 mt-1">Ensure all systems are ready before starting the exam.</p>
      </div>

      {/* Camera Preview */}
      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">Camera Preview</h2>
        <div className="aspect-video bg-surface-900 rounded-xl overflow-hidden relative">
          <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
          {!stream && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Camera className="w-12 h-12 text-surface-600" />
            </div>
          )}
        </div>
      </div>

      {/* Checklist */}
      <div className="space-y-3">
        <CheckItem label="Camera Access" icon={Camera} status={checks.camera} />
        <CheckItem label="Microphone Access" icon={Mic} status={checks.microphone} />
        <CheckItem label="Fullscreen Support" icon={Monitor} status={checks.fullscreen} />
        <CheckItem label="Browser Compatibility" icon={Monitor} status={checks.browser} />
      </div>

      {/* Start Button */}
      <button
        id="start-exam-btn"
        onClick={handleStartExam}
        disabled={!allPassed || starting}
        className="w-full py-4 bg-gradient-to-r from-primary-600 to-primary-500 text-white font-semibold rounded-xl hover:from-primary-500 hover:to-primary-400 transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-primary-600/20 text-lg"
      >
        {starting ? <Loader2 className="w-5 h-5 animate-spin" /> : <> Start Exam <ArrowRight className="w-5 h-5" /> </>}
      </button>
    </div>
  )
}
