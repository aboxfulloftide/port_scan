import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { ArrowLeft, Zap, CheckCheck, Save, Unlink, X, Pencil, Check } from 'lucide-react'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { formatDate } from '../utils/format'

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export default function HostDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [notes, setNotes] = useState(null)
  const [activeTab, setActiveTab] = useState('ports')
  const [editingHostname, setEditingHostname] = useState(false)
  const [hostnameInput, setHostnameInput] = useState('')

  const { data: host, isLoading } = useQuery({
    queryKey: ['host', id],
    queryFn: () => api.get(`/hosts/${id}`).then(r => r.data),
  })

  const { data: trafficHistory } = useQuery({
    queryKey: ['host-traffic', id],
    queryFn: () => api.get(`/traffic/hosts/${id}/history?hours=24`).then(r => r.data),
  })

  const saveNotes = useMutation({
    mutationFn: () => api.patch(`/hosts/${id}`, { notes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['host', id] }),
  })

  const ackHost = useMutation({
    mutationFn: () => api.post(`/hosts/${id}/acknowledge`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['host', id] })
      qc.invalidateQueries({ queryKey: ['hosts'] })
    },
  })

  const sendWol = useMutation({
    mutationFn: () => api.post('/wol/send', { host_id: +id }),
  })

  const unmergeMutation = useMutation({
    mutationFn: (aliasId) => api.post(`/hosts/${aliasId}/unmerge`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['host', id] })
      qc.invalidateQueries({ queryKey: ['hosts'] })
    },
  })

  const removeNetworkId = useMutation({
    mutationFn: (nid) => api.delete(`/hosts/${id}/network-ids/${nid}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['host', id] })
      qc.invalidateQueries({ queryKey: ['hosts'] })
    },
  })

  const updateHostname = useMutation({
    mutationFn: (hostname) => api.patch(`/hosts/${id}`, { hostname }),
    onSuccess: () => {
      setEditingHostname(false)
      qc.invalidateQueries({ queryKey: ['host', id] })
      qc.invalidateQueries({ queryKey: ['hosts'] })
    },
  })

  if (isLoading) return <div className="text-gray-500 p-4">Loading…</div>
  if (!host) return <div className="text-red-400 p-4">Host not found.</div>

  const displayNotes = notes ?? host.notes ?? ''

  return (
    <div className="space-y-6 max-w-5xl">
      <Link to="/hosts" className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors">
        <ArrowLeft size={14} /> Back to Hosts
      </Link>

      {/* Alias banner */}
      {host.primary_host_id && (
        <div className="bg-blue-900/30 border border-blue-700/40 rounded-lg p-3 text-sm text-blue-300">
          This host is an alias of{' '}
          <Link to={`/hosts/${host.primary_host_id}`} className="text-blue-400 hover:underline font-medium">
            Host #{host.primary_host_id}
          </Link>
        </div>
      )}

      {/* Header card */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              {editingHostname ? (
                <div className="flex items-center gap-2">
                  <input
                    value={hostnameInput}
                    onChange={e => setHostnameInput(e.target.value)}
                    placeholder="Hostname (blank to clear)"
                    className="text-2xl font-bold bg-gray-800 border border-gray-600 rounded px-2 py-0.5 focus:outline-none focus:border-blue-500 w-64"
                    autoFocus
                    onKeyDown={e => {
                      if (e.key === 'Enter') updateHostname.mutate(hostnameInput)
                      if (e.key === 'Escape') setEditingHostname(false)
                    }}
                  />
                  <button
                    onClick={() => updateHostname.mutate(hostnameInput)}
                    className="text-green-400 hover:text-green-300 p-1"
                    title="Save"
                  >
                    <Check size={18} />
                  </button>
                  <button
                    onClick={() => setEditingHostname(false)}
                    className="text-gray-400 hover:text-gray-300 p-1"
                    title="Cancel"
                  >
                    <X size={18} />
                  </button>
                </div>
              ) : (
                <>
                  <h1 className="text-2xl font-bold">{host.hostname || host.current_ip}</h1>
                  <button
                    onClick={() => { setHostnameInput(host.hostname || ''); setEditingHostname(true) }}
                    className="text-gray-500 hover:text-gray-300 p-1"
                    title="Edit hostname"
                  >
                    <Pencil size={14} />
                  </button>
                </>
              )}
              <StatusBadge status={host.is_up ? 'up' : 'down'} />
              {host.is_new && <StatusBadge status="new" />}
            </div>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
              <Detail label="IP"        value={<span className="font-mono">{host.current_ip}</span>} />
              <Detail label="MAC"       value={<span className="font-mono">{host.current_mac || '—'}</span>} />
              <Detail label="Vendor"    value={host.vendor || '—'} />
              <Detail label="OS"        value={host.os_guess || 'Unknown'} />
              <Detail label="First seen" value={formatDate(host.first_seen)} />
              <Detail label="Last seen"  value={formatDate(host.last_seen)} />
            </dl>

            {/* Network Identity chips */}
            {host.network_ids && host.network_ids.length > 0 && (
              <div className="mt-3">
                <span className="text-xs text-gray-500 uppercase tracking-wider">Known Identities</span>
                <div className="flex gap-2 flex-wrap mt-1">
                  {host.network_ids.map(n => (
                    <span key={n.id} className="inline-flex items-center gap-1 text-xs bg-gray-800 border border-gray-700 px-2 py-1 rounded-full font-mono group">
                      <span className="text-gray-300">{n.ip_address}</span>
                      {n.mac_address && <span className="text-gray-500">/ {n.mac_address}</span>}
                      <span className={`ml-1 px-1 rounded text-[10px] ${
                        n.source === 'dhcp' ? 'bg-green-900/40 text-green-400' :
                        n.source === 'manual' ? 'bg-blue-900/40 text-blue-400' :
                        'bg-gray-700 text-gray-400'
                      }`}>{n.source}</span>
                      <button
                        onClick={() => { if (confirm(`Remove identity ${n.ip_address}?`)) removeNetworkId.mutate(n.id) }}
                        className="ml-0.5 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Remove this identity"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2 shrink-0">
            {host.is_new && (
              <button
                onClick={() => ackHost.mutate()}
                disabled={ackHost.isPending}
                className="flex items-center gap-2 text-sm bg-purple-700 hover:bg-purple-600 disabled:opacity-50 px-3 py-2 rounded-lg transition-colors"
              >
                <CheckCheck size={14} /> Acknowledge
              </button>
            )}
            {host.wol_enabled && host.current_mac && (
              <button
                onClick={() => sendWol.mutate()}
                disabled={sendWol.isPending}
                className="flex items-center gap-2 text-sm bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 px-3 py-2 rounded-lg transition-colors"
              >
                <Zap size={14} /> {sendWol.isPending ? 'Sending…' : 'Wake'}
              </button>
            )}
            {sendWol.isSuccess && <span className="text-xs text-green-400">Packet sent!</span>}
            {sendWol.isError && (
              <span className="text-xs text-red-400">
                {sendWol.error?.response?.data?.detail ?? 'WoL failed'}
              </span>
            )}
          </div>
        </div>

        {/* Notes */}
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">Notes</label>
          <div className="flex gap-2 mt-1">
            <textarea
              value={displayNotes}
              onChange={e => setNotes(e.target.value)}
              rows={2}
              placeholder="Add notes about this host…"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => saveNotes.mutate()}
              disabled={saveNotes.isPending || notes === null}
              className="flex items-center gap-1 text-sm bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-2 rounded-lg self-start transition-colors"
            >
              <Save size={14} /> {saveNotes.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>

      {/* Aliases section */}
      {host.aliases && host.aliases.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Aliases ({host.aliases.length})</h3>
          <div className="space-y-2">
            {host.aliases.map(a => (
              <div key={a.id} className="flex items-center justify-between bg-gray-800 rounded-lg p-3">
                <div>
                  <Link to={`/hosts/${a.id}`} className="text-blue-400 hover:underline text-sm font-medium">
                    {a.hostname || a.current_ip}
                  </Link>
                  <div className="text-xs text-gray-500 font-mono mt-0.5">
                    {a.current_ip} {a.current_mac && `/ ${a.current_mac}`}
                  </div>
                </div>
                <button
                  onClick={() => unmergeMutation.mutate(a.id)}
                  disabled={unmergeMutation.isPending}
                  className="flex items-center gap-1 text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  <Unlink size={12} /> Unmerge
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {['ports', 'traffic', 'history'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize transition-colors
              ${activeTab === tab
                ? 'border-b-2 border-blue-500 text-white'
                : 'text-gray-400 hover:text-white'
              }`}
          >
            {tab}
            {tab === 'ports' && host.ports?.length > 0 && (
              <span className="ml-1.5 text-xs text-gray-500">({host.ports.length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Ports tab */}
      {activeTab === 'ports' && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          {host.ports?.length === 0 ? (
            <div className="px-5 py-8 text-center text-gray-600 text-sm">No ports recorded.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
                <tr>
                  <th className="px-4 py-3 text-left">Port</th>
                  <th className="px-4 py-3 text-left">Proto</th>
                  <th className="px-4 py-3 text-left">State</th>
                  <th className="px-4 py-3 text-left">Service</th>
                  <th className="px-4 py-3 text-left">Version / Banner</th>
                  <th className="px-4 py-3 text-left">Screenshot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {host.ports?.map(p => {
                  const WEB_PORTS = new Set([80, 443, 8080, 8443, 8000, 8888, 3000])
                  const svc = (p.service_name || '').toLowerCase()
                  const isWeb = p.protocol === 'tcp' && (WEB_PORTS.has(p.port) || svc.includes('http'))
                  const webUrl = isWeb
                    ? `${p.port === 443 || p.port === 8443 || svc.includes('https') ? 'https' : 'http'}://${host.current_ip}:${p.port}`
                    : null
                  return (
                  <tr key={p.id} className="hover:bg-gray-800/40">
                    <td className="px-4 py-2 font-mono font-bold">
                      {webUrl ? (
                        <button
                          onClick={() => window.open(webUrl, '_blank', 'noopener,noreferrer')}
                          className="text-blue-400 hover:text-blue-300 hover:underline"
                          title={`Open ${webUrl}`}
                        >
                          {p.port}
                        </button>
                      ) : (
                        <span className="text-blue-300">{p.port}</span>
                      )}
                      {p.is_new && (
                        <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded-full">new</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-400 uppercase text-xs">{p.protocol}</td>
                    <td className="px-4 py-2"><StatusBadge status={p.state} /></td>
                    <td className="px-4 py-2 text-gray-300">{p.service_name || '—'}</td>
                    <td className="px-4 py-2 text-gray-400 text-xs font-mono truncate max-w-xs">
                      {p.service_ver || p.banner || '—'}
                    </td>
                    <td className="px-4 py-2">
                      {p.screenshot_url ? (
                        <a href={p.screenshot_url} target="_blank" rel="noreferrer">
                          <img
                            src={p.screenshot_url}
                            alt="screenshot"
                            className="h-12 w-20 object-cover rounded border border-gray-700 hover:border-blue-500 transition-colors"
                          />
                        </a>
                      ) : '—'}
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Traffic tab */}
      {activeTab === 'traffic' && (
        <div className="space-y-4">
          {!trafficHistory || trafficHistory.length === 0 ? (
            <div className="text-gray-600 text-sm">No traffic data recorded for this host.</div>
          ) : (
            <>
              {/* Latest snapshot stats */}
              {(() => {
                const latest = trafficHistory[trafficHistory.length - 1]
                return (
                  <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                    <h3 className="text-sm font-semibold text-gray-300 mb-3">Latest Traffic</h3>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                      <div>
                        <div className="text-xs text-gray-500">Bytes Sent</div>
                        <div className="text-lg font-bold text-green-400">{formatBytes(latest.bytes_sent)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500">Bytes Received</div>
                        <div className="text-lg font-bold text-blue-400">{formatBytes(latest.bytes_recv)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500">Packets Sent</div>
                        <div className="text-lg font-bold text-gray-300">{latest.packets_sent?.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500">Packets Received</div>
                        <div className="text-lg font-bold text-gray-300">{latest.packets_recv?.toLocaleString()}</div>
                      </div>
                    </div>
                  </div>
                )
              })()}

              {/* Traffic chart */}
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Bandwidth (24h)</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={trafficHistory.map(p => ({
                    time: new Date(p.scraped_at + (/[Z+\-]\d*$/.test(p.scraped_at) ? '' : 'Z')).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    sent: p.bytes_sent,
                    recv: p.bytes_recv,
                  }))}>
                    <XAxis dataKey="time" tick={{ fill: '#9ca3af', fontSize: 10 }} />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} tickFormatter={formatBytes} />
                    <Tooltip
                      contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                      formatter={(v) => formatBytes(v)}
                    />
                    <Line type="monotone" dataKey="recv" name="Received" stroke="#3b82f6" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="sent" name="Sent" stroke="#22c55e" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      )}

      {/* History tab */}
      {activeTab === 'history' && (
        <div className="space-y-2">
          {host.history?.length === 0 ? (
            <div className="text-gray-600 text-sm">No change history recorded.</div>
          ) : host.history?.map(h => (
            <div key={h.id} className="bg-gray-900 rounded-lg p-4 border border-gray-800 text-sm flex gap-4">
              <div className="text-gray-600 text-xs whitespace-nowrap pt-0.5">{formatDate(h.recorded_at)}</div>
              <div>
                <span className="text-gray-400 uppercase text-xs tracking-wide">{h.event_type}</span>
                <div className="text-gray-300 text-xs mt-0.5 font-mono">
                  {h.old_value && <span className="text-red-400">{h.old_value}</span>}
                  {h.old_value && h.new_value && <span className="text-gray-600"> → </span>}
                  {h.new_value && <span className="text-green-400">{h.new_value}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Detail({ label, value }) {
  return (
    <>
      <dt className="text-gray-500">{label}</dt>
      <dd className="text-gray-200">{value}</dd>
    </>
  )
}
