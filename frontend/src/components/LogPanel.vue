<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()
const autoRefresh = ref(true)
let timer = 0

async function refresh() {
  await store.refreshLogs()
}

function startTimer() {
  window.clearInterval(timer)
  timer = window.setInterval(() => {
    if (autoRefresh.value) void refresh()
  }, 1500)
}

watch(autoRefresh, startTimer)
onMounted(() => {
  void refresh()
  startTimer()
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="card log-card">
    <div class="row">
      <h2 class="grow">运行日志</h2>
      <label class="row toggle">
        <input v-model="autoRefresh" type="checkbox" />
        <span class="muted">自动刷新</span>
      </label>
      <button class="ghost" @click="refresh()">立即刷新</button>
      <button class="ghost" :disabled="!store.state.log_file" @click="store.openPath(store.state.log_file)">
        打开日志文件
      </button>
    </div>
    <pre class="log scroll">{{ store.state.log_tail.join('\n') || '暂无日志' }}</pre>
  </div>
</template>

<style scoped>
.log-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.toggle {
  gap: 4px;
  font-size: 11px;
}

.log {
  flex: 1;
  min-height: 120px;
  max-height: 220px;
  margin: 0;
  padding: 10px;
  font-family: var(--dm-mono);
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--dm-border-soft);
  border-radius: var(--dm-radius-sm);
  user-select: text;
}
</style>
