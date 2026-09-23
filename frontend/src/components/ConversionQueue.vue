<script setup lang="ts">
import { computed } from 'vue'

import TaskItem from '@/components/TaskItem.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()

const tasks = computed(() => [...store.state.tasks].reverse())
</script>

<template>
  <div class="card queue-card">
    <div class="row">
      <h2 class="grow">转换队列</h2>
      <button class="ghost" @click="store.refreshLogs()">刷新</button>
    </div>
    <div v-if="tasks.length" class="list scroll">
      <TaskItem v-for="task in tasks" :key="task.id" :task="task" />
    </div>
    <div v-else class="empty muted">暂无任务。选择文件后点击「执行转换」或「批量转换」。</div>
  </div>
</template>

<style scoped>
.queue-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.list {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--dm-border-soft);
  border-radius: var(--dm-radius-sm);
  background: rgba(255, 255, 255, 0.45);
}

.empty {
  font-size: 12px;
  padding: 14px 4px;
}
</style>
