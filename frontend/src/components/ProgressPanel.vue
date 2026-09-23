<script setup lang="ts">
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()

const summaryText = computed(() => {
  const summary = store.summary
  if (!summary) return ''
  return `共 ${summary.total} · 成功 ${summary.succeeded} · 跳过 ${summary.skipped} · 失败 ${summary.failed} · 取消 ${summary.cancelled} · ${summary.duration_s}s`
})
</script>

<template>
  <div class="progress-panel">
    <div class="track">
      <div class="chunk" :style="{ width: `${store.state.progress}%` }" />
    </div>
    <div class="row">
      <span class="grow truncate status">{{ store.state.progress_text || '就绪' }}</span>
      <span v-if="store.busy" class="muted pct">{{ store.state.progress }}%</span>
    </div>
    <div v-if="summaryText" class="muted summary">{{ summaryText }}</div>
  </div>
</template>

<style scoped>
.progress-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.track {
  height: 10px;
  border: 1px solid #c0c0c0;
  border-radius: 6px;
  background: #f0f0f0;
  overflow: hidden;
}

.chunk {
  height: 100%;
  background: linear-gradient(90deg, var(--dm-accent-soft), var(--dm-accent));
  border-radius: 5px;
  transition: width 0.25s ease;
}

.status {
  font-size: 12px;
  color: #444;
}

.pct {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.summary {
  font-size: 11px;
}
</style>
