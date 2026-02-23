const colors = {
  completed: 'bg-green-900 text-green-300',
  running:   'bg-blue-900 text-blue-300',
  queued:    'bg-yellow-900 text-yellow-300',
  failed:    'bg-red-900 text-red-300',
  cancelled: 'bg-gray-800 text-gray-400',
  up:        'bg-green-900 text-green-300',
  down:      'bg-red-900 text-red-300',
}

export default function StatusBadge({ status }) {
  const cls = colors[status] ?? 'bg-gray-800 text-gray-400'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}
