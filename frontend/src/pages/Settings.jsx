import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { Plus, Trash2, X } from 'lucide-react'

const ROLES = ['viewer', 'operator', 'admin']

const roleColor = (role) => ({
  admin: 'bg-red-500/20 text-red-400',
  operator: 'bg-blue-500/20 text-blue-400',
  viewer: 'bg-gray-500/20 text-gray-400',
}[role] ?? 'bg-gray-500/20 text-gray-400')

function UserModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ username: '', password: '', role: 'viewer' })
  const [error, setError] = useState(null)

  const create = useMutation({
    mutationFn: (data) => api.post('/users', data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); onClose() },
    onError: (e) => setError(e.response?.data?.detail ?? 'Create failed'),
  })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">New User</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400 hover:text-white" /></button>
        </div>
        {error && <div className="text-red-400 text-sm mb-3">{error}</div>}
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Username</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Password</label>
            <input
              type="password"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Role</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
            >
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
          <button
            onClick={() => create.mutate(form)}
            disabled={create.isPending}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
          >
            {create.isPending ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [deleteId, setDeleteId] = useState(null)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
    enabled: user?.role === 'admin',
  })

  const del = useMutation({
    mutationFn: (id) => api.delete(`/users/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setDeleteId(null) },
  })

  if (user?.role !== 'admin') {
    return (
      <div>
        <h1 className="text-xl font-semibold text-white mb-4">Settings</h1>
        <div className="text-gray-400 text-sm">Admin access required.</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Settings — Users</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
        >
          <Plus className="w-4 h-4" /> New User
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left text-gray-400 font-medium px-4 py-3">Username</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Role</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Last Login</th>
                <th className="text-right text-gray-400 font-medium px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-white">{u.username}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${roleColor(u.role)}`}>{u.role}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                  <td className="px-4 py-3 text-right">
                    {u.id !== user?.id && (
                      <button onClick={() => setDeleteId(u.id)} className="text-gray-400 hover:text-red-400">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && <UserModal onClose={() => setShowModal(false)} />}

      {deleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-80">
            <h2 className="text-white font-semibold mb-2">Delete User?</h2>
            <p className="text-gray-400 text-sm mb-4">This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteId(null)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button
                onClick={() => del.mutate(deleteId)}
                disabled={del.isPending}
                className="px-4 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
