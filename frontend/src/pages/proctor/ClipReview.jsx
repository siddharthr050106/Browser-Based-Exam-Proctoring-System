import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clipApi } from '../../lib/api'
import { ArrowLeft, CheckCircle, XCircle, Loader2 } from 'lucide-react'

export default function ClipReview() {
  const { eventId } = useParams()
  const [verdict, setVerdict] = useState(null) // 'confirmed' | 'false_positive'

  const { data, isLoading, error } = useQuery({
    queryKey: ['clip', eventId],
    queryFn: () => clipApi.get(eventId),
  })

  const handleVerdict = (v) => {
    setVerdict(v)
    // TODO: POST to proctor_reviews API
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div className="flex items-center gap-4">
        <Link to="/proctor" className="glass-light p-2 rounded-xl hover:bg-surface-700 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-xl font-bold">Video Clip Review</h1>
          <p className="text-xs text-surface-500 font-mono">Event: {eventId?.slice(0, 8)}...</p>
        </div>
      </div>

      {/* Video Player */}
      <div className="glass p-6">
        <div className="aspect-video bg-surface-900 rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-8 h-8 text-surface-500 animate-spin" />
            </div>
          ) : error || !data?.clip_url ? (
            <div className="flex items-center justify-center h-full text-surface-500">
              <p>No clip available for this event</p>
            </div>
          ) : (
            <video
              src={data.clip_url}
              controls
              className="w-full h-full object-contain"
              autoPlay={false}
            />
          )}
        </div>
      </div>

      {/* Verdict Buttons */}
      <div className="glass p-6">
        <h2 className="text-sm font-semibold text-surface-400 uppercase tracking-wider mb-4">Review Verdict</h2>
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => handleVerdict('confirmed')}
            className={`p-4 rounded-xl border-2 transition-all flex items-center justify-center gap-2 font-medium ${
              verdict === 'confirmed'
                ? 'border-danger bg-danger/10 text-danger'
                : 'border-surface-700 hover:border-danger/50 text-surface-300'
            }`}
          >
            <XCircle className="w-5 h-5" /> Confirm Violation
          </button>
          <button
            onClick={() => handleVerdict('false_positive')}
            className={`p-4 rounded-xl border-2 transition-all flex items-center justify-center gap-2 font-medium ${
              verdict === 'false_positive'
                ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400'
                : 'border-surface-700 hover:border-emerald-500/50 text-surface-300'
            }`}
          >
            <CheckCircle className="w-5 h-5" /> False Positive
          </button>
        </div>
        {verdict && (
          <p className="text-center text-sm text-surface-400 mt-4 animate-fade-in">
            Verdict recorded: <span className="font-medium text-surface-200">{verdict.replace('_', ' ')}</span>
          </p>
        )}
      </div>
    </div>
  )
}
