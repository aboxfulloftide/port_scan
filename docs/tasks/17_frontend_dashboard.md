# Task 17: Frontend — Dashboard Page

**Depends on:** Task 16, Task 15  
**Complexity:** Medium  
**Description:** Implement the Dashboard page with live stats cards, subnet breakdown, recent scans table, and a manual scan trigger button.

---

## Files to Create / Modify

- `src/pages/Dashboard.jsx`
- `src/components/StatusBadge.jsx`
- `src/components/ScanProgressModal.jsx`

---

## `src/components/StatusBadge.jsx`

```jsx
const colors = {
  up:        'bg-green-500/20 text-green-400',
  down:      'bg-red-500/20 text-red-400',
  running:   'bg-blue-500/20 text-blue-400',
  queued:    'bg-yellow-500/20 text-yellow-400',
  completed: 'bg-green-500/20 text-green-400',
  failed:    'bg-red-500/20 text-red-400',
  cancelled: 'bg-gray-500/20 text-gray-400',
  new:       'bg-purple-500/20 text-purple-400',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] ?? 'bg-gray-700 text-gray-300'}`}>
      {status}
    </span>
  )
}
```

---

## `src/components/ScanProgressModal.jsx`

```jsx
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

export default function ScanProgressModal({ jobId, onClose }) {
  const [events, setEvents] = useState([])
  const [done, setDone] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!jobId) return
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/scans/${jobId}`)
    ws.onmessage = (e) => {
      const evt = JSON.parse(e.data)
      setEvents(prev => [...prev, evt])
      if (evt.type === 'job_done') {
        setDone(true)
        ws.close()
      }
    }
    ws.onerror = () => setDone(true)
    return () => ws.close()
  }, [jobId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-2xl p-6 border border-gray-700">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Scan Progress — Job #{jobId}</h2>
          {done && (
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <X size={20} />
            </button>
          )}
        </div>
        <div className="bg-gray-950 rounded-lg p-4 h-72 overflow-y-auto font-mono text-sm space-y-1">
          {events.map((evt, i) => (
            <div key={i} className={`
              ${evt.type === 'job_done' && evt.status === 'completed' ? 'text-green-400' : ''}
              ${evt.type === 'job_done' && evt.status === 'failed' ? 'text-red-400' : ''}
              ${evt.type === 'tier_start' ? 'text-blue-400' : ''}
              ${evt.type === 'tier_done' ? 'text-gray-300' : ''}
              ${evt.type === 'job_start' ? 'text-yellow-400' : ''}
            `}>
              [{evt.type}] {JSON.stringify(evt, null, 0).replace(/^{|}$/g, '')}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        {!done && (
          <div className="mt-3 flex items-center gap-2 text-sm text-blue-400">
            <span className="animate-pulse">●</span> Scan in progress…
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## `src/pages/Dashboard.jsx`

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import ScanProgressModal from '../components/ScanProgressModal'
import { Play, RefreshCw } from 'lucide-react'

// ── Data fetching ─────────────────────────────────────────────────────────────

const fetchDashboard = () => api.get('/dashboard/').then(r => r.data)
const fetchSubnets   = () => api.get('/subnets/').then(r => r.data)
const fetchProfiles  = () => api.get('/profiles/').then(r => r.data)

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color = 'text-white' }) {
  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-3xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  )
}

// ── Manual Scan Form ──────────────────────────────────────────────────────────

function ManualScanForm({ subnets, profiles, onJobStarted }) {
  const [subnetId, setSubnetId] = useState('')
  const [profileId, setProfileId] = useState('')

  const mutation = useMutation({
    mutationFn: () => api.post('/scans/', { subnet_id: +subnetId, profile_id: +profileId }).then(r => r.data),
    onSuccess: (data) => onJobStarted(data.id),
  })

  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Manual Scan</h3>
      <div className="flex gap-3 flex-wrap">
        <select
          value={subnetId} onChange={e => setSubnetId(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm flex-1 min-w-32"
        >
          <option value="">Select subnet…</option>
          {subnets?.map(s => <option key={s.id} value={s.id}>{s.cidr} {s.label ? `(${s.label})` : ''}</option>)}
        </select>
        <select
          value={profileId} onChange={e => setProfileId(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm flex-1 min-w-32"
        >
          <option value="">Select profile…</option>
          {profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button
          onClick={() => mutation.mutate()}
          disabled={!subnetId || !profileId || mutation.isPending}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Play size={14} /> {mutation.isPending ? 'Starting…' : 'Start Scan'}
        </button>
      </div>
      {mutation.isError && (
        <div className="mt-2 text-red-400 text-xs">{mutation.error?.response?.data?.detail || 'Failed to start scan'}</div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const qc = useQueryClient()
  const [activeJobId, setActiveJobId] = useState(null)

  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 15000,
  })
  const { data: subnets } = useQuery({ queryKey: ['subnets'], queryFn: fetchSubnets })
  const { data: profiles } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })

  const handleJobStarted = (jobId) => {
    setActiveJobId(jobId)
    qc.invalidateQueries(['dashboard'])
  }

  if (isLoading) return <div className="text-gray-500">Loading dashboard…</div>

  const chartData = stats?.subnets?.map(s => ({
    name: s.label || s.cidr,
    up: s.up_count,
    down: s.host_count - s.up_count,
  })) ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={() => qc.invalidateQueries(['dashboard'])}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Hosts"  value={stats.total_hosts} />
        <StatCard label="Hosts Up"     value={stats.hosts_up}    color="text-green-400" />
        <StatCard label="Hosts Down"   value={stats.hosts_down}  color="text-red-400" />
        <StatCard label="Active Scans" value={stats.active_scans} color="text-blue-400" />
      </div>

      {/* New alerts */}
      {(stats.new_hosts > 0 || stats.new_ports > 0) && (
        <div className="bg-purple-900/30 border border-purple-700 rounded-xl p-4 text-sm text-purple-300">
          ⚠️ <strong>{stats.new_hosts}</strong> new host(s) and <strong>{stats.new_ports}</strong> new port(s) detected since last acknowledgement.
        </div>
      )}

      {/* Manual scan */}
      <ManualScanForm subnets={subnets} profiles={profiles} onJobStarted={handleJobStarted} />

      {/* Subnet chart */}
      {chartData.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Hosts per Subnet</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} barSize={24}>
              <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }} />
              <Bar dataKey="up"   name="Up"   stackId="a" fill="#22c55e" />
              <Bar dataKey="down" name="Down" stackId="a" fill="#ef4444" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent scans */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800 text-sm font-semibold text-gray-300">Recent Scans</div>
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
            <tr>
              <th className="px-4 py-2 text-left">ID</th>
              <th className="px-4 py-2 text-left">Subnet</th>
              <th className="px-4 py-2 text-left">Profile</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-left">Hosts</th>
              <th className="px-4 py-2 text-left">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {stats.recent_scans?.map(scan => (
              <tr key={scan.id} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-4 py-2 text-gray-400">#{scan.id}</td>
                <td className="px-4 py-2 font-mono text-xs">{scan.subnet_cidr}</td>
                <td className="px-4 py-2 text-gray-300">{scan.profile_name}</td>
                <td className="px-4 py-2"><StatusBadge status={scan.status} /></td>
                <td className="px-4 py-2">{scan.hosts_found}</td>
                <td className="px-4 py-2 text-gray-400 text-xs">{new Date(scan.started_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Scan progress modal */}
      {activeJobId && (
        <ScanProgressModal jobId={activeJobId} onClose={() => setActiveJobId(null)} />
      )}
    </div>
  )
}
```
