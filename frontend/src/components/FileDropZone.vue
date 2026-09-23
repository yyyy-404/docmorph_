<script setup lang="ts">
import { ref } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()
const dragging = ref(false)
const hint = ref('')

function onDragOver(event: DragEvent) {
  event.preventDefault()
  dragging.value = true
}

function onDragLeave() {
  dragging.value = false
}

/**
 * 桌面壳（WebView2）不会把真实文件路径暴露给普通 HTML5 拖拽，
 * 真正的路径由 Python 侧通过 pywebview 的 DOM drop 事件获取并回填；
 * 这里只负责视觉反馈与浏览器预览模式下的提示。
 */
async function onDrop(event: DragEvent) {
  event.preventDefault()
  dragging.value = false
  const files = Array.from(event.dataTransfer?.files ?? [])
  const paths = files
    .map((file) => (file as File & { path?: string; pywebviewFullPath?: string }))
    .map((file) => file.pywebviewFullPath ?? file.path)
    .filter((value): value is string => Boolean(value))
  if (paths.length) {
    await store.drop(paths)
    return
  }
  hint.value = '未能读取拖入文件路径，请改用「选择文件 / 选择文件夹」。'
  if (files.length) {
    store.notify(hint.value, 'info')
  }
}
</script>

<template>
  <div
    id="drop-zone"
    class="drop-zone"
    :class="{ dragging }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="icon">📥</div>
    <div class="title">拖拽文件或文件夹到这里</div>
    <div class="sub muted">
      {{ store.selectedCount ? `已选择 ${store.selectedCount} 个文件` : '支持 PDF / DOCX / XLSX / MD / HTML / TXT / CSV' }}
    </div>
    <div v-if="hint" class="sub warn-text">{{ hint }}</div>
  </div>
</template>

<style scoped>
.drop-zone {
  border: 2px dashed #bbbbbb;
  border-radius: var(--dm-radius);
  background: #f5f5f7;
  padding: 22px 16px;
  text-align: center;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.drop-zone.dragging {
  border-color: #4a90e2;
  background: #e3f2fd;
}

.icon {
  font-size: 22px;
  line-height: 1.2;
}

.title {
  font-size: 15px;
  font-weight: 600;
  color: #444;
  margin-top: 4px;
}

.sub {
  font-size: 12px;
  margin-top: 4px;
}

.warn-text {
  color: #8d3b3b;
}
</style>
