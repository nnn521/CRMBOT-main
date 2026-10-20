import { useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

interface Props {
  children: ReactNode
  /** B端需要 admin 角色，C端只检查本地用户信息（后端仍做最终鉴权） */
  requireAdmin?: boolean
}

export default function AuthGuard({ children, requireAdmin = false }: Props) {
  const navigate = useNavigate()

  useEffect(() => {
    function check() {
      const userStr = localStorage.getItem('crmbot_user')
      if (!userStr) {
        navigate(requireAdmin ? '/login' : '/register', { replace: true })
        return
      }
      if (requireAdmin) {
        try {
          const user = JSON.parse(userStr) as { role?: string }
          if (user.role !== 'admin') {
            navigate('/login', { replace: true })
          }
        } catch {
          navigate('/login', { replace: true })
        }
      }
    }
    check()
    // 401 会话失效（apiFetch 触发）时重新检查
    window.addEventListener('auth-expired', check)
    return () => window.removeEventListener('auth-expired', check)
  }, [navigate, requireAdmin])

  return <>{children}</>
}
