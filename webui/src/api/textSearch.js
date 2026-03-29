import { sanitizePayload } from '@/utils/textSanitizer'

async function requestJson(path) {
  const response = await fetch(path, {
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

export function fetchMeta() {
  return requestJson('/api/meta')
}

export function searchText({
  keyword,
  lang,
  page = 1,
  size = 30,
  resultLangs = [],
  playerName = '开拓者',
  playerGender = 'both'
}) {
  const params = new URLSearchParams({
    keyword,
    lang,
    page: String(page),
    size: String(size),
    playerName,
    playerGender
  })

  for (const code of resultLangs) {
    params.append('resultLangs', code)
  }

  return requestJson(`/api/search?${params.toString()}`)
}
