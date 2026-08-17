import { useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

interface Props {
  children: ReactNode
  /** B端需要 admin 角色，C端只检查 token */
  requireAdmin?: boolean
}

export default function AuthGuard({ children, requireAdmin = false }: Props) {
  const navigate = useNavigate()

  useEffect(() => {
    const token = localStorage.getItem('crmbot_token')
    if (!token) {
      navigate(requireAdmin ? '/login' : '/register', { replace: true })
      return
    }
    if (requireAdmin) {
      const userStr = localStorage.getItem('crmbot_user')
      if (!userStr) {
        navigate('/login', { replace: true })
        return
      }
      try {
        const user = JSON.parse(userStr)
        if (user.role !== 'admin') {
          navigate('/login', { replace: true })
        }
      } catch {
        navigate('/login', { replace: true })
      }
    }
  }, [navigate, requireAdmin])

  return <>{children}</>
}
