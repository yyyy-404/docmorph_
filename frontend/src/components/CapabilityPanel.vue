<script setup lang="ts">
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()

const groups = computed(() => {
  const items = store.capabilities?.capabilities ?? []
  return [
    { title: '转换引擎（外部软件）', kind: 'external-app' },
    { title: 'Python 依赖', kind: 'python-package' },
    { title: '系统运行时', kind: 'system-runtime' },
  ].map((group) => ({
    ...group,
    items: items.filter((item) => item.kind === group.kind),
  }))
})
</script>

<template>
  <div class="card">
    <h2>系统能力</h2>
    <p class="muted intro">
      转换是否可用取决于本机安装了什么。下面是当前环境的实时检测结果——
      缺少的引擎只会影响对应格式，其它转换仍然可用。
    </p>
    <div v-for="group in groups" :key="group.kind" class="group">
      <div class="group-title">{{ group.title }}</div>
      <div v-for="item in group.items" :key="item.id" class="item">
        <span class="tag" :class="item.available ? 'ok' : 'bad'">
          {{ item.available ? '✔ 可用' : '✘ 不可用' }}
        </span>
        <span class="name">{{ item.label }}</span>
        <span class="muted detail truncate" :title="item.detail">{{ item.detail }}</span>
        <span v-if="!item.available && item.hint" class="hint">{{ item.hint }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.intro {
  font-size: 12px;
  line-height: 1.6;
  margin: 0 0 12px;
}

.group {
  margin-bottom: 12px;
}

.group-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--dm-muted);
  margin-bottom: 6px;
}

.item {
  display: grid;
  grid-template-columns: 78px minmax(140px, 32%) 1fr;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
}

.name {
  font-weight: 600;
  color: #3a3f45;
}

.detail {
  font-size: 11px;
  user-select: text;
}

.hint {
  grid-column: 3;
  font-size: 11px;
  color: #7a5316;
}
</style>
