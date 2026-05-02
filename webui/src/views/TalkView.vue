<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { searchTalks } from '@/api/textSearch'
import SearchPager from '@/components/SearchPager.vue'
import TalkResultCard from '@/components/TalkResultCard.vue'
import {
  appState,
  ensureMetaLoaded,
  getSearchPreferences,
  getViewState,
  saveViewState
} from '@/stores/appState'

const PAGE_SIZE = 30
const VIEW_KEY = 'talk'

const selectedLanguage = ref('chs')
const speakerKeyword = ref('')
const keyword = ref('')
const createdVersion = ref('')
const updatedVersion = ref('')
const loading = ref(false)
const errorMessage = ref('')
const results = ref([])
const total = ref(0)
const currentPage = ref(1)
const hasSearched = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasActiveFilters = computed(() =>
  Boolean(
    speakerKeyword.value.trim()
      || keyword.value.trim()
      || createdVersion.value
      || updatedVersion.value
  )
)

watch(
  [selectedLanguage, speakerKeyword, keyword, createdVersion, updatedVersion, currentPage, hasSearched],
  () => {
    saveViewState(VIEW_KEY, {
      selectedLanguage: selectedLanguage.value,
      speakerKeyword: speakerKeyword.value,
      keyword: keyword.value,
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
    speakerKeyword.value = snapshot.speakerKeyword || ''
    keyword.value = snapshot.keyword || ''
    createdVersion.value = snapshot.createdVersion || ''
    updatedVersion.value = snapshot.updatedVersion || ''

    if (snapshot.hasSearched && hasActiveFilters.value) {
      await onSearch(snapshot.currentPage || 1)
    }
  } catch (error) {
    errorMessage.value = appState.metaError || '加载对话搜索页面失败。'
  }
})

function clearResults() {
  loading.value = false
  results.value = []
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
    const payload = await searchTalks({
      speakerKeyword: speakerKeyword.value.trim(),
      keyword: keyword.value.trim(),
      lang: selectedLanguage.value,
      sourceLang: preferences.sourceLanguage,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      page,
      size: PAGE_SIZE
    })
    results.value = payload.results || []
    total.value = payload.total || 0
    currentPage.value = payload.page || page
    hasSearched.value = true
  } catch (error) {
    results.value = []
    total.value = 0
    hasSearched.value = true
    errorMessage.value = error instanceof Error ? error.message : '对白检索失败，请稍后重试。'
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
          v-model="speakerKeyword"
          placeholder="输入说话人名称"
          clearable
          @keyup.enter="onSearch(1)"
        />

        <el-input
          v-model="keyword"
          placeholder="输入对白片段或 TalkSentenceID"
          clearable
          @keyup.enter="onSearch(1)"
        />

        <el-select v-model="createdVersion" placeholder="创建版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`talk-created-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="updatedVersion" placeholder="更新版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`talk-updated-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-button type="primary" class="searchButton" @click="onSearch(1)">
          搜索对白
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

    <div class="panel">
      <div class="summaryRow">
        <div>
          <p class="summaryLabel">对话搜索</p>
          <h2>{{ hasSearched ? `${total} 条结果` : '等待筛选' }}</h2>
        </div>
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
        <el-skeleton v-for="idx in 4" :key="idx" animated :rows="4" />
      </div>

      <el-empty
        v-else-if="hasSearched && results.length === 0"
        description="当前筛选条件下没有找到对白"
      />

      <div v-else-if="results.length > 0" class="resultList">
        <TalkResultCard
          v-for="item in results"
          :key="item.talkSentenceId"
          :item="item"
          :keyword="keyword"
          :speaker-keyword="speakerKeyword"
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
  grid-template-columns:
    minmax(0, 160px)
    minmax(0, 220px)
    minmax(0, 1fr)
    repeat(2, minmax(0, 160px))
    auto;
  gap: 12px;
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

.resultList {
  display: grid;
  gap: 14px;
  margin-top: 20px;
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
    flex-direction: column;
  }

  .searchButton {
    width: 100%;
  }
}
</style>
