<script setup>
import { computed } from 'vue'

import { buildVersionBadges } from '@/utils/versionDisplay'

const props = defineProps({
  createdVersion: {
    type: String,
    default: ''
  },
  updatedVersion: {
    type: String,
    default: ''
  }
})

const badges = computed(() => buildVersionBadges(props.createdVersion, props.updatedVersion))
</script>

<template>
  <div v-if="badges.length" class="versionBadges">
    <span
      v-for="badge in badges"
      :key="badge.key"
      class="versionTag"
    >
      {{ badge.label }}
    </span>
  </div>
</template>

<style scoped>
.versionBadges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.versionTag {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: rgba(233, 239, 250, 0.78);
  background: rgba(255, 255, 255, 0.06);
}
</style>
