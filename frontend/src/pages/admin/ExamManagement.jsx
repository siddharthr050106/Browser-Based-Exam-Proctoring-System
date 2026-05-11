import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { examApi } from '../../lib/api'
import { Plus, Pencil, Trash2, X, Save, Clock, Users } from 'lucide-react'

export default function ExamManagement() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingExam, setEditingExam] = useState(null)
  const [form, setForm] = useState({ title: '', description: '', duration_minutes: 60, max_attempts: 1, fl_enabled: false })

  const { data, isLoading } = useQuery({ queryKey: ['exams'], queryFn: examApi.list })
  const exams = data?.exams || []

  const createMutation = useMutation({
    mutationFn: examApi.create,
    onSuccess: () => { queryClient.invalidateQueries(['exams']); resetForm() },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => examApi.update(id, data),
    onSuccess: () => { queryClient.invalidateQueries(['exams']); resetForm() },
  })

  const deleteMutation = useMutation({
    mutationFn: examApi.delete,
    onSuccess: () => queryClient.invalidateQueries(['exams']),
  })

  function resetForm() {
    setForm({ title: '', description: '', duration_minutes: 60, max_attempts: 1, fl_enabled: false })
    setEditingExam(null)
    setShowForm(false)
  }

  function handleEdit(exam) {
    setEditingExam(exam)
    setForm({
      title: exam.title,
      description: exam.description || '',
      duration_minutes: exam.duration_minutes,
      max_attempts: exam.max_attempts,
      fl_enabled: exam.fl_enabled,
    })
    setShowForm(true)
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (editingExam) {
      updateMutation.mutate({ id: editingExam.id, data: form })
    } else {
      createMutation.mutate(form)
    }
  }

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Exam Management</h1>
          <p className="text-surface-400 mt-1">Create, edit, and manage examinations.</p>
        </div>
        <button
          onClick={() => { resetForm(); setShowForm(true) }}
          className="px-4 py-2 bg-gradient-to-r from-primary-600 to-primary-500 text-white rounded-xl font-medium flex items-center gap-2 hover:from-primary-500 hover:to-primary-400 transition-all shadow-lg shadow-primary-600/20"
        >
          <Plus className="w-4 h-4" /> Create Exam
        </button>
      </div>

      {/* Form Modal */}
      {showForm && (
        <div className="glass p-6 animate-fade-in">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{editingExam ? 'Edit Exam' : 'Create New Exam'}</h2>
            <button onClick={resetForm} className="text-surface-500 hover:text-surface-200"><X className="w-5 h-5" /></button>
          </div>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-surface-300 mb-1.5">Title</label>
              <input value={form.title} onChange={update('title')} required
                className="w-full px-4 py-3 bg-surface-800/50 border border-surface-700 rounded-xl text-surface-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all"
                placeholder="Exam title" />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-surface-300 mb-1.5">Description</label>
              <textarea value={form.description} onChange={update('description')} rows={3}
                className="w-full px-4 py-3 bg-surface-800/50 border border-surface-700 rounded-xl text-surface-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all resize-none"
                placeholder="Optional description" />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-300 mb-1.5">Duration (minutes)</label>
              <input type="number" value={form.duration_minutes} onChange={update('duration_minutes')} min={1}
                className="w-full px-4 py-3 bg-surface-800/50 border border-surface-700 rounded-xl text-surface-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all" />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-300 mb-1.5">Max Attempts</label>
              <input type="number" value={form.max_attempts} onChange={update('max_attempts')} min={1}
                className="w-full px-4 py-3 bg-surface-800/50 border border-surface-700 rounded-xl text-surface-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-all" />
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="fl-enabled" checked={form.fl_enabled} onChange={update('fl_enabled')} className="w-4 h-4 accent-primary-500" />
              <label htmlFor="fl-enabled" className="text-sm text-surface-300">Enable Federated Learning</label>
            </div>
            <div className="md:col-span-2 flex justify-end gap-3">
              <button type="button" onClick={resetForm} className="px-4 py-2 glass-light text-surface-300 rounded-xl hover:bg-surface-700 transition-colors">Cancel</button>
              <button type="submit" className="px-6 py-2 bg-primary-600 text-white rounded-xl font-medium flex items-center gap-2 hover:bg-primary-500 transition-colors">
                <Save className="w-4 h-4" /> {editingExam ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Exam List */}
      {isLoading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" /></div>
      ) : (
        <div className="space-y-3">
          {exams.map(exam => (
            <div key={exam.id} className="glass-light p-5 flex items-center justify-between">
              <div className="flex-1">
                <h3 className="font-semibold">{exam.title}</h3>
                <div className="flex items-center gap-4 mt-1">
                  <span className="text-xs text-surface-500 flex items-center gap-1"><Clock className="w-3 h-3" /> {exam.duration_minutes} min</span>
                  <span className="text-xs text-surface-500 flex items-center gap-1"><Users className="w-3 h-3" /> {exam.max_attempts} attempts</span>
                  {exam.fl_enabled && <span className="text-xs px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-400 border border-primary-500/20">FL Enabled</span>}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${exam.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-surface-700 text-surface-500'}`}>{exam.is_active ? 'Active' : 'Inactive'}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleEdit(exam)} className="p-2 glass-light hover:bg-surface-700 transition-colors rounded-lg"><Pencil className="w-4 h-4" /></button>
                <button onClick={() => deleteMutation.mutate(exam.id)} className="p-2 glass-light hover:bg-danger/20 text-danger transition-colors rounded-lg"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
