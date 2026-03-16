import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { Play, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import ScanProgressModal from '../components/ScanProgressModal'
import { formatDate } from '../utils/format'

const fetchDashboard = () => api.get('/dashboard').then(r => r.data)
const fetchSubnets   = () => api.get('/subnets').then(r => r.data)
const fetchProfiles  = () => api.get('/profiles').then(r => r.data)
const fetchTrafficInterfaces = () => api.get('/traffic/interfaces').then(r => r.data)

const DAILY_RANGE_OPTIONS = [
  { label: '7d',  days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: '1y',  days: 365 },
  { label: '2y',  days: 730 },
]

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function StatCard({ label, value, color = 'text-white', to }) {
  const inner = (
    <>
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-3xl font-bold ${color}`}>{value ?? 0}</div>
    </>
  )
  if (to) {
    return (
      <Link to={to} className="bg-gray-900 rounded-xl p-5 border border-gray-800 hover:border-gray-600 transition-colors block">
        {inner}
      </Link>
    )
  }
  return <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">{inner}</div>
}

function ManualScanForm({ subnets, profiles, onJobStarted }) {
  const [subnetIds, setSubnetIds] = useState('')
  const [profileId, setProfileId] = useState('')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: () => api.post('/scans', {
      subnet_ids: [+subnetIds],
      profile_id: +profileId,
    }).then(r => r.data),
    onSuccess: (data) => {
      setError('')
      onJobStarted(data.job_id)
    },
    onError: (err) => setError(err.response?.data?.detail ?? 'Failed to start scan'),
  })

  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">Manual Scan</h3>
      <div className="flex gap-3 flex-wrap items-end">
        <select
          value={subnetIds}
          onChange={e => setSubnetIds(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm flex-1 min-w-40"
        >
          <option value="">Select subnet…</option>
          {subnets?.map(s => (
            <option key={s.id} value={s.id}>{s.cidr}{s.label ? ` — ${s.label}` : ''}</option>
          ))}
        </select>
        <select
          value={profileId}
          onChange={e => setProfileId(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm flex-1 min-w-40"
        >
          <option value="">Select profile…</option>
          {profiles?.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <button
          onClick={() => mutation.mutate()}
          disabled={!subnetIds || !profileId || mutation.isPending}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Play size={14} /> {mutation.isPending ? 'Starting…' : 'Start Scan'}
        </button>
      </div>
      {error && <p className="mt-2 text-red-400 text-xs">{error}</p>}
    </div>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()
  const [activeJobId, setActiveJobId] = useState(null)
  const [dailyDays, setDailyDays] = useState(30)

  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 15000,
  })
  const { data: subnets } = useQuery({ queryKey: ['subnets'], queryFn: fetchSubnets })
  const { data: profiles } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const { data: trafficInterfaces } = useQuery({
    queryKey: ['traffic-interfaces'],
    queryFn: fetchTrafficInterfaces,
    refetchInterval: 60000,
  })
  const { data: dailyTraffic } = useQuery({
    queryKey: ['traffic-daily', dailyDays],
    queryFn: () => api.get(`/traffic/interfaces/daily?days=${dailyDays}`).then(r => r.data),
    refetchInterval: 300000,
  })

  const handleJobStarted = (jobId) => {
    setActiveJobId(jobId)
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  if (isLoading) return <div className="text-gray-500 p-4">Loading dashboard…</div>

  const chartData = stats?.subnets?.map(s => ({
    name: s.label || s.cidr,
    up:   s.up_count,
    down: s.host_count - s.up_count,
  })) ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['dashboard'] })}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Hosts"  value={stats.total_hosts}  to="/hosts" />
        <StatCard label="Hosts Up"     value={stats.hosts_up}    color="text-green-400" to="/hosts?is_up=true" />
        <StatCard label="Hosts Down"   value={stats.hosts_down}  color="text-red-400"   to="/hosts?is_up=false" />
        <StatCard label="Active Scans" value={stats.active_scans} color="text-blue-400" />
      </div>

      {/* New-host / new-port alert */}
      {(stats.new_hosts > 0 || stats.new_ports > 0) && (
        <div className="bg-purple-900/30 border border-purple-700 rounded-xl p-4 text-sm text-purple-300">
          ⚠️{' '}
          <strong>{stats.new_hosts}</strong> new host(s) and{' '}
          <strong>{stats.new_ports}</strong> new port(s) detected since last acknowledgement.
        </div>
      )}

      {/* Manual scan trigger */}
      <ManualScanForm subnets={subnets} profiles={profiles} onJobStarted={handleJobStarted} />

      {/* Network Traffic */}
      {trafficInterfaces && trafficInterfaces.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-300">Network Traffic</h3>
            <div className="flex gap-1">
              {DAILY_RANGE_OPTIONS.map(opt => (
                <button
                  key={opt.days}
                  onClick={() => setDailyDays(opt.days)}
                  className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                    dailyDays === opt.days
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            {trafficInterfaces.map(iface => (
              <div key={iface.interface} className="space-y-1">
                <div className="text-xs text-gray-500 uppercase tracking-wider">{iface.interface}</div>
                <div className="text-sm">
                  <span className="text-green-400">↑ {formatBytes(iface.bytes_sent)}</span>
                  {' / '}
                  <span className="text-blue-400">↓ {formatBytes(iface.bytes_recv)}</span>
                </div>
              </div>
            ))}
          </div>
          {dailyTraffic && dailyTraffic.length > 0 && (() => {
            // Pivot daily data: one object per day with keys like "WAN_recv", "LAN_sent"
            const byDay = {}
            dailyTraffic.forEach(p => {
              const d = p.day
              if (!byDay[d]) byDay[d] = { day: d }
              byDay[d][`${p.interface}_recv`] = p.bytes_recv
              byDay[d][`${p.interface}_sent`] = p.bytes_sent
            })
            const chartData = Object.values(byDay)
            const interfaces = [...new Set(dailyTraffic.map(p => p.interface))]
            const recvColors = ['#3b82f6', '#a855f7', '#06b6d4', '#f59e0b']
            const sentColors = ['#22c55e', '#eab308', '#10b981', '#ef4444']
            return (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData}>
                  <XAxis
                    dataKey="day"
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                    tickFormatter={v => {
                      const d = new Date(v + 'T00:00:00')
                      return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
                    }}
                  />
                  <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} tickFormatter={formatBytes} />
                  <Tooltip
                    contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                    formatter={(v) => formatBytes(v)}
                    labelFormatter={v => {
                      const d = new Date(v + 'T00:00:00')
                      return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
                    }}
                  />
                  <Legend />
                  {interfaces.map((iface, i) => (
                    <Bar key={`${iface}_recv`} dataKey={`${iface}_recv`} name={`${iface} ↓`} stackId={iface} fill={recvColors[i % recvColors.length]} />
                  ))}
                  {interfaces.map((iface, i) => (
                    <Bar key={`${iface}_sent`} dataKey={`${iface}_sent`} name={`${iface} ↑`} stackId={iface} fill={sentColors[i % sentColors.length]} radius={[2, 2, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )
          })()}
        </div>
      )}

      {/* Subnet chart */}
      {chartData.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Hosts per Subnet</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} barSize={28}>
              <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }} />
              <Bar dataKey="up"   name="Up"   stackId="a" fill="#22c55e" />
              <Bar dataKey="down" name="Down" stackId="a" fill="#ef4444" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent scans table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800 text-sm font-semibold text-gray-300">
          Recent Scans
        </div>
        {stats.recent_scans?.length === 0 ? (
          <div className="px-5 py-8 text-center text-gray-600 text-sm">No scans yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
              <tr>
                <th className="px-4 py-2 text-left">ID</th>
                <th className="px-4 py-2 text-left">Profile</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-right">Discovered</th>
                <th className="px-4 py-2 text-right">Up</th>
                <th className="px-4 py-2 text-right">New</th>
                <th className="px-4 py-2 text-left">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {stats.recent_scans?.map(scan => (
                <tr key={scan.id} className="hover:bg-gray-800/40 transition-colors">
                  <td className="px-4 py-2 text-gray-400">#{scan.id}</td>
                  <td className="px-4 py-2 text-gray-300">{scan.profile_name ?? '—'}</td>
                  <td className="px-4 py-2"><StatusBadge status={scan.status} /></td>
                  <td className="px-4 py-2 text-right">{scan.hosts_discovered ?? '—'}</td>
                  <td className="px-4 py-2 text-right">{scan.hosts_up ?? '—'}</td>
                  <td className="px-4 py-2 text-right text-purple-400">{scan.new_hosts_found ?? '—'}</td>
                  <td className="px-4 py-2 text-gray-400 text-xs">{formatDate(scan.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Live scan progress modal */}
      {activeJobId && (
        <ScanProgressModal
          jobId={activeJobId}
          onClose={() => {
            setActiveJobId(null)
            qc.invalidateQueries({ queryKey: ['dashboard'] })
          }}
        />
      )}
    </div>
  )
}
