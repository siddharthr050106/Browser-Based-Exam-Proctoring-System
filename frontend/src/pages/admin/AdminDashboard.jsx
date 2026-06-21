import { useQuery } from '@tanstack/react-query'
import { examApi, sessionApi } from '../../lib/api'
import { BarChart3, BookOpen, Users, AlertTriangle, Activity, TrendingUp } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444']

export default function AdminDashboard() {
  const { data: examsData } = useQuery({ queryKey: ['exams'], queryFn: examApi.list })
  const { data: sessionsData } = useQuery({ queryKey: ['active-sessions'], queryFn: sessionApi.listActive })

  const exams = examsData?.exams || []
  const sessions = sessionsData?.sessions || []

  // Mock data for charts (would come from reporting API)
  const eventTypeData = [
    { name: 'Tab Switch', count: 42 },
    { name: 'Phone', count: 8 },
    { name: 'Multi-Person', count: 5 },
    { name: 'Gaze Anomaly', count: 15 },
    { name: 'No Face', count: 12 },
  ]

  const tierDistribution = [
    { name: 'Info', value: 60 },
    { name: 'Warning', value: 25 },
    { name: 'Flag', value: 12 },
    { name: 'Critical', value: 3 },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <BarChart3 className="w-7 h-7 text-amber-400" /> Admin Dashboard
        </h1>
        <p className="text-surface-400 mt-1">System overview and aggregate statistics.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { icon: BookOpen, label: 'Total Exams', value: exams.length, color: 'text-primary-400', bg: 'bg-primary-600/10' },
          { icon: Activity, label: 'Active Sessions', value: sessions.length, color: 'text-emerald-400', bg: 'bg-emerald-600/10' },
          { icon: Users, label: 'Users', value: '—', color: 'text-amber-400', bg: 'bg-amber-600/10' },
          { icon: AlertTriangle, label: 'Total Flags', value: '—', color: 'text-danger', bg: 'bg-danger/10' },
        ].map(({ icon: Icon, label, value, color, bg }) => (
          <div key={label} className="glass-light p-5 flex items-center gap-4 hover:scale-[1.02] transition-transform">
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

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Event Type Distribution */}
        <div className="glass p-6">
          <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">
            Events by Type
          </h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={eventTypeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px' }} />
              <Bar dataKey="count" fill="#6366f1" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Tier Distribution */}
        <div className="glass p-6">
          <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">
            Tier Distribution
          </h2>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={tierDistribution} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {tierDistribution.map((_, index) => (
                  <Cell key={index} fill={COLORS[index]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* System Health */}
      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">
          System Health
        </h2>
        <div className="grid grid-cols-5 gap-4">
          {[
            { label: 'API Server', status: 'healthy' },
            { label: 'PostgreSQL', status: 'healthy' },
            { label: 'Redis', status: 'healthy' },
            { label: 'Detection Sidecar', status: 'healthy' },
            { label: 'Audio Service', status: 'healthy' },
          ].map(({ label, status }) => (
            <div key={label} className="glass-light p-4 flex items-center gap-3">
              <div className={`status-dot ${status === 'healthy' ? 'green' : 'red'}`} />
              <div>
                <p className="text-sm font-medium">{label}</p>
                <p className="text-xs text-surface-500 capitalize">{status}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
