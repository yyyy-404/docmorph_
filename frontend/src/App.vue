<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import CapabilityBar from '@/components/CapabilityBar.vue'
import CapabilityPanel from '@/components/CapabilityPanel.vue'
import ConversionQueue from '@/components/ConversionQueue.vue'
import FileDropZone from '@/components/FileDropZone.vue'
import FileList from '@/components/FileList.vue'
import FormatSelector from '@/components/FormatSelector.vue'
import LogPanel from '@/components/LogPanel.vue'
import PdfToolsPanel from '@/components/PdfToolsPanel.vue'
import ProgressPanel from '@/components/ProgressPanel.vue'
import ResultPanel from '@/components/ResultPanel.vue'
import SettingsPanel from '@/components/SettingsPanel.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const tab = ref<'convert' | 'pdf' | 'logs' | 'capabilities' | 'settings'>('convert')

const tabs = [
  { id: 'convert', label: '转换' },
  { id: 'pdf', label: 'PDF 工具' },
  { id: 'logs', label: '日志' },
  { id: 'capabilities', label: '系统能力' },
  { id: 'settings', label: '设置' },
] as const

const canStart = computed(() => store.selectedCount > 0 && !store.busy)
const messageClass = computed(() => `banner ${store.messageKind}`)
const dragging = ref(false)

/** 整窗拖拽反馈：真实路径由 Python 侧的 DOM drop 事件解析（WebView2 不向 JS 暴露路径）。 */
function onWindowDragOver(event: DragEvent) {
  event.preventDefault()
  dragging.value = true
}

function onWindowDragLeave(event: DragEvent) {
  if (event.relatedTarget === null) dragging.value = false
}

function onWindowDrop(event: DragEvent) {
  event.preventDefault()
  dragging.value = false
}

onMounted(() => {
  void store.init()
  // 桌面壳在 Python 侧解析拖拽路径后回调这里（WebView2 不向 JS 暴露真实路径）
  ;(window as unknown as Record<string, unknown>).docmorphDrop = (payload: unknown) => {
    store.applySelection(payload as never)
  }
})
</script>

<template>
  <div
    class="shell"
    @dragover="onWindowDragOver"
    @dragleave="onWindowDragLeave"
    @drop="onWindowDrop"
  >
    <div v-if="dragging" class="drag-overlay">
      <div class="drag-card">松开即可添加文件</div>
    </div>
    <header class="head">
      <div class="row title-row">
        <div class="title grow">
          <span class="logo">📄</span>
          <div>
            <div class="name">DocMorph</div>
            <div class="sub muted">本地文档格式转换 · 文件不离开本机</div>
          </div>
        </div>
        <nav class="tabs">
          <button
            v-for="item in tabs"
            :key="item.id"
            class="tab"
            :class="{ active: tab === item.id }"
            @click="tab = item.id"
          >
            {{ item.label }}
          </button>
        </nav>
      </div>
      <CapabilityBar />
    </header>

    <div v-if="store.message" :class="messageClass" @click="store.message = ''">
      {{ store.message }}
    </div>
    <div v-if="store.safeMode" class="banner safe">
      安全模式：仅加载内置转换能力（Pandoc / 纯 Python）。Office、WPS、LibreOffice、WeasyPrint 已临时禁用。
      <a href="#" @click.prevent="store.recheckCapabilities()">重新检测</a>
    </div>
    <div v-else-if="store.capabilityPending" class="banner">
      正在后台检测可用转换引擎…（可直接开始转换，检测完成会自动刷新可用格式）
    </div>

    <main class="body scroll">
      <!-- ------------------------------------------------------------ 转换 -->
      <div v-if="tab === 'convert'" class="convert-grid">
        <section class="left">
          <div class="card">
            <h2>输入</h2>
            <div class="row">
              <button :disabled="store.busy" @click="store.pickFiles()">📁 选择多个文件</button>
              <button :disabled="store.busy" @click="store.pickFolder()">📂 选择文件夹</button>
              <span class="grow" />
              <span class="tag" :class="store.selectedCount ? 'ok' : ''">
                {{ store.selectedCount ? `${store.selectedCount} 个文件` : '未选择' }}
              </span>
            </div>
            <div class="spacer" />
            <FileDropZone />
            <div class="spacer" />
            <FileList />
          </div>

          <div class="card">
            <h2>输出</h2>
            <div class="row">
              <input type="text" class="grow" :value="store.state.output_directory" readonly />
              <button :disabled="store.busy" @click="store.pickOutput()">浏览…</button>
            </div>
            <div v-if="store.presets.length" class="presets">
              <span class="label">最近使用</span>
              <button
                v-for="preset in store.presets"
                :key="`${preset.source}-${preset.target}`"
                class="ghost preset"
                :title="`切换为 ${preset.source} → ${preset.target}`"
                @click="store.applyPreset(preset)"
              >
                {{ preset.source }} → {{ preset.target }}
              </button>
            </div>
            <div class="spacer" />
            <FormatSelector />
          </div>

          <div class="card">
            <div class="row">
              <button class="primary grow" :disabled="!canStart" @click="store.start()">
                🚀 {{ store.busy ? '转换中…' : '执行转换' }}
              </button>
              <button class="danger" :disabled="!store.busy" @click="store.cancel()">⏹ 取消</button>
            </div>
            <div class="spacer" />
            <ProgressPanel />
          </div>
        </section>

        <section class="right">
          <ConversionQueue />
          <ResultPanel />
        </section>
      </div>

      <!-- ------------------------------------------------------------ 日志 -->
      <div v-else-if="tab === 'pdf'" class="single">
        <PdfToolsPanel />
      </div>

      <div v-else-if="tab === 'logs'" class="single">
        <LogPanel />
      </div>

      <!-- -------------------------------------------------------- 系统能力 -->
      <div v-else-if="tab === 'capabilities'" class="single">
        <CapabilityPanel />
      </div>

      <!-- ------------------------------------------------------------ 设置 -->
      <div v-else class="single">
        <SettingsPanel />
      </div>
    </main>

    <footer class="foot muted">
      <span>DocMorph {{ store.state.version }} · Python {{ store.state.platform }}</span>
      <span class="grow" />
      <span>{{ store.desktop ? '桌面模式' : '浏览器预览模式（功能受限）' }}</span>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 14px 16px 10px;
  gap: 10px;
}

