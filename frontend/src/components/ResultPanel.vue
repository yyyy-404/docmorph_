<script setup lang="ts">
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()

const failures = computed(() =>
  store.state.tasks.filter((task) => !task.status.startsWith('success')).slice(0, 12),
)
</script>

<template>
  <div v-if="store.state.tasks.length" class="card">
    <div class="row">
      <h2 class="grow">结果</h2>
      <button class="ghost" @click="store.revealOutput()">打开输出目录</button>
    </div>
    <div v-if="!failures.length" class="ok-line">✅ 全部任务已完成，没有失败项。</div>
    <div v-else class="list">
      <div v-for="task in failures" :key="task.id" class="line">
        <span class="badge">{{ task.status_label }}</span>
        <span class="name truncate" :title="task.input">{{ task.file_name }}</span>
        <span class="muted msg truncate" :title="task.error">{{ task.error }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ok-line {
  font-size: 12px;
  color: #2f6b52;
}

.line {
  display: grid;
  grid-template-columns: 110px minmax(120px, 34%) 1fr;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3dada;
  color: #8d3b3b;
  text-align: center;
}

.name {
  font-weight: 600;
  color: #3a3f45;
}

.msg {
  font-size: 11px;
}
</style>
