import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

export default function ScanProgressModal({ jobId, onClose }) {
  const [events, setEvents] = useState([])
  const [summary, setSummary] = useState(null)
  const [done, setDone] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!jobId) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/scans/ws/${jobId}`)
    ws.onmessage = (e) => {
      const evt = JSON.parse(e.data)
      setEvents(prev => [...prev, evt])
      if (['completed', 'failed', 'cancelled'].includes(evt.type)) {
        setSummary(evt.summary ?? null)
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

  const lineColor = (type) => {
    if (type === 'completed') return 'text-green-400'
    if (type === 'failed')    return 'text-red-400'
    if (type === 'error')     return 'text-red-400'
    if (type === 'progress')  return 'text-gray-300'
    return 'text-blue-400'
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-lg p-6 border border-gray-700 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold">Scan Job #{jobId}</h2>
          {done && (
            <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
              <X size={20} />
            </button>
          )}
        </div>

        <div className="bg-gray-950 rounded-lg p-3 h-52 overflow-y-auto font-mono text-xs space-y-1">
          {events.length === 0 && <div className="text-gray-600">Waiting for events…</div>}
          {events.map((evt, i) => (
            <div key={i} className={lineColor(evt.type)}>
              [{evt.type}]
              {evt.status    != null && ` status=${evt.status}`}
              {evt.hosts_up  != null && ` hosts_up=${evt.hosts_up}`}
              {evt.new_hosts_found != null && ` new_hosts=${evt.new_hosts_found}`}
              {evt.new_ports_found != null && ` new_ports=${evt.new_ports_found}`}
              {evt.message   != null && ` ${evt.message}`}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {summary && (
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              ['Hosts Up',   summary.hosts_up ?? 0],
              ['New Hosts',  summary.new_hosts_found ?? 0],
              ['New Ports',  summary.new_ports_found ?? 0],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-800 rounded-lg py-3">
                <div className="text-2xl font-bold">{val}</div>
                <div className="text-xs text-gray-400 mt-1">{label}</div>
              </div>
            ))}
          </div>
        )}

        {!done ? (
          <div className="flex items-center gap-2 text-sm text-blue-400">
            <span className="animate-pulse">●</span> Scan in progress…
          </div>
        ) : (
          <button
            onClick={onClose}
            className="w-full py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm transition-colors"
          >
            Close
          </button>
        )}
      </div>
    </div>
  )
}
