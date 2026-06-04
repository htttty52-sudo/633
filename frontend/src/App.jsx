import { NavLink, Routes, Route } from 'react-router-dom'
import DevicesPage from './DevicesPage'
import TemplatesPage from './TemplatesPage'
import OtaPage from './OtaPage'

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
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<DevicesPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/ota" element={<OtaPage />} />
      </Routes>
    </div>
  )
}
