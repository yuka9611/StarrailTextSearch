<script setup>
import { computed } from 'vue'

import StylizedText from '@/components/StylizedText.vue'

const props = defineProps({
  translations: {
    type: Object,
    default: () => ({})
  },
  languageLabels: {
    type: Object,
    default: () => ({})
  },
  keyword: {
    type: String,
    default: ''
  },
  emptyText: {
    type: String,
    default: '暂无文本'
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const entries = computed(() =>
  Object.entries(props.translations || {}).filter(([, text]) => Boolean(text))
)
</script>

<template>
  <div class="translationList" :class="{ compact }">
    <template v-if="entries.length">
      <div
        v-for="[code, text] in entries"
        :key="code"
        class="translationItem"
      >
        <span class="languageLabel">{{ languageLabels[code] || code.toUpperCase() }}</span>
        <StylizedText :text="text" :keyword="keyword" class="translationText" />
      </div>
    </template>
    <p v-else class="emptyText">{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.translationList {
  display: grid;
  gap: 14px;
}

.translationList.compact {
  gap: 10px;
}

.translationItem {
  display: grid;
  gap: 8px;
}

.languageLabel {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(215, 188, 126, 0.92);
}

.translationText {
  color: inherit;
}

.emptyText {
  margin: 0;
  color: rgba(223, 231, 246, 0.56);
}
</style>
