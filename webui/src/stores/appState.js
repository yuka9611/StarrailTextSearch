import { reactive } from 'vue'

import { fetchMeta, fetchVersions } from '@/api/textSearch'

const SEARCH_SETTINGS_STORAGE_KEY = 'starrail-text-search.settings'
const VIEW_STATE_STORAGE_KEY = 'starrail-text-search.view-state'
const DEFAULT_PLAYER_NAME = '开拓者'
const DEFAULT_PLAYER_GENDER = 'both'
const VALID_PLAYER_GENDERS = new Set(['male', 'female', 'both'])

let pendingMetaRequest = null

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
  versions: [],
  messageCamps: [],
  availablePages: [],
  defaultLanguage: 'chs',
  defaultSourceLanguage: 'chs',
  currentVersion: '',
  currentVersionRaw: '',
  dataAvailable: false,
  databaseAvailable: false,
  dataDir: '',
  dbPath: ''
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

function readStoredViewStates() {
  if (typeof window === 'undefined') {
    return {}
  }

  const rawValue = window.sessionStorage.getItem(VIEW_STATE_STORAGE_KEY)
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

function writeStoredViewStates(states) {
  if (typeof window === 'undefined') {
    return
  }

  window.sessionStorage.setItem(VIEW_STATE_STORAGE_KEY, JSON.stringify(states))
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
  if (appState.metaLoaded && !force) {
    return
  }
  if (pendingMetaRequest && !force) {
    await pendingMetaRequest
    return
  }

  appState.metaLoading = true
  appState.metaError = ''

  const request = (async () => {
    const [metaPayload, versionPayload] = await Promise.all([
      fetchMeta(),
      fetchVersions()
    ])

    appState.languages = metaPayload.languages || []
    appState.versions = versionPayload.versions || []
    appState.messageCamps = metaPayload.messageCamps || []
    appState.availablePages = metaPayload.availablePages || []
    appState.defaultLanguage = metaPayload.defaultLanguage || 'chs'
    appState.defaultSourceLanguage = metaPayload.defaultSourceLanguage || appState.defaultLanguage
    appState.currentVersion = versionPayload.currentVersion || metaPayload.currentVersion || ''
    appState.currentVersionRaw = versionPayload.currentVersionRaw || metaPayload.currentVersionRaw || ''
    appState.dataAvailable = Boolean(metaPayload.dataAvailable)
    appState.databaseAvailable = Boolean(metaPayload.databaseAvailable)
    appState.dataDir = metaPayload.dataDir || ''
    appState.dbPath = metaPayload.dbPath || ''
    appState.metaLoaded = true
  })()

  pendingMetaRequest = request

  try {
    await request
  } catch (error) {
    appState.metaLoaded = false
    appState.metaError = error instanceof Error ? error.message : '加载应用元数据失败。'
    throw error
  } finally {
    if (pendingMetaRequest === request) {
      pendingMetaRequest = null
    }
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

export function getDefaultSourceLanguage() {
  const stored = readStoredSettings().sourceLanguage
  if (isLanguageSupported(stored)) {
    return stored
  }

  if (isLanguageSupported(appState.defaultSourceLanguage)) {
    return appState.defaultSourceLanguage
  }

  return getDefaultSearchLanguage()
}

export function getSearchPreferences(searchLanguage = '') {
  const stored = readStoredSettings()
  const defaultLanguage = isLanguageSupported(stored.defaultLanguage)
    ? stored.defaultLanguage
    : getDefaultSearchLanguage()
  const sourceLanguage = isLanguageSupported(stored.sourceLanguage)
    ? stored.sourceLanguage
    : getDefaultSourceLanguage()
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
    sourceLanguage,
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
  const sourceLanguage = isLanguageSupported(preferences.sourceLanguage)
    ? preferences.sourceLanguage
    : getDefaultSourceLanguage()
  const resultLanguages = normalizeLanguageList(
    preferences.resultLanguages || [],
    [defaultLanguage]
  )
  const snapshot = {
    defaultLanguage,
    sourceLanguage,
    resultLanguages,
    playerName: String(preferences.playerName || '').trim() || DEFAULT_PLAYER_NAME,
    playerGender: VALID_PLAYER_GENDERS.has(preferences.playerGender)
      ? preferences.playerGender
      : DEFAULT_PLAYER_GENDER
  }

  window.localStorage.setItem(SEARCH_SETTINGS_STORAGE_KEY, JSON.stringify(snapshot))
  return snapshot
}

export function getViewState(viewKey, fallback = {}) {
  const key = String(viewKey || '').trim()
  if (!key) {
    return { ...fallback }
  }

  const states = readStoredViewStates()
  const snapshot = states[key]
  if (!snapshot || typeof snapshot !== 'object') {
    return { ...fallback }
  }
  return {
    ...fallback,
    ...snapshot
  }
}

export function saveViewState(viewKey, state) {
  const key = String(viewKey || '').trim()
  if (!key || typeof window === 'undefined') {
    return
  }

  const states = readStoredViewStates()
  states[key] = {
    ...(states[key] && typeof states[key] === 'object' ? states[key] : {}),
    ...(state && typeof state === 'object' ? state : {})
  }
  writeStoredViewStates(states)
}
