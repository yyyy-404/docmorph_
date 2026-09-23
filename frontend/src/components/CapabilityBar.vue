<script setup lang="ts">
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()

const chips = computed(() => {
  const items = store.capabilities?.capabilities ?? []
  return items.filter((item) =>
    ['word', 'excel', 'wps', 'libreoffice', 'pandoc', 'weasyprint', 'webview2'].includes(item.id),
  )
})
</script>

<template>
  <div class="bar row wrap">
    <span
      v-for="chip in chips"
      :key="chip.id"
      class="tag"
      :class="chip.available ? 'ok' : 'bad'"
      :title="chip.available ? chip.detail : `${chip.detail}${chip.hint ? ' · ' + chip.hint : ''}`"
    >
      {{ chip.available ? '✔' : '✘' }} {{ chip.label.replace(/（.*?）/, '') }}
    </span>
  </div>
</template>

<style scoped>
.bar {
  gap: 6px;
}
</style>
