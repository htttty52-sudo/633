import axios from 'axios'

const API_BASE = '/api/dashboard'

export async function fetchHeatmap(nocache = false) {
  const params = nocache ? { nocache: true } : {}
  const res = await axios.get(`${API_BASE}/heatmap`, { params })
  return res.data
}

export async function fetchDrift({ skip = 0, limit = 50, driftedOnly = false, nocache = false } = {}) {
  const params = { skip, limit, drifted_only: driftedOnly }
  if (nocache) params.nocache = true
  const res = await axios.get(`${API_BASE}/drift`, { params })
  return res.data
}

export async function fetchWorkers() {
  const res = await axios.get(`${API_BASE}/workers`)
  return res.data
}

export async function fetchStreamStats() {
  const res = await axios.get(`${API_BASE}/stream-stats`)
  return res.data
}
