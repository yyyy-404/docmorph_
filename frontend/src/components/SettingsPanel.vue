<script setup lang="ts">
import { ref } from 'vue'

import { useAppStore } from '@/stores/app'

const store = useAppStore()
const saved = ref('')

async function apply(patch: Record<string, unknown>) {
  await store.saveSettings(patch)
  saved.value = new Date().toLocaleTimeString()
}
</script>

<template>
  <div class="card">
    <div class="row">
      <h2 class="grow">设置</h2>
      <span v-if="saved" class="muted small">已保存 {{ saved }}</span>
    </div>

    <div class="grid">
      <label class="field">
        <span class="label">输出目录</span>
        <div class="row">
          <input type="text" :value="store.state.output_directory" readonly class="grow" />
          <button @click="store.pickOutput()">浏览…</button>
        </div>
      </label>

      <label class="field">
        <span class="label">目标文件已存在时</span>
        <select
          :value="store.state.conflict_policy"
          @change="apply({ conflict_policy: ($event.target as HTMLSelectElement).value })"
        >
          <option value="rename">自动改名（不覆盖，推荐）</option>
          <option value="overwrite">覆盖</option>
          <option value="skip">跳过</option>
        </select>
      </label>

      <label class="field">
        <span class="label">批量并发数</span>
        <input
          type="text"
          :value="store.state.max_workers"
          @change="apply({ max_workers: Number(($event.target as HTMLInputElement).value) || 4 })"
        />
        <span class="muted small">Word / Excel 转换会强制串行执行</span>
      </label>

      <label class="field">
        <span class="label">xlsx → csv 模式</span>
        <select
          :value="store.state.xlsx_csv_mode"
          @change="apply({ xlsx_csv_mode: ($event.target as HTMLSelectElement).value })"
        >
          <option value="sheets">每个工作表一个文件</option>
          <option value="merged">合并为一个文件（加 sheet 列）</option>
          <option value="first">仅第一个工作表</option>
        </select>
      </label>

      <label class="field">
        <span class="label">PDF 引擎偏好</span>
        <select
          :value="store.state.pdf_backend_preference"
          @change="apply({ pdf_backend_preference: ($event.target as HTMLSelectElement).value })"
        >
          <option value="auto">自动（按可用性）</option>
          <option value="word">Microsoft Word</option>
          <option value="wps">WPS Office</option>
          <option value="libreoffice">LibreOffice</option>
          <option value="weasyprint">WeasyPrint</option>
        </select>
      </label>

      <label class="field check">
        <input
          type="checkbox"
          :checked="store.state.keep_structure"
          @change="apply({ keep_structure: ($event.target as HTMLInputElement).checked })"
        />
        <span>批量转换保留目录结构</span>
      </label>

      <label class="field check">
        <input
          type="checkbox"
          :checked="store.state.extract_media"
          @change="apply({ extract_media: ($event.target as HTMLInputElement).checked })"
        />
        <span>转 Markdown 时抽取图片到 _media 目录</span>
      </label>
    </div>

    <div class="paths muted small">
      <div>配置文件：{{ store.state.config_path || '（默认位置）' }}</div>
      <div v-if="store.state.config_warnings.length" class="warn-text">
        {{ store.state.config_warnings.join('；') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field.check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.field.check input {
  width: auto;
}

.small {
  font-size: 11px;
}

.paths {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  user-select: text;
}

.warn-text {
  color: #8d3b3b;
}
</style>
