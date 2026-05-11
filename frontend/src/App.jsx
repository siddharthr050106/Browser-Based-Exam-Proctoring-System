import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'

// Layouts
import StudentLayout from './layouts/StudentLayout'
import ProctorLayout from './layouts/ProctorLayout'
import AdminLayout from './layouts/AdminLayout'

// Auth
import LoginPage from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'

// Student
import StudentDashboard from './pages/student/StudentDashboard'
import ExamList from './pages/student/ExamList'
import SystemCheck from './pages/student/SystemCheck'
import ExamSession from './pages/student/ExamSession'
import StudentResults from './pages/student/StudentResults'

// Proctor
import ProctorDashboard from './pages/proctor/ProctorDashboard'
import SessionMonitor from './pages/proctor/SessionMonitor'
import ClipReview from './pages/proctor/ClipReview'

// Admin
import AdminDashboard from './pages/admin/AdminDashboard'
import ExamManagement from './pages/admin/ExamManagement'
import UserManagement from './pages/admin/UserManagement'
import Reports from './pages/admin/Reports'

function ProtectedRoute({ children, allowedRoles }) {
  const { user, isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (allowedRoles && !allowedRoles.includes(user?.role)) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      {/* Auth */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Student Routes */}
      <Route path="/student" element={
        <ProtectedRoute allowedRoles={['student']}>
          <StudentLayout />
        </ProtectedRoute>
      }>
        <Route index element={<StudentDashboard />} />
        <Route path="exams" element={<ExamList />} />
        <Route path="system-check/:examId" element={<SystemCheck />} />
        <Route path="exam/:sessionId" element={<ExamSession />} />
        <Route path="results" element={<StudentResults />} />
      </Route>

      {/* Proctor Routes */}
      <Route path="/proctor" element={
        <ProtectedRoute allowedRoles={['proctor', 'admin']}>
          <ProctorLayout />
        </ProtectedRoute>
      }>
        <Route index element={<ProctorDashboard />} />
        <Route path="session/:sessionId" element={<SessionMonitor />} />
        <Route path="clip/:eventId" element={<ClipReview />} />
      </Route>

      {/* Admin Routes */}
      <Route path="/admin" element={
        <ProtectedRoute allowedRoles={['admin']}>
          <AdminLayout />
        </ProtectedRoute>
      }>
        <Route index element={<AdminDashboard />} />
        <Route path="exams" element={<ExamManagement />} />
        <Route path="users" element={<UserManagement />} />
        <Route path="reports" element={<Reports />} />
      </Route>

      {/* Default */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
