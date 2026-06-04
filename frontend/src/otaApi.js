import axios from 'axios'

const api = axios.create({
  baseURL: '/api/ota',
  timeout: 10000,
})

export function fetchFirmwares(params = {}) {
  return api.get('/firmwares/', { params })
}

export function createFirmware(data) {
  return api.post('/firmwares/', data)
}

export function deleteFirmware(firmwareId) {
  return api.delete(`/firmwares/${firmwareId}`)
}

export function fetchOtaTasks(params = {}) {
  return api.get('/tasks/', { params })
}

export function getOtaTask(taskId) {
  return api.get(`/tasks/${taskId}`)
}

export function createOtaTask(data) {
  return api.post('/tasks/', data)
}

export function confirmBatch(taskId) {
  return api.post(`/tasks/${taskId}/confirm`)
}

export function abortOtaTask(taskId) {
  return api.post(`/tasks/${taskId}/abort`)
}

export function fetchOtaDeviceTasks(taskId, params = {}) {
  return api.get(`/tasks/${taskId}/devices`, { params })
}
