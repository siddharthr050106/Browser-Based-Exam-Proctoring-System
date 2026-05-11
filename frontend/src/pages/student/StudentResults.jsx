import { CheckCircle, BookOpen } from 'lucide-react'

export default function StudentResults() {
  // Placeholder — results data would come from session/event APIs
  const results = []

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Exam Results</h1>
        <p className="text-surface-400 mt-1">View your completed exam scores and attempt history.</p>
      </div>

      {results.length === 0 ? (
        <div className="glass p-12 text-center">
          <BookOpen className="w-12 h-12 text-surface-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-surface-300">No Results Yet</h3>
          <p className="text-surface-500 mt-1">Complete an exam to see your results here.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {results.map((r, i) => (
            <div key={i} className="glass-light p-6 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <CheckCircle className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <h3 className="font-medium">{r.examTitle}</h3>
                  <p className="text-sm text-surface-400">{r.date} • {r.duration}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-emerald-400">{r.score}%</p>
                <p className="text-xs text-surface-500">{r.flags} flags raised</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
