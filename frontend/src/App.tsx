import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import LoginPage from './pages/LoginPage'
import AppLayout from './pages/AppLayout'
import ChatPage from './pages/ChatPage'
import IssueIntelligencePage from './pages/IssueIntelligencePage'
import AdminDocumentsPage from './pages/AdminDocumentsPage'
import './App.css'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth()
  if (loading) return <div className="center">Loading…</div>
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <AppLayout />
              </PrivateRoute>
            }
          >
            <Route index element={<ChatPage />} />
            <Route path="intelligence" element={<IssueIntelligencePage />} />
            <Route path="documents" element={<AdminDocumentsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
