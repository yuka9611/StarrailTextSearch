<template>
  <article class="resultCard">
    <div class="resultCardHeader">
      <div>
        <span class="hashLabel">TextMap Hash</span>
        <code>{{ result.hash }}</code>
      </div>
      <span class="langCount">{{ visibleTranslations.length }} 种语言</span>
    </div>

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
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'

import StylizedText from '@/components/StylizedText.vue'
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

.resultCardHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.langCount {
  font-size: 12px;
  color: rgba(233, 239, 250, 0.62);
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

.translationBlock + .translationBlock {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid rgba(126, 153, 201, 0.16);
}

.translationHeader {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
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
