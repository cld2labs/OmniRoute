import { Navigate, Route, Routes } from 'react-router-dom'
import ChatAccessGuard from './components/ChatAccessGuard'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import HomePage from './pages/HomePage'
import UploadPage from './pages/UploadPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />} path="/">
        <Route element={<HomePage />} index />
        <Route
          element={
            <ChatAccessGuard>
              <ChatPage />
            </ChatAccessGuard>
          }
          path="chat"
        />
        <Route element={<UploadPage />} path="upload" />
        <Route element={<Navigate replace to="/" />} path="admin" />
        <Route element={<Navigate replace to="/chat" />} path="admin/chat" />
        <Route element={<Navigate replace to="/upload" />} path="admin/data" />
        <Route element={<Navigate replace to="/" />} path="admin/incidents" />
        <Route element={<Navigate replace to="/" />} path="admin/simulation" />
      </Route>
      <Route element={<Navigate replace to="/" />} path="*" />
    </Routes>
  )
}
