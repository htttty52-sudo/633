import { useState, useEffect, useCallback } from 'react'
import { fetchDevices, createDevice, deleteDevice } from './api'
import DeviceTable from './DeviceTable'
import CreateDeviceModal from './CreateDeviceModal'

export default function App() {
  const [devices, setDevices] = useState([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState(null) // null = all, true = online, false = offline
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  const loadDevices = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter !== null) params.is_online = filter
      const data = await fetchDevices(params)
      setDevices(data.devices)
      setTotal(data.total)
    } catch (err) {
      console.error('Failed to load devices:', err)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    loadDevices()
    const interval = setInterval(loadDevices, 5000)
    return () => clearInterval(interval)
  }, [loadDevices])

  const handleCreate = async (formData) => {
    await createDevice(formData)
    await loadDevices()
  }

  const handleDelete = async (deviceId) => {
    if (!window.confirm(`确认删除设备 ${deviceId}?`)) return
    try {
      await deleteDevice(deviceId)
      await loadDevices()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>嵌入式Linux系统构建与配置平台</h1>
        <p>设备管理 - 实时监控设备在线状态</p>
      </header>

      <div className="toolbar">
        <div className="filter-group">
          <button
            className={`filter-btn ${filter === null ? 'active' : ''}`}
            onClick={() => setFilter(null)}
          >
            全部
          </button>
          <button
            className={`filter-btn ${filter === true ? 'active' : ''}`}
            onClick={() => setFilter(true)}
          >
            在线
          </button>
          <button
            className={`filter-btn ${filter === false ? 'active' : ''}`}
            onClick={() => setFilter(false)}
          >
            离线
          </button>
        </div>

        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + 创建设备
        </button>

        <span className="total-count">共 {total} 台设备</span>
      </div>

      {loading && devices.length === 0 ? (
        <div className="loading">加载中...</div>
      ) : (
        <DeviceTable devices={devices} onDelete={handleDelete} />
      )}

      {showCreate && (
        <CreateDeviceModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreate}
        />
      )}
    </div>
  )
}
