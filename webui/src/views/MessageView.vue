<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { searchMessages } from '@/api/textSearch'
import MessageThreadCard from '@/components/MessageThreadCard.vue'
import SearchPager from '@/components/SearchPager.vue'
import {
  appState,
  ensureMetaLoaded,
  getSearchPreferences,
  getViewState,
  saveViewState
} from '@/stores/appState'

const PAGE_SIZE = 24
const VIEW_KEY = 'message'

const keyword = ref('')
const selectedLanguage = ref('chs')
const selectedCamp = ref('')
const createdVersion = ref('')
const updatedVersion = ref('')
const loading = ref(false)
const errorMessage = ref('')
const threads = ref([])
const total = ref(0)
const currentPage = ref(1)
const hasSearched = ref(false)
const campOptions = ref([])

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasActiveFilters = computed(() =>
  Boolean(keyword.value.trim() || selectedCamp.value || createdVersion.value || updatedVersion.value)
)

watch(
  [keyword, selectedLanguage, selectedCamp, createdVersion, updatedVersion, currentPage, hasSearched],
  () => {
    saveViewState(VIEW_KEY, {
      keyword: keyword.value,
      selectedLanguage: selectedLanguage.value,
      selectedCamp: selectedCamp.value,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      currentPage: currentPage.value,
      hasSearched: hasSearched.value
    })
  },
  { deep: true }
)

onMounted(async () => {
  try {
    await ensureMetaLoaded()
    const preferences = getSearchPreferences()
    const snapshot = getViewState(VIEW_KEY, {})

    selectedLanguage.value = snapshot.selectedLanguage || preferences.defaultLanguage
    keyword.value = snapshot.keyword || ''
    selectedCamp.value = snapshot.selectedCamp || ''
    createdVersion.value = snapshot.createdVersion || ''
    updatedVersion.value = snapshot.updatedVersion || ''
    campOptions.value = appState.messageCamps

    if (snapshot.hasSearched && hasActiveFilters.value) {
      await onSearch(snapshot.currentPage || 1)
    }
  } catch (error) {
    errorMessage.value = appState.metaError || '加载短信索引失败。'
  }
})

function clearResults() {
  loading.value = false
  threads.value = []
  total.value = 0
  currentPage.value = 1
  hasSearched.value = false
}

async function onSearch(page = 1) {
  if (!hasActiveFilters.value) {
    errorMessage.value = ''
    clearResults()
    return
  }

  loading.value = true
  errorMessage.value = ''
  currentPage.value = page
  const preferences = getSearchPreferences(selectedLanguage.value)

  try {
    const payload = await searchMessages({
      keyword: keyword.value.trim(),
      lang: selectedLanguage.value,
      sourceLang: preferences.sourceLanguage,
      camp: selectedCamp.value,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      page,
      size: PAGE_SIZE
    })
    threads.value = payload.results || []
    total.value = payload.total || 0
    currentPage.value = payload.page || page
    campOptions.value = payload.campOptions || appState.messageCamps
    hasSearched.value = true
  } catch (error) {
    threads.value = []
    total.value = 0
    hasSearched.value = true
    errorMessage.value = error instanceof Error ? error.message : '加载短信列表失败。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="pageSection">
    <div class="panel filterPanel stickyPanel">
      <div class="filterGrid">
        <el-input
          v-model="keyword"
          placeholder="输入联系人名称、短信内容或主线关联"
          clearable
          @keyup.enter="onSearch(1)"
        />

        <el-select v-model="selectedCamp" placeholder="阵营筛选" clearable>
          <el-option
            v-for="camp in campOptions"
            :key="camp.id"
            :label="camp.label"
            :value="camp.id"
          />
        </el-select>

        <el-select v-model="createdVersion" placeholder="创建版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`message-created-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="updatedVersion" placeholder="更新版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`message-updated-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-button type="primary" class="searchButton" @click="onSearch(1)">
          搜索联系人
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      class="inlineAlert"
      type="error"
      :closable="false"
      :title="errorMessage"
    />

    <div class="panel wallPanel">
      <div class="summaryRow">
        <div>
          <p class="summaryLabel">短信搜索</p>
          <h2>{{ hasSearched ? `${total} 个联系人` : '等待筛选' }}</h2>
        </div>
        <p class="summaryMeta">
          结果会按联系人聚合展示，并在详情页整合全部短信段落。
        </p>
      </div>

      <SearchPager
        v-if="total > 0"
        class="paginationWrap"
        :current-page="currentPage"
        :total-pages="totalPages"
        :total="total"
        :disabled="loading"
        @change="onSearch"
      />

      <div v-if="loading" class="cardGrid">
        <el-skeleton v-for="idx in 6" :key="idx" animated>
          <template #template>
            <div class="threadSkeleton">
              <el-skeleton-item variant="circle" style="width: 56px; height: 56px" />
              <el-skeleton-item variant="h3" style="width: 64%; margin-top: 16px" />
              <el-skeleton-item variant="text" style="width: 92%; margin-top: 10px" />
            </div>
          </template>
        </el-skeleton>
      </div>

      <el-empty
        v-else-if="hasSearched && threads.length === 0"
        description="当前筛选条件下没有短信联系人"
      />

      <div v-else-if="threads.length > 0" class="cardGrid">
        <MessageThreadCard
          v-for="thread in threads"
          :key="thread.threadId"
          :thread="thread"
          :keyword="keyword"
        />
      </div>

      <el-empty v-else description="等待筛选" />

      <SearchPager
        v-if="total > 0"
        class="paginationWrap"
        :current-page="currentPage"
        :total-pages="totalPages"
        :total="total"
        :disabled="loading"
        @change="onSearch"
      />
    </div>
  </section>
</template>

<style scoped>
.pageSection {
  display: grid;
  gap: 18px;
}

.panel {
  padding: 22px;
  border-radius: 24px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
}

.stickyPanel {
  position: sticky;
  top: calc(0px - var(--content-pane-pad-top, 0px));
  z-index: 3;
  backdrop-filter: blur(16px);
}

.filterPanel,
.wallPanel {
  border: 1px solid rgba(126, 153, 201, 0.18);
  background: rgba(9, 18, 34, 0.78);
}

.filterGrid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) repeat(3, minmax(0, 180px)) auto;
  gap: 12px;
}

.searchButton {
  min-width: 132px;
}

.summaryRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.summaryLabel {
  margin: 0 0 8px;
  color: rgba(211, 221, 240, 0.58);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
}

.summaryMeta,
.emptyState {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
}

.cardGrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 18px;
  margin-top: 20px;
}

.threadSkeleton {
  padding: 20px;
  border-radius: 24px;
  background: rgba(10, 20, 37, 0.72);
}

.paginationWrap {
  margin-top: 20px;
}

@media (max-width: 1180px) {
  .filterGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .filterGrid {
    display: flex;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .filterGrid > * {
    flex: 0 0 min(72vw, 240px);
  }

  .searchButton {
    flex-basis: 132px;
  }
}
</style>
