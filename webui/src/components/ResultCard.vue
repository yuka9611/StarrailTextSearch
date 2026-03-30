<template>
  <article class="resultCard">
    <div class="resultCardHeader">
      <div>
        <span class="hashLabel">TextMap Hash</span>
        <code>{{ result.hash }}</code>
      </div>
      <div class="headerMeta">
        <span class="langCount">{{ visibleTranslations.length }} 种语言</span>
        <span v-if="showSourcePanel && hasMultipleSources" class="sourceCount">{{ result.sourceCount }} 个来源</span>
      </div>
    </div>

    <div v-if="showSourcePanel" class="sourcePanel">
      <div class="sourceText">
        <span class="sourceType">{{ sourceLabel }}</span>
        <StylizedText :text="primarySource.title || '未归类文本'" class="sourceTitle" />
        <StylizedText v-if="primarySource.subtitle" :text="primarySource.subtitle" class="sourceSubtitle" />
      </div>
      <div class="sourceActions">
        <el-button
          v-if="primarySource.detailQuery"
          size="small"
          @click="openDetail(primarySource.detailQuery)"
        >
          来源详情
        </el-button>
        <el-button v-if="hasMultipleSources" size="small" plain @click="openTextDetail">
          全部来源
        </el-button>
      </div>
    </div>

    <VersionBadges
      class="versionRow"
      :created-version="result.createdVersion"
      :updated-version="result.updatedVersion"
    />

    <div
      v-for="item in visibleTranslations"
      :key="`${result.hash}-${item.code}`"
      class="translationBlock"
    >
      <div class="translationHeader">
        <span class="languageLabel">{{ item.label }}</span>
        <el-button
          class="copyButton"
          :icon="CopyDocument"
          circle
          size="small"
          :title="'复制'"
          @click="copyTranslation(item.text)"
        />
      </div>

      <StylizedText :text="item.text" :keyword="keyword" class="contentText" />
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'

import StylizedText from '@/components/StylizedText.vue'
import VersionBadges from '@/components/VersionBadges.vue'
import { buildDetailLocation } from '@/utils/detailRoute'
import { toCopyableText } from '@/utils/textContent'

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  keyword: {
    type: String,
    default: ''
  },
  displayLanguages: {
    type: Array,
    default: () => []
  },
  languageLabels: {
    type: Object,
    default: () => ({})
  }
})

const router = useRouter()
const knownSourceTypes = new Set(['mission', 'message', 'book', 'voice', 'story'])

const visibleTranslations = computed(() => {
  const translates = props.result.translates || {}
  const ordered = []
  const seen = new Set()

  for (const code of props.displayLanguages) {
    const text = translates[code]
    if (!text || seen.has(code)) {
      continue
    }
    seen.add(code)
    ordered.push({
      code,
      label: props.languageLabels[code] || code.toUpperCase(),
      text
    })
  }

  for (const [code, text] of Object.entries(translates)) {
    if (!text || seen.has(code)) {
      continue
    }
    ordered.push({
      code,
      label: props.languageLabels[code] || code.toUpperCase(),
      text
    })
  }

  return ordered
})

const primarySource = computed(() => props.result.primarySource || {})
const showSourcePanel = computed(() => {
  const sourceType = primarySource.value.sourceType || ''
  const title = primarySource.value.title || ''

  if (!sourceType && !title) {
    return false
  }

  if (sourceType === 'unknown') {
    return false
  }

  return knownSourceTypes.has(sourceType) || !title.startsWith('未归类文本')
})

const hasMultipleSources = computed(() => Number(props.result.sourceCount || 0) > 1)

const sourceLabel = computed(() => {
  const mapping = {
    mission: '任务',
    message: '短信',
    book: '书籍',
    voice: '角色语音',
    story: '角色故事',
    unknown: '未归类'
  }
  return mapping[primarySource.value.sourceType] || '文本来源'
})

function openDetail(detailQuery) {
  router.push(buildDetailLocation(detailQuery))
}

function openTextDetail() {
  router.push(
    buildDetailLocation({
      kind: 'text',
      hash: props.result.hash
    })
  )
}

async function copyTranslation(text) {
  const copyableText = toCopyableText(text)
  if (!copyableText) {
    ElMessage.warning('没有可复制的文本')
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(copyableText)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = copyableText
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.resultCard {
  padding: 18px 20px;
  border: 1px solid rgba(113, 139, 191, 0.2);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(15, 27, 48, 0.92), rgba(10, 20, 37, 0.92));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.resultCardHeader,
.translationHeader,
.sourcePanel,
.versionRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.resultCardHeader {
  margin-bottom: 14px;
}

.headerMeta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.langCount,
.sourceCount {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: rgba(233, 239, 250, 0.72);
  background: rgba(122, 183, 255, 0.12);
}

.hashLabel {
  display: block;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(240, 245, 255, 0.62);
}

code {
  color: #9eceff;
  font-size: 13px;
}

.sourcePanel {
  align-items: flex-start;
  padding: 16px;
  border-radius: 18px;
  background: rgba(11, 21, 39, 0.7);
  border: 1px solid rgba(122, 183, 255, 0.14);
}

.sourceText {
  min-width: 0;
}

.sourceType {
  display: inline-flex;
  margin-bottom: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(240, 208, 142, 0.12);
  color: #f5d398;
  font-size: 12px;
}

.sourceTitle {
  color: inherit;
  font-size: 20px;
  font-weight: 700;
}

.sourceTitle:deep(p),
.sourceSubtitle:deep(p) {
  margin: 0;
}

.sourceSubtitle {
  color: rgba(223, 231, 246, 0.68);
  margin-top: 8px;
}

.sourceActions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.versionRow {
  margin-top: 12px;
  justify-content: flex-start;
}

.translationBlock + .translationBlock {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid rgba(126, 153, 201, 0.16);
}

.translationBlock:first-of-type {
  margin-top: 18px;
}

.languageLabel {
  font-size: 14px;
  font-weight: 600;
  color: #d9e6ff;
}

.copyButton {
  transition: all 0.3s ease;
}

.copyButton:hover {
  transform: scale(1.1);
}

.contentText {
  margin: 0;
  color: #f3f6ff;
  line-height: 1.8;
}
</style>
