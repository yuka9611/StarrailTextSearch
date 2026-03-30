<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { appState, ensureMetaLoaded, getViewState, saveViewState } from '@/stores/appState'

const route = useRoute()
const contentPane = ref(null)
const isCompactScreen = ref(false)

const keepAliveViews = new Set(['search', 'mission-book', 'message', 'voice', 'story', 'settings'])

const activePath = computed(() => {
  if (route.path !== '/detail') {
    return route.path
  }

  const kind = String(route.query.kind || '').toLowerCase()
  if (kind === 'mission' || kind === 'book') {
    return '/mission-book'
  }
  if (kind === 'message') {
    return '/message'
  }
  if (kind === 'voice') {
    return '/voice'
  }
  if (kind === 'story') {
    return '/story'
  }
  return '/'
})

const pageTitle = computed(() => route.meta.title || '星铁文本搜索')
const versionLabel = computed(() => appState.currentVersion || '当前版本未识别')
const menuMode = computed(() => (isCompactScreen.value ? 'horizontal' : 'vertical'))

function updateScreenMode() {
  if (typeof window === 'undefined') {
    return
  }
  isCompactScreen.value = window.innerWidth <= 860
}

function saveScrollPosition(routeKey) {
  if (!contentPane.value || !routeKey) {
    return
  }
  saveViewState(`scroll:${routeKey}`, {
    scrollTop: contentPane.value.scrollTop
  })
}

async function restoreScrollPosition(routeKey) {
  await nextTick()
  if (!contentPane.value) {
    return
  }
  const snapshot = getViewState(`scroll:${routeKey}`, {
    scrollTop: 0
  })
  contentPane.value.scrollTo({
    left: 0,
    top: Number(snapshot.scrollTop || 0),
    behavior: 'auto'
  })
}

onMounted(async () => {
  updateScreenMode()
  window.addEventListener('resize', updateScreenMode)
  try {
    await ensureMetaLoaded()
  } catch (error) {
    // 页面本身会展示错误提示，这里不额外处理。
  }
  await restoreScrollPosition(route.fullPath)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateScreenMode)
})

watch(
  () => route.fullPath,
  async (to, from) => {
    if (from) {
      saveScrollPosition(from)
    }
    await restoreScrollPosition(to)
  }
)
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brandPanel">
        <img class="brandIcon" src="/favicon.svg" alt="星铁文本搜索图标" />
        <div>
          <div class="brandTitle">星铁文本搜索</div>
          <div class="brandSubtitle">Star Rail Text Search</div>
        </div>
      </div>

      <div class="versionPanel">
        <span class="versionLabel">数据版本</span>
        <strong>{{ versionLabel }}</strong>
      </div>

      <el-menu
        class="navMenu"
        :default-active="activePath"
        :router="true"
        :mode="menuMode"
      >
        <el-menu-item index="/">
          关键词搜索
        </el-menu-item>
        <el-menu-item index="/mission-book">
          任务 / 书籍搜索
        </el-menu-item>
        <el-menu-item index="/message">
          短信搜索
        </el-menu-item>
        <el-menu-item index="/voice">
          角色语音搜索
        </el-menu-item>
        <el-menu-item index="/story">
          角色故事搜索
        </el-menu-item>
        <el-menu-item index="/settings">
          设置
        </el-menu-item>
      </el-menu>
    </aside>

    <main ref="contentPane" class="contentPane">
      <header class="contentHeader">
        <div>
          <p class="eyebrow">Astral Archive</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="statusGroup">
          <div
            class="statusBadge"
            :class="appState.dataAvailable ? 'statusOk' : 'statusWarn'"
          >
            {{ appState.dataAvailable ? '数据目录已连接' : '数据目录不可用' }}
          </div>
          <div
            class="statusBadge"
            :class="appState.databaseAvailable ? 'statusOk' : 'statusWarn'"
          >
            {{ appState.databaseAvailable ? '数据库已就绪' : '数据库待初始化' }}
          </div>
        </div>
      </header>

      <el-alert
        v-if="appState.metaError"
        class="pageAlert"
        type="error"
        :closable="false"
        :title="appState.metaError"
      />

      <el-alert
        v-else-if="appState.metaLoaded && !appState.dataAvailable"
        class="pageAlert"
        type="warning"
        :closable="false"
        :title="`未找到数据目录：${appState.dataDir}`"
      />

      <router-view v-slot="{ Component, route: currentRoute }">
        <keep-alive>
          <component
            :is="Component"
            v-if="currentRoute.meta.keepAlive && keepAliveViews.has(String(currentRoute.name || ''))"
            :key="currentRoute.name"
          />
        </keep-alive>
        <component
          :is="Component"
          v-if="!currentRoute.meta.keepAlive || !keepAliveViews.has(String(currentRoute.name || ''))"
          :key="currentRoute.fullPath"
        />
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 292px minmax(0, 1fr);
}

