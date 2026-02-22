# Task 19: Frontend — Admin Pages (Subnets, Profiles, Schedules, Settings)

**Depends on:** Task 16, Task 08, Task 09, Task 12, Task 07  
**Complexity:** Medium  
**Description:** Implement the four admin/operator pages: Subnets CRUD, Scan Profiles CRUD, Schedules CRUD, and User Management (admin only).

---

## Files to Create

- `src/pages/Subnets.jsx`
- `src/pages/Profiles.jsx`
- `src/pages/Schedules.jsx`
- `src/pages/Settings.jsx`

---

## Shared Pattern

All four pages follow the same pattern:
1. Fetch list with `useQuery`
2. Show table
3. Modal form for create/edit (controlled state)
4. Delete with confirmation
5. Mutations via `useMutation` + `queryClient.invalidateQueries`

A reusable modal wrapper is used across all pages.

---

## `src/pages/Subnets.jsx`

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Pencil, Trash2 } from 'lucide-react'

const fetchSubnets = () => api.get('/subnets/').then(r => r.data)

function SubnetModal({ initial, onClose, onSave }) {
  const [cidr, setCidr]   = useState(initial?.cidr ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-md p-6 border border-gray-700 space-y-4">
        <h2 className="text-lg font-semibold">{initial ? 'Edit Subnet' : 'Add Subnet'}</h2>
        <div className="space-y-3">
          <input value={cidr} onChange={e => setCidr(e.target.value)} placeholder="CIDR (e.g. 192.168.1.0/24)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <input value={label} onChange={e => setLabel(e.target.value)} placeholder="Label (optional)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes (optional)" rows={2}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm resize-none" />
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm bg-gray-700 rounded-lg">Cancel</button>
          <button onClick={() => onSave({ cidr, label, notes })}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded-lg">Save</button>
        </div>
      </div>
    </div>
  )
}

