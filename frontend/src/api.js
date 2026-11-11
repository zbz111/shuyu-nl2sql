import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1', timeout: 120000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (!location.hash.startsWith('#/login')) location.hash = '#/login'
    }
    return Promise.reject(error)
  }
)

export function errorMessage(error) {
  return error?.response?.data?.detail || error?.message || '请求失败'
}

/** SSE 流式问答：返回一个 async generator，逐事件产出 {event, data} */
export async function streamChat(payload, signal) {
  const resp = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(payload),
    signal
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `HTTP ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  return {
    async *[Symbol.asyncIterator]() {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const eventLine = raw.split('\n').find((l) => l.startsWith('event:'))
          const dataLine = raw.split('\n').find((l) => l.startsWith('data:'))
          if (!dataLine) continue
          const event = eventLine ? eventLine.slice(6).trim() : 'message'
          const data = dataLine.slice(5).trim()
          try {
            yield { event, data: JSON.parse(data) }
          } catch {
            yield { event, data }
          }
        }
      }
    }
  }
}

export default api
