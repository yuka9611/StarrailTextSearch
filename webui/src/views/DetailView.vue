<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  fetchBookDetail,
  fetchMessageDetail,
  fetchMissionDetail,
  fetchStoryDetail,
  fetchTextSources,
  fetchVoiceDetail
} from '@/api/textSearch'
import DetailTranslations from '@/components/DetailTranslations.vue'
import VersionBadges from '@/components/VersionBadges.vue'
import { appState, ensureMetaLoaded, getSearchPreferences } from '@/stores/appState'
import { buildDetailLocation } from '@/utils/detailRoute'
import { toCopyableText } from '@/utils/textContent'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const detail = ref(null)
const activeSectionId = ref(null)
const selectedOptionKeys = ref({})

const languageLabelMap = computed(() =>
  Object.fromEntries(appState.languages.map((item) => [item.code, item.label]))
)

const detailKind = computed(() => String(route.query.kind || '').toLowerCase())

const detailTitle = computed(() => {
  const payload = detail.value
  if (!payload) {
    return '详情'
  }
  if (payload.kind === 'mission') {
    return toCopyableText(payload.title || '') || '任务详情'
  }
  if (payload.kind === 'book') {
    return toCopyableText(payload.title || '') || '书籍详情'
  }
  if (payload.kind === 'message') {
    return toCopyableText(payload.displayName || '') || '短信详情'
  }
  if (payload.kind === 'voice' || payload.kind === 'story') {
    const title = [payload.avatarName, payload.title]
      .map((item) => toCopyableText(item || ''))
      .filter(Boolean)
      .join(' · ')
    return title || '详情'
  }
  if (payload.hash) {
    return `TextMap ${payload.hash}`
  }
  return '详情'
})

const messageSections = computed(() =>
  detail.value?.kind === 'message' ? detail.value.sections || [] : []
)

const visibleMessageSections = computed(() => {
  const activeSection = messageSections.value.find(
    (section) => Number(section.sectionId) === Number(activeSectionId.value)
  )
  const sections = activeSection ? [activeSection] : messageSections.value.slice(0, 1)
  return sections.map((section) => ({
    ...section,
    displayEntries: expandMessageNodes(section.sectionId, section.nodes)
  }))
})

watch(
  () => route.fullPath,
  () => {
    loadDetail()
  },
  { immediate: true }
)

watch(messageSections, (sections) => {
  if (!sections.length) {
    activeSectionId.value = null
    return
  }
  if (!sections.some((section) => Number(section.sectionId) === Number(activeSectionId.value))) {
    activeSectionId.value = sections[0].sectionId
  }
})

