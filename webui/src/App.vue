<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { RouterView } from 'vue-router'

let disposeBrowserSessionMonitor = () => {}

const BROWSER_SESSION_HEARTBEAT_MS = 20000
const BROWSER_SESSION_STORAGE_KEY = 'sts-browser-session-id'

function getBrowserSessionId() {
  try {
    const existingId = window.sessionStorage.getItem(BROWSER_SESSION_STORAGE_KEY)
    if (existingId) {
      return existingId
    }

    const nextId = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`

    window.sessionStorage.setItem(BROWSER_SESSION_STORAGE_KEY, nextId)
    return nextId
  } catch (e) {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`
  }
}

function createBrowserSessionMonitor() {
  if (typeof window === 'undefined') {
    return () => {}
  }

  const clientId = getBrowserSessionId()
  let timerId = 0
  let closed = false

  const postJson = async (url, keepalive = false) => {
    try {
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientId }),
        keepalive
      })
    } catch (e) {
      // The server may already be stopping; silence network noise.
    }
  }

  const sendHeartbeat = () => {
    void postJson('/api/browser-session/heartbeat')
  }

  const sendDisconnect = () => {
    if (closed) {
      return
    }
    closed = true

    const payload = JSON.stringify({ clientId })
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' })
        if (navigator.sendBeacon('/api/browser-session/disconnect', blob)) {
          return
        }
      }
    } catch (e) {
      // Fall through to keepalive fetch.
    }

    void postJson('/api/browser-session/disconnect', true)
  }

  const handlePageHide = (event) => {
    if (event.persisted) {
      return
    }
    sendDisconnect()
  }

  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible' && !closed) {
      sendHeartbeat()
    }
  }

  sendHeartbeat()
  timerId = window.setInterval(sendHeartbeat, BROWSER_SESSION_HEARTBEAT_MS)
  window.addEventListener('pagehide', handlePageHide)
  window.addEventListener('beforeunload', sendDisconnect)
  document.addEventListener('visibilitychange', handleVisibilityChange)

  return () => {
    window.clearInterval(timerId)
    window.removeEventListener('pagehide', handlePageHide)
    window.removeEventListener('beforeunload', sendDisconnect)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
}

onMounted(() => {
  disposeBrowserSessionMonitor = createBrowserSessionMonitor()
})

onBeforeUnmount(() => {
  disposeBrowserSessionMonitor()
})
</script>

<template>
  <RouterView />
</template>
