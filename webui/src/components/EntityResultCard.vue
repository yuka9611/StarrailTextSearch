<script setup>
import { useRouter } from 'vue-router'

import StylizedText from '@/components/StylizedText.vue'
import VersionBadges from '@/components/VersionBadges.vue'
import { buildDetailLocation } from '@/utils/detailRoute'

const props = defineProps({
  item: {
    type: Object,
    required: true
  },
  keyword: {
    type: String,
    default: ''
  },
  eyebrow: {
    type: String,
    default: '条目'
  }
})

const router = useRouter()

function openDetail() {
  if (!props.item.detailQuery) {
    return
  }
  router.push(buildDetailLocation(props.item.detailQuery))
}
</script>

<template>
  <article class="entityCard">
    <div class="entityHeader">
      <div class="entityMain">
        <span class="eyebrowLabel">{{ eyebrow }}</span>
        <StylizedText :text="item.title" class="titleText" />
      </div>
      <VersionBadges
        class="versionStack"
        :created-version="item.createdVersion"
        :updated-version="item.updatedVersion"
      />
    </div>

    <p v-if="item.entityKey" class="entityKey">
      ID / Key: {{ item.entityKey }}
    </p>

    <StylizedText :text="item.preview || '暂无摘要'" :keyword="keyword" class="previewText" />

    <div class="actionRow">
      <el-button type="primary" @click="openDetail">
        查看详情
      </el-button>
    </div>
  </article>
</template>

<style scoped>
.entityCard {
  padding: 18px 20px;
  border-radius: 20px;
  border: 1px solid rgba(113, 139, 191, 0.2);
  background: rgba(10, 20, 37, 0.86);
}

.entityHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.eyebrowLabel {
  display: inline-flex;
  margin-bottom: 10px;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #d7bc7e;
}

.titleText {
  color: inherit;
  font-size: 22px;
  font-weight: 700;
}

.titleText:deep(p) {
  margin: 0;
}

.versionStack {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.entityKey {
  margin: 12px 0 0;
  color: rgba(158, 206, 255, 0.75);
  font-size: 13px;
}

.previewText {
  margin-top: 16px;
  color: rgba(242, 247, 255, 0.88);
}

.actionRow {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}
</style>
