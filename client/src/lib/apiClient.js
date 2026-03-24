const API_BASE_URL =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function buildUrl(path, query = {}) {
  const url = new URL(path, API_BASE_URL)

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }

    url.searchParams.set(key, value)
  })

  return url.toString()
}

async function parseResponse(response) {
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await response.json() : null

  if (!response.ok) {
    const message = data?.message || data?.detail || 'Request failed.'
    const error = new Error(message)
    error.status = response.status
    error.data = data
    throw error
  }

  return data
}

async function request(path, options = {}, query = undefined) {
  const response = await fetch(buildUrl(path, query), {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  return parseResponse(response)
}

async function requestForm(path, formData, query = undefined) {
  const response = await fetch(buildUrl(path, query), {
    method: 'POST',
    body: formData,
  })
  return parseResponse(response)
}

export function getDashboardOverview() {
  return request('/admin/dashboard/overview', { method: 'GET' })
}

export function getRoutes(query = {}) {
  return request('/admin/routes', { method: 'GET' }, query)
}

export function getTrips(query = {}) {
  return request('/admin/trips', { method: 'GET' }, query)
}

export function getReservations(query = {}) {
  return request('/admin/reservations', { method: 'GET' }, query)
}

export function getIncidents(query = {}) {
  return request('/admin/incidents', { method: 'GET' }, query)
}

export function createIncident(payload) {
  return request('/admin/incidents', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function runAdminQuery(payload) {
  return request('/admin/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getSimulationStatus() {
  return request('/admin/simulation/status', { method: 'GET' })
}

export function startSimulation() {
  return request('/admin/simulation/start', {
    method: 'POST',
    body: JSON.stringify({ action: 'start' }),
  })
}

export function stopSimulation() {
  return request('/admin/simulation/stop', {
    method: 'POST',
    body: JSON.stringify({ action: 'stop' }),
  })
}

export function runSimulationTick() {
  return request('/admin/simulation/tick', { method: 'POST', body: JSON.stringify({}) })
}

export function seedData(payload) {
  return request('/admin/data/seed', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function uploadCsv({ dataset, file }) {
  const formData = new FormData()
  formData.append('file', file)
  return requestForm('/admin/uploads/csv', formData, { dataset })
}

export function updateSimulationConfig(payload) {
  return request('/admin/simulation/config', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export { API_BASE_URL }
