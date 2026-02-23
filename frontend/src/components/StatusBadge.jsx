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