async function loadDetail() {
  loading.value = true
  errorMessage.value = ''
  detail.value = null
  activeSectionId.value = null
  selectedOptionKeys.value = {}

  try {
    await ensureMetaLoaded()
    const preferences = getSearchPreferences()
    const common = {
      sourceLang: preferences.sourceLanguage,
      resultLangs: preferences.resultLanguages,
      playerName: preferences.playerName,
      playerGender: preferences.playerGender
    }

    let payload = null

    switch (detailKind.value) {
      case 'text':
        payload = await fetchTextSources({
          hash: route.query.hash,
          ...common
        })
        break
      case 'mission':
        payload = await fetchMissionDetail({
          missionId: route.query.missionId,
          ...common
        })
        break
      case 'book':
        payload = await fetchBookDetail({
          bookId: route.query.bookId,
          ...common
        })
        break
      case 'message':
        payload = await fetchMessageDetail({
          threadId: route.query.threadId,
          ...common
        })
        break
      case 'voice':
        payload = await fetchVoiceDetail({
          entryKey: route.query.entryKey,
          ...common
        })
        break
      case 'story':
        payload = await fetchStoryDetail({
          entryKey: route.query.entryKey,
          ...common
        })
        break
      default:
        throw new Error('缺少可识别的详情类型。')
    }

    detail.value = payload
    if (payload?.kind === 'message' && payload.sections?.length) {
      activeSectionId.value = payload.sections[0].sectionId
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载详情失败。'
  } finally {
    loading.value = false
  }
}

function openSourceDetail(source) {
  if (!source?.detailQuery) {
    return
  }
  router.push(buildDetailLocation(source.detailQuery))
}

function shouldShowSender(entry, index, entries) {
  if (detail.value?.kind !== 'message') {
    return false
  }
  const node = entry?.node
  if (node.type === 'option_group' || node.sender === 'player') {
    return false
  }
  if (detail.value.threadType === 'group') {
    return true
  }
  if (index === 0) {
    return true
  }
  const previous = entries[index - 1]?.node
  return previous?.sender !== node.sender
}

function resolveSenderLabel(node) {
  if (node.sender === 'player') {
    return '开拓者'
  }
  if (detail.value?.threadType === 'group') {
    return detail.value?.displayName || '群聊'
  }
  return '对方'
}

function buildOptionSelectionKeyForNode(sectionId, node, fallbackKey) {
  if (node?.groupId != null) {
    return `${sectionId}:${node.groupId}`
  }
  return `${sectionId}:${fallbackKey}`
}

function selectOption(sectionId, node, fallbackKey, option) {
  selectedOptionKeys.value = {
    ...selectedOptionKeys.value,
    [buildOptionSelectionKeyForNode(sectionId, node, fallbackKey)]: option.itemId
  }
}

function resolveSelectedOption(sectionId, node, fallbackKey) {
  const optionId = selectedOptionKeys.value[buildOptionSelectionKeyForNode(sectionId, node, fallbackKey)]
  return node.options.find((option) => Number(option.itemId) === Number(optionId)) || node.options[0] || null
}

function hasTranslations(translations) {
  return Object.keys(translations || {}).length > 0
}

function resolveOptionBubbleTranslations(option) {
  if (hasTranslations(option?.content)) {
    return option.content
  }
  return option?.label || {}
}

function resolveSelectedBranchNodes(sectionId, node, fallbackKey) {
  const selected = resolveSelectedOption(sectionId, node, fallbackKey)
  const branches = node?.optionBranches || []
  const selectedBranch = branches.find(
    (branch) => Number(branch?.optionItemId) === Number(selected?.itemId)
  )
  return selectedBranch?.nodes || []
}

function expandMessageNodes(sectionId, nodes) {
  const expanded = []
  for (let index = 0; index < (nodes || []).length; index += 1) {
    const node = nodes[index]
    const fallbackKey = index
    expanded.push({
      node,
      key: `${sectionId}-${index}`,
      fallbackKey
    })
    if (node?.type === 'option_group') {
      const branchNodes = resolveSelectedBranchNodes(sectionId, node, fallbackKey)
      for (let branchIndex = 0; branchIndex < branchNodes.length; branchIndex += 1) {
        const branchNode = branchNodes[branchIndex]
        const branchItemId = branchNode?.itemId ?? branchIndex
        expanded.push({
          node: branchNode,
          key: `${sectionId}-${index}-branch-${branchItemId}-${branchIndex}`,
          fallbackKey: `${index}-branch-${branchIndex}`
        })
      }
    }
  }
  return expanded
}
</script>

<template>
  <section class="pageSection">
    <div class="panel headerPanel">
      <p class="summaryLabel">Detail</p>
      <h2>{{ detailTitle }}</h2>
      <div v-if="detail" class="metaRow">
        <VersionBadges
          :created-version="detail.createdVersion"
          :updated-version="detail.updatedVersion"
        />
        <span v-if="detail.kind === 'message' && detail.camp" class="metaTag">{{ detail.camp.label }}</span>
        <span v-if="detail.kind === 'message'" class="metaTag">{{ detail.threadType === 'group' ? '群聊' : '单聊' }}</span>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      type="error"
      :closable="false"
      :title="errorMessage"
    />

    <div v-if="loading" class="panel">
      <el-skeleton animated :rows="10" />
    </div>

    <div v-else-if="detail?.kind === 'mission'" class="panel">
      <p class="subMeta">任务文件：{{ (detail.storyPaths || []).join(' · ') || '无' }}</p>
      <div class="dialogueList">
        <article v-for="line in detail.lines" :key="`mission-${line.lineOrder}`" class="dialogueCard">
          <div class="dialogueHead">
            <span class="orderTag">#{{ line.lineOrder + 1 }}</span>
            <span v-if="line.lineType" class="typeTag">{{ line.lineType }}</span>
            <strong>{{ line.speaker || '旁白' }}</strong>
          </div>
          <DetailTranslations
            :translations="line.translates"
            :language-labels="languageLabelMap"
            compact
          />
        </article>
      </div>
    </div>

    <div v-else-if="detail?.kind === 'book'" class="panel detailBody">
      <div class="infoGrid">
        <div v-if="detail.series" class="infoCard">
          <span class="infoLabel">系列</span>
          <strong>{{ detail.series }}</strong>
        </div>
        <div v-if="detail.comment" class="infoCard">
          <span class="infoLabel">注释</span>
          <p>{{ detail.comment }}</p>
        </div>
      </div>
      <DetailTranslations
        :translations="detail.translates"
        :language-labels="languageLabelMap"
      />
    </div>

    <div v-else-if="detail?.kind === 'message'" class="messageDetail">
      <div class="messageSummary">
        <div>
          <p class="summaryLabel">Message Thread</p>
          <h2>{{ detail.displayName }}</h2>
          <p v-if="detail.signature" class="messageSignature">{{ detail.signature }}</p>
        </div>
        <div class="messageSummaryMeta">
          <VersionBadges
            :created-version="detail.createdVersion"
            :updated-version="detail.updatedVersion"
          />
          <span v-if="detail.messageCount" class="metaTag">{{ detail.messageCount }} 条消息</span>
          <span v-if="detail.linkedMainMissionId" class="metaTag">主线 {{ detail.linkedMainMissionId }}</span>
        </div>
      </div>

      <div v-if="messageSections.length" class="sectionDirectory">
        <button
          v-for="section in messageSections"
          :key="section.sectionId"
          type="button"
          class="sectionButton"
          :class="{ active: Number(activeSectionId) === Number(section.sectionId) }"
          @click="activeSectionId = section.sectionId"
        >
          <span>{{ section.title }}</span>
          <small>{{ section.messageCount }} 条</small>
        </button>
      </div>

      <div class="messageSectionList">
        <article
          v-for="section in visibleMessageSections"
          :key="section.sectionId"
          class="messageSectionCard"
        >
          <div class="sectionHeader">
            <div>
              <p class="summaryLabel">Section {{ section.index }}</p>
              <h3>{{ section.title }}</h3>
            </div>
            <div class="metaRow">
              <span v-if="section.linkedMainMissionId" class="metaTag">主线 {{ section.linkedMainMissionId }}</span>
              <span class="metaTag">{{ section.messageCount }} 条</span>
            </div>
          </div>

          <div class="messageTimeline">
            <template
              v-for="(entry, index) in section.displayEntries"
              :key="entry.key"
            >
              <div v-if="entry.node.type === 'option_group'" class="optionGroup">
                <div class="optionSelector">
                  <button
                    v-for="option in entry.node.options"
                    :key="option.itemId"
                    type="button"
                    class="optionButton"
                    :class="{
                      active:
                        resolveSelectedOption(section.sectionId, entry.node, entry.fallbackKey)?.itemId ===
                        option.itemId
                    }"
                    @click="selectOption(section.sectionId, entry.node, entry.fallbackKey, option)"
                  >
                    <DetailTranslations
                      :translations="option.label"
                      :language-labels="languageLabelMap"
                      compact
                    />
                  </button>
                </div>

                <div
                  v-if="resolveSelectedOption(section.sectionId, entry.node, entry.fallbackKey)"
                  class="messageRow fromPlayer"
                >
                  <span class="senderLabel">开拓者</span>
                  <div class="bubble playerBubble">
                    <DetailTranslations
                      :translations="
                        resolveOptionBubbleTranslations(
                          resolveSelectedOption(section.sectionId, entry.node, entry.fallbackKey)
                        )
                      "
                      :language-labels="languageLabelMap"
                      compact
                    />
                  </div>
                </div>
              </div>

              <div
                v-else
                class="messageRow"
                :class="entry.node.sender === 'player' ? 'fromPlayer' : 'fromNpc'"
              >
                <span
                  v-if="shouldShowSender(entry, index, section.displayEntries)"
                  class="senderLabel"
                >
                  {{ resolveSenderLabel(entry.node) }}
                </span>
                <div class="bubble" :class="entry.node.sender === 'player' ? 'playerBubble' : 'npcBubble'">
                  <span
                    v-if="entry.node.type === 'image' || entry.node.type === 'link'"
                    class="bubbleKind"
                  >
                    {{ entry.node.type === 'image' ? '图片短信' : '链接短信' }}
                  </span>
                  <DetailTranslations
                    :translations="entry.node.translates"
                    :language-labels="languageLabelMap"
                    compact
                  />
                </div>
              </div>
            </template>
          </div>
        </article>
      </div>
    </div>

    <div v-else-if="detail?.kind === 'voice'" class="panel detailBody">
      <div class="infoGrid">
        <div v-if="detail.avatarName" class="infoCard">
          <span class="infoLabel">角色</span>
          <strong>{{ detail.avatarName }}</strong>
        </div>
        <div v-if="detail.voicePath" class="infoCard">
          <span class="infoLabel">语音路径</span>
          <code>{{ detail.voicePath }}</code>
        </div>
      </div>
      <DetailTranslations
        :translations="detail.translates"
        :language-labels="languageLabelMap"
      />
    </div>

    <div v-else-if="detail?.kind === 'story'" class="panel detailBody">
      <div class="infoGrid">
        <div v-if="detail.avatarName" class="infoCard">
          <span class="infoLabel">角色</span>
          <strong>{{ detail.avatarName }}</strong>
        </div>
      </div>
      <DetailTranslations
        :translations="detail.translates"
        :language-labels="languageLabelMap"
      />
    </div>

    <div v-else-if="detail?.hash" class="panel detailBody">
      <DetailTranslations
        :translations="detail.translates"
        :language-labels="languageLabelMap"
      />

      <div class="sourceList">
        <article
          v-for="source in detail.sources"
          :key="`${source.sourceType}-${source.sourceKey}-${source.role}`"
          class="sourceCard"
        >
          <div>
            <span class="sourceRole">{{ source.role || source.sourceType }}</span>
            <h3>{{ source.title }}</h3>
            <p v-if="source.subtitle" class="sourceSubtitle">{{ source.subtitle }}</p>
          </div>
          <div class="sourceMeta">
            <VersionBadges
              :created-version="source.createdVersion"
              :updated-version="source.updatedVersion"
            />
            <el-button size="small" @click="openSourceDetail(source)">
              打开来源
            </el-button>
          </div>
        </article>
      </div>
    </div>

    <el-empty v-else description="没有可展示的详情内容" />
  </section>
