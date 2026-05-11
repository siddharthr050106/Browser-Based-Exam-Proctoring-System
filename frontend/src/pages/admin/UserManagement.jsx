import { Users, Plus, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'

export default function UserManagement() {
  const [showForm, setShowForm] = useState(false)
  const users = [
    { id: '1', full_name: 'Alice Johnson', email: 'alice@uni.edu', role: 'student', is_active: true },
    { id: '2', full_name: 'Dr. Smith', email: 'smith@uni.edu', role: 'proctor', is_active: true },
    { id: '3', full_name: 'Admin User', email: 'admin@uni.edu', role: 'admin', is_active: true },
  ]
  const roleColors = { student: 'bg-primary-500/10 text-primary-400', proctor: 'bg-emerald-500/10 text-emerald-400', admin: 'bg-amber-500/10 text-amber-400' }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">User Management</h1>
          <p className="text-surface-400 mt-1">Manage students, proctors, and admins.</p>
        </div>
        <div className="flex gap-2">
          <button className="px-4 py-2 glass-light text-surface-300 rounded-xl hover:bg-surface-700 transition-colors flex items-center gap-2 text-sm"><Upload className="w-4 h-4" /> CSV Import</button>
          <button onClick={() => setShowForm(!showForm)} className="px-4 py-2 bg-gradient-to-r from-primary-600 to-primary-500 text-white rounded-xl font-medium flex items-center gap-2"><Plus className="w-4 h-4" /> Add User</button>
        </div>
      </div>
      <div className="glass overflow-hidden">
        <table className="w-full">
          <thead><tr className="border-b border-surface-800">
            <th className="text-left text-xs font-semibold text-surface-400 uppercase px-6 py-4">Name</th>
            <th className="text-left text-xs font-semibold text-surface-400 uppercase px-6 py-4">Email</th>
            <th className="text-left text-xs font-semibold text-surface-400 uppercase px-6 py-4">Role</th>
            <th className="text-left text-xs font-semibold text-surface-400 uppercase px-6 py-4">Status</th>
            <th className="px-6 py-4"></th>
          </tr></thead>
          <tbody>{users.map(u => (
            <tr key={u.id} className="border-b border-surface-800/50 hover:bg-surface-800/30 transition-colors">
              <td className="px-6 py-4 font-medium">{u.full_name}</td>
              <td className="px-6 py-4 text-sm text-surface-400">{u.email}</td>
              <td className="px-6 py-4"><span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${roleColors[u.role]}`}>{u.role}</span></td>
              <td className="px-6 py-4"><span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400">Active</span></td>
              <td className="px-6 py-4 text-right"><button className="p-2 hover:bg-danger/20 text-surface-500 hover:text-danger transition-colors rounded-lg"><Trash2 className="w-4 h-4" /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  )
}
