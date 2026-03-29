<template>
  <div class="searchBar">
    <el-select
      v-model="localLanguage"
      class="languageSelect"
      placeholder="搜索语言"
    >
      <el-option
        v-for="item in languages"
        :key="item.code"
        :label="item.label"
        :value="item.code"
      />
    </el-select>

    <el-input
      v-model="localKeyword"
      class="keywordInput"
      placeholder="输入要检索的关键词"
      clearable
      @keyup.enter="emitSearch"
    />

    <el-button type="primary" class="searchButton" @click="emitSearch">
      搜索
    </el-button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  keyword: {
    type: String,
    default: ''
  },
  language: {
    type: String,
    default: 'chs'
  },
  languages: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:keyword', 'update:language', 'search'])

const localKeyword = ref(props.keyword)
const localLanguage = ref(props.language)

watch(
  () => props.keyword,
  (value) => {
    localKeyword.value = value
  }
)

watch(
  () => props.language,
  (value) => {
    localLanguage.value = value
  }
)

watch(localKeyword, (value) => {
  emit('update:keyword', value)
})

watch(localLanguage, (value) => {
  emit('update:language', value)
})

function emitSearch() {
  emit('search')
}
</script>

<style scoped>
.searchBar {
  display: grid;
  grid-template-columns: minmax(150px, 180px) minmax(0, 1fr) auto;
  gap: 12px;
}

.languageSelect,
.keywordInput {
  width: 100%;
}

.searchButton {
  min-width: 120px;
  border: 0;
  color: #1f1306;
  background: linear-gradient(135deg, #f0d08e, #bf7f3a);
  box-shadow: 0 10px 24px rgba(168, 112, 45, 0.26);
}

.searchButton:hover,
.searchButton:focus-visible {
  color: #1f1306;
  background: linear-gradient(135deg, #f4daa1, #c78944);
  box-shadow: 0 14px 28px rgba(168, 112, 45, 0.34);
}

.searchButton:deep(span) {
  font-weight: 600;
}

@media (max-width: 720px) {
  .searchBar {
    grid-template-columns: 1fr;
  }

  .searchButton {
    width: 100%;
  }
}
</style>
