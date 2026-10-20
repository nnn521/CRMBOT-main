import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import {
  MessageSquare,
  Users,
  BarChart3,
  BookOpen,
  Settings,
  LogOut,
} from 'lucide-react'
import { logout } from '@/api/chat'
import { useChatStore } from '@/stores/chat'

const NAV_ITEMS = [
  { icon: MessageSquare, label: '消息', path: '/' },
  { icon: Users, label: '客户', path: '/customers' },
  { icon: BarChart3, label: '报表', path: '/reports' },
  { icon: BookOpen, label: '知识库', path: '/knowledge' },
  { icon: Settings, label: '设置', path: '/settings' },
]

export default function ChatLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  async function handleLogout() {
    await logout()
    localStorage.removeItem('crmbot_user')
    useChatStore.getState().refreshSessionId()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white">
      {/* Left: Icon Nav Bar (72px, with labels) */}
      <nav className="flex w-[72px] shrink-0 flex-col items-center gap-2.5 bg-[#1a1a1a] py-4">
        {/* Logo / brand */}
        <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
          <MessageSquare size={16} className="text-white" strokeWidth={1.5} />
        </div>

        {NAV_ITEMS.map((item) => (
          <button
            key={item.label}
            onClick={() => navigate(item.path)}
            className={`flex w-full flex-col items-center gap-1 py-1.5 transition-colors ${
              isActive(item.path)
                ? 'text-white'
                : 'text-neutral-500 hover:text-white'
            }`}
          >
            <item.icon size={20} strokeWidth={1.5} />
            <span className="text-[10px] leading-none">{item.label}</span>
          </button>
        ))}

        <div className="mt-auto" />

        {/* Logout */}
        <button
          onClick={handleLogout}
          aria-label="退出登录"
          className="flex w-full flex-col items-center gap-1 py-1.5 text-neutral-500 hover:text-white transition-colors"
          title="退出登录"
        >
          <LogOut size={18} strokeWidth={1.5} />
          <span className="text-[10px] leading-none">退出</span>
        </button>
      </nav>

      {/* Content area — child routes render via <Outlet /> */}
      <Outlet />
    </div>
  )
}
