import { createBrowserRouter } from 'react-router-dom'
import ChatLayout from './layouts/ChatLayout'
import ChatContent from './components/ChatContent'
import ReportsPage from './components/ReportsPage'
import CustomersPage from './pages/CustomersPage'
import KnowledgePage from './pages/KnowledgePage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import AuthGuard from './components/AuthGuard'
import App from './App'
import HistoryPage from './pages/HistoryPage'

function AdminGuard() {
  return <AuthGuard requireAdmin><ChatLayout /></AuthGuard>
}

function CustomerGuard() {
  return <AuthGuard><App /></AuthGuard>
}

function CustomerHistoryGuard() {
  return <AuthGuard><HistoryPage /></AuthGuard>
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AdminGuard />,
    children: [
      { index: true, element: <ChatContent /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'customers', element: <CustomersPage /> },
      { path: 'knowledge', element: <KnowledgePage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
  { path: '/chat', element: <CustomerGuard /> },
  { path: '/history', element: <CustomerHistoryGuard /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
])