.sidebar {
  position: relative;
  padding: 26px 20px;
  border-right: 1px solid rgba(212, 180, 109, 0.15);
  background:
    linear-gradient(180deg, rgba(8, 15, 30, 0.94), rgba(7, 13, 24, 0.98)),
    radial-gradient(circle at top, rgba(122, 183, 255, 0.14), transparent 42%);
}

.sidebar::after {
  content: '';
  position: absolute;
  inset: 14px;
  border: 1px solid rgba(212, 180, 109, 0.08);
  border-radius: 24px;
  pointer-events: none;
}

.brandPanel {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 8px 22px;
}

.brandIcon {
  width: 56px;
  height: 56px;
  flex: none;
}

.brandTitle {
  font-size: 20px;
  font-weight: 700;
  color: #f6f8ff;
}

.brandSubtitle {
  margin-top: 4px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(201, 214, 236, 0.65);
}

.versionPanel {
  margin: 0 8px 18px;
  padding: 14px 16px;
  border: 1px solid rgba(122, 183, 255, 0.18);
  border-radius: 18px;
  background: rgba(12, 22, 41, 0.7);
  display: grid;
  gap: 8px;
}

.versionLabel {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(201, 214, 236, 0.58);
}

.versionPanel strong {
  color: #f6d69d;
  line-height: 1.4;
}

.navMenu {
  border-right: none;
  background: transparent;
}

.navMenu :deep(.el-menu-item) {
  margin-bottom: 8px;
  border-radius: 16px;
  color: rgba(232, 238, 252, 0.8);
}

.navMenu :deep(.el-menu-item.is-active) {
  color: #0b1425;
  background: linear-gradient(135deg, #f1d390, #7ab7ff);
}

.contentPane {
  --content-pane-pad-top: 32px;
  padding: var(--content-pane-pad-top) 32px 32px;
  overflow-y: auto;
  max-height: 100vh;
}

.contentHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}

.statusGroup {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.eyebrow {
  margin: 0 0 10px;
  color: #d7bc7e;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1 {
  margin: 0 0 8px;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.1;
}

.statusBadge {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 13px;
  white-space: nowrap;
}

.statusOk {
  background: rgba(124, 197, 142, 0.16);
  color: #9be3ad;
}

.statusWarn {
  background: rgba(229, 188, 115, 0.16);
  color: #f3ce8d;
}

.pageAlert {
  margin-bottom: 18px;
}

@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .sidebar {
    padding: 18px 16px 10px;
    border-right: none;
    border-bottom: 1px solid rgba(212, 180, 109, 0.15);
  }

  .sidebar::after {
    inset: 10px;
  }

  .brandPanel {
    padding: 6px 4px 14px;
  }

  .versionPanel {
    margin: 0 4px 12px;
  }

  .navMenu {
    overflow-x: auto;
  }

  .navMenu :deep(.el-menu--horizontal) {
    display: flex;
    gap: 8px;
    border-bottom: none;
  }

  .navMenu :deep(.el-menu-item) {
    margin-bottom: 0;
    min-width: max-content;
  }

  .contentPane {
    --content-pane-pad-top: 22px;
    padding: var(--content-pane-pad-top) 16px 28px;
  }

  .contentHeader {
    flex-direction: column;
  }
}
</style>
