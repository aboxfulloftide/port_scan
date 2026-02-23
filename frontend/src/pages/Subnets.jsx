import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Pencil, Trash2, X } from 'lucide-react'

function SubnetModal({ subnet, onClose }) {
  const qc = useQueryClient()
  const isEdit = !!subnet
  const [form, setForm] = useState({
    cidr: subnet?.cidr ?? '',
    label: subnet?.label ?? '',
    description: subnet?.description ?? '',
  })
  const [error, setError] = useState(null)

  const save = useMutation({
    mutationFn: (data) =>
      isEdit
        ? api.patch(`/subnets/${subnet.id}`, data).then(r => r.data)
        : api.post('/subnets', data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['subnets'] }); onClose() },
    onError: (e) => setError(e.response?.data?.detail ?? 'Save failed'),
  })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">{isEdit ? 'Edit Subnet' : 'Add Subnet'}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400 hover:text-white" /></button>
        </div>
        {error && <div className="text-red-400 text-sm mb-3">{error}</div>}
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">CIDR</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.cidr}
              onChange={e => setForm(f => ({ ...f, cidr: e.target.value }))}
              placeholder="192.168.1.0/24"
              disabled={isEdit}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Label</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.label}
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
              placeholder="Home LAN"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Description</label>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              rows={3}
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
          <button
            onClick={() => save.mutate(form)}
            disabled={save.isPending}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
          >
            {save.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Subnets() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null) // null | 'add' | subnet object
  const [deleteId, setDeleteId] = useState(null)

  const { data: subnets = [], isLoading } = useQuery({
    queryKey: ['subnets'],
    queryFn: () => api.get('/subnets').then(r => r.data),
  })

  const del = useMutation({
    mutationFn: (id) => api.delete(`/subnets/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['subnets'] }); setDeleteId(null) },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Subnets</h1>
        <button
          onClick={() => setModal('add')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
        >
          <Plus className="w-4 h-4" /> Add Subnet
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left text-gray-400 font-medium px-4 py-3">CIDR</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Label</th>
                <th className="text-left text-gray-400 font-medium px-4 py-3">Description</th>
                <th className="text-right text-gray-400 font-medium px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {subnets.map(s => (
                <tr key={s.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-white font-mono">{s.cidr}</td>
                  <td className="px-4 py-3 text-gray-300">{s.label}</td>
                  <td className="px-4 py-3 text-gray-400">{s.description}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => setModal(s)} className="text-gray-400 hover:text-white mr-3">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => setDeleteId(s.id)} className="text-gray-400 hover:text-red-400">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {subnets.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500">No subnets configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(modal === 'add' || (modal && modal !== 'add')) && (
        <SubnetModal subnet={modal === 'add' ? null : modal} onClose={() => setModal(null)} />
      )}

      {deleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-80">
            <h2 className="text-white font-semibold mb-2">Delete Subnet?</h2>
            <p className="text-gray-400 text-sm mb-4">This will remove the subnet and cannot be undone.</p>
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
