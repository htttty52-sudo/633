import { useState } from 'react'

export default function CreateDeviceModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ device_id: '', model: '', kernel_version: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!form.device_id.trim() || !form.model.trim() || !form.kernel_version.trim()) {
      setError('所有字段均为必填')
      return
    }

    setLoading(true)
    try {
      await onCreated(form)
      onClose()
    } catch (err) {
      if (err.response?.status === 409) {
        const detail = err.response.data?.detail
        setError(detail?.message || `设备ID "${form.device_id}" 已存在`)
      } else {
        setError(err.response?.data?.detail?.message || err.response?.data?.detail || '创建失败')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>创建设备</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>设备ID</label>
            <input
              value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })}
              placeholder="例如: DEV-RK3588-001"
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>设备型号</label>
            <input
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder="例如: RK3588, IMX6ULL, STM32MP1"
            />
          </div>
          <div className="form-group">
            <label>内核版本</label>
            <input
              value={form.kernel_version}
              onChange={(e) => setForm({ ...form, kernel_version: e.target.value })}
              placeholder="例如: 5.10.110"
            />
          </div>
          {error && <div className="error-msg">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={onClose}>取消</button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '创建中...' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
