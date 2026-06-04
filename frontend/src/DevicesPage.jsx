import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchDevices, createDevice, deleteDevice } from './api'
import DeviceTable from './DeviceTable'
import CreateDeviceModal from './CreateDeviceModal'

const POLL_INTERVAL = 3000

export default function DevicesPage() {
  const [devices, setDevices] = useState([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [countdown, setCountdown] = useState(POLL_INTERVAL / 1000)
  const intervalRef = useRef(null)
  const countdownRef = useRef(null)

  const loadDevices = useCallback(async () => {
    try {
      const params = {}
      if (filter !== null) params.is_online = filter
      const data = await fetchDevices(params)
      setDevices(data.devices)
      setTotal(data.total)
      setLastRefresh(new Date())
      setCountdown(POLL_INTERVAL / 1000)
    } catch (err) {
      console.error('Failed to load devices:', err)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    setLoading(true)
    loadDevices()

    intervalRef.current = setInterval(loadDevices, POLL_INTERVAL)

    countdownRef.current = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : POLL_INTERVAL / 1000))
    }, 1000)

    return () => {
      clearInterval(intervalRef.current)
      clearInterval(countdownRef.current)
    }
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

  const handleManualRefresh = () => {
    loadDevices()
  }

  const formatTime = (date) => {
    if (!date) return '--'
    return date.toLocaleTimeString('zh-CN')
  }

  return (
    <>
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

      <div className="poll-status">
        <span className="poll-indicator" />
        <span>自动刷新: {countdown}秒后更新</span>
        <span className="last-refresh">上次刷新: {formatTime(lastRefresh)}</span>
        <button className="btn-refresh" onClick={handleManualRefresh}>手动刷新</button>
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
    </>
  )
}
