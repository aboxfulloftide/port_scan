import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Pencil, Trash2, X, Wifi, Play, CheckCircle, AlertCircle, Clock } from 'lucide-react'

const BRAND_LABELS = { tplink_deco: 'TP-Link Deco', netgear: 'Netgear' }

const DEFAULTS = {
  name: '',
  brand: 'tplink_deco',
  url: 'http://192.168.1.1',
  username: 'admin',
  password: '',
  enabled: true,
  scrape_interval_min: 5,
  notes: '',
}

function APModal({ ap, onClose }) {
  const qc = useQueryClient()
  const isEdit = !!ap
  const [form, setForm] = useState(isEdit ? {
    name: ap.name,
    brand: ap.brand,
    url: ap.url,
    username: ap.username ?? '',
    password: '',
    enabled: ap.enabled,
    scrape_interval_min: ap.scrape_interval_min,
    notes: ap.notes ?? '',
  } : { ...DEFAULTS })
  const [error, setError] = useState(null)

  const save = useMutation({
    mutationFn: (data) => {
      const payload = { ...data }
      // Don't send empty password on edit — means "don't change it"
      if (isEdit && !payload.password) delete payload.password
      return isEdit
        ? api.patch(`/wireless-aps/${ap.id}`, payload).then(r => r.data)
        : api.post('/wireless-aps', payload).then(r => r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wireless-aps'] }); onClose() },
    onError: (e) => setError(e.response?.data?.detail ?? 'Save failed'),
  })

  const f = (key) => (e) => setForm(p => ({ ...p, [key]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 py-8">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">{isEdit ? 'Edit AP' : 'Add Wireless AP'}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-400 hover:text-white" /></button>
        </div>
        {error && <div className="text-red-400 text-sm mb-3">{error}</div>}

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Name</label>
              <input
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.name} onChange={f('name')} placeholder="Living Room Deco"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Brand</label>
              <select
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.brand} onChange={f('brand')}
              >
                <option value="tplink_deco">TP-Link Deco</option>
                <option value="netgear">Netgear</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">URL</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              value={form.url} onChange={f('url')} placeholder="http://192.168.1.1"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Username</label>
              <input
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.username} onChange={f('username')} placeholder="admin"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">
                Password {isEdit && <span className="text-gray-500">(leave blank to keep)</span>}
              </label>
              <input
                type="password"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.password} onChange={f('password')}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Scrape Interval (min)</label>
              <input
                type="number" min="1"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                value={form.scrape_interval_min}
                onChange={e => setForm(p => ({ ...p, scrape_interval_min: +e.target.value }))}
              />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={form.enabled}
                  onChange={e => setForm(p => ({ ...p, enabled: e.target.checked }))}
                />
                <span className="text-sm text-gray-300">Enabled</span>
              </label>
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Notes</label>
            <textarea
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500 resize-none"
              value={form.notes} onChange={f('notes')}
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

function APCard({ ap, onEdit, onDelete }) {
  const qc = useQueryClient()
  const [scrapeResult, setScrapeResult] = useState(null)

  const scrape = useMutation({
    mutationFn: () => api.post(`/wireless-aps/${ap.id}/scrape`).then(r => r.data),
    onSuccess: (data) => {
      setScrapeResult({ ok: true, count: data.client_count })
      qc.invalidateQueries({ queryKey: ['wireless-aps'] })
    },
    onError: (e) => setScrapeResult({ ok: false, msg: e.response?.data?.detail ?? 'Scrape failed' }),
  })

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wifi className={`w-4 h-4 ${ap.enabled ? 'text-blue-400' : 'text-gray-600'}`} />
          <div>
            <h3 className="text-white font-medium">{ap.name}</h3>
            <div className="text-xs text-gray-400">{BRAND_LABELS[ap.brand]}</div>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={onEdit} className="text-gray-400 hover:text-white">
            <Pencil className="w-4 h-4" />
          </button>
          <button onClick={onDelete} className="text-gray-400 hover:text-red-400">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="space-y-1 text-xs mb-3">
        <div className="flex justify-between">
          <span className="text-gray-500">URL</span>
          <span className="text-gray-300 font-mono truncate max-w-[180px]">{ap.url}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Interval</span>
          <span className="text-gray-300">every {ap.scrape_interval_min}m</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Last scraped</span>
          <span className="text-gray-300">
            {ap.last_scraped
              ? new Date(ap.last_scraped + 'Z').toLocaleTimeString()
              : <span className="text-gray-600">never</span>}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Password</span>
          <span className={ap.password_set ? 'text-green-400' : 'text-yellow-400'}>
            {ap.password_set ? 'set' : 'not set'}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => scrape.mutate()}
          disabled={scrape.isPending || !ap.enabled}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded disabled:opacity-40"
        >
          {scrape.isPending
            ? <><Clock className="w-3 h-3 animate-spin" /> Scraping...</>
            : <><Play className="w-3 h-3" /> Scrape Now</>}
        </button>

        {scrapeResult && (
          <span className={`flex items-center gap-1 text-xs ${scrapeResult.ok ? 'text-green-400' : 'text-red-400'}`}>
            {scrapeResult.ok
              ? <><CheckCircle className="w-3 h-3" /> {scrapeResult.count} clients</>
              : <><AlertCircle className="w-3 h-3" /> {scrapeResult.msg}</>}
          </span>
        )}

        <span className={`ml-auto text-xs px-2 py-0.5 rounded-full ${ap.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-500'}`}>
          {ap.enabled ? 'enabled' : 'disabled'}
        </span>
      </div>
    </div>
  )
}

export default function WirelessAPs() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [deleteId, setDeleteId] = useState(null)

  const { data: aps = [], isLoading } = useQuery({
    queryKey: ['wireless-aps'],
    queryFn: () => api.get('/wireless-aps').then(r => r.data),
  })

  const del = useMutation({
    mutationFn: (id) => api.delete(`/wireless-aps/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wireless-aps'] }); setDeleteId(null) },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Wireless APs</h1>
          <p className="text-sm text-gray-400 mt-0.5">Scrape connected wireless clients from your access points</p>
        </div>
        <button
          onClick={() => setModal('new')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
        >
          <Plus className="w-4 h-4" /> Add AP
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : aps.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Wifi className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No wireless APs configured.</p>
          <p className="text-sm mt-1">Add your Deco or Netgear AP to start tracking wireless clients.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {aps.map(ap => (
            <APCard
              key={ap.id}
              ap={ap}
              onEdit={() => setModal(ap)}
              onDelete={() => setDeleteId(ap.id)}
            />
          ))}
        </div>
      )}

      {modal && (
        <APModal ap={modal === 'new' ? null : modal} onClose={() => setModal(null)} />
      )}

      {deleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-80">
            <h2 className="text-white font-semibold mb-2">Delete AP?</h2>
            <p className="text-gray-400 text-sm mb-4">This will also delete all wireless client records for this AP.</p>
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
