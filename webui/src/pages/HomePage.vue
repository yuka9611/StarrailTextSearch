<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { appState, ensureMetaLoaded } from '@/stores/appState'

const route = useRoute()

const activePath = computed(() => route.path)
const pageTitle = computed(() => route.meta.title || '星铁文本搜索')

onMounted(async () => {
  try {
    await ensureMetaLoaded()
  } catch (error) {
    // 页面上会直接展示错误提示，这里不额外处理。
  }
})
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

      <el-menu
        class="navMenu"
        :default-active="activePath"
        :router="true"
      >
        <el-menu-item index="/">
          关键词搜索
        </el-menu-item>
        <el-menu-item index="/settings">
          设置
        </el-menu-item>
      </el-menu>
    </aside>

    <main class="contentPane">
      <header class="contentHeader">
        <div>
          <p class="eyebrow">Astral Archive</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div
          class="statusBadge"
          :class="appState.dataAvailable ? 'statusOk' : 'statusWarn'"
        >
          {{ appState.dataAvailable ? '数据目录已连接' : '数据目录不可用' }}
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

      <router-view />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
}

.sidebar {
  position: relative;
  padding: 26px 20px;
  border-right: 1px solid rgba(212, 180, 109, 0.15);
  background:
    linear-gradient(180deg, rgba(8, 15, 30, 0.92), rgba(7, 13, 24, 0.96)),
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
  padding: 10px 8px 26px;
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
  padding: 32px;
}

.contentHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
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
  color: #dff6de;
  background: rgba(92, 173, 116, 0.16);
  border: 1px solid rgba(92, 173, 116, 0.28);
}

.statusWarn {
  color: #ffe7b1;
  background: rgba(212, 180, 109, 0.14);
  border: 1px solid rgba(212, 180, 109, 0.24);
}

.pageAlert {
  margin-bottom: 20px;
}

@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: none;
    border-bottom: 1px solid rgba(212, 180, 109, 0.15);
  }

  .contentPane {
    padding: 24px 18px 32px;
  }

  .contentHeader {
    flex-direction: column;
  }
}
</style>
