import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { examApi } from '../../lib/api'
import { BookOpen, Clock, Users, ChevronRight } from 'lucide-react'

export default function ExamList() {
  const { data, isLoading } = useQuery({ queryKey: ['exams'], queryFn: examApi.list })
  const exams = data?.exams || []

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Available Exams</h1>
          <p className="text-surface-400 mt-1">Select an exam to begin your proctored session.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
        </div>
      ) : exams.length === 0 ? (
        <div className="glass p-12 text-center">
          <BookOpen className="w-12 h-12 text-surface-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-surface-300">No Exams Available</h3>
          <p className="text-surface-500 mt-1">Check back later for scheduled exams.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {exams.map((exam) => (
            <Link
              key={exam.id}
              to={`/student/system-check/${exam.id}`}
              className="glass-light p-6 hover:bg-surface-800/60 transition-all duration-200 group hover:scale-[1.01] block"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold group-hover:text-primary-300 transition-colors">{exam.title}</h3>
                  {exam.description && (
                    <p className="text-sm text-surface-400 mt-1 line-clamp-2">{exam.description}</p>
                  )}
                  <div className="flex items-center gap-4 mt-3">
                    <span className="flex items-center gap-1.5 text-xs text-surface-500">
                      <Clock className="w-3.5 h-3.5" /> {exam.duration_minutes} min
                    </span>
                    <span className="flex items-center gap-1.5 text-xs text-surface-500">
                      <Users className="w-3.5 h-3.5" /> {exam.max_attempts} attempt(s)
                    </span>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-surface-600 group-hover:text-primary-400 group-hover:translate-x-1 transition-all" />
              </div>
              {exam.is_active && (
                <div className="mt-3 inline-block px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Active
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
