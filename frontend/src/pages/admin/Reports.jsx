import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { FileText, Download } from 'lucide-react'

export default function Reports() {
  const weeklyData = [
    { day: 'Mon', flags: 5, warnings: 12 },
    { day: 'Tue', flags: 3, warnings: 8 },
    { day: 'Wed', flags: 7, warnings: 15 },
    { day: 'Thu', flags: 2, warnings: 6 },
    { day: 'Fri', flags: 4, warnings: 10 },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Reports</h1>
          <p className="text-surface-400 mt-1">Aggregate flag statistics and detection performance.</p>
        </div>
        <button className="px-4 py-2 glass-light text-surface-300 rounded-xl hover:bg-surface-700 transition-colors flex items-center gap-2 text-sm">
          <Download className="w-4 h-4" /> Export Report
        </button>
      </div>

      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">Weekly Detection Activity</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={weeklyData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 12 }} />
            <YAxis tick={{ fill: '#64748b', fontSize: 12 }} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px' }} />
            <Bar dataKey="warnings" fill="#f59e0b" radius={[4, 4, 0, 0]} name="Warnings" />
            <Bar dataKey="flags" fill="#ef4444" radius={[4, 4, 0, 0]} name="Flags" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'False Positive Rate', value: '12%', desc: 'Based on proctor reviews' },
          { label: 'Avg Flags/Session', value: '1.3', desc: 'Across all exams' },
          { label: 'Model Accuracy', value: '—', desc: 'ML model not yet deployed' },
        ].map(({ label, value, desc }) => (
          <div key={label} className="glass-light p-5 text-center">
            <p className="text-3xl font-bold gradient-text">{value}</p>
            <p className="text-sm font-medium mt-1">{label}</p>
            <p className="text-xs text-surface-500 mt-0.5">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
