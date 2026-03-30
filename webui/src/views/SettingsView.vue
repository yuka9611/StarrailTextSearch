<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  appState,
  ensureMetaLoaded,
  getSearchPreferences,
  playerGenderOptions,
  saveSearchPreferences
} from '@/stores/appState'

const selectedLanguage = ref('chs')
const selectedSourceLanguage = ref('chs')
const selectedResultLanguages = ref([])
const playerName = ref('开拓者')
const playerGender = ref('both')
const loading = ref(false)

const transferData = computed(() =>
  appState.languages.map((item) => ({
    key: item.code,
    label: item.label,
    disabled: false
  }))
)

onMounted(async () => {
  loading.value = true
  try {
    await ensureMetaLoaded()
    const preferences = getSearchPreferences()
    selectedLanguage.value = preferences.defaultLanguage
    selectedSourceLanguage.value = preferences.sourceLanguage
    selectedResultLanguages.value = preferences.resultLanguages
    playerName.value = preferences.playerName
    playerGender.value = preferences.playerGender
  } finally {
    loading.value = false
  }
})

function onSave() {
  const snapshot = saveSearchPreferences({
    defaultLanguage: selectedLanguage.value,
    sourceLanguage: selectedSourceLanguage.value,
    resultLanguages: selectedResultLanguages.value,
    playerName: playerName.value,
    playerGender: playerGender.value
  })
  selectedLanguage.value = snapshot.defaultLanguage
  selectedSourceLanguage.value = snapshot.sourceLanguage
  selectedResultLanguages.value = snapshot.resultLanguages
  playerName.value = snapshot.playerName
  playerGender.value = snapshot.playerGender
  ElMessage.success('设置已保存。')
}
</script>

<template>
  <section class="settingsPage">
    <div class="settingsCard">
      <p class="eyebrow">Search Preferences</p>
      <h2>搜索设置</h2>
      <p class="pageLead">
        默认结果语言、来源语言和玩家替换会同步用于关键词搜索、详情页以及短信阅读页。
      </p>

      <el-skeleton v-if="loading" :rows="8" animated />

      <el-form v-else label-position="top" class="settingsForm">
        <div class="twoColumn">
          <el-form-item label="默认搜索语言">
            <el-select
              v-model="selectedLanguage"
              class="languageSelect"
              placeholder="请选择默认语言"
            >
              <el-option
                v-for="item in appState.languages"
                :key="item.code"
                :label="item.label"
                :value="item.code"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="来源标题语言">
            <el-select
              v-model="selectedSourceLanguage"
              class="languageSelect"
              placeholder="请选择来源语言"
            >
              <el-option
                v-for="item in appState.languages"
                :key="`source-${item.code}`"
                :label="item.label"
                :value="item.code"
              />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item label="结果语言">
          <el-transfer
            v-model="selectedResultLanguages"
            class="resultLanguageTransfer"
            :data="transferData"
            :titles="['可选语言', '已选语言']"
            target-order="push"
          />
        </el-form-item>

        <div class="twoColumn">
          <el-form-item label="玩家昵称">
            <el-input
              v-model="playerName"
              class="textInput"
              maxlength="24"
              placeholder="用于替换 {NICKNAME}"
              clearable
            />
          </el-form-item>

          <el-form-item label="玩家性别">
            <el-radio-group v-model="playerGender" class="genderGroup">
              <el-radio-button
                v-for="item in playerGenderOptions"
                :key="item.value"
                :label="item.value"
              >
                {{ item.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>
        </div>

        <div class="infoRow">
          <span v-if="appState.currentVersion" class="versionChip">
            当前数据库版本：{{ appState.currentVersion }}
          </span>
          <span v-if="appState.dbPath" class="pathChip">
            {{ appState.dbPath }}
          </span>
        </div>

        <el-button
          class="saveButton"
          type="primary"
          :disabled="!appState.languages.length"
          @click="onSave"
        >
          保存设置
        </el-button>
      </el-form>
    </div>
  </section>
</template>

<style scoped>
.settingsPage {
  display: grid;
}

.settingsCard {
  padding: 26px;
  border: 1px solid rgba(126, 153, 201, 0.18);
  border-radius: 24px;
  background: rgba(9, 18, 34, 0.78);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(16px);
}

.eyebrow {
  margin: 0 0 10px;
  color: #d7bc7e;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  font-size: 28px;
}

.pageLead {
  margin: 10px 0 0;
  color: rgba(223, 231, 246, 0.72);
}

.settingsForm {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.twoColumn {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.languageSelect,
.textInput {
  width: 100%;
}

.resultLanguageTransfer {
  width: 100%;
}

.resultLanguageTransfer:deep(.el-transfer-panel) {
  width: min(100%, 320px);
  background: rgba(8, 16, 30, 0.82);
  border-color: rgba(169, 127, 68, 0.24);
}

.resultLanguageTransfer:deep(.el-transfer-panel__header),
.resultLanguageTransfer:deep(.el-transfer-panel__body),
.resultLanguageTransfer:deep(.el-transfer-panel__filter) {
  background: transparent;
}

.resultLanguageTransfer:deep(.el-transfer-panel__item) {
  color: rgba(233, 239, 250, 0.82);
}

.genderGroup {
  display: flex;
  flex-wrap: wrap;
}

.genderGroup:deep(.el-radio-button__inner) {
  min-width: 88px;
  background: rgba(8, 16, 30, 0.82);
  border-color: rgba(169, 127, 68, 0.24);
  color: rgba(233, 239, 250, 0.82);
}

.genderGroup:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, #f0d08e, #bf7f3a);
  border-color: transparent;
  color: #1f1306;
  box-shadow: none;
}

.infoRow {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.versionChip,
.pathChip {
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(233, 239, 250, 0.75);
}

.saveButton {
  width: fit-content;
  min-width: 132px;
}

@media (max-width: 900px) {
  .twoColumn {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .settingsCard {
    padding: 20px;
    border-radius: 20px;
  }

  .resultLanguageTransfer:deep(.el-transfer) {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
