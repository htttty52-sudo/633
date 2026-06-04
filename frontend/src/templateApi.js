import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export async function fetchTemplates(params = {}) {
  const resp = await api.get('/templates/', { params })
  return resp.data
}

export async function fetchTemplate(templateId) {
  const resp = await api.get(`/templates/${templateId}`)
  return resp.data
}

export async function createTemplate(data) {
  const resp = await api.post('/templates/', data)
  return resp.data
}

export async function updateTemplate(templateId, data) {
  const resp = await api.put(`/templates/${templateId}`, data)
  return resp.data
}

export async function deleteTemplate(templateId) {
  await api.delete(`/templates/${templateId}`)
}

export async function renderPreview(templateId, deviceId) {
  const resp = await api.post('/templates/render-preview', {
    template_id: templateId,
    device_id: deviceId,
  })
  return resp.data
}

export async function validateTemplate(content) {
  const resp = await api.post('/templates/validate', { content })
  return resp.data
}

export async function createBinding(templateId, deviceId) {
  const resp = await api.post('/bindings/', {
    template_id: templateId,
    device_id: deviceId,
  })
  return resp.data
}

export async function fetchBindings(params = {}) {
  const resp = await api.get('/bindings/', { params })
  return resp.data
}

export async function deleteBinding(bindingId) {
  await api.delete(`/bindings/${bindingId}`)
}

export async function compareBinding(bindingId) {
  const resp = await api.get(`/bindings/${bindingId}/compare`)
  return resp.data
}

export async function createDeployment(bindingId) {
  const resp = await api.post('/deployments/', { binding_id: bindingId })
  return resp.data
}

export async function fetchDeployments(params = {}) {
  const resp = await api.get('/deployments/', { params })
  return resp.data
}
