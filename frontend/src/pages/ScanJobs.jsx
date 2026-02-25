import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import ScanProgressModal from '../components/ScanProgressModal'
import { formatDate, formatDuration } from '../utils/format'
import { XCircle } from 'lucide-react'

export default function ScanJobs() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [activeJob, setActiveJob] = useState(null)
  const perPage = 20

  const { data, isLoading } = useQuery({
    queryKey: ['scan-jobs', page],
    queryFn: () => api.get('/scans', { params: { page, per_page: perPage } }).then(r => r.data),
    refetchInterval: 5000,
  })

  const cancel = useMutation({
    mutationFn: (id) => api.post(`/scans/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scan-jobs'] }),
  })

  const jobs = data?.scans ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Scan Jobs</h1>
        <div className="text-sm text-gray-400">{total} total</div>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading...</div>
      ) : (
        <>
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left text-gray-400 font-medium px-4 py-3">ID</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Status</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Profile</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Hosts</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Started</th>
                  <th className="text-left text-gray-400 font-medium px-4 py-3">Duration</th>
                  <th className="text-right text-gray-400 font-medium px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => (
                  <tr
                    key={j.id}
                    className="border-b border-gray-800 last:border-0 hover:bg-gray-800/40 cursor-pointer"
                    onClick={() => setActiveJob(j.id)}
                  >
                    <td className="px-4 py-3 text-gray-400 font-mono">#{j.id}</td>
                    <td className="px-4 py-3"><StatusBadge status={j.status} /></td>
                    <td className="px-4 py-3 text-gray-300">{j.profile_name ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-300">{j.hosts_discovered ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-400">{j.started_at ? formatDate(j.started_at) : '—'}</td>
                    <td className="px-4 py-3 text-gray-400">{formatDuration(j.started_at, j.completed_at)}</td>
                    <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                      {(j.status === 'queued' || j.status === 'running') && (
                        <button
                          onClick={() => cancel.mutate(j.id)}
                          disabled={cancel.isPending}
                          className="text-gray-400 hover:text-red-400"
                          title="Cancel job"
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No scan jobs found</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm text-gray-400">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {activeJob && (
        <ScanProgressModal jobId={activeJob} onClose={() => setActiveJob(null)} />
      )}
    </div>
  )
}
