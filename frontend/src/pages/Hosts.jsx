import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, RefreshCw, GitMerge, X, ChevronUp, ChevronDown, EyeOff, Eye, Undo2, Wifi } from 'lucide-react'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { formatDate } from '../utils/format'

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

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
  const [selected, setSelected] = useState(new Set())
  const [mergeModal, setMergeModal] = useState(false)
  const [primaryId, setPrimaryId] = useState(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [showIgnored, setShowIgnored] = useState(false)
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

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

  const { data: suggestions } = useQuery({
    queryKey: ['merge-suggestions'],
    queryFn: () => api.get('/hosts/merge-suggestions').then(r => r.data),
  })

  const { data: ignoredSuggestions } = useQuery({
    queryKey: ['merge-suggestions-ignored'],
    queryFn: () => api.get('/hosts/merge-suggestions/ignored').then(r => r.data),
    enabled: showIgnored,
  })

  const mergeMutation = useMutation({
    mutationFn: (body) => api.post('/hosts/merge', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      queryClient.invalidateQueries({ queryKey: ['merge-suggestions'] })
      setMergeModal(false)
      setSelected(new Set())
      setPrimaryId(null)
    },
  })

  const ignoreMutation = useMutation({
    mutationFn: (host_ids) => api.post('/hosts/merge-suggestions/ignore', { host_ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['merge-suggestions'] })
      queryClient.invalidateQueries({ queryKey: ['merge-suggestions-ignored'] })
    },
  })

  const unignoreMutation = useMutation({
    mutationFn: (host_ids) => api.post('/hosts/merge-suggestions/unignore', { host_ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['merge-suggestions'] })
      queryClient.invalidateQueries({ queryKey: ['merge-suggestions-ignored'] })
    },
  })

  const rawHosts = data?.hosts ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)
  const suggestionCount = suggestions?.length ?? 0

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const hosts = [...rawHosts].sort((a, b) => {
    if (!sortKey) return 0
    let av = a[sortKey]
    let bv = b[sortKey]
    // Nulls last
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (typeof av === 'boolean') { av = av ? 1 : 0; bv = bv ? 1 : 0 }
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'asc' ? cmp : -cmp
  })

  const SortHeader = ({ field, children, align }) => (
    <th
      className={`px-4 py-3 ${align === 'right' ? 'text-right' : 'text-left'} cursor-pointer select-none hover:text-gray-300 transition-colors`}
      onClick={() => toggleSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortKey === field ? (
          sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
        ) : (
          <span className="w-3" />
        )}
      </span>
    </th>
  )

  const setFilter = (setter) => (e) => { setter(e.target.value); setPage(1) }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === hosts.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(hosts.map(h => h.id)))
    }
  }

  const openMergeModal = () => {
    if (selected.size < 2) return
    setPrimaryId([...selected][0])
    setMergeModal(true)
  }

  const doMerge = () => {
    if (!primaryId) return
    const aliasIds = [...selected].filter(id => id !== primaryId)
    mergeMutation.mutate({ primary_host_id: primaryId, alias_host_ids: aliasIds })
  }

  const doSuggestionMerge = (suggestion) => {
    if (suggestion.hosts.length < 2) return
    const sortedHosts = [...suggestion.hosts].sort((a, b) => a.id - b.id)
    const primary = sortedHosts[0]
    const aliases = sortedHosts.slice(1).map(h => h.id)
    mergeMutation.mutate({ primary_host_id: primary.id, alias_host_ids: aliases })
  }

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
          {selected.size >= 2 && (
            <button
              onClick={openMergeModal}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-purple-700 border border-purple-600 rounded-lg hover:bg-purple-600 transition-colors"
            >
              <GitMerge size={14} />
              Merge Selected ({selected.size})
            </button>
          )}
          {suggestionCount > 0 && (
            <button
              onClick={() => setShowSuggestions(!showSuggestions)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-yellow-700/50 border border-yellow-600/50 rounded-lg hover:bg-yellow-600/50 transition-colors"
            >
              <GitMerge size={14} />
              {suggestionCount} Merge Suggestion{suggestionCount > 1 ? 's' : ''}
            </button>
          )}
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

      {/* Merge Suggestions Panel */}
      {showSuggestions && (
        <div className="bg-yellow-900/20 border border-yellow-700/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-yellow-300">Merge Suggestions</h3>
            <button onClick={() => setShowSuggestions(false)} className="text-gray-400 hover:text-white">
              <X size={16} />
            </button>
          </div>
          {suggestions && suggestions.length > 0 ? suggestions.map((s, i) => (
            <div key={i} className="bg-gray-900/60 rounded-lg p-3 flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="text-xs text-yellow-400 mb-1">{s.reason}</div>
                <div className="flex gap-2 flex-wrap">
                  {s.hosts.map(h => (
                    <span key={h.id} className="text-xs bg-gray-800 px-2 py-1 rounded font-mono">
                      {h.hostname || h.current_ip} <span className="text-gray-500">({h.current_ip})</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                <button
                  onClick={() => ignoreMutation.mutate(s.hosts.map(h => h.id))}
                  disabled={ignoreMutation.isPending}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
                  title="Ignore this suggestion"
                >
                  <EyeOff size={12} /> Ignore
                </button>
                <button
                  onClick={() => doSuggestionMerge(s)}
                  disabled={mergeMutation.isPending}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs bg-purple-700 hover:bg-purple-600 rounded-lg transition-colors disabled:opacity-50"
                >
                  <GitMerge size={12} /> Merge
                </button>
              </div>
            </div>
          )) : (
            <p className="text-xs text-gray-500">No active merge suggestions.</p>
          )}

          {/* Show Ignored toggle */}
          <div className="pt-2 border-t border-yellow-700/30">
            <button
              onClick={() => setShowIgnored(!showIgnored)}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-300 transition-colors"
            >
              {showIgnored ? <Eye size={12} /> : <EyeOff size={12} />}
              {showIgnored ? 'Hide' : 'Show'} Ignored Suggestions
            </button>
          </div>

          {/* Ignored suggestions list */}
          {showIgnored && ignoredSuggestions && ignoredSuggestions.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-gray-400">Ignored</h4>
              {ignoredSuggestions.map((g, i) => (
                <div key={i} className="bg-gray-900/40 rounded-lg p-3 flex items-center justify-between gap-4 opacity-70">
                  <div className="flex-1 min-w-0">
                    <div className="flex gap-2 flex-wrap">
                      {g.hosts.map(h => (
                        <span key={h.id} className="text-xs bg-gray-800 px-2 py-1 rounded font-mono">
                          {h.hostname || h.current_ip} <span className="text-gray-500">({h.current_ip})</span>
                        </span>
                      ))}
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      Dismissed {new Date(g.dismissed_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button
                    onClick={() => unignoreMutation.mutate(g.host_ids)}
                    disabled={unignoreMutation.isPending}
                    className="shrink-0 flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
                    title="Restore this suggestion"
                  >
                    <Undo2 size={12} /> Restore
                  </button>
                </div>
              ))}
            </div>
          )}
          {showIgnored && ignoredSuggestions && ignoredSuggestions.length === 0 && (
            <p className="text-xs text-gray-500">No ignored suggestions.</p>
          )}
        </div>
      )}

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
              <th className="px-3 py-3 text-left w-8">
                <input
                  type="checkbox"
                  checked={hosts.length > 0 && selected.size === hosts.length}
                  onChange={toggleSelectAll}
                  className="rounded border-gray-600"
                />
              </th>
              <SortHeader field="hostname">Hostname</SortHeader>
              <SortHeader field="current_ip">IP Address</SortHeader>
              <SortHeader field="current_mac">MAC</SortHeader>
              <SortHeader field="is_up">Status</SortHeader>
              <SortHeader field="open_port_count" align="right">Ports</SortHeader>
              <SortHeader field="bandwidth_1h" align="right">Bandwidth (1h)</SortHeader>
              <SortHeader field="os_guess">OS</SortHeader>
              <SortHeader field="last_seen">Last Seen</SortHeader>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {isLoading ? (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : hosts.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">No hosts found.</td></tr>
            ) : hosts.map(h => (
              <tr key={h.id} className="hover:bg-gray-800/40 transition-colors">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(h.id)}
                    onChange={() => toggleSelect(h.id)}
                    className="rounded border-gray-600"
                  />
                </td>
                <td className="px-4 py-2">
                  <Link to={`/hosts/${h.id}`} className="text-blue-400 hover:underline font-medium">
                    {h.hostname || (h.notes ? <span className="text-gray-400 italic">{h.notes}</span> : '—')}
                  </Link>
                  {h.connection_type === 'wireless' && (
                    <span className="ml-2 inline-flex items-center gap-0.5 text-xs bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full">
                      <Wifi size={10} />wifi
                    </span>
                  )}
                  {h.is_new && (
                    <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded-full">new</span>
                  )}
                  {h.alias_count > 0 && (
                    <span className="ml-2 text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full">+{h.alias_count}</span>
                  )}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-gray-300">{h.current_ip}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{h.current_mac || '—'}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={h.is_up ? 'up' : 'down'} />
                </td>
                <td className="px-4 py-2 text-right text-gray-300">{h.open_port_count}</td>
                <td className="px-4 py-2 text-right text-gray-300">{h.bandwidth_1h ? formatBytes(h.bandwidth_1h) : '—'}</td>
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

      {/* Merge Modal */}
      {mergeModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h2 className="text-lg font-bold">Merge Hosts</h2>
            <p className="text-sm text-gray-400">
              Select the primary host. All other selected hosts will become aliases.
            </p>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {hosts.filter(h => selected.has(h.id)).map(h => (
                <label
                  key={h.id}
                  className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                    primaryId === h.id ? 'bg-purple-900/40 border border-purple-600' : 'bg-gray-800 border border-gray-700 hover:bg-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="primary"
                    checked={primaryId === h.id}
                    onChange={() => setPrimaryId(h.id)}
                    className="text-purple-600"
                  />
                  <div>
                    <div className="text-sm font-medium">{h.hostname || h.current_ip}</div>
                    <div className="text-xs text-gray-500 font-mono">{h.current_ip} {h.current_mac || ''}</div>
                  </div>
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setMergeModal(false); setPrimaryId(null) }}
                className="px-4 py-2 text-sm bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={doMerge}
                disabled={!primaryId || mergeMutation.isPending}
                className="px-4 py-2 text-sm bg-purple-700 rounded-lg hover:bg-purple-600 disabled:opacity-50 transition-colors"
              >
                {mergeMutation.isPending ? 'Merging…' : 'Merge'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
