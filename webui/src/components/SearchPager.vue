<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentPage: {
    type: Number,
    default: 1
  },
  totalPages: {
    type: Number,
    default: 1
  },
  total: {
    type: Number,
    default: 0
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['change'])

const safeCurrentPage = computed(() => Math.max(1, Number(props.currentPage) || 1))
const safeTotalPages = computed(() => Math.max(1, Number(props.totalPages) || 1))
const canGoPrev = computed(() => !props.disabled && safeCurrentPage.value > 1)
const canGoNext = computed(() => !props.disabled && safeCurrentPage.value < safeTotalPages.value)

function goTo(page) {
  const nextPage = Math.min(Math.max(1, Number(page) || 1), safeTotalPages.value)
  if (props.disabled || nextPage === safeCurrentPage.value) {
    return
  }
  emit('change', nextPage)
}
</script>

<template>
  <div class="pagerShell">
    <div class="pagerActions">
      <el-button :disabled="!canGoPrev" @click="goTo(1)">
        首页
      </el-button>
      <el-button :disabled="!canGoPrev" @click="goTo(safeCurrentPage - 1)">
        上一页
      </el-button>
      <el-button :disabled="!canGoNext" @click="goTo(safeCurrentPage + 1)">
        下一页
      </el-button>
      <el-button :disabled="!canGoNext" @click="goTo(safeTotalPages)">
        末页
      </el-button>
    </div>

    <p class="pagerMeta">
      第 {{ safeCurrentPage }} / {{ safeTotalPages }} 页 · 共 {{ total }} 条
    </p>
  </div>
</template>

<style scoped>
.pagerShell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.pagerActions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.pagerMeta {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
  font-size: 13px;
}
</style>