export default function Subnets() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null) // null | { mode: 'create'|'edit', data? }

  const { data: subnets = [] } = useQuery({ queryKey: ['subnets'], queryFn: fetchSubnets })

  const create = useMutation({
    mutationFn: (body) => api.post('/subnets/', body),
    onSuccess: () => { qc.invalidateQueries(['subnets']); setModal(null) },
  })
  const update = useMutation({
    mutationFn: ({ id, body }) => api.put(`/subnets/${id}`, body),
    onSuccess: () => { qc.invalidateQueries(['subnets']); setModal(null) },
  })
  const remove = useMutation({
    mutationFn: (id) => api.delete(`/subnets/${id}`),
    onSuccess: () => qc.invalidateQueries(['subnets']),
  })

  const handleSave = (data) => {
    if (modal.mode === 'create') create.mutate(data)
    else update.mutate({ id: modal.data.id, body: data })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Subnets</h1>
        <button onClick={() => setModal({ mode: 'create' })}
          className="flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded-lg">
          <Plus size={14} /> Add Subnet
        </button>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left">CIDR</th>
              <th className="px-4 py-3 text-left">Label</th>
              <th className="px-4 py-3 text-left">Notes</th>
              <th className="px-4 py-3 text-left">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {subnets.map(s => (
              <tr key={s.id} className="hover:bg-gray-800/40">
                <td className="px-4 py-2 font-mono text-blue-300">{s.cidr}</td>
                <td className="px-4 py-2 text-gray-300">{s.label || '—'}</td>
                <td className="px-4 py-2 text-gray-400 text-xs truncate max-w-xs">{s.notes || '—'}</td>
                <td className="px-4 py-2 flex gap-2">
                  <button onClick={() => setModal({ mode: 'edit', data: s })}
                    className="text-gray-400 hover:text-white"><Pencil size={14} /></button>
                  <button onClick={() => { if (confirm(`Delete ${s.cidr}?`)) remove.mutate(s.id) }}
                    className="text-red-400 hover:text-red-300"><Trash2 size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && <SubnetModal initial={modal.data} onClose={() => setModal(null)} onSave={handleSave} />}
    </div>
  )
}
```

---

## `src/pages/Profiles.jsx`

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { Plus, Pencil, Trash2 } from 'lucide-react'

const fetchProfiles = () => api.get('/profiles/').then(r => r.data)

function ProfileModal({ initial, onClose, onSave }) {
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    port_range: initial?.port_range ?? '1-65535',
    enable_udp: initial?.enable_udp ?? false,
    enable_screenshots: initial?.enable_screenshots ?? true,
    concurrency: initial?.concurrency ?? 100,
    rate_limit: initial?.rate_limit ?? 300,
    timeout: initial?.timeout ?? 5,
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-lg p-6 border border-gray-700 space-y-4">
        <h2 className="text-lg font-semibold">{initial ? 'Edit Profile' : 'New Scan Profile'}</h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-gray-400">Name</label>
            <input value={form.name} onChange={set('name')}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-400">Port Range</label>
            <input value={form.port_range} onChange={set('port_range')}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono" />
          </div>
          <div>
            <label className="text-xs text-gray-400">Concurrency</label>
            <input type="number" value={form.concurrency} onChange={set('concurrency')}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-400">Rate Limit (pkts/s)</label>
            <input type="number" value={form.rate_limit} onChange={set('rate_limit')}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-400">Timeout (s)</label>
            <input type="number" value={form.timeout} onChange={set('timeout')}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          </div>
          <label className="flex items-center gap-2 text-sm col-span-2">
            <input type="checkbox" checked={form.enable_udp} onChange={set('enable_udp')} />
            Enable UDP Scan
          </label>
          <label className="flex items-center gap-2 text-sm col-span-2">
            <input type="checkbox" checked={form.enable_screenshots} onChange={set('enable_screenshots')} />
            Enable Web Screenshots
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm bg-gray-700 rounded-lg">Cancel</button>
          <button onClick={() => onSave(form)}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded-lg">Save</button>
        </div>
      </div>
    </div>
  )
}

export default function Profiles() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })

  const create = useMutation({ mutationFn: (b) => api.post('/profiles/', b), onSuccess: () => { qc.invalidateQueries(['profiles']); setModal(null) } })
  const update = useMutation({ mutationFn: ({ id, b }) => api.put(`/profiles/${id}`, b), onSuccess: () => { qc.invalidateQueries(['profiles']); setModal(null) } })
  const remove = useMutation({ mutationFn: (id) => api.delete(`/profiles/${id}`), onSuccess: () => qc.invalidateQueries(['profiles']) })

  const handleSave = (data) => modal.mode === 'create' ? create.mutate(data) : update.mutate({ id: modal.data.id, b: data })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Scan Profiles</h1>
        <button onClick={() => setModal({ mode: 'create' })}
          className="flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded-lg">
          <Plus size={14} /> New Profile
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {profiles.map(p => (
          <div key={p.id} className="bg-gray-900 rounded-xl p-5 border border-gray-800 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{p.name}</h3>
              {p.is_default && <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full">default</span>}
            </div>
            <div className="text-xs text-gray-400 space-y-1">
              <div>Ports: <span className="font-mono text-gray-200">{p.port_range}</span></div>
              <div>UDP: {p.enable_udp ? '✓' : '✗'} · Screenshots: {p.enable_screenshots ? '✓' : '✗'}</div>
              <div>Concurrency: {p.concurrency} · Rate: {p.rate_limit}/s · Timeout: {p.timeout}s</div>
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setModal({ mode: 'edit', data: p })}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-white">
                <Pencil size={12} /> Edit
              </button>
              {!p.is_default && (
                <button onClick={() => { if (confirm(`Delete "${p.name}"?`)) remove.mutate(p.id) }}
                  className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300">
                  <Trash2 size={12} /> Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {modal && <ProfileModal initial={modal.data} onClose={() => setModal(null)} onSave={handleSave} />}
    </div>
  )
}
```

---

## `src/pages/Schedules.jsx`

```jsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'

const fetchSchedules = () => api.get('/schedules/').then(r => r.data)
const fetchSubnets   = () => api.get('/subnets/').then(r => r.data)
const fetchProfiles  = () => api.get('/profiles/').then(r => r.data)

function ScheduleModal({ onClose, onSave, subnets, profiles }) {
  const [form, setForm] = useState({ name: '', subnet_id: '', profile_id: '', cron_expr: '0 2 * * *', enabled: true })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-md p-6 border border-gray-700 space-y-4">
        <h2 className="text-lg font-semibold">New Schedule</h2>
        <div className="space-y-3">
          <input value={form.name} onChange={set('name')} placeholder="Schedule name"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <select value={form.subnet_id} onChange={set('subnet_id')}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            <option value="">Select subnet…</option>
            {subnets?.map(s => <option key={s.id} value={s.id}>{s.cidr}</option>)}
          </select>
          <select value={form.profile_id} onChange={set('profile_id')}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            <option value="">Select profile…</option>
            {profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div>
            <label className="text-xs text-gray-400">Cron Expression</label>
            <input value={form.cron_expr} onChange={set('cron_expr')} placeholder="0 2 * * *"
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono" />
            <div className="text-xs text-gray-500 mt-1">e.g. "0 2 * * *" = daily at 2 AM UTC</div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.enabled} onChange={set('enabled')} /> Enabled
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm bg-gray-700 rounded-lg">Cancel</button>
          <button onClick={() => onSave({ ...form, subnet_id: +form.subnet_id, profile_id: +form.profile_id })}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded-lg">Save</button>
        </div>
      </div>
    </div>
  )
}

export default function Schedules() {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const { data: schedules = [] } = useQuery({ queryKey: ['schedules'], queryFn: fetchSchedules })
  const { data: subnets } = useQuery({ queryKey: ['subnets'], queryFn: fetchSubnets })
  const { data: profiles } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })

  const create = useMutation({ mutationFn: (b) => api.post('/schedules/', b), onSuccess: () => { qc.invalidateQueries(['schedules']); setShowModal(false) } })
  const remove = useMutation({ mutationFn: (id) => api.delete(`/schedules/${id}`), onSuccess: () => qc.invalidateQueries(['schedules']) })
  const toggle = useMutation({ mutationFn: (id) => api.post(`/schedules/${id}/toggle`), onSuccess: () => qc.invalidateQueries(['schedules']) })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Schedules</h1>
        <button onClick={() => setShowModal(true)}
          className="flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded-lg">
          <Plus size={14} /> New Schedule
        </button>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Subnet</th>
              <th className="px-4 py-3 text-left">Profile</th>
              <th className="px-4 py-3 text-left">Cron</th>
              <th className="px-4 py-3 text-left">Next Run</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {schedules.map(s => (
              <tr key={s.id} className="hover:bg-gray-800/40">
                <td className="px-4 py-2 font-medium">{s.name}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-300">{s.subnet_cidr}</td>
                <td className="px-4 py-2 text-gray-300">{s.profile_name}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{s.cron_expr}</td>
                <td className="px-4 py-2 text-xs text-gray-400">{s.next_run ? new Date(s.next_run).toLocaleString() : '—'}</td>
                <td className="px-4 py-2"><StatusBadge status={s.enabled ? 'up' : 'down'} /></td>
                <td className="px-4 py-2 flex gap-2">
                  <button onClick={() => toggle.mutate(s.id)} className="text-gray-400 hover:text-white">
                    {s.enabled ? <ToggleRight size={16} className="text-green-400" /> : <ToggleLeft size={16} />}
                  </button>
                  <button onClick={() => { if (confirm(`Delete "${s.name}"?`)) remove.mutate(s.id) }}
                    className="text-red-400 hover:text-red-300"><Trash2 size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showModal && <ScheduleModal onClose={() => setShowModal(false)} onSave={(b) => create.mutate(b)} subnets={subnets} profiles={profiles} />}
    </div>
  )
}
```

---

## `src/pages/Settings.jsx` (User Management — Admin Only)

```jsx
import { useState, useContext } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { AuthContext } from '../context/AuthContext'
import { Plus, Trash2, Key } from 'lucide-react'

const fetchUsers = () => api.get('/users/').then(r => r.data)

function UserModal({ onClose, onSave }) {
  const [form, setForm] = useState({ username: '', password: '', email: '', role: 'viewer' })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl w-full max-w-sm p-6 border border-gray-700 space-y-4">
        <h2 className="text-lg font-semibold">New User</h2>
        <div className="space-y-3">
          <input value={form.username} onChange={set('username')} placeholder="Username"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <input value={form.email} onChange={set('email')} placeholder="Email (optional)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <input type="password" value={form.password} onChange={set('password')} placeholder="Password"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <select value={form.role} onChange={set('role')}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            <option value="viewer">Viewer</option>
            <option value="operator">Operator</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm bg-gray-700 rounded-lg">Cancel</button>
          <button onClick={() => onSave(form)}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded-lg">Create</button>
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const { user: me } = useContext(AuthContext)
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)

  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: fetchUsers })
  const create = useMutation({ mutationFn: (b) => api.post('/users/', b), onSuccess: () => { qc.invalidateQueries(['users']); setShowModal(false) } })
  const remove = useMutation({ mutationFn: (id) => api.delete(`/users/${id}`), onSuccess: () => qc.invalidateQueries(['users']) })

  const roleColor = { admin: 'text-red-400', operator: 'text-yellow-400', viewer: 'text-gray-400' }

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">User Management</h1>
        {me?.role === 'admin' && (
          <button onClick={() => setShowModal(true)}
            className="flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded-lg">
            <Plus size={14} /> New User
          </button>
        )}
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left">Username</th>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Role</th>
              <th className="px-4 py-3 text-left">Created</th>
              {me?.role === 'admin' && <th className="px-4 py-3 text-left">Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-gray-800/40">
                <td className="px-4 py-2 font-medium">
                  {u.username}
                  {u.id === me?.id && <span className="ml-2 text-xs text-gray-500">(you)</span>}
                </td>
                <td className="px-4 py-2 text-gray-400">{u.email || '—'}</td>
                <td className={`px-4 py-2 font-medium ${roleColor[u.role]}`}>{u.role}</td>
                <td className="px-4 py-2 text-gray-400 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                {me?.role === 'admin' && (
                  <td className="px-4 py-2 flex gap-2">
                    <button
                      disabled={u.id === me?.id}
                      onClick={() => { if (confirm(`Delete user "${u.username}"?`)) remove.mutate(u.id) }}
                      className="text-red-400 hover:text-red-300 disabled:opacity-30">
                      <Trash2 size={14} />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showModal && <UserModal onClose={() => setShowModal(false)} onSave={(b) => create.mutate(b)} />}
    </div>
  )
}
```
