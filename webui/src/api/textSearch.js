import { sanitizePayload } from '@/utils/textSanitizer'

function buildUrl(path, params = {}) {
  const query = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item === undefined || item === null || item === '') {
          return
        }
        query.append(key, String(item))
      })
      return
    }

    query.set(key, String(value))
  })

  const queryString = query.toString()
  return queryString ? `${path}?${queryString}` : path
}

async function requestJson(path, params = {}) {
  const response = await fetch(buildUrl(path, params), {
    headers: {
      Accept: 'application/json'
    }
  })

  let payload = null
  try {
    payload = await response.json()
  } catch (error) {
    payload = null
  }

  if (!response.ok) {
    const message = payload?.error || `请求失败（${response.status}）`
    throw new Error(message)
  }

  return sanitizePayload(payload)
}

export function fetchMeta(params = {}) {
  return requestJson('/api/meta', params)
}

export function fetchVersions() {
  return requestJson('/api/version')
}

export function searchText(params) {
  return requestJson('/api/search', params)
}

export function fetchTextSources(params) {
  return requestJson('/api/text/sources', params)
}

export function searchMissions(params) {
  return requestJson('/api/mission/search', params)
}

export function fetchMissionDetail(params) {
  return requestJson('/api/mission/detail', params)
}

export function searchBooks(params) {
  return requestJson('/api/book/search', params)
}

export function fetchBookDetail(params) {
  return requestJson('/api/book/detail', params)
}

export function searchMessages(params) {
  return requestJson('/api/message/search', params)
}

export function fetchMessageDetail(params) {
  return requestJson('/api/message/detail', params)
}

export function searchAvatars(params) {
  return requestJson('/api/avatar/search', params)
}

export function searchVoices(params) {
  return requestJson('/api/voice/search', params)
}

export function fetchVoiceEntriesByAvatar(params) {
  return requestJson('/api/voice/by-avatar', params)
}

export function fetchVoiceDetail(params) {
  return requestJson('/api/voice/detail', params)
}

export function searchStories(params) {
  return requestJson('/api/story/search', params)
}

export function fetchStoryEntriesByAvatar(params) {
  return requestJson('/api/story/by-avatar', params)
}

export function fetchStoryDetail(params) {
  return requestJson('/api/story/detail', params)
}
