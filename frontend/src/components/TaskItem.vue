<script setup lang="ts">
import type { TaskResult } from '@/types'

defineProps<{ task: TaskResult }>()
</script>

<template>
  <div class="task" :class="task.status">
    <span class="mark">{{ task.status.startsWith('success') ? '✅' : task.status === 'skipped_exists' ? '⏭' : task.status === 'cancelled' ? '⏹' : '❌' }}</span>
    <div class="body grow">
      <div class="row">
        <span class="name grow truncate" :title="task.input">{{ task.file_name }}</span>
        <span class="tag" :class="task.status.startsWith('success') ? 'ok' : task.status === 'skipped_exists' ? 'warn' : 'bad'">
          {{ task.status_label }}
        </span>
        <span v-if="task.backend" class="muted backend">{{ task.backend }}</span>
        <span class="muted time">{{ task.duration_s }}s</span>
      </div>
      <div v-if="task.outputs.length" class="muted detail truncate" :title="task.outputs.join(' | ')">
        → {{ task.outputs.map((item) => item.split(/[\\/]/).pop()).join(', ') }}
      </div>
      <div v-if="task.error" class="detail error">{{ task.error }}</div>
      <div v-for="warning in task.warnings" :key="warning" class="detail warn">提示：{{ warning }}</div>
    </div>
  </div>
</template>

<style scoped>
.task {
  display: flex;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  font-size: 12px;
}

.task:last-child {
  border-bottom: none;
}

.mark {
  line-height: 1.4;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.name {
  font-weight: 600;
  color: #34383d;
}

.backend,
.time {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.detail {
  font-size: 11px;
}

.detail.error {
  color: #8d3b3b;
}

.detail.warn {
  color: #7a5316;
}
</style>
