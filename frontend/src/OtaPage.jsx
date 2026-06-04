import { useState, useEffect, useCallback } from 'react'
import {
  fetchFirmwares, createFirmware, deleteFirmware,
  fetchOtaTasks, createOtaTask, getOtaTask,
  confirmBatch, abortOtaTask, fetchOtaDeviceTasks,
} from './otaApi'

const POLL_INTERVAL = 3000

export default function OtaPage() {
  const [tab, setTab] = useState('firmwares')
  const [firmwares, setFirmwares] = useState([])
  const [tasks, setTasks] = useState([])
  const [showFwModal, setShowFwModal] = useState(false)
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [selectedTask, setSelectedTask] = useState(null)

  const loadFirmwares = useCallback(async () => {
    try {
      const resp = await fetchFirmwares()
      setFirmwares(resp.data.firmwares)
    } catch (e) { /* ignore */ }
  }, [])

  const loadTasks = useCallback(async () => {
    try {
      const resp = await fetchOtaTasks()
      setTasks(resp.data.tasks)
    } catch (e) { /* ignore */ }
  }, [])

  useEffect(() => {
    loadFirmwares()
    loadTasks()
    const interval = setInterval(() => {
      loadFirmwares()
      loadTasks()
    }, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [loadFirmwares, loadTasks])

  return (
    <div className="ota-page">
      <div className="ota-tabs">
        <button
          className={`tab-btn ${tab === 'firmwares' ? 'active' : ''}`}
          onClick={() => setTab('firmwares')}
        >
          固件管理
        </button>
        <button
          className={`tab-btn ${tab === 'tasks' ? 'active' : ''}`}
          onClick={() => setTab('tasks')}
        >
          升级任务
        </button>
      </div>

      {tab === 'firmwares' && (
        <FirmwareSection
          firmwares={firmwares}
          onRefresh={loadFirmwares}
          showModal={showFwModal}
          setShowModal={setShowFwModal}
        />
      )}

      {tab === 'tasks' && !selectedTask && (
        <TaskSection
          tasks={tasks}
          firmwares={firmwares}
          onRefresh={loadTasks}
          showModal={showTaskModal}
          setShowModal={setShowTaskModal}
          onSelectTask={setSelectedTask}
        />
      )}

      {tab === 'tasks' && selectedTask && (
        <TaskDetail
          taskId={selectedTask}
          onBack={() => setSelectedTask(null)}
        />
      )}
    </div>
  )
}

function FirmwareSection({ firmwares, onRefresh, showModal, setShowModal }) {
  const handleDelete = async (id) => {
    if (!window.confirm('确认删除此固件？')) return
    await deleteFirmware(id)
    onRefresh()
  }

  return (
    <div className="ota-section">
      <div className="section-toolbar">
        <h3>固件列表</h3>
        <button className="btn-primary" onClick={() => setShowModal(true)}>上传固件</button>
      </div>
      <table className="device-table">
        <thead>
          <tr>
            <th>版本</th>
            <th>目标型号</th>
            <th>文件名</th>
            <th>大小</th>
            <th>校验和</th>
            <th>上传时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {firmwares.map(fw => (
            <tr key={fw.id}>
              <td><strong>{fw.version}</strong></td>
              <td>{fw.target_model}</td>
              <td>{fw.filename}</td>
              <td>{(fw.file_size / 1024 / 1024).toFixed(2)} MB</td>
              <td className="hash-cell">{fw.checksum.slice(0, 12)}...</td>
              <td>{new Date(fw.created_at).toLocaleString()}</td>
              <td>
                <button className="btn-danger" onClick={() => handleDelete(fw.id)}>删除</button>
              </td>
            </tr>
          ))}
          {firmwares.length === 0 && (
            <tr><td colSpan="7" className="empty-cell">暂无固件</td></tr>
          )}
        </tbody>
      </table>
      {showModal && <FirmwareModal onClose={() => setShowModal(false)} onSuccess={onRefresh} />}
    </div>
  )
}

function FirmwareModal({ onClose, onSuccess }) {
  const [form, setForm] = useState({
    version: '', target_model: '', filename: '', file_size: '', description: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.version || !form.target_model || !form.filename || !form.file_size) {
      setError('请填写所有必填字段')
      return
    }
    setLoading(true)
    setError('')
    try {
      await createFirmware({
        ...form,
        file_size: parseInt(form.file_size, 10),
      })
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || '上传失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>上传固件</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>固件版本 *</label>
            <input value={form.version} onChange={e => setForm({...form, version: e.target.value})} placeholder="例如: v2.1.0" />
          </div>
          <div className="form-group">
            <label>目标设备型号 *</label>
            <input value={form.target_model} onChange={e => setForm({...form, target_model: e.target.value})} placeholder="例如: RK3588" />
          </div>
          <div className="form-group">
            <label>文件名 *</label>
            <input value={form.filename} onChange={e => setForm({...form, filename: e.target.value})} placeholder="例如: firmware-v2.1.0.bin" />
          </div>
          <div className="form-group">
            <label>文件大小 (字节) *</label>
            <input type="number" value={form.file_size} onChange={e => setForm({...form, file_size: e.target.value})} placeholder="例如: 15728640" />
          </div>
          <div className="form-group">
            <label>描述</label>
            <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="版本说明..." />
          </div>
          {error && <div className="error-msg">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '上传中...' : '上传'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TaskSection({ tasks, firmwares, onRefresh, showModal, setShowModal, onSelectTask }) {
  const statusLabel = (status) => {
    const map = {
      'batch1_pending': '等待确认 (10%)',
      'batch1_running': '执行中 (10%)',
      'batch2_pending': '等待确认 (50%)',
      'batch2_running': '执行中 (50%)',
      'batch3_pending': '等待确认 (100%)',
      'batch3_running': '执行中 (100%)',
      'completed': '已完成',
      'aborted': '已中止',
    }
    return map[status] || status
  }

  const statusClass = (status) => {
    if (status === 'completed') return 'status-success'
    if (status === 'aborted') return 'status-failed'
    if (status.includes('running')) return 'status-upgrading'
    return 'status-pending'
  }

  return (
    <div className="ota-section">
      <div className="section-toolbar">
        <h3>升级任务</h3>
        <button className="btn-primary" onClick={() => setShowModal(true)}>创建任务</button>
      </div>
      <table className="device-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>目标型号</th>
            <th>设备数</th>
            <th>批次 (10%/50%/100%)</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(task => (
            <tr key={task.id}>
              <td>{task.id}</td>
              <td>{task.target_model}</td>
              <td>{task.total_devices}</td>
              <td>{task.batch1_size} / {task.batch2_size} / {task.batch3_size}</td>
              <td><span className={`status-badge ${statusClass(task.status)}`}>{statusLabel(task.status)}</span></td>
              <td>{new Date(task.created_at).toLocaleString()}</td>
              <td>
                <button className="btn-link" onClick={() => onSelectTask(task.id)}>详情</button>
              </td>
            </tr>
          ))}
          {tasks.length === 0 && (
            <tr><td colSpan="7" className="empty-cell">暂无升级任务</td></tr>
          )}
        </tbody>
      </table>
      {showModal && <TaskModal firmwares={firmwares} onClose={() => setShowModal(false)} onSuccess={onRefresh} />}
    </div>
  )
}

function TaskModal({ firmwares, onClose, onSuccess }) {
  const [firmwareId, setFirmwareId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!firmwareId) {
      setError('请选择固件')
      return
    }
    setLoading(true)
    setError('')
    try {
      await createOtaTask({ firmware_id: parseInt(firmwareId, 10) })
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>创建OTA升级任务</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>选择固件 *</label>
            <select value={firmwareId} onChange={e => setFirmwareId(e.target.value)}>
              <option value="">-- 请选择固件 --</option>
              {firmwares.map(fw => (
                <option key={fw.id} value={fw.id}>
                  {fw.version} ({fw.target_model}) - {fw.filename}
                </option>
              ))}
            </select>
          </div>
          {error && <div className="error-msg">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '创建中...' : '创建任务'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TaskDetail({ taskId, onBack }) {
  const [task, setTask] = useState(null)
  const [deviceTasks, setDeviceTasks] = useState([])
  const [loading, setLoading] = useState(false)

  const loadDetail = useCallback(async () => {
    try {
      const [taskResp, devResp] = await Promise.all([
        getOtaTask(taskId),
        fetchOtaDeviceTasks(taskId, { limit: 200 }),
      ])
      setTask(taskResp.data)
      setDeviceTasks(devResp.data.device_tasks)
    } catch (e) { /* ignore */ }
  }, [taskId])

  useEffect(() => {
    loadDetail()
    const interval = setInterval(loadDetail, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [loadDetail])

  const handleConfirm = async () => {
    if (!window.confirm(`确认执行第 ${task.current_batch} 批升级？`)) return
    setLoading(true)
    try {
      await confirmBatch(taskId)
      await loadDetail()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAbort = async () => {
    if (!window.confirm('确认中止升级任务？')) return
    setLoading(true)
    try {
      await abortOtaTask(taskId)
      await loadDetail()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  if (!task) return <div className="loading">加载中...</div>

  const canConfirm = task.status.endsWith('_pending')
  const canAbort = !['completed', 'aborted'].includes(task.status)

  return (
    <div className="task-detail">
      <button className="btn-link" onClick={onBack}>&larr; 返回任务列表</button>

      <div className="task-header">
        <h3>升级任务 #{task.id}</h3>
        <span className={`status-badge ${task.status === 'completed' ? 'status-success' : task.status === 'aborted' ? 'status-failed' : 'status-upgrading'}`}>
          {task.status}
        </span>
      </div>

      <div className="task-info">
        <div><strong>目标型号:</strong> {task.target_model}</div>
        <div><strong>设备总数:</strong> {task.total_devices}</div>
        <div><strong>当前批次:</strong> {task.current_batch}</div>
      </div>

      <div className="batch-progress">
        <BatchStep batch={1} size={task.batch1_size} stats={task.batch1} current={task.current_batch} label="10%" />
        <BatchStep batch={2} size={task.batch2_size} stats={task.batch2} current={task.current_batch} label="50%" />
        <BatchStep batch={3} size={task.batch3_size} stats={task.batch3} current={task.current_batch} label="100%" />
      </div>

      <div className="task-actions">
        {canConfirm && (
          <button className="btn-primary" onClick={handleConfirm} disabled={loading}>
            {loading ? '执行中...' : `确认执行第 ${task.current_batch} 批`}
          </button>
        )}
        {canAbort && (
          <button className="btn-danger" onClick={handleAbort} disabled={loading}>
            中止任务
          </button>
        )}
      </div>

      <h4>设备升级详情</h4>
      <table className="device-table">
        <thead>
          <tr>
            <th>设备ID</th>
            <th>批次</th>
            <th>状态</th>
            <th>原版本</th>
            <th>目标版本</th>
            <th>错误信息</th>
            <th>完成时间</th>
          </tr>
        </thead>
        <tbody>
          {deviceTasks.map(dt => (
            <tr key={dt.id}>
              <td>{dt.device_id}</td>
              <td>第{dt.batch_number}批</td>
              <td><span className={`status-badge status-${dt.status}`}>{dt.status}</span></td>
              <td>{dt.previous_version}</td>
              <td>{dt.target_version}</td>
              <td className="error-cell">{dt.error_message || '-'}</td>
              <td>{dt.completed_at ? new Date(dt.completed_at).toLocaleString() : '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BatchStep({ batch, size, stats, current, label }) {
  let stepClass = 'batch-step'
  if (current > batch) stepClass += ' batch-done'
  else if (current === batch) stepClass += ' batch-active'

  return (
    <div className={stepClass}>
      <div className="batch-label">第{batch}批 ({label})</div>
      <div className="batch-size">{size} 台设备</div>
      {stats && (
        <div className="batch-stats">
          {stats.success > 0 && <span className="stat-success">{stats.success} 成功</span>}
          {stats.failed > 0 && <span className="stat-failed">{stats.failed} 失败</span>}
          {stats.pending > 0 && <span className="stat-pending">{stats.pending} 等待</span>}
        </div>
      )}
    </div>
  )
}
