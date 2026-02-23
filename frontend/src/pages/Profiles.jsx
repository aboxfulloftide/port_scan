import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Pencil, Trash2, X } from 'lucide-react'

const DEFAULT_NAMES = ['Quick Ping', 'Standard', 'Full Deep Scan']

const DEFAULTS = {
  name: '', port_range: '1-1024',
  enable_icmp: true, enable_tcp_syn: true, enable_udp: false,
  enable_fingerprint: true, enable_banner: false, enable_screenshot: false,
  max_concurrency: 10, rate_limit: 1000, timeout_sec: 30,
}

function ProfileModal({ profile, onClose }) {
  const qc = useQueryClient()
  const isEdit = !!profile
  const [form, setForm] = useState(isEdit ? {
    name: profile.name,
    port_range: profile.port_range,
    enable_icmp: profile.enable_icmp,
    enable_tcp_syn: profile.enable_tcp_syn,
    enable_udp: profile.enable_udp,
    enable_fingerprint: profile.enable_fingerprint,
    enable_banner: profile.enable_banner,
    enable_screenshot: profile.enable_screenshot,
    max_concurrency: profile.max_concurrency,
    rate_limit: profile.rate_limit,
    timeout_sec: profile.timeout_sec,
  } : { ...DEFAULTS })
  const [error, setError] = useState(null)

  const save = useMutation({
    mutationFn: (data) =>
      isEdit
        ? api.patch(`/profiles/${profile.id}`, data).then(r => r.data)
        : api.post('/profiles', data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); onClose() },
    onError: (e) => setError(e.response?.data?.detail ?? 'Save failed'),
  })

  const toggle = (key) => setForm(f => ({ ...f, [key]: !f[key] }))

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 overflow-y-auto py-8">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">{isEdit ? 'Edit Profile' : 'New Profile'}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400 hover:text-white" /></button>
        </div>
        {error && <div className="text-red-400 text-sm mb-3">{error}</div>}
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Name</label>
              <input
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Port Range</label>
              <input
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.port_range}
                onChange={e => setForm(f => ({ ...f, port_range: e.target.value }))}
                placeholder="1-65535"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {['enable_icmp','enable_tcp_syn','enable_udp','enable_fingerprint','enable_banner','enable_screenshot'].map(key => (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={form[key]}
                  onChange={() => toggle(key)}
                />
                <span className="text-xs text-gray-300">{key.replace('enable_', '')}</span>
              </label>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Max Concurrency</label>
              <input
                type="number"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.max_concurrency}
                onChange={e => setForm(f => ({ ...f, max_concurrency: +e.target.value }))}
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Rate Limit</label>
              <input
                type="number"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.rate_limit}
                onChange={e => setForm(f => ({ ...f, rate_limit: +e.target.value }))}
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Timeout (sec)</label>
              <input
                type="number"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.timeout_sec}
                onChange={e => setForm(f => ({ ...f, timeout_sec: +e.target.value }))}
              />
            </div>
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

export default function Profiles() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [deleteId, setDeleteId] = useState(null)

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => api.get('/profiles').then(r => r.data),
  })

  const del = useMutation({
    mutationFn: (id) => api.delete(`/profiles/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); setDeleteId(null) },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Scan Profiles</h1>
        <button
          onClick={() => setModal('new')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
        >
          <Plus className="w-4 h-4" /> New Profile
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.map(p => (
            <div key={p.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-white font-medium">{p.name}</h3>
                  <div className="text-xs text-gray-400 mt-0.5">Ports: {p.port_range}</div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setModal(p)} className="text-gray-400 hover:text-white">
                    <Pencil className="w-4 h-4" />
                  </button>
                  {!DEFAULT_NAMES.includes(p.name) && (
                    <button onClick={() => setDeleteId(p.id)} className="text-gray-400 hover:text-red-400">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                {['icmp','tcp_syn','udp','fingerprint','banner','screenshot'].map(key => {
                  const val = p[`enable_${key}`]
                  return (
                    <span key={key} className={`text-xs px-2 py-0.5 rounded-full ${val ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-500'}`}>
                      {key}
                    </span>
                  )
                })}
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div><span className="text-gray-500">concurrency</span><div className="text-gray-300">{p.max_concurrency}</div></div>
                <div><span className="text-gray-500">rate</span><div className="text-gray-300">{p.rate_limit}</div></div>
                <div><span className="text-gray-500">timeout</span><div className="text-gray-300">{p.timeout_sec}s</div></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <ProfileModal profile={modal === 'new' ? null : modal} onClose={() => setModal(null)} />
      )}

      {deleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-80">
            <h2 className="text-white font-semibold mb-2">Delete Profile?</h2>
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
