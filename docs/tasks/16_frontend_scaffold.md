# Task 16: Frontend Scaffold

**Depends on:** Task 06  
**Complexity:** Medium  
**Description:** Set up the frontend project structure — Vite + React + TailwindCSS — served as static files by Nginx. Implement the app shell, routing, auth context, and API client.

---

## Stack

| Tool | Purpose |
|------|---------|
| Vite | Build tool / dev server |
| React 18 | UI framework |
| React Router v6 | Client-side routing |
| TailwindCSS | Utility-first styling |
| Axios | HTTP client |
| React Query (TanStack) | Server state management |
| Recharts | Charts on dashboard |

---

## Directory Structure

```
frontend/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api/
    │   └── client.js          # Axios instance + interceptors
    ├── context/
    │   └── AuthContext.jsx    # JWT auth state
    ├── hooks/
    │   └── useAuth.js
    ├── pages/
    │   ├── Login.jsx
    │   ├── Dashboard.jsx
    │   ├── Hosts.jsx
    │   ├── HostDetail.jsx
    │   ├── Subnets.jsx
    │   ├── Profiles.jsx
    │   ├── Schedules.jsx
    │   ├── ScanJobs.jsx
    │   └── Settings.jsx       # User management (admin)
    ├── components/
    │   ├── Layout.jsx         # Sidebar + topbar shell
    │   ├── ProtectedRoute.jsx
    │   ├── StatusBadge.jsx
    │   └── ScanProgressModal.jsx
    └── utils/
        └── format.js
```

---

## `package.json`

```json
{
  "name": "netscan-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.0.0",
    "recharts": "^2.10.0",
    "lucide-react": "^0.344.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.1.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

---

## `vite.config.js`

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  }
})
```

---

## `src/api/client.js`

```js
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,   // send httpOnly cookies
})

let isRefreshing = false
let failedQueue = []

const processQueue = (error) => {
  failedQueue.forEach(p => error ? p.reject(error) : p.resolve())
  failedQueue = []
}

api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(() => api(original)).catch(e => Promise.reject(e))
      }
      original._retry = true
      isRefreshing = true
      try {
        await api.post('/auth/refresh')
        processQueue(null)
        return api(original)
      } catch (e) {
        processQueue(e)
        window.location.href = '/login'
        return Promise.reject(e)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(err)
  }
)

export default api
```

---

## `src/context/AuthContext.jsx`

```jsx
import { createContext, useState, useEffect, useCallback } from 'react'
import api from '../api/client'

export const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchMe() }, [fetchMe])

  const login = async (username, password) => {
    await api.post('/auth/login', { username, password })
    await fetchMe()
  }

  const logout = async () => {
    await api.post('/auth/logout')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refetch: fetchMe }}>
      {children}
    </AuthContext.Provider>
  )
}
```

---

## `src/App.jsx`

```jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Hosts from './pages/Hosts'
import HostDetail from './pages/HostDetail'
import Subnets from './pages/Subnets'
import Profiles from './pages/Profiles'
import Schedules from './pages/Schedules'
import ScanJobs from './pages/ScanJobs'
import Settings from './pages/Settings'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/hosts" element={<Hosts />} />
                <Route path="/hosts/:id" element={<HostDetail />} />
                <Route path="/subnets" element={<Subnets />} />
                <Route path="/profiles" element={<Profiles />} />
                <Route path="/schedules" element={<Schedules />} />
                <Route path="/scans" element={<ScanJobs />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
```

---

## `src/components/ProtectedRoute.jsx`

```jsx
import { Navigate, Outlet } from 'react-router-dom'
import { useContext } from 'react'
import { AuthContext } from '../context/AuthContext'

export default function ProtectedRoute({ requiredRole }) {
  const { user, loading } = useContext(AuthContext)
  if (loading) return <div className="flex items-center justify-center h-screen">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (requiredRole && user.role !== requiredRole) return <Navigate to="/dashboard" replace />
  return <Outlet />
}
```

---

## `src/components/Layout.jsx`

```jsx
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useContext } from 'react'
import { AuthContext } from '../context/AuthContext'
import {
  LayoutDashboard, Monitor, Network, ScanLine,
  Clock, CalendarClock, Settings, LogOut
} from 'lucide-react'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/hosts',     icon: Monitor,         label: 'Hosts' },
  { to: '/subnets',   icon: Network,         label: 'Subnets' },
  { to: '/profiles',  icon: ScanLine,        label: 'Scan Profiles' },
  { to: '/scans',     icon: Clock,           label: 'Scan Jobs' },
  { to: '/schedules', icon: CalendarClock,   label: 'Schedules' },
  { to: '/settings',  icon: Settings,        label: 'Settings' },
]

export default function Layout() {
  const { user, logout } = useContext(AuthContext)
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 flex flex-col border-r border-gray-800">
        <div className="px-4 py-5 text-xl font-bold text-blue-400 tracking-wide">
          🔍 NetScan
        </div>
        <nav className="flex-1 px-2 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`
              }
            >
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-800 text-xs text-gray-500">
          <div className="mb-2">{user?.username} <span className="text-gray-600">({user?.role})</span></div>
          <button onClick={handleLogout} className="flex items-center gap-2 text-red-400 hover:text-red-300">
            <LogOut size={14} /> Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
```

---

## Build & Deploy

```bash
cd /home/matheau/code/port_scan/frontend
npm install
npm run build
# Output goes to /home/matheau/code/port_scan/static/
```

Nginx serves `/home/matheau/code/port_scan/static/` as the root and proxies `/api` to FastAPI (configured in Task 01).
