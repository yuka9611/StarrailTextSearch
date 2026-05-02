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
  speakerKeyword: {
    type: String,
    default: ''
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
  <article class="talkCard">
    <div class="cardHeader">
      <div>
        <span class="eyebrowLabel">Dialogue</span>
        <h3>{{ item.title }}</h3>
      </div>
      <VersionBadges
        class="versionStack"
        :created-version="item.createdVersion"
        :updated-version="item.updatedVersion"
      />
    </div>

    <div class="metaRow">
      <span class="metaTag">说话人</span>
      <StylizedText :text="item.speaker || '旁白'" :keyword="speakerKeyword" class="speakerText" />
      <span v-if="item.voiceId" class="metaTag">Voice ID {{ item.voiceId }}</span>
    </div>

    <StylizedText :text="item.preview || '暂无对白预览'" :keyword="keyword" class="previewText" />

    <div class="actionRow">
      <el-button type="primary" @click="openDetail">
        查看详情
      </el-button>
    </div>
  </article>
</template>

<style scoped>
.talkCard {
  padding: 18px 20px;
  border-radius: 20px;
  border: 1px solid rgba(113, 139, 191, 0.2);
  background: rgba(10, 20, 37, 0.86);
  display: grid;
  gap: 14px;
}

.cardHeader,
.metaRow,
.actionRow {
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

h3 {
  margin: 0;
  font-size: 22px;
}

.versionStack {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.metaRow {
  align-items: center;
  justify-content: flex-start;
}

.metaTag {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(122, 183, 255, 0.12);
  color: rgba(233, 239, 250, 0.8);
}

.speakerText {
  color: rgba(242, 247, 255, 0.92);
}

.speakerText:deep(p) {
  margin: 0;
}

.previewText {
  color: rgba(242, 247, 255, 0.88);
}

.actionRow {
  justify-content: flex-end;
}
</style>
