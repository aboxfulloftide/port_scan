import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
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
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <aside className="w-56 bg-gray-900 flex flex-col border-r border-gray-800 shrink-0">
        <div className="px-4 py-5 text-xl font-bold text-blue-400 tracking-wide">
          NetScan
        </div>
        <nav className="flex-1 px-2 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive
                   ? 'bg-blue-600 text-white'
                   : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                 }`
              }
            >
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-800 text-xs text-gray-500">
          <div className="mb-2">
            {user?.username}{' '}
            <span className="text-gray-600">({user?.role})</span>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-red-400 hover:text-red-300 transition-colors"
          >
            <LogOut size={14} /> Logout
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
