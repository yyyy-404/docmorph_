<script setup lang="ts">
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()

const files = computed(() => store.selection.files.slice(0, 60))
const overflow = computed(() => Math.max(0, store.selection.files.length - files.value.length))

function baseName(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}
</script>

<template>
  <div v-if="store.selection.files.length" class="list scroll">
    <div v-for="file in files" :key="file" class="item" :title="file">
      <span class="dot" :class="{ folder: false }" />
      <span class="name truncate">{{ baseName(file) }}</span>
      <span class="path truncate muted">{{ file }}</span>
    </div>
    <div v-if="overflow" class="more muted">…另有 {{ overflow }} 个文件</div>
  </div>
  <div v-else class="empty muted">
    {{ store.selection.directory ? `目录：${store.selection.directory}` : '尚未选择文件' }}
  </div>
</template>

<style scoped>
.list {
  max-height: 168px;
  border: 1px solid var(--dm-border-soft);
  border-radius: var(--dm-radius-sm);
  background: rgba(255, 255, 255, 0.45);
}

.item {
  display: grid;
  grid-template-columns: 8px minmax(90px, 40%) 1fr;
  gap: 8px;
  align-items: center;
  padding: 5px 10px;
  font-size: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
}

.item:last-child {
  border-bottom: none;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--dm-accent);
}

.name {
  font-weight: 600;
  color: #3a3f45;
}

.path {
  font-size: 11px;
}

.more,
.empty {
  font-size: 12px;
  padding: 8px 10px;
}
</style>
