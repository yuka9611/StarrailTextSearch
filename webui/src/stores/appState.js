import { reactive } from 'vue'

import { fetchMeta } from '@/api/textSearch'

const SEARCH_SETTINGS_STORAGE_KEY = 'starrail-text-search.settings'
const DEFAULT_PLAYER_NAME = '开拓者'
const DEFAULT_PLAYER_GENDER = 'both'
const VALID_PLAYER_GENDERS = new Set(['male', 'female', 'both'])

export const playerGenderOptions = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
  { value: 'both', label: '双写法' }
]

export const appState = reactive({
  metaLoaded: false,
  metaLoading: false,
  metaError: '',
  languages: [],
  defaultLanguage: 'chs',
  dataAvailable: false,
  dataDir: ''
})

function readStoredSettings() {
  if (typeof window === 'undefined') {
    return {}
  }

  const rawValue = window.localStorage.getItem(SEARCH_SETTINGS_STORAGE_KEY)
  if (!rawValue) {
    return {}
  }

  try {
    const parsed = JSON.parse(rawValue)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch (error) {
    return {}
  }
}

function isLanguageSupported(code) {
  return appState.languages.some((item) => item.code === code)
}

function normalizeLanguageList(codes, fallback = []) {
  const normalized = []
  const seen = new Set()

  for (const code of [...codes, ...fallback]) {
    const text = String(code || '').trim().toLowerCase()
    if (!text || !isLanguageSupported(text) || seen.has(text)) {
      continue
    }
    seen.add(text)
    normalized.push(text)
  }

  return normalized
}

export async function ensureMetaLoaded(force = false) {
  if (appState.metaLoading) {
    return
  }
  if (appState.metaLoaded && !force) {
    return
  }

  appState.metaLoading = true
  appState.metaError = ''

  try {
    const payload = await fetchMeta()
    appState.languages = payload.languages || []
    appState.defaultLanguage = payload.defaultLanguage || 'chs'
    appState.dataAvailable = Boolean(payload.dataAvailable)
    appState.dataDir = payload.dataDir || ''
    appState.metaLoaded = true
  } catch (error) {
    appState.metaLoaded = false
    appState.metaError = error instanceof Error ? error.message : '加载应用元数据失败。'
    throw error
  } finally {
    appState.metaLoading = false
  }
}

export function getDefaultSearchLanguage() {
  const stored = readStoredSettings().defaultLanguage
  if (isLanguageSupported(stored)) {
    return stored
  }

  if (isLanguageSupported(appState.defaultLanguage)) {
    return appState.defaultLanguage
  }

  return appState.languages[0]?.code || 'chs'
}

export function getSearchPreferences(searchLanguage = '') {
  const stored = readStoredSettings()
  const defaultLanguage = isLanguageSupported(stored.defaultLanguage)
    ? stored.defaultLanguage
    : getDefaultSearchLanguage()
  const normalizedSearchLanguage = isLanguageSupported(searchLanguage) ? searchLanguage : ''
  const resultLanguages = normalizeLanguageList(stored.resultLanguages || [], [defaultLanguage])

  const orderedResultLanguages = normalizeLanguageList(
    normalizedSearchLanguage ? [normalizedSearchLanguage, ...resultLanguages] : resultLanguages,
    [defaultLanguage]
  )

  const playerName = String(stored.playerName || '').trim() || DEFAULT_PLAYER_NAME
  const playerGender = VALID_PLAYER_GENDERS.has(stored.playerGender)
    ? stored.playerGender
    : DEFAULT_PLAYER_GENDER

  return {
    defaultLanguage,
    resultLanguages: orderedResultLanguages,
    playerName,
    playerGender
  }
}

export function saveSearchPreferences(preferences) {
  if (typeof window === 'undefined') {
    return getSearchPreferences()
  }

  const defaultLanguage = isLanguageSupported(preferences.defaultLanguage)
    ? preferences.defaultLanguage
    : getDefaultSearchLanguage()
  const resultLanguages = normalizeLanguageList(
    preferences.resultLanguages || [],
    [defaultLanguage]
  )
  const snapshot = {
    defaultLanguage,
    resultLanguages,
    playerName: String(preferences.playerName || '').trim() || DEFAULT_PLAYER_NAME,
    playerGender: VALID_PLAYER_GENDERS.has(preferences.playerGender)
      ? preferences.playerGender
      : DEFAULT_PLAYER_GENDER
  }

  window.localStorage.setItem(SEARCH_SETTINGS_STORAGE_KEY, JSON.stringify(snapshot))
  return snapshot
}
