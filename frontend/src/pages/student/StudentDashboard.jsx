import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import { examApi } from '../../lib/api'
import { BookOpen, Clock, CheckCircle, AlertTriangle } from 'lucide-react'

export default function StudentDashboard() {
  const { user } = useAuthStore()
  const { data } = useQuery({ queryKey: ['exams'], queryFn: examApi.list })

  const exams = data?.exams || []
  const upcomingExams = exams.filter(e => e.is_active).slice(0, 3)

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="glass p-8">
        <h1 className="text-2xl font-bold mb-2">
          Welcome back, <span className="gradient-text">{user?.full_name || 'Student'}</span>
        </h1>
        <p className="text-surface-400">Here's your exam overview and upcoming assessments.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { icon: BookOpen, label: 'Available Exams', value: exams.length, color: 'text-primary-400', bg: 'bg-primary-600/10' },
          { icon: Clock, label: 'Upcoming', value: upcomingExams.length, color: 'text-amber-400', bg: 'bg-amber-600/10' },
          { icon: CheckCircle, label: 'Completed', value: 0, color: 'text-emerald-400', bg: 'bg-emerald-600/10' },
        ].map(({ icon: Icon, label, value, color, bg }) => (
          <div key={label} className="glass-light p-6 flex items-center gap-4 hover:scale-[1.02] transition-transform duration-200">
            <div className={`w-12 h-12 rounded-xl ${bg} flex items-center justify-center`}>
              <Icon className={`w-6 h-6 ${color}`} />
            </div>
            <div>
              <p className="text-2xl font-bold">{value}</p>
              <p className="text-sm text-surface-400">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Upcoming Exams */}
      <div className="glass p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-primary-400" /> Upcoming Exams
        </h2>
        {upcomingExams.length === 0 ? (
          <p className="text-surface-500 text-center py-8">No upcoming exams scheduled.</p>
        ) : (
          <div className="space-y-3">
            {upcomingExams.map((exam) => (
              <div key={exam.id} className="glass-light p-4 flex items-center justify-between hover:bg-surface-800/50 transition-colors rounded-xl">
                <div>
                  <h3 className="font-medium">{exam.title}</h3>
                  <p className="text-sm text-surface-400">{exam.duration_minutes} min • {exam.max_attempts} attempt(s)</p>
                </div>
                <a href={`/student/system-check/${exam.id}`}
                  className="px-4 py-2 bg-primary-600/20 text-primary-300 rounded-lg text-sm font-medium hover:bg-primary-600/30 transition-colors border border-primary-500/30">
                  Start Exam
                </a>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Privacy Notice */}
      <div className="glass-light p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-amber-300">Privacy-First Proctoring</p>
          <p className="text-xs text-surface-400 mt-1">
            BEZP processes video locally on your device. Only detection event metadata is sent to the server.
            Video clips are uploaded only when an anomaly is detected. No continuous video streaming occurs.
          </p>
        </div>
      </div>
    </div>
  )
}
