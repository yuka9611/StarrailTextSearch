<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { searchText } from '@/api/textSearch'
import ResultCard from '@/components/ResultCard.vue'
import SearchPager from '@/components/SearchPager.vue'
import {
  appState,
  ensureMetaLoaded,
  getSearchPreferences,
  getViewState,
  saveViewState
} from '@/stores/appState'

const PAGE_SIZE = 30
const VIEW_KEY = 'search'

const sourceTypeOptions = [
  { value: 'mission', label: '任务' },
  { value: 'message', label: '短信' },
  { value: 'book', label: '书籍' },
  { value: 'voice', label: '角色语音' },
  { value: 'story', label: '角色故事' }
]

const keyword = ref('')
const selectedLanguage = ref('chs')
const selectedSourceTypes = ref([])
const createdVersion = ref('')
const updatedVersion = ref('')
const loading = ref(false)
const errorMessage = ref('')
const results = ref([])
const total = ref(0)
const currentPage = ref(1)
const hasSearched = ref(false)
const activeResultLanguages = ref([])
const activeSourceLanguage = ref('chs')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const languageLabelMap = computed(() =>
  Object.fromEntries(appState.languages.map((item) => [item.code, item.label]))
)

watch(
  [keyword, selectedLanguage, selectedSourceTypes, createdVersion, updatedVersion, currentPage, hasSearched],
  () => {
    saveViewState(VIEW_KEY, {
      keyword: keyword.value,
      selectedLanguage: selectedLanguage.value,
      selectedSourceTypes: [...selectedSourceTypes.value],
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
    activeResultLanguages.value = preferences.resultLanguages
    activeSourceLanguage.value = preferences.sourceLanguage
    keyword.value = snapshot.keyword || ''
    selectedSourceTypes.value = (snapshot.selectedSourceTypes || []).filter((item) =>
      sourceTypeOptions.some((option) => option.value === item)
    )
    createdVersion.value = snapshot.createdVersion || ''
    updatedVersion.value = snapshot.updatedVersion || ''

    if (snapshot.hasSearched && keyword.value.trim()) {
      await onSearch(snapshot.currentPage || 1)
    }
  } catch (error) {
    errorMessage.value = appState.metaError || '加载语言列表失败。'
  }
})

async function onSearch(page = 1) {
  const normalizedKeyword = keyword.value.trim()
  errorMessage.value = ''

  if (!normalizedKeyword) {
    hasSearched.value = false
    results.value = []
    total.value = 0
    currentPage.value = 1
    return
  }

  if (!appState.dataAvailable) {
    errorMessage.value = `未找到数据目录：${appState.dataDir}`
    return
  }

  loading.value = true
  currentPage.value = page
  const preferences = getSearchPreferences(selectedLanguage.value)
  activeResultLanguages.value = preferences.resultLanguages
  activeSourceLanguage.value = preferences.sourceLanguage

  try {
    const payload = await searchText({
      keyword: normalizedKeyword,
      lang: selectedLanguage.value,
      page,
      size: PAGE_SIZE,
      resultLangs: preferences.resultLanguages,
      sourceLang: preferences.sourceLanguage,
      playerName: preferences.playerName,
      playerGender: preferences.playerGender,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      sourceTypes: selectedSourceTypes.value
    })
    results.value = payload.results || []
    total.value = payload.total || 0
    currentPage.value = payload.page || page
    activeResultLanguages.value = payload.resultLangs || preferences.resultLanguages
    activeSourceLanguage.value = payload.sourceLang || preferences.sourceLanguage
    hasSearched.value = true
  } catch (error) {
    results.value = []
    total.value = 0
    hasSearched.value = true
    errorMessage.value = error instanceof Error ? error.message : '搜索失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="pageSection">
    <div class="panel stickyPanel">
      <div class="filterGrid">
        <el-select v-model="selectedLanguage" placeholder="搜索语言">
          <el-option
            v-for="item in appState.languages"
            :key="item.code"
            :label="item.label"
            :value="item.code"
          />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="输入要检索的关键词"
          clearable
          @keyup.enter="onSearch(1)"
        />

        <el-select
          v-model="selectedSourceTypes"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="限制来源类型"
          clearable
        >
          <el-option
            v-for="item in sourceTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>

        <el-select v-model="createdVersion" placeholder="创建版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`created-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="updatedVersion" placeholder="更新版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`updated-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-button type="primary" class="searchButton" @click="onSearch(1)">
          搜索
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

    <div class="panel resultPanel">
      <div class="resultSummary">
        <div>
          <p class="summaryLabel">关键词搜索</p>
          <h2>{{ hasSearched ? `${total} 条匹配` : '等待搜索' }}</h2>
        </div>
        <p class="summaryMeta">
          搜索语言：{{ languageLabelMap[selectedLanguage] || '未选择' }} · 结果语言：{{ activeResultLanguages.length }} 种
          · 来源语言：{{ languageLabelMap[activeSourceLanguage] || activeSourceLanguage.toUpperCase() }}
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

      <div v-if="loading" class="resultList">
        <el-skeleton v-for="idx in 4" :key="idx" animated>
          <template #template>
            <div class="skeletonItem">
              <el-skeleton-item variant="text" style="width: 28%" />
              <el-skeleton-item variant="h3" style="width: 68%; margin-top: 18px" />
              <el-skeleton-item variant="text" style="width: 94%; margin-top: 10px" />
            </div>
          </template>
        </el-skeleton>
      </div>

      <el-empty
        v-else-if="hasSearched && results.length === 0"
        description="未找到匹配的文本"
      />

      <div v-else-if="results.length > 0" class="resultList">
        <ResultCard
          v-for="item in results"
          :key="item.hash"
          :result="item"
          :keyword="keyword"
          :display-languages="activeResultLanguages"
          :language-labels="languageLabelMap"
        />
      </div>

      <el-empty v-else description="等待搜索" />

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
  border: 1px solid rgba(126, 153, 201, 0.18);
  border-radius: 24px;
  background: rgba(9, 18, 34, 0.78);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
}

.stickyPanel {
  position: sticky;
  top: calc(0px - var(--content-pane-pad-top, 0px));
  z-index: 3;
  backdrop-filter: blur(16px);
}

.filterGrid {
  display: grid;
  grid-template-columns: minmax(0, 160px) minmax(0, 1.4fr) minmax(0, 1.1fr) repeat(2, minmax(0, 160px)) auto;
  gap: 12px;
}

.searchButton {
  min-width: 120px;
}

.resultSummary {
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

.summaryMeta {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
}

.paginationWrap {
  margin-top: 20px;
}

.resultList {
  display: grid;
  gap: 14px;
  margin-top: 20px;
}

.skeletonItem {
  padding: 18px 20px;
  border-radius: 20px;
  border: 1px solid rgba(113, 139, 191, 0.2);
  background: rgba(10, 20, 37, 0.72);
}

.emptyState {
  margin-top: 20px;
  color: rgba(223, 231, 246, 0.72);
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
    flex-basis: 120px;
  }
}
</style>
