<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import StylizedText from '@/components/StylizedText.vue'
import VersionBadges from '@/components/VersionBadges.vue'
import { buildDetailLocation } from '@/utils/detailRoute'
import { toCopyableText } from '@/utils/textContent'

const props = defineProps({
  thread: {
    type: Object,
    required: true
  },
  keyword: {
    type: String,
    default: ''
  }
})

const router = useRouter()

const avatarText = computed(() => {
  const name = toCopyableText(props.thread.displayName || '')
  if (!name) {
    return '短信'
  }
  return name.length <= 2 ? name : name.slice(0, 2)
})

const threadTypeLabel = computed(() => {
  const mapping = {
    group: '群聊',
    system: '系统',
    contact: '单聊'
  }
  return mapping[props.thread.threadType] || '短信'
})

function openDetail() {
  router.push(
    buildDetailLocation({
      kind: 'message',
      threadId: props.thread.threadId
    })
  )
}
</script>

<template>
  <article class="threadCard" @click="openDetail">
    <div class="threadTop">
      <div class="avatarChip">
        {{ avatarText }}
      </div>
      <div class="threadMeta">
        <div class="titleRow">
          <StylizedText :text="thread.displayName" class="titleText" />
          <span class="typeBadge">{{ threadTypeLabel }}</span>
        </div>
        <div class="badgeRow">
          <span v-if="thread.camp" class="campBadge">{{ thread.camp.label }}</span>
          <span class="countBadge">{{ thread.messageCount }} 条</span>
        </div>
      </div>
    </div>

    <StylizedText
      :text="thread.latestPreview || '暂无短信预览'"
      :keyword="keyword"
      class="previewText"
    />

    <VersionBadges
      class="versionRow"
      :created-version="thread.createdVersion"
      :updated-version="thread.updatedVersion"
    />
  </article>
</template>

<style scoped>
.threadCard {
  height: 100%;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(126, 153, 201, 0.18);
  background:
    linear-gradient(180deg, rgba(13, 24, 43, 0.96), rgba(9, 18, 34, 0.96)),
    radial-gradient(circle at top right, rgba(122, 183, 255, 0.14), transparent 45%);
  color: #edf3ff;
  cursor: pointer;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.threadCard:hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 36px rgba(7, 18, 33, 0.28);
}

.threadTop {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.avatarChip {
  width: 56px;
  height: 56px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  flex: none;
  color: #183156;
  font-weight: 700;
  background: linear-gradient(135deg, #f7e8c1, #d9e8fb);
  border: 1px solid rgba(94, 126, 180, 0.16);
}

.threadMeta {
  min-width: 0;
  flex: 1;
}

.titleRow,
.badgeRow,
.versionRow {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.titleRow h3 {
  margin: 0;
  font-size: 20px;
}

.titleText {
  color: inherit;
  font-size: 20px;
  font-weight: 700;
}

.titleText:deep(p) {
  margin: 0;
}

.typeBadge,
.campBadge,
.countBadge,
.versionTag {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.typeBadge {
  background: rgba(122, 183, 255, 0.16);
  color: #a5d2ff;
}

.campBadge {
  background: rgba(229, 188, 115, 0.2);
  color: #f1cf95;
}

.countBadge {
  background: rgba(24, 49, 86, 0.08);
  color: rgba(233, 239, 250, 0.75);
}

.previewText {
  margin-top: 16px;
  color: rgba(233, 239, 250, 0.84);
  min-height: 82px;
}

.versionRow {
  margin-top: 16px;
}
</style>