.head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.title-row {
  gap: 12px;
}

.title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo {
  font-size: 22px;
}

.name {
  font-size: 17px;
  font-weight: 700;
  color: var(--dm-text-strong);
  letter-spacing: 0.02em;
}

.sub {
  font-size: 11px;
}

.tabs {
  display: flex;
  gap: 4px;
  background: rgba(255, 255, 255, 0.45);
  border: 1px solid var(--dm-border-soft);
  border-radius: 999px;
  padding: 3px;
}

.tab {
  border: none;
  background: transparent;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12px;
}

.tab.active {
  background: var(--dm-card-strong);
  box-shadow: var(--dm-shadow-soft);
  font-weight: 600;
}

.banner {
  padding: 8px 12px;
  border-radius: var(--dm-radius-sm);
  font-size: 12px;
  border: 1px solid var(--dm-border-soft);
  background: var(--dm-cream);
  cursor: pointer;
}

.banner.error {
  background: #f7e2e2;
  border-color: #e0bcbc;
  color: #8d3b3b;
}

.banner.success {
  background: var(--dm-mist);
  border-color: #a7cde6;
  color: #1f4a66;
}

.banner.safe {
  background: var(--dm-sand);
  border-color: #e8cfa8;
  color: #7a5316;
}

.drag-overlay {
  position: fixed;
  inset: 0;
  background: rgba(140, 192, 235, 0.18);
  border: 2px dashed var(--dm-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  pointer-events: none;
}

.drag-card {
  background: var(--dm-card-strong);
  border-radius: var(--dm-radius);
  padding: 14px 22px;
  font-size: 14px;
  font-weight: 600;
  color: var(--dm-accent-ink);
  box-shadow: var(--dm-shadow);
}

.presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.preset {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  border-color: var(--dm-border-soft);
}

.banner a {
  color: inherit;
  text-decoration: underline;
}

.body {
  flex: 1;
  min-height: 0;
}

.convert-grid {
  display: grid;
  grid-template-columns: minmax(340px, 1fr) minmax(320px, 1fr);
  gap: 12px;
  align-items: stretch;
  height: 100%;
}

.left,
.right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.right {
  height: 100%;
}

.right > :first-child {
  flex: 1;
}

.single {
  max-width: 900px;
  margin: 0 auto;
}

.spacer {
  height: 10px;
}

.foot {
  display: flex;
  gap: 8px;
  font-size: 11px;
}

@media (max-width: 860px) {
  .convert-grid {
    grid-template-columns: 1fr;
  }
}
</style>
