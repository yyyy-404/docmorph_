<script setup lang="ts">
import { ref } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()
const pages = ref('')

function baseName(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}
</script>

<template>
  <div class="card">
    <h2>PDF 工具</h2>
    <p class="muted intro">
      合并与拆分都在本机完成，输出默认写入「输出目录」；目标同名时按设置处理（默认自动改名，不覆盖）。
    </p>

    <section class="block">
      <div class="block-title">合并 PDF</div>
      <div class="row">
        <button :disabled="store.pdfBusy" @click="store.pickMergeFiles()">选择 PDF（可多选）</button>
        <button class="primary" :disabled="store.pdfBusy || store.mergeFiles.length < 2" @click="store.mergePdfs()">
          合并为 merged.pdf
        </button>
      </div>
      <ul v-if="store.mergeFiles.length" class="list">
        <li v-for="file in store.mergeFiles" :key="file" :title="file">{{ baseName(file) }}</li>
      </ul>
      <div v-else class="muted small">尚未选择文件</div>
    </section>

    <section class="block">
      <div class="block-title">拆分 / 提取页面</div>
      <div class="row">
        <button :disabled="store.pdfBusy" @click="store.pickSplitInput()">选择 PDF</button>
        <input
          v-model="pages"
          type="text"
          class="grow"
          placeholder="页范围，例如 1-3,5,7-9（留空 = 每页一个文件）"
        />
        <button class="primary" :disabled="store.pdfBusy || !store.splitInput" @click="store.splitPdf(pages)">
          开始拆分
        </button>
      </div>
      <div v-if="store.splitInput" class="muted small" :title="store.splitInput">
        已选择：{{ baseName(store.splitInput) }}
      </div>
      <div class="muted small">输出文件名形如 <code>原文件名_p1-3.pdf</code></div>
    </section>
  </div>
</template>

<style scoped>
.intro {
  font-size: 12px;
  line-height: 1.6;
  margin: 0 0 12px;
}

.block {
  padding: 10px 0;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.block:first-of-type {
  border-top: none;
}

.block-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--dm-muted);
  margin-bottom: 6px;
}

.list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #3a3f45;
  max-height: 120px;
  overflow: auto;
}

.small {
  font-size: 11px;
  margin-top: 6px;
}

code {
  background: var(--dm-cream);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
