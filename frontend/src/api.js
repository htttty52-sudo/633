import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export async function fetchDevices(params = {}) {
  const response = await api.get('/devices/', { params })
  return response.data
}

export async function fetchDevice(deviceId) {
  const response = await api.get(`/devices/${deviceId}`)
  return response.data
}

export async function createDevice(data) {
  const response = await api.post('/devices/', data)
  return response.data
}

export async function updateDevice(deviceId, data) {
  const response = await api.put(`/devices/${deviceId}`, data)
  return response.data
}

export async function deleteDevice(deviceId) {
  await api.delete(`/devices/${deviceId}`)
}

export async function sendHeartbeat(deviceId) {
  const response = await api.post(`/devices/${deviceId}/heartbeat`)
  return response.data
}
