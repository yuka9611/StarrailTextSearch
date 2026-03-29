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
    resultLanguages: selectedResultLanguages.value,
    playerName: playerName.value,
    playerGender: playerGender.value
  })
  selectedLanguage.value = snapshot.defaultLanguage
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

      <el-skeleton v-if="loading" :rows="8" animated />

      <el-form v-else label-position="top" class="settingsForm">
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

        <el-form-item label="结果语言">
          <el-transfer
            v-model="selectedResultLanguages"
            class="resultLanguageTransfer"
            :data="transferData"
            :titles="['可选语言', '已选语言']"
            target-order="push"
          />
        </el-form-item>

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
  margin: 0 0 10px;
  font-size: 28px;
}

.settingsForm {
  display: grid;
  gap: 8px;
}

.languageSelect {
  width: min(360px, 100%);
}

.textInput {
  width: min(420px, 100%);
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

.saveButton {
  width: fit-content;
  min-width: 132px;
  border: 0;
  color: #1f1306;
  background: linear-gradient(135deg, #f0d08e, #bf7f3a);
  box-shadow: 0 12px 28px rgba(168, 112, 45, 0.28);
}

.saveButton:hover,
.saveButton:focus-visible {
  color: #1f1306;
  background: linear-gradient(135deg, #f4daa1, #c78944);
  box-shadow: 0 14px 30px rgba(168, 112, 45, 0.34);
}

.saveButton:deep(span) {
  font-weight: 600;
}

.saveButton.is-disabled,
.saveButton.is-disabled:hover,
.saveButton.is-disabled:focus-visible {
  color: rgba(255, 244, 225, 0.56);
  background: linear-gradient(135deg, rgba(125, 99, 63, 0.5), rgba(93, 67, 40, 0.5));
  box-shadow: none;
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