</template>

<style scoped>
.pageSection {
  display: grid;
  gap: 18px;
}

.panel,
.messageDetail {
  padding: 22px;
  border-radius: 24px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
}

.panel,
.messageDetail {
  border: 1px solid rgba(126, 153, 201, 0.18);
  background: rgba(9, 18, 34, 0.78);
}

.headerPanel h2,
.messageSummary h2,
h3 {
  margin: 0;
}

.summaryLabel {
  margin: 0 0 8px;
  color: rgba(211, 221, 240, 0.58);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.metaRow,
.dialogueHead,
.sourceMeta,
.messageSummaryMeta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.metaRow,
.messageSummaryMeta {
  margin-top: 14px;
}

.metaTag,
.orderTag,
.typeTag,
.sourceRole {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(233, 239, 250, 0.82);
}

.sourceRole {
  display: inline-flex;
  margin-bottom: 10px;
  background: rgba(240, 208, 142, 0.14);
  color: #f5d398;
}

.subMeta,
.sourceSubtitle,
.messageSignature {
  margin: 0;
  color: rgba(223, 231, 246, 0.72);
}

.detailBody {
  display: grid;
  gap: 18px;
}

.infoGrid {
  display: grid;
  gap: 14px;
}

.infoCard {
  padding: 16px;
  border-radius: 18px;
  background: rgba(10, 20, 37, 0.72);
  border: 1px solid rgba(122, 183, 255, 0.14);
  display: grid;
  gap: 8px;
}

.infoCard p {
  margin: 0;
}

.infoLabel {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(211, 221, 240, 0.6);
}

.dialogueList,
.sourceList,
.messageSectionList {
  display: grid;
  gap: 14px;
}

.dialogueCard,
.sourceCard,
.messageSectionCard {
  padding: 18px;
  border-radius: 20px;
  background: rgba(10, 20, 37, 0.7);
  border: 1px solid rgba(122, 183, 255, 0.14);
  display: grid;
  gap: 12px;
}

.messageSummary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.messageToolbar {
  margin-top: 20px;
}

.sectionDirectory {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.sectionButton {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(122, 183, 255, 0.16);
  background: rgba(10, 20, 37, 0.7);
  color: inherit;
  display: grid;
  gap: 4px;
  cursor: pointer;
  text-align: left;
}

.sectionButton.active {
  border-color: rgba(240, 208, 142, 0.46);
  box-shadow: inset 0 0 0 1px rgba(240, 208, 142, 0.16);
}

.sectionButton small {
  color: rgba(223, 231, 246, 0.64);
}

.sectionHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.messageTimeline {
  display: grid;
  gap: 14px;
}

.messageRow {
  display: grid;
  gap: 6px;
}

.fromNpc {
  justify-items: flex-start;
}

.fromPlayer {
  justify-items: flex-end;
}

.senderLabel {
  font-size: 12px;
  color: rgba(223, 231, 246, 0.62);
}

.bubble {
  max-width: min(760px, 92%);
  padding: 14px 16px;
  border-radius: 22px;
  display: grid;
  gap: 10px;
  border: 1px solid rgba(94, 126, 180, 0.12);
}

.npcBubble {
  border-top-left-radius: 10px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(239, 244, 255, 0.94);
}

.playerBubble {
  border-top-right-radius: 10px;
  background: linear-gradient(135deg, rgba(212, 171, 102, 0.3), rgba(255, 240, 212, 0.18));
  color: #fff6e7;
}

.bubbleKind {
  font-size: 12px;
  color: rgba(223, 231, 246, 0.54);
}

.optionGroup {
  display: grid;
  gap: 12px;
}

.optionSelector {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.optionButton {
  min-width: 180px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(126, 153, 201, 0.18);
  background: rgba(10, 20, 37, 0.74);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.optionButton.active {
  border-color: rgba(240, 208, 142, 0.48);
  box-shadow: inset 0 0 0 1px rgba(240, 208, 142, 0.18);
}

@media (max-width: 720px) {
  .messageSummary,
  .sectionHeader {
    flex-direction: column;
  }

  .bubble,
  .optionButton {
    max-width: 100%;
    width: 100%;
  }
}
</style>
