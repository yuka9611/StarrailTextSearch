<script setup>
import { computed, onMounted, ref } from 'vue'

import { searchText } from '@/api/textSearch'
import ResultCard from '@/components/ResultCard.vue'
import SearchBar from '@/components/SearchBar.vue'
import { appState, ensureMetaLoaded, getSearchPreferences } from '@/stores/appState'

const PAGE_SIZE = 30

const keyword = ref('')
const selectedLanguage = ref('chs')
const loading = ref(false)
const errorMessage = ref('')
const results = ref([])
const total = ref(0)
const currentPage = ref(1)
const hasSearched = ref(false)
const activeResultLanguages = ref([])

const totalPages = computed(() => {
  if (total.value === 0) {
    return 1
  }
  return Math.ceil(total.value / PAGE_SIZE)
})

const languageLabelMap = computed(() =>
  Object.fromEntries(appState.languages.map((item) => [item.code, item.label]))
)

onMounted(async () => {
  try {
    await ensureMetaLoaded()
    const preferences = getSearchPreferences()
    selectedLanguage.value = preferences.defaultLanguage
    activeResultLanguages.value = preferences.resultLanguages
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
    errorMessage.value = '请输入要搜索的关键词。'
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

  try {
    const payload = await searchText({
      keyword: normalizedKeyword,
      lang: selectedLanguage.value,
      page,
      size: PAGE_SIZE,
      resultLangs: preferences.resultLanguages,
      playerName: preferences.playerName,
      playerGender: preferences.playerGender
    })
    results.value = payload.results || []
    total.value = payload.total || 0
    currentPage.value = payload.page || page
    activeResultLanguages.value = payload.resultLangs || preferences.resultLanguages
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

function onPageChange(page) {
  onSearch(page)
}
</script>

<template>
  <section class="pageSection">
    <div class="panel">
      <SearchBar
        v-model:keyword="keyword"
        v-model:language="selectedLanguage"
        :languages="appState.languages"
        @search="onSearch(1)"
      />
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
          <p class="summaryLabel">检索结果</p>
          <h2>{{ total }} 条匹配</h2>
        </div>
        <p class="summaryMeta">
          搜索语言：{{ languageLabelMap[selectedLanguage] || '未选择' }} · 结果语言：{{ activeResultLanguages.length }} 种
        </p>
      </div>

      <div v-if="total > 0" class="paginationWrap paginationWrapTop">
        <el-pagination
          class="paginationControl"
          layout="prev, pager, next, jumper, ->, total"
          :current-page="currentPage"
          :page-size="PAGE_SIZE"
          :total="total"
          :pager-count="7"
          @current-change="onPageChange"
        />
        <p class="pageMeta">
          第 {{ currentPage }} / {{ totalPages }} 页
        </p>
      </div>

      <div v-if="loading" class="resultList">
        <el-skeleton v-for="idx in 4" :key="idx" animated>
          <template #template>
            <div class="skeletonItem">
              <el-skeleton-item variant="text" style="width: 26%" />
              <el-skeleton-item variant="h3" style="width: 92%; margin-top: 16px" />
              <el-skeleton-item variant="text" style="width: 88%; margin-top: 8px" />
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

      <div v-else class="emptyState">
        输入关键词后开始搜索。
      </div>

      <div v-if="total > 0" class="paginationWrap">
        <el-pagination
          class="paginationControl"
          layout="prev, pager, next, jumper, ->, total"
          :current-page="currentPage"
          :page-size="PAGE_SIZE"
          :total="total"
          :pager-count="7"
          @current-change="onPageChange"
        />
        <p class="pageMeta">
          第 {{ currentPage }} / {{ totalPages }} 页
        </p>
      </div>
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
  backdrop-filter: blur(16px);
}

.inlineAlert {
  margin-top: -4px;
}

.resultPanel {
  min-height: 420px;
}

.resultSummary {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
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
  font-size: 30px;
}

.summaryMeta {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
}

.resultList {
  display: grid;
  gap: 14px;
}

.skeletonItem {
  padding: 18px 0;
}

.emptyState {
  display: grid;
  place-items: center;
  min-height: 220px;
  color: rgba(223, 231, 246, 0.52);
}

.paginationWrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.paginationWrapTop {
  margin-bottom: 20px;
}

.paginationWrap:not(.paginationWrapTop) {
  margin-top: 22px;
}

.pageMeta {
  margin: 0;
  color: rgba(223, 231, 246, 0.66);
}

.paginationControl:deep(.btn-prev),
.paginationControl:deep(.btn-next),
.paginationControl:deep(.el-pager li),
.paginationControl:deep(.el-pagination__jump),
.paginationControl:deep(.el-pagination__total) {
  background: transparent;
  color: rgba(232, 239, 252, 0.82);
}

.paginationControl:deep(.btn-prev),
.paginationControl:deep(.btn-next),
.paginationControl:deep(.el-pager li) {
  min-width: 34px;
  height: 34px;
  border: 1px solid rgba(169, 127, 68, 0.24);
  border-radius: 12px;
  background: rgba(8, 16, 30, 0.82);
}

.paginationControl:deep(.el-pager li.is-active) {
  color: #1f1306;
  border-color: transparent;
  background: linear-gradient(135deg, #f0d08e, #bf7f3a);
}

.paginationControl:deep(.btn-prev:disabled),
.paginationControl:deep(.btn-next:disabled) {
  opacity: 0.38;
}

.paginationControl:deep(.el-input__wrapper) {
  background: rgba(8, 16, 30, 0.82);
  box-shadow: 0 0 0 1px rgba(169, 127, 68, 0.24) inset;
}

@media (max-width: 720px) {
  .panel {
    padding: 18px;
    border-radius: 20px;
  }

  .resultSummary {
    flex-direction: column;
    align-items: flex-start;
  }

  .paginationWrap {
    align-items: flex-start;
  }
}
</style>
