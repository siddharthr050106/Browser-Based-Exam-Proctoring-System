import { useAuthStore } from '../stores/authStore'

const BASE = '/api'

async function request(path, options = {}) {
  const token = useAuthStore.getState().token
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    // FastAPI returns validation errors as detail: [{msg: "..."}, ...]
    let message = 'Request failed'
    if (typeof err.detail === 'string') {
      message = err.detail
    } else if (Array.isArray(err.detail) && err.detail.length > 0) {
      message = err.detail.map(e => e.msg || e.message || JSON.stringify(e)).join('. ')
    } else if (err.detail) {
      message = JSON.stringify(err.detail)
    }
    throw new Error(message)
  }

  if (res.status === 204) return null
  return res.json()
}

// ── Auth ──
export const authApi = {
  login: (data) => request('/users/login', { method: 'POST', body: JSON.stringify(data) }),
  register: (data) => request('/users/register', { method: 'POST', body: JSON.stringify(data) }),
}

// ── Exams ──
export const examApi = {
  list: () => request('/exams/'),
  get: (id) => request(`/exams/${id}`),
  create: (data) => request('/exams/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/exams/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id) => request(`/exams/${id}`, { method: 'DELETE' }),
}

// ── Sessions ──
export const sessionApi = {
  start: (data) => request('/sessions/start', { method: 'POST', body: JSON.stringify(data) }),
  get: (id) => request(`/sessions/${id}`),
  end: (id) => request(`/sessions/${id}/end`, { method: 'POST' }),
  update: (id, data) => request(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  listActive: () => request('/sessions/'),
  warn: (id, message) => request(`/sessions/${id}/warn`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  }),
  terminate: (id, reason) => request(`/sessions/${id}/terminate`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  }),
  review: (id, verdict, notes) => request(`/sessions/${id}/review`, {
    method: 'POST',
    body: JSON.stringify({ verdict, notes }),
  }),
}

// ── Events ──
export const eventApi = {
  create: (data) => request('/events/', { method: 'POST', body: JSON.stringify(data) }),
  listForSession: (sessionId) => request(`/events/${sessionId}`),
  gazeSnapshots: (sessionId) => request(`/events/gaze/${sessionId}`),
}

// ── Clips ──
export const clipApi = {
  upload: async (sessionId, eventId, blob) => {
    const token = useAuthStore.getState().token
    const form = new FormData()
    form.append('clip', blob, 'clip.webm')
    const res = await fetch(`${BASE}/clips/${sessionId}/${eventId}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
    if (!res.ok) throw new Error('Clip upload failed')
    return res.json()
  },
  get: (eventId) => request(`/clips/${eventId}`),
}
