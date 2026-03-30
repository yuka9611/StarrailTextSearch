<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  fetchStoryEntriesByAvatar,
  fetchVoiceEntriesByAvatar,
  searchAvatars
} from '@/api/textSearch'
import DetailTranslations from '@/components/DetailTranslations.vue'
import StylizedText from '@/components/StylizedText.vue'
import VersionBadges from '@/components/VersionBadges.vue'
import {
  appState,
  ensureMetaLoaded,
  getSearchPreferences,
  getViewState,
  saveViewState
} from '@/stores/appState'
import { buildDetailLocation } from '@/utils/detailRoute'

const props = defineProps({
  kind: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  eyebrow: {
    type: String,
    default: 'Atlas'
  },
  avatarPlaceholder: {
    type: String,
    default: '输入角色名'
  },
  searchPlaceholder: {
    type: String,
    default: '输入标题或正文片段'
  },
  emptyText: {
    type: String,
    default: '没有找到匹配结果'
  },
  viewActionLabel: {
    type: String,
    default: '查看条目'
  },
  viewKey: {
    type: String,
    default: 'avatar-atlas'
  }
})

const router = useRouter()

const avatarKeyword = ref('')
const keyword = ref('')
const selectedLanguage = ref('chs')
const createdVersion = ref('')
const updatedVersion = ref('')
const loadingAvatars = ref(false)
const loadingEntries = ref(false)
const errorMessage = ref('')
const avatarResults = ref([])
const selectedAvatar = ref(null)
const entryResults = ref([])
const hasSearched = ref(false)
const activeResultLanguages = ref([])
const activeSourceLanguage = ref('chs')

const selectedAvatarLabel = computed(() => selectedAvatar.value?.name || '')
const hasActiveFilters = computed(() =>
  Boolean(avatarKeyword.value.trim() || keyword.value.trim() || createdVersion.value || updatedVersion.value)
)
const languageLabelMap = computed(() =>
  Object.fromEntries(appState.languages.map((item) => [item.code, item.label]))
)

const entryFetcher = computed(() => (
  props.kind === 'voice' ? fetchVoiceEntriesByAvatar : fetchStoryEntriesByAvatar
))

onMounted(async () => {
  try {
    await ensureMetaLoaded()
    const preferences = getSearchPreferences()
    selectedLanguage.value = preferences.defaultLanguage
    activeResultLanguages.value = preferences.resultLanguages
    activeSourceLanguage.value = preferences.sourceLanguage

    const snapshot = getViewState(props.viewKey, {})
    avatarKeyword.value = snapshot.avatarKeyword || ''
    keyword.value = snapshot.keyword || ''
    createdVersion.value = snapshot.createdVersion || ''
    updatedVersion.value = snapshot.updatedVersion || ''
    selectedLanguage.value = snapshot.selectedLanguage || preferences.defaultLanguage

    if (snapshot.hasSearched && (
      avatarKeyword.value.trim() || keyword.value.trim() || createdVersion.value || updatedVersion.value
    )) {
      await onSearch(snapshot.selectedAvatarId || null)
    }
  } catch (error) {
    errorMessage.value = appState.metaError || '加载角色索引失败。'
  }
})

watch(
  [avatarKeyword, keyword, selectedLanguage, createdVersion, updatedVersion, selectedAvatar, hasSearched],
  () => {
    saveViewState(props.viewKey, {
      avatarKeyword: avatarKeyword.value,
      keyword: keyword.value,
      selectedLanguage: selectedLanguage.value,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      selectedAvatarId: selectedAvatar.value?.avatarId || null,
      hasSearched: hasSearched.value
    })
  },
  { deep: true }
)

async function onSearch(restoredAvatarId = null) {
  errorMessage.value = ''
  entryResults.value = []
  selectedAvatar.value = null

  if (!hasActiveFilters.value) {
    hasSearched.value = false
    avatarResults.value = []
    return
  }

  loadingAvatars.value = true
  const preferences = getSearchPreferences(selectedLanguage.value)
  activeResultLanguages.value = preferences.resultLanguages
  activeSourceLanguage.value = preferences.sourceLanguage

  try {
    const payload = await searchAvatars({
      kind: props.kind,
      avatarKeyword: avatarKeyword.value.trim(),
      keyword: keyword.value.trim(),
      lang: selectedLanguage.value,
      sourceLang: preferences.sourceLanguage,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      playerGender: preferences.playerGender
    })
    avatarResults.value = payload.results || []
    hasSearched.value = true

    if (restoredAvatarId) {
      const matchedAvatar = avatarResults.value.find((item) => Number(item.avatarId) === Number(restoredAvatarId))
      if (matchedAvatar) {
        await openAvatar(matchedAvatar)
      }
    }
  } catch (error) {
    avatarResults.value = []
    hasSearched.value = true
    errorMessage.value = error instanceof Error ? error.message : '加载角色卡片失败。'
  } finally {
    loadingAvatars.value = false
  }
}

async function openAvatar(avatar) {
  loadingEntries.value = true
  errorMessage.value = ''
  selectedAvatar.value = avatar
  const preferences = getSearchPreferences(selectedLanguage.value)
  activeResultLanguages.value = preferences.resultLanguages
  activeSourceLanguage.value = preferences.sourceLanguage

  try {
    const payload = await entryFetcher.value({
      avatarId: avatar.avatarId,
      keyword: keyword.value.trim(),
      sourceLang: preferences.sourceLanguage,
      resultLangs: preferences.resultLanguages,
      createdVersion: createdVersion.value,
      updatedVersion: updatedVersion.value,
      playerName: preferences.playerName,
      playerGender: preferences.playerGender
    })
    entryResults.value = payload.results || []
  } catch (error) {
    entryResults.value = []
    errorMessage.value = error instanceof Error ? error.message : '加载角色条目失败。'
  } finally {
    loadingEntries.value = false
  }
}

