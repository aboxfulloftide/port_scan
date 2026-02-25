export function formatDate(iso) {
  if (!iso) return '—'
  // Backend returns naive UTC datetimes without a timezone suffix.
  // Appending 'Z' tells the browser to treat the value as UTC so it
  // converts correctly to the user's local time via toLocaleString().
  const str = /[Z+\-]\d*$/.test(iso) ? iso : iso + 'Z'
  return new Date(str).toLocaleString()
}

export function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const secs = Math.round((new Date(endIso) - new Date(startIso)) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const rem = secs % 60
  return rem ? `${mins}m ${rem}s` : `${mins}m`
}

export function statusColor(status) {
  switch (status) {
    case 'completed': return 'text-green-400'
    case 'running':   return 'text-blue-400'
    case 'queued':    return 'text-yellow-400'
    case 'failed':    return 'text-red-400'
    case 'cancelled': return 'text-gray-400'
    default:          return 'text-gray-400'
  }
}
