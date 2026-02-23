import { useEffect, useState } from 'react'
import StatusBadge from './StatusBadge'

export default function ScanProgressModal({ jobId, onClose }) {
  const [state, setState] = useState({ status: 'queued', hosts_up: 0, new_hosts_found: 0, new_ports_found: 0 })
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!jobId) return
    const ws = new WebSocket(`ws://${window.location.host}/api/scans/ws/${jobId}`)
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      setState(msg)
      if (msg.type === 'completed' || msg.type === 'failed' || msg.type === 'cancelled') {
        setDone(true)
      }
    }
    ws.onerror = () => setDone(true)
    return () => ws.close()
  }, [jobId])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-96 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Scan Job #{jobId}</h2>
          <StatusBadge status={state.status} />
        </div>

        <div className="grid grid-cols-3 gap-3 text-center">
          <Stat label="Hosts Up" value={state.hosts_up ?? state.summary?.hosts_up ?? 0} />
          <Stat label="New Hosts" value={state.new_hosts_found ?? state.summary?.new_hosts_found ?? 0} />
          <Stat label="New Ports" value={state.new_ports_found ?? state.summary?.new_ports_found ?? 0} />
        </div>

        {!done && (
          <div className="flex items-center gap-2 text-sm text-blue-400">
            <span className="animate-pulse">●</span> Scan in progress…
          </div>
        )}

        <button
          onClick={onClose}
          className="w-full py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm transition-colors"
        >
          {done ? 'Close' : 'Dismiss'}
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-gray-800 rounded-lg py-3">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  )
}
