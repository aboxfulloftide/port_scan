import { useEffect, useState } from 'react'
import { X, Radar, XCircle } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'

const TIERS = [
  { n: 1, label: 'ICMP Ping Sweep' },
  { n: 2, label: 'TCP Scan' },
  { n: 3, label: 'UDP Scan' },
  { n: 4, label: 'Service Fingerprint' },
  { n: 5, label: 'Screenshots' },
]

export default function ScanProgressModal({ jobId, onClose }) {
  const qc = useQueryClient()
  const [status, setStatus]             = useState('connecting')
  const [stats, setStats]               = useState({ hosts_up: 0, new_hosts_found: 0, new_ports_found: 0 })
  const [currentTier, setTier]          = useState(null)
  const [doneTiers, setDoneTiers]       = useState([])
  const [summary, setSummary]           = useState(null)
  const [done, setDone]                 = useState(false)
  const [error, setError]               = useState(null)
  const [errorMessage, setErrorMessage] = useState(null) // backend error_message for failed jobs
  const [hostProgress, setHostProgress] = useState(null) // { done, total } for active tier

  const cancel = useMutation({
    mutationFn: () => api.post(`/scans/${jobId}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan-jobs'] }),
  })

  useEffect(() => {
    if (!jobId) return
    let ws = null
    let cancelled = false

    function openWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/scans/ws/${jobId}`)
      let connected = false
      ws.onopen  = () => { connected = true; setStatus('connected') }
      ws.onclose = (e) => { if (!connected && e.code !== 1000) { setError('WebSocket connection failed'); setDone(true) } }
      ws.onerror = () => { if (!connected) { setError('WebSocket error'); setDone(true) } }
      ws.onmessage = (e) => {
        const evt = JSON.parse(e.data)
        if (evt.type === 'progress') {
          setStatus('running')
          setStats({ hosts_up: evt.hosts_up ?? 0, new_hosts_found: evt.new_hosts_found ?? 0, new_ports_found: evt.new_ports_found ?? 0 })
        } else if (evt.type === 'tier_start') {
          setTier(evt.tier); setHostProgress(evt.host_count ? { done: 0, total: evt.host_count } : null)
        } else if (evt.type === 'host_progress') {
          setHostProgress({ done: evt.done, total: evt.total })
        } else if (evt.type === 'tier_done') {
          setDoneTiers(prev => [...prev, evt.tier]); setTier(null); setHostProgress(null)
        } else if (['completed', 'failed', 'cancelled'].includes(evt.type)) {
          setStatus(evt.type); setSummary(evt.summary ?? null); setDone(true); ws.close()
        } else if (evt.type === 'job_done') {
          setStatus(evt.status ?? 'completed'); setSummary(evt); setDone(true); ws.close()
        } else if (evt.type === 'error') {
          setError(evt.message); setDone(true)
        }
      }
    }

    // Preflight: refresh token if needed AND detect already-terminal jobs so we
    // can skip the WebSocket entirely and show the result (+ any error) directly.
    api.get(`/scans/${jobId}`).then(res => {
      if (cancelled) return
      const job = res.data
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        setStatus(job.status)
        setStats({ hosts_up: job.hosts_up ?? 0, new_hosts_found: job.new_hosts_found ?? 0, new_ports_found: job.new_ports_found ?? 0 })
        if (job.error_message) setErrorMessage(job.error_message)
        setDone(true)
      } else {
        openWs()
      }
    }).catch(() => {
      if (!cancelled) openWs()
    })

    return () => { cancelled = true; ws?.close() }
  }, [jobId])

  const statusColor = {
    connecting: 'text-gray-400',
    connected:  'text-blue-400',
    running:    'text-blue-400',
    completed:  'text-green-400',
    failed:     'text-red-400',
    cancelled:  'text-yellow-400',
  }[status] ?? 'text-gray-400'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 rounded-xl w-full max-w-md p-6 border border-gray-700 space-y-5" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            {!done && <Radar size={16} className="animate-pulse text-blue-400" />}
            <h2 className="text-white font-semibold">Scan Job #{jobId}</h2>
          </div>
          <div className="flex items-center gap-2">
            {!done && (
              <button
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
                className="text-gray-400 hover:text-red-400 disabled:opacity-40"
                title="Cancel scan"
              >
                <XCircle size={18} />
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white" title="Dismiss">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Status */}
        <div className={`text-sm font-medium ${statusColor}`}>
          {!done && <span className="animate-pulse mr-1">●</span>}
          {status.charAt(0).toUpperCase() + status.slice(1)}
          {error && <span className="text-red-400 ml-2">— {error}</span>}
        </div>

        {/* Failure reason */}
        {errorMessage && (
          <div className="bg-red-950/50 border border-red-800/60 rounded-lg px-3 py-2">
            <div className="text-xs text-red-400 font-medium mb-1">Error</div>
            <div className="text-xs text-red-300 font-mono break-all whitespace-pre-wrap">{errorMessage}</div>
          </div>
        )}

        {/* Live stats */}
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            ['Hosts Up',   summary?.hosts_up        ?? stats.hosts_up],
            ['New Hosts',  summary?.new_hosts_found ?? stats.new_hosts_found],
            ['New Ports',  summary?.new_ports_found ?? stats.new_ports_found],
          ].map(([label, val]) => (
            <div key={label} className="bg-gray-800 rounded-lg py-3">
              <div className="text-2xl font-bold text-white">{val}</div>
              <div className="text-xs text-gray-400 mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* Tier progress */}
        <div className="space-y-2">
          {TIERS.map(({ n, label }) => {
            const isDone    = doneTiers.includes(n)
            const isRunning = currentTier === n
            const isPending = !isDone && !isRunning
            return (
              <div key={n} className={`flex items-center gap-3 text-sm rounded-lg px-3 py-2
                ${isRunning ? 'bg-blue-900/30 border border-blue-700/40' : 'bg-gray-800/40'}`}>
                <span className={`text-base leading-none
                  ${isDone    ? 'text-green-400' :
                    isRunning ? 'text-blue-400 animate-pulse' :
                    'text-gray-600'}`}>
                  {isDone ? '✓' : isRunning ? '●' : '○'}
                </span>
                <span className={isDone ? 'text-gray-300' : isRunning ? 'text-white' : 'text-gray-500'}>
                  Tier {n} — {label}
                </span>
                {isRunning && (
                  <span className="ml-auto text-xs text-blue-400 animate-pulse">
                    {hostProgress ? `${hostProgress.done}/${hostProgress.total}` : 'running'}
                  </span>
                )}
                {isDone && <span className="ml-auto text-xs text-green-500">done</span>}
              </div>
            )
          })}
        </div>

        <button
          onClick={onClose}
          className="w-full py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm text-gray-300 transition-colors"
        >
          {done ? 'Close' : 'Dismiss'}
        </button>
      </div>
    </div>
  )
}
