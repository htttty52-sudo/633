import { NavLink, Routes, Route } from 'react-router-dom'
import DevicesPage from './DevicesPage'
import TemplatesPage from './TemplatesPage'
import OtaPage from './OtaPage'
import DashboardPage from './DashboardPage'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>嵌入式Linux系统构建与配置平台</h1>
        <nav className="nav-bar">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            设备管理
          </NavLink>
          <NavLink to="/templates" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            配置模板
          </NavLink>
          <NavLink to="/ota" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            OTA升级
          </NavLink>
          <NavLink to="/dashboard" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            系统构建看板
          </NavLink>
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<DevicesPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/ota" element={<OtaPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </div>
  )
}