function openStoryDetail(entry) {
  if (props.kind !== 'story') {
    return
  }
  router.push(buildDetailLocation(entry.detailQuery))
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
          v-model="avatarKeyword"
          :placeholder="avatarPlaceholder"
          clearable
          @keyup.enter="onSearch()"
        />

        <el-input
          v-model="keyword"
          :placeholder="searchPlaceholder"
          clearable
          @keyup.enter="onSearch()"
        />

        <el-select v-model="createdVersion" placeholder="创建版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`${props.kind}-created-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-select v-model="updatedVersion" placeholder="更新版本" clearable>
          <el-option
            v-for="item in appState.versions"
            :key="`${props.kind}-updated-${item}`"
            :label="item"
            :value="item"
          />
        </el-select>

        <el-button type="primary" class="searchButton" @click="onSearch()">
          搜索角色
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
          <p class="summaryLabel">{{ eyebrow }}</p>
          <h2>{{ hasSearched ? `${avatarResults.length} 个角色` : '等待检索' }}</h2>
        </div>
        <p class="summaryMeta">
          输入角色名可先筛角色，也可以直接用标题或版本筛出角色卡片。
        </p>
      </div>

      <div v-if="loadingAvatars" class="cardGrid">
        <el-skeleton v-for="idx in 4" :key="idx" animated :rows="3" />
      </div>

      <el-empty
        v-else-if="hasSearched && avatarResults.length === 0"
        :description="emptyText"
      />

      <div v-else-if="avatarResults.length > 0" class="cardGrid">
        <article
          v-for="avatar in avatarResults"
          :key="avatar.avatarId"
          class="avatarCard"
          :class="{ active: selectedAvatar?.avatarId === avatar.avatarId }"
        >
          <div>
            <StylizedText :text="avatar.name" class="cardTitle" />
            <p class="cardMeta">角色 ID：{{ avatar.avatarId }}</p>
            <p class="cardMeta">{{ avatar.entryCount }} 条匹配</p>
          </div>
          <el-button type="primary" size="small" @click="openAvatar(avatar)">
            {{ viewActionLabel }}
          </el-button>
        </article>
      </div>

      <el-empty v-else description="等待检索" />
    </div>

    <div class="panel">
      <div class="summaryRow">
        <div>
          <p class="summaryLabel">{{ props.title }}</p>
          <h2>{{ selectedAvatarLabel ? `${selectedAvatarLabel} · ${entryResults.length} 条` : '未选择角色' }}</h2>
        </div>
        <p class="summaryMeta">
          来源语言：{{ activeSourceLanguage.toUpperCase() }} · 结果语言：{{ activeResultLanguages.length }} 种
        </p>
      </div>

      <div v-if="loadingEntries" class="entryList">
        <el-skeleton v-for="idx in 4" :key="`entry-${idx}`" animated :rows="5" />
      </div>

      <el-empty
        v-else-if="selectedAvatar && entryResults.length === 0"
        description="当前筛选条件下没有条目"
      />

      <div v-else-if="entryResults.length > 0" class="entryList">
        <article
          v-for="entry in entryResults"
          :key="`${props.kind}-${entry.entryKey}`"
          class="entryCard"
        >
          <div class="entryHeader">
            <div>
              <StylizedText :text="entry.title" class="entryTitle" />
            </div>
            <VersionBadges
              :created-version="entry.createdVersion"
              :updated-version="entry.updatedVersion"
            />
          </div>

          <div v-if="props.kind === 'voice' && entry.voicePath" class="voicePath">
            {{ entry.voicePath }}
          </div>

          <DetailTranslations
            :translations="entry.translates"
            :language-labels="languageLabelMap"
            :keyword="keyword"
          />

          <div v-if="props.kind === 'story'" class="entryActions">
            <el-button size="small" @click="openStoryDetail(entry)">
              打开详情
            </el-button>
          </div>
        </article>
      </div>

      <el-empty
        v-else
        :description="selectedAvatar ? emptyText : '未选择角色'"
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
  grid-template-columns: minmax(0, 160px) repeat(2, minmax(0, 1fr)) repeat(2, minmax(0, 160px)) auto;
  gap: 12px;
}

.searchButton {
  min-width: 120px;
}

.summaryRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
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
.cardMeta,
.entryMeta,
.voicePath {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
}

.cardGrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.avatarCard,
.entryCard {
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(122, 183, 255, 0.14);
  background: rgba(10, 20, 37, 0.72);
  display: grid;
  gap: 12px;
}

.avatarCard.active {
  border-color: rgba(240, 208, 142, 0.5);
  box-shadow: inset 0 0 0 1px rgba(240, 208, 142, 0.2);
}

.cardTitle,
.entryTitle {
  color: inherit;
  font-size: 20px;
  font-weight: 700;
}

.cardTitle:deep(p),
.entryTitle:deep(p) {
  margin: 0;
}

.entryList {
  display: grid;
  gap: 14px;
}

.entryHeader {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.voicePath {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
  word-break: break-all;
}

.entryActions {
  display: flex;
  justify-content: flex-end;
}

.emptyState {
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
