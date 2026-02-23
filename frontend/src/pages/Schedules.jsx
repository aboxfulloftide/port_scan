import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Trash2, X, ToggleLeft, ToggleRight } from 'lucide-react'
import { formatDate } from '../utils/format'

function ScheduleModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    subnet_id: '',
    profile_id: '',
    cron_expression: '0 2 * * *',
    is_active: true,
  })
  const [error, setError] = useState(null)

  const { data: subnets = [] } = useQuery({
    queryKey: ['subnets'],
    queryFn: () => api.get('/subnets').then(r => r.data),
  })
  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => api.get('/profiles').then(r => r.data),
  })

  const save = useMutation({
    mutationFn: (data) => api.post('/schedules', data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedules'] }); onClose() },
    onError: (e) => setError(e.response?.data?.detail ?? 'Save failed'),
  })

  const handleSubmit = () => {
    if (!form.subnet_id || !form.profile_id) { setError('Select a subnet and profile'); return }
    save.mutate({
      subnet_ids: [+form.subnet_id],
      profile_id: +form.profile_id,
      cron_expression: form.cron_expression,
      is_active: form.is_active,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">New Schedule</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400 hover:text-white" /></button>
        </div>
        {error && <div className="text-red-400 text-sm mb-3">{error}</div>}
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Subnet</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.subnet_id}
              onChange={e => setForm(f => ({ ...f, subnet_id: e.target.value }))}
            >
              <option value="">Select subnet...</option>
              {subnets.map(s => <option key={s.id} value={s.id}>{s.label} ({s.cidr})</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Profile</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.profile_id}
              onChange={e => setForm(f => ({ ...f, profile_id: e.target.value }))}
            >
              <option value="">Select profile...</option>
              {profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Cron Expression</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-blue-500"
              value={form.cron_expression}
              onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))}
              placeholder="0 2 * * *"
            />
            <div className="text-xs text-gray-500 mt-1">min hour day month weekday</div>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
            />
            <span className="text-sm text-gray-300">Active</span>
          </label>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={save.isPending}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
          >
            {save.isPending ? 'Saving...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Schedules() {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [deleteId, setDeleteId] = useState(null)

  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ['schedules'],
    queryFn: () => api.get('/schedules').then(r => r.data),
  })

  const toggle = useMutation({
    mutationFn: (s) => api.patch(`/schedules/${s.id}`, { is_active: !s.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  })

  const del = useMutation({
    mutationFn: (id) => api.delete(`/schedules/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedules'] }); setDeleteId(null) },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Schedules</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
        >
          <Plus className="w-4 h-4" /> New Schedule
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left text-gray-400 font-medium px-4 py-3">Profile</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Cron</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Next Run</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Status</th>
                <th className="text-right text-gray-400 font-medium px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map(s => (
                <tr key={s.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-white">{s.profile_name ?? `Profile #${s.profile_id}`}</td>
                  <td className="px-4 py-3 text-gray-300 font-mono">{s.cron_expression}</td>
                  <td className="px-4 py-3 text-gray-400">{s.next_run_at ? formatDate(s.next_run_at) : '—'}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggle.mutate(s)} className="flex items-center gap-1.5 text-sm">
                      {s.is_active
                        ? <><ToggleRight className="w-5 h-5 text-green-400" /><span className="text-green-400">Active</span></>
                        : <><ToggleLeft className="w-5 h-5 text-gray-500" /><span className="text-gray-500">Inactive</span></>
                      }
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => setDeleteId(s.id)} className="text-gray-400 hover:text-red-400">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {schedules.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No schedules configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showModal && <ScheduleModal onClose={() => setShowModal(false)} />}

      {deleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-80">
            <h2 className="text-white font-semibold mb-2">Delete Schedule?</h2>
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
