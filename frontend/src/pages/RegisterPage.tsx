import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare } from 'lucide-react'

interface LoginResponse {
  access_token: string
  token_type: string
  user: { id: number; username: string; role: string }
}

export default function RegisterPage() {
  const navigate = useNavigate()

  // Tab: 注册 / 登录 (default: 注册)
  const [tab, setTab] = useState<'register' | 'login'>('register')

  // Form fields
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as any).detail || '登录失败')
      }

      const data: LoginResponse = await res.json()
      localStorage.setItem('crmbot_token', data.access_token)
      localStorage.setItem('crmbot_user', JSON.stringify(data.user))

      navigate('/chat', { replace: true })
    } catch (e: any) {
      setError(e.message || '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('两次密码输入不一致')
      return
    }

    setLoading(true)

    try {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role: 'customer' }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as any).detail || '注册失败')
      }

      const data: LoginResponse = await res.json()
      localStorage.setItem('crmbot_token', data.access_token)
      localStorage.setItem('crmbot_user', JSON.stringify(data.user))

      navigate('/chat', { replace: true })
    } catch (e: any) {
      setError(e.message || '注册失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-neutral-50">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-lg">
        {/* Logo */}
        <div className="mb-6 flex flex-col items-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 mb-3">
            <MessageSquare size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-semibold">CRMBOT</h1>
          <p className="mt-1 text-sm text-neutral-500">客户咨询端</p>
        </div>

        {/* Tabs: 注册 / 登录 */}
        <div className="mb-4 flex rounded-lg border border-neutral-200 bg-neutral-50 p-0.5">
          <button
            onClick={() => { setTab('register'); setError('') }}
            className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
              tab === 'register'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-500 hover:text-neutral-700'
            }`}
          >
            注册
          </button>
          <button
            onClick={() => { setTab('login'); setError('') }}
            className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
              tab === 'login'
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-500 hover:text-neutral-700'
            }`}
          >
            登录
          </button>
        </div>

        {/* Register form */}
        {tab === 'register' && (
          <form onSubmit={handleRegister} className="flex flex-col gap-4">
            {error && (
              <div className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600">
                {error}
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-sm font-medium text-neutral-700">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                required
                className="w-full rounded-lg border border-neutral-300 px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-neutral-700">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                required
                minLength={4}
                className="w-full rounded-lg border border-neutral-300 px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-neutral-700">
                确认密码
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="请再次输入密码"
                required
                minLength={4}
                className="w-full rounded-lg border border-neutral-300 px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="mt-1 w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? '注册中...' : '注册'}
            </button>
          </form>
        )}

        {/* Login form */}
        {tab === 'login' && (
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            {error && (
              <div className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600">
                {error}
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-sm font-medium text-neutral-700">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                required
                className="w-full rounded-lg border border-neutral-300 px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-neutral-700">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                required
                className="w-full rounded-lg border border-neutral-300 px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="mt-1 w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? '登录中...' : '登录'}
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-xs text-neutral-400">
          新用户请先注册账号
        </p>
      </div>
    </div>
  )
}
