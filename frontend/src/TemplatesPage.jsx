import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchDevices } from './api'
import {
  fetchTemplates, createTemplate, updateTemplate, deleteTemplate,
  renderPreview, validateTemplate,
  createBinding, fetchBindings, deleteBinding,
  createDeployment, fetchDeployments,
} from './templateApi'

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadTemplates = useCallback(async () => {
    try {
      const data = await fetchTemplates()
      setTemplates(data.templates)
    } catch (err) {
      console.error('Failed to load templates:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadTemplates() }, [loadTemplates])

  const handleDelete = async (id) => {
    if (!window.confirm('确认删除此模板?')) return
    try {
      await deleteTemplate(id)
      if (selectedTemplate?.id === id) setSelectedTemplate(null)
      await loadTemplates()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div className="templates-page">
      <div className="templates-toolbar">
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ 创建模板</button>
        <span className="total-count">共 {templates.length} 个模板</span>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : (
        <div className="templates-layout">
          <div className="templates-list">
            <table className="device-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>描述</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((t) => (
                  <tr key={t.id} className={selectedTemplate?.id === t.id ? 'selected-row' : ''}>
                    <td>
                      <a href="#" onClick={(e) => { e.preventDefault(); setSelectedTemplate(t) }}>
                        {t.name}
                      </a>
                    </td>
                    <td>{t.description || '--'}</td>
                    <td>{new Date(t.created_at).toLocaleDateString('zh-CN')}</td>
                    <td>
                      <button className="btn-danger btn-sm" onClick={() => handleDelete(t.id)}>删除</button>
                    </td>
                  </tr>
                ))}
                {templates.length === 0 && (
                  <tr><td colSpan="4" className="empty-state">暂无模板，点击"创建模板"开始</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {selectedTemplate && (
            <TemplateDetail
              template={selectedTemplate}
              onUpdated={(t) => { setSelectedTemplate(t); loadTemplates() }}
            />
          )}
        </div>
      )}

      {showCreate && (
        <CreateTemplateModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadTemplates() }}
        />
      )}
    </div>
  )
}

function CreateTemplateModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', description: '', content: '' })
  const [error, setError] = useState('')
  const [yamlError, setYamlError] = useState(null)
  const [loading, setLoading] = useState(false)
  const validateTimer = useRef(null)

  const handleContentChange = (value) => {
    setForm({ ...form, content: value })
    if (validateTimer.current) clearTimeout(validateTimer.current)
    if (!value.trim()) {
      setYamlError(null)
      return
    }
    validateTimer.current = setTimeout(async () => {
      try {
        const result = await validateTemplate(value)
        setYamlError(result.valid ? null : result.error)
      } catch {
        setYamlError(null)
      }
    }, 500)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.content.trim()) {
      setError('名称和内容不能为空')
      return
    }
    setLoading(true)
    setError('')
    try {
      await createTemplate(form)
      onCreated()
    } catch (err) {
      setError(err.response?.data?.detail || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h2>创建配置模板</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>模板名称</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="例如: network-config"
            />
          </div>
          <div className="form-group">
            <label>描述</label>
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="可选描述"
            />
          </div>
          <div className="form-group">
            <label>模板内容 (YAML + Jinja2)</label>
            <textarea
              className={`yaml-editor ${yamlError ? 'yaml-editor-error' : ''}`}
              value={form.content}
              onChange={(e) => handleContentChange(e.target.value)}
              placeholder={'hostname: "{{ device_id }}"\nmodel: "{{ model }}"\nkernel: "{{ kernel_version }}"'}
              rows={10}
            />
            {yamlError && (
              <div className="yaml-live-error">{yamlError}</div>
            )}
          </div>
          {error && <div className="error-msg">{error}</div>}
          <div className="modal-actions">
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '创建中...' : '创建'}
            </button>
            <button type="button" className="btn-cancel" onClick={onClose}>取消</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TemplateDetail({ template, onUpdated }) {
  const [content, setContent] = useState(template.content)
  const [devices, setDevices] = useState([])
  const [bindings, setBindings] = useState([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [previewResult, setPreviewResult] = useState(null)
  const [previewError, setPreviewError] = useState(null)
  const [yamlError, setYamlError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deployments, setDeployments] = useState({})
  const validateTimer = useRef(null)

  useEffect(() => {
    setContent(template.content)
    setPreviewResult(null)
    setPreviewError(null)
    setYamlError(null)
    loadBindings()
    loadDevices()
  }, [template.id])

  const loadDevices = async () => {
    try {
      const data = await fetchDevices()
      setDevices(data.devices)
    } catch (err) {
      console.error('Failed to load devices:', err)
    }
  }

  const loadBindings = async () => {
    try {
      const data = await fetchBindings({ template_id: template.id })
      setBindings(data.bindings)
    } catch (err) {
      console.error('Failed to load bindings:', err)
    }
  }

  const handleContentChange = (value) => {
    setContent(value)
    if (validateTimer.current) clearTimeout(validateTimer.current)
    if (!value.trim()) {
      setYamlError(null)
      return
    }
    validateTimer.current = setTimeout(async () => {
      try {
        const result = await validateTemplate(value)
        setYamlError(result.valid ? null : result.error)
      } catch {
        setYamlError(null)
      }
    }, 500)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await updateTemplate(template.id, { content })
      onUpdated(updated)
      await loadBindings()
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  const handleBind = async () => {
    if (!selectedDevice) return
    try {
      await createBinding(template.id, selectedDevice)
      setSelectedDevice('')
      await loadBindings()
    } catch (err) {
      alert('绑定失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleUnbind = async (bindingId) => {
    if (!window.confirm('确认解除绑定?')) return
    try {
      await deleteBinding(bindingId)
      await loadBindings()
    } catch (err) {
      alert('解绑失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handlePreview = async (deviceId) => {
    setPreviewResult(null)
    setPreviewError(null)
    try {
      const result = await renderPreview(template.id, deviceId)
      setPreviewResult(result)
    } catch (err) {
      if (err.response?.status === 422) {
        setPreviewError(err.response.data.detail)
      } else {
        setPreviewError({ error_type: 'request_error', message: err.message, details: {} })
      }
    }
  }

  const handleDeploy = async (bindingId) => {
    try {
      const task = await createDeployment(bindingId)
      setDeployments((prev) => ({
        ...prev,
        [bindingId]: [task, ...(prev[bindingId] || [])],
      }))
      await loadBindings()
    } catch (err) {
      alert('下发失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const loadDeploymentHistory = async (bindingId) => {
    try {
      const data = await fetchDeployments({ binding_id: bindingId })
      setDeployments((prev) => ({ ...prev, [bindingId]: data.deployments }))
    } catch (err) {
      console.error('Failed to load deployments:', err)
    }
  }

  const boundDeviceIds = bindings.map((b) => b.device_id)
  const availableDevices = devices.filter((d) => !boundDeviceIds.includes(d.device_id))

  return (
    <div className="template-detail">
      <h3>{template.name}</h3>
      <p className="template-desc">{template.description || '无描述'}</p>

      <div className="detail-section">
        <h4>模板内容</h4>
        <textarea
          className={`yaml-editor ${yamlError ? 'yaml-editor-error' : ''}`}
          value={content}
          onChange={(e) => handleContentChange(e.target.value)}
          rows={12}
        />
        {yamlError && (
          <div className="yaml-live-error">{yamlError}</div>
        )}
        <div className="editor-actions">
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '保存中...' : '保存（更新绑定哈希）'}
          </button>
        </div>
      </div>

      <div className="detail-section">
        <h4>绑定设备</h4>
        <div className="bind-row">
          <select value={selectedDevice} onChange={(e) => setSelectedDevice(e.target.value)}>
            <option value="">选择设备...</option>
            {availableDevices.map((d) => (
              <option key={d.device_id} value={d.device_id}>{d.device_id} ({d.model})</option>
            ))}
          </select>
          <button className="btn-primary" onClick={handleBind} disabled={!selectedDevice}>绑定</button>
        </div>

        {bindings.length > 0 && (
          <table className="device-table bindings-table">
            <thead>
              <tr>
                <th>设备ID</th>
                <th>配置状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {bindings.map((b) => (
                <BindingRow
                  key={b.id}
                  binding={b}
                  onPreview={() => handlePreview(b.device_id)}
                  onDeploy={() => handleDeploy(b.id)}
                  onUnbind={() => handleUnbind(b.id)}
                  onLoadHistory={() => loadDeploymentHistory(b.id)}
                  deployments={deployments[b.id] || []}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {(previewResult || previewError) && (
        <div className="detail-section">
          <h4>渲染预览</h4>
          {previewResult && (
            <div className="preview-panel">
              <div className="preview-meta">
                <span>Hash: <code>{previewResult.config_hash.substring(0, 16)}...</code></span>
                <span className="preview-vars">
                  注入变量: {Object.entries(previewResult.variables_used).map(([k, v]) => `${k}="${v}"`).join(', ')}
                </span>
              </div>
              <pre className="rendered-output">{previewResult.rendered_content}</pre>
            </div>
          )}
          {previewError && (
            <div className="render-error">
              <div className="error-type">
                {previewError.error_type === 'syntax_error' && 'Jinja2 模板语法错误'}
                {previewError.error_type === 'missing_variable' && 'Jinja2 变量未定义'}
                {previewError.error_type === 'invalid_yaml_output' && '渲染结果不是有效YAML'}
                {previewError.error_type === 'request_error' && '请求错误'}
              </div>
              <div className="error-message">{previewError.message}</div>
              {previewError.details?.line && (
                <div className="error-location">
                  <span className="error-line-badge">Line {previewError.details.line}</span>
                  <span>{previewError.details.description}</span>
                </div>
              )}
              {previewError.details?.available_variables && (
                <div className="error-hint">
                  <strong>可用变量:</strong> {previewError.details.available_variables.map((v) => (
                    <code key={v} className="var-tag">{`{{ ${v} }}`}</code>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function BindingRow({ binding, onPreview, onDeploy, onUnbind, onLoadHistory, deployments }) {
  const [expanded, setExpanded] = useState(true)
  const isMatch = binding.expected_config_hash && binding.expected_config_hash === binding.current_config_hash

  useEffect(() => {
    onLoadHistory()
  }, [])

  return (
    <>
      <tr>
        <td>{binding.device_id}</td>
        <td>
          <span className={`hash-badge ${isMatch ? 'hash-match' : 'hash-mismatch'}`}>
            {isMatch ? '配置一致' : '配置不一致'}
          </span>
          <div className="hash-detail">
            <small>预期: {binding.expected_config_hash?.substring(0, 8) || '--'}...</small>
            <small>当前: {binding.current_config_hash?.substring(0, 8) || '--'}...</small>
          </div>
        </td>
        <td className="binding-actions">
          <button className="btn-sm btn-secondary" onClick={onPreview}>预览</button>
          <button className="btn-sm btn-primary" onClick={onDeploy}>下发</button>
          <button className="btn-sm btn-danger" onClick={onUnbind}>解绑</button>
          {deployments.length > 0 && (
            <button className="btn-sm btn-secondary" onClick={() => setExpanded(!expanded)}>
              {expanded ? '收起' : `记录(${deployments.length})`}
            </button>
          )}
        </td>
      </tr>
      {expanded && deployments.length > 0 && (
        <tr className="deployment-history-row">
          <td colSpan="3">
            <div className="deployment-history">
              <div className="deployment-history-title">最近下发任务</div>
              {deployments.slice(0, 5).map((d) => (
                <div key={d.id} className={`deployment-item deploy-${d.status}`}>
                  <span className={`deploy-badge ${d.status}`}>
                    {d.status === 'success' ? '成功' : d.status === 'failed' ? '失败' : '进行中'}
                  </span>
                  <span className="deploy-time">{new Date(d.created_at).toLocaleString('zh-CN')}</span>
                  {d.error_message && <span className="deploy-error">{d.error_message}</span>}
                </div>
              ))}
              {deployments.length > 5 && (
                <div className="deployment-more">...共 {deployments.length} 条记录</div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
