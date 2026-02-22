# Task 18: Frontend — Hosts Page & Host Detail

**Depends on:** Task 16, Task 10, Task 13  
**Complexity:** Medium  
**Description:** Implement the Hosts list page with filtering/search and the Host Detail page with ports, banners, screenshots, history, and WoL controls.

---

## Files to Create

- `src/pages/Hosts.jsx`
- `src/pages/HostDetail.jsx`

---

## `src/pages/Hosts.jsx`

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { Search, CheckCheck } from 'lucide-react'

const fetchHosts = (params) => api.get('/hosts/', { params }).then(r => r.data)

export default function Hosts() {
  const qc = useQueryClient()
  const [search, setSearch]     = useState('')
  const [status, setStatus]     = useState('')
  const [subnetId, setSubnetId] = useState('')
  const [page, setPage]         = useState(1)
  const limit = 50

  const { data, isLoading } = useQuery({
    queryKey: ['hosts', search, status, subnetId, page],
    queryFn: () => fetchHosts({
      search: search || undefined,
      status: status || undefined,
      subnet_id: subnetId || undefined,
      offset: (page - 1) * limit,
      limit,
    }),
    keepPreviousData: true,
  })

  const ackAll = useMutation({
    mutationFn: () => api.post('/hosts/acknowledge-all'),
    onSuccess: () => qc.invalidateQueries(['hosts']),
  })

  const { data: subnets } = useQuery({
    queryKey: ['subnets'],
    queryFn: () => api.get('/subnets/').then(r => r.data),
  })

  const hosts = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Hosts</h1>
        <button
          onClick={() => ackAll.mutate()}
          className="flex items-center gap-2 text-sm bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded-lg"
        >
          <CheckCheck size={14} /> Acknowledge All New
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search hostname or IP…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-8 pr-3 py-2 text-sm"
          />
        </div>
        <select
          value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="up">Up</option>
          <option value="down">Down</option>
        </select>
        <select
          value={subnetId} onChange={e => { setSubnetId(e.target.value); setPage(1) }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All subnets</option>
          {subnets?.map(s => <option key={s.id} value={s.id}>{s.cidr}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left">Hostname</th>
              <th className="px-4 py-3 text-left">IP Address</th>
              <th className="px-4 py-3 text-left">MAC</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Open Ports</th>
              <th className="px-4 py-3 text-left">OS</th>
              <th className="px-4 py-3 text-left">Last Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {isLoading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : hosts.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No hosts found</td></tr>
            ) : hosts.map(h => (
              <tr key={h.id} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-4 py-2">
                  <Link to={`/hosts/${h.id}`} className="text-blue-400 hover:underline font-medium">
                    {h.hostname || '—'}
                  </Link>
                  {h.is_new && <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded-full">new</span>}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-gray-300">{h.ip_address}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{h.mac_address || '—'}</td>
                <td className="px-4 py-2"><StatusBadge status={h.status} /></td>
                <td className="px-4 py-2 text-gray-300">{h.open_port_count}</td>
                <td className="px-4 py-2 text-gray-400 text-xs truncate max-w-32">{h.os_guess || '—'}</td>
                <td className="px-4 py-2 text-gray-400 text-xs">{h.last_seen ? new Date(h.last_seen).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-400">
        <span>{total} host(s) total</span>
        <div className="flex gap-2">
          <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-40">← Prev</button>
          <span className="px-3 py-1">Page {page}</span>
          <button disabled={page * limit >= total} onClick={() => setPage(p => p + 1)}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-40">Next →</button>
        </div>
      </div>
    </div>
  )
}
```

---

## `src/pages/HostDetail.jsx`

```jsx
import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { Zap, ArrowLeft, CheckCheck, Save } from 'lucide-react'

const fetchHost    = (id) => api.get(`/hosts/${id}`).then(r => r.data)
const fetchPorts   = (id) => api.get(`/hosts/${id}/ports`).then(r => r.data)
const fetchHistory = (id) => api.get(`/hosts/${id}/history`).then(r => r.data)

export default function HostDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [notes, setNotes] = useState(null)
  const [activeTab, setActiveTab] = useState('ports')

  const { data: host } = useQuery({ queryKey: ['host', id], queryFn: () => fetchHost(id) })
  const { data: ports } = useQuery({ queryKey: ['host-ports', id], queryFn: () => fetchPorts(id) })
  const { data: history } = useQuery({ queryKey: ['host-history', id], queryFn: () => fetchHistory(id) })

  const saveNotes = useMutation({
    mutationFn: () => api.patch(`/hosts/${id}`, { notes }),
    onSuccess: () => qc.invalidateQueries(['host', id]),
  })

  const ackHost = useMutation({
    mutationFn: () => api.post(`/hosts/${id}/acknowledge`),
    onSuccess: () => qc.invalidateQueries(['host', id]),
  })

  const sendWol = useMutation({
    mutationFn: () => api.post('/wol/send', { host_id: +id }),
    onSuccess: () => alert('WoL magic packet sent!'),
    onError: (e) => alert(e.response?.data?.detail || 'WoL failed'),
  })

  if (!host) return <div className="text-gray-500">Loading…</div>

  const displayNotes = notes ?? host.notes ?? ''

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Back */}
      <Link to="/hosts" className="flex items-center gap-2 text-sm text-gray-400 hover:text-white">
        <ArrowLeft size={14} /> Back to Hosts
      </Link>

      {/* Header */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold">{host.hostname || host.ip_address}</h1>
              <StatusBadge status={host.status} />
              {host.is_new && <StatusBadge status="new" />}
            </div>
            <div className="text-sm text-gray-400 space-y-0.5">
              <div>IP: <span className="font-mono text-gray-200">{host.ip_address}</span></div>
              <div>MAC: <span className="font-mono text-gray-200">{host.mac_address || '—'}</span></div>
              <div>OS: <span className="text-gray-200">{host.os_guess || 'Unknown'}</span></div>
              <div>First seen: {new Date(host.first_seen).toLocaleString()}</div>
              <div>Last seen: {new Date(host.last_seen).toLocaleString()}</div>
            </div>
          </div>
          <div className="flex gap-2">
            {host.is_new && (
              <button onClick={() => ackHost.mutate()}
                className="flex items-center gap-2 text-sm bg-purple-700 hover:bg-purple-600 px-3 py-2 rounded-lg">
                <CheckCheck size={14} /> Acknowledge
              </button>
            )}
            {host.wol_enabled && host.mac_address && (
              <button onClick={() => sendWol.mutate()}
                disabled={sendWol.isPending}
                className="flex items-center gap-2 text-sm bg-yellow-600 hover:bg-yellow-500 px-3 py-2 rounded-lg disabled:opacity-50">
                <Zap size={14} /> Wake
              </button>
            )}
          </div>
        </div>

        {/* Notes */}
        <div className="mt-4">
          <label className="text-xs text-gray-500 uppercase tracking-wider">Notes</label>
          <div className="flex gap-2 mt-1">
            <textarea
              value={displayNotes}
              onChange={e => setNotes(e.target.value)}
              rows={2}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm resize-none"
              placeholder="Add notes about this host…"
            />
            <button onClick={() => saveNotes.mutate()}
              className="flex items-center gap-1 text-sm bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded-lg self-start">
              <Save size={14} /> Save
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {['ports', 'history'].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize transition-colors
              ${activeTab === tab ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-white'}`}>
            {tab}
          </button>
        ))}
      </div>

      {/* Ports tab */}
      {activeTab === 'ports' && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
              <tr>
                <th className="px-4 py-3 text-left">Port</th>
                <th className="px-4 py-3 text-left">Proto</th>
                <th className="px-4 py-3 text-left">State</th>
                <th className="px-4 py-3 text-left">Service</th>
                <th className="px-4 py-3 text-left">Banner / Version</th>
                <th className="px-4 py-3 text-left">Screenshot</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {ports?.map(p => (
                <tr key={p.id} className="hover:bg-gray-800/40">
                  <td className="px-4 py-2 font-mono font-bold text-blue-300">
                    {p.port}
                    {p.is_new && <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded-full">new</span>}
                  </td>
                  <td className="px-4 py-2 text-gray-400 uppercase text-xs">{p.protocol}</td>
                  <td className="px-4 py-2"><StatusBadge status={p.state} /></td>
                  <td className="px-4 py-2 text-gray-300">{p.service || '—'}</td>
                  <td className="px-4 py-2 text-gray-400 text-xs font-mono truncate max-w-xs">
                    {p.banner?.raw_banner || p.banner?.version || '—'}
                  </td>
                  <td className="px-4 py-2">
                    {p.screenshot ? (
                      <a href={`/api/hosts/screenshots/${p.screenshot.filename}`} target="_blank" rel="noreferrer">
                        <img src={`/api/hosts/screenshots/${p.screenshot.filename}`}
                          alt="screenshot" className="h-12 w-20 object-cover rounded border border-gray-700" />
                      </a>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* History tab */}
      {activeTab === 'history' && (
        <div className="space-y-2">
          {history?.length === 0 && <div className="text-gray-500 text-sm">No change history recorded.</div>}
          {history?.map(h => (
            <div key={h.id} className="bg-gray-900 rounded-lg p-4 border border-gray-800 text-sm">
              <div className="text-gray-400 text-xs mb-1">{new Date(h.recorded_at).toLocaleString()}</div>
              <pre className="text-gray-300 text-xs whitespace-pre-wrap">{h.changes}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```
