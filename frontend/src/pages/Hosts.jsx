import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, RefreshCw } from 'lucide-react'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { formatDate } from '../utils/format'

const PER_PAGE = 50

export default function Hosts() {
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState(null)
  const [search,   setSearch]   = useState('')
  const [isUp,     setIsUp]     = useState(searchParams.get('is_up') ?? '')
  const [subnetId, setSubnetId] = useState('')
  const [page,     setPage]     = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['hosts', search, isUp, subnetId, page],
    queryFn: () => api.get('/hosts', { params: {
      search:    search    || undefined,
      is_up:     isUp      === '' ? undefined : isUp === 'true',
      subnet_id: subnetId  || undefined,
      page,
      per_page:  PER_PAGE,
    }}).then(r => r.data),
    placeholderData: d => d,
  })

  const { data: subnets } = useQuery({
    queryKey: ['subnets'],
    queryFn: () => api.get('/subnets').then(r => r.data),
  })

  const hosts = data?.hosts ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)

  const setFilter = (setter) => (e) => { setter(e.target.value); setPage(1) }

  const handleDhcpSync = async () => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await api.post('/hosts/dhcp-sync')
      const d = res.data
      if (!d || typeof d !== 'object') {
        setSyncMsg('DHCP sync completed (no response body)')
      } else {
        setSyncMsg(d.status === 'ok'
          ? `Synced ${d.entries_scraped} entries — updated ${d.hosts_updated}, created ${d.hosts_created || 0}`
          : d.message || 'No data returned')
      }
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
    } catch (e) {
      setSyncMsg(e.response?.data?.detail || 'DHCP sync failed')
    } finally {
      setSyncing(false)
      setTimeout(() => setSyncMsg(null), 5000)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Hosts</h1>
        <div className="flex items-center gap-3">
          {syncMsg && <span className="text-xs text-gray-400">{syncMsg}</span>}
          <button
            onClick={handleDhcpSync}
            disabled={syncing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing…' : 'Sync DHCP'}
          </button>
          <span className="text-sm text-gray-500">{total} total</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-52">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={setFilter(setSearch)}
            placeholder="Search hostname, IP, or MAC…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
        <select
          value={isUp}
          onChange={setFilter(setIsUp)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="true">Up</option>
          <option value="false">Down</option>
        </select>
        <select
          value={subnetId}
          onChange={setFilter(setSubnetId)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All subnets</option>
          {subnets?.map(s => (
            <option key={s.id} value={s.id}>{s.cidr}{s.label ? ` — ${s.label}` : ''}</option>
          ))}
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
              <th className="px-4 py-3 text-right">Ports</th>
              <th className="px-4 py-3 text-left">OS</th>
              <th className="px-4 py-3 text-left">Last Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {isLoading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : hosts.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No hosts found.</td></tr>
            ) : hosts.map(h => (
              <tr key={h.id} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-4 py-2">
                  <Link to={`/hosts/${h.id}`} className="text-blue-400 hover:underline font-medium">
                    {h.hostname || '—'}
                  </Link>
                  {h.is_new && (
                    <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded-full">new</span>
                  )}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-gray-300">{h.current_ip}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{h.current_mac || '—'}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={h.is_up ? 'up' : 'down'} />
                </td>
                <td className="px-4 py-2 text-right text-gray-300">{h.open_port_count}</td>
                <td className="px-4 py-2 text-gray-400 text-xs truncate max-w-36">{h.os_guess || '—'}</td>
                <td className="px-4 py-2 text-gray-400 text-xs">{formatDate(h.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1 bg-gray-800 rounded disabled:opacity-40 hover:bg-gray-700"
            >
              ← Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1 bg-gray-800 rounded disabled:opacity-40 hover:bg-gray-700"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
