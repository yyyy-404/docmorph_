import { defineStore } from 'pinia'

import { api, desktopUnavailable, isDesktop, waitForBridge } from '@/api'
import type {
  AppState,
  BatchSummary,
  CapabilityPayload,
  PdfTaskPayload,
  RecentPreset,
  SelectionPayload,
  SourceEntry,
  StartPayload,
  TaskResult,
} from '@/types'

const PRESET_KEY = 'docmorph.recentPresets'
const PRESET_LIMIT = 6

function emptyState(): AppState {
  return {
    version: '',
    platform: '',
    running: false,
    cancel_requested: false,
    progress: 0,
    progress_text: '就绪',
    summary: null,
    tasks: [],
    output_directory: '',
    input_directory: '',
    keep_structure: true,
    conflict_policy: 'rename',
    max_workers: 4,
    xlsx_csv_mode: 'sheets',
    extract_media: true,
    pdf_backend_preference: 'auto',
    theme_colors: [],
    log_tail: [],
    log_file: '',
    config_path: '',
    config_warnings: [],
    webview_available: true,
    safe_mode: false,
    capability_pending: false,
    temp_retention_hours: 24,
  }
}

function loadPresets(): RecentPreset[] {
  try {
    const raw = window.localStorage.getItem(PRESET_KEY)
    const parsed = raw ? (JSON.parse(raw) as RecentPreset[]) : []
    return Array.isArray(parsed) ? parsed.slice(0, PRESET_LIMIT) : []
  } catch {
    return []
  }
}

export const useAppStore = defineStore('app', {
  state: () => ({
    state: emptyState(),
    catalog: [] as SourceEntry[],
    capabilities: null as CapabilityPayload | null,
    selection: { files: [], directory: '', count: 0, notes: [] } as SelectionPayload,
    sourceFormat: 'docx',
    targetFormat: 'pdf',
    message: '',
    messageKind: 'info' as 'info' | 'error' | 'success',
    desktop: false,
    ready: false,
    pollTimer: 0,
    presets: [] as RecentPreset[],
    capabilityTimer: 0,
    pdfBusy: false,
    mergeFiles: [] as string[],
    splitInput: '',
  }),

  getters: {
    currentSource(state): SourceEntry | undefined {
      return state.catalog.find((item) => item.source === state.sourceFormat)
    },
    targetOptions(): { target: string; available: boolean; reason: string }[] {
      return (this.currentSource?.targets ?? []).map((item) => ({
        target: item.target,
        available: item.available,
        reason: item.reason,
      }))
    },
    selectedCount(state): number {
      return state.selection.count
    },
    busy(state): boolean {
      return state.state.running
    },
    failures(state): TaskResult[] {
      return state.state.tasks.filter((task) => !task.status.startsWith('success'))
    },
    summary(state): BatchSummary | null {
      return state.state.summary
    },
    missingCapabilities(state): string[] {
      return state.capabilities?.missing ?? []
    },
    capabilityPending(state): boolean {
      return Boolean(state.capabilities?.pending) || state.state.capability_pending
    },
    safeMode(state): boolean {
      return state.state.safe_mode || Boolean(state.capabilities?.safe_mode)
    },
    lastOutputs(state): string[] {
      const task = [...state.state.tasks].reverse().find((item) => item.outputs.length)
      return task?.outputs ?? []
    },
  },

  actions: {
    notify(text: string, kind: 'info' | 'error' | 'success' = 'info') {
      this.message = text
      this.messageKind = kind
    },

    async init() {
      this.desktop = await waitForBridge()
      if (!this.desktop) {
        this.ready = true
        this.notify(desktopUnavailable, 'info')
        return
      }
      this.catalog = await api.getCatalog()
      this.capabilities = await api.getCapabilities()
      this.presets = loadPresets()
      await this.refresh()
      this.applyDefaults()
      this.ready = true
      this.watchCapabilities()
      window.setInterval(async () => {
        if (this.state.running) await this.refresh()
      }, 600)
    },

    /** 启动阶段后端先返回轻量能力结果，这里轮询直到完整检测完成。 */
    watchCapabilities() {
      if (!isDesktop()) return
      window.clearInterval(this.capabilityTimer)
      if (!this.capabilityPending) return
      this.capabilityTimer = window.setInterval(async () => {
        try {
          this.capabilities = await api.getCapabilities()
        } catch {
          /* 轮询失败无所谓，下次再试 */
        }
        if (!this.capabilityPending) window.clearInterval(this.capabilityTimer)
      }, 800)
    },

    async recheckCapabilities() {
      if (!this.ensureDesktop()) return
      try {
        this.notify('正在重新检测系统能力…')
        this.capabilities = await api.recheckCapabilities()
        this.catalog = await api.getCatalog()
        this.notify('系统能力已更新', 'success')
        this.watchCapabilities()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    applyDefaults() {
      const entry = this.catalog.find((item) => item.source === this.sourceFormat)
      if (entry) this.targetFormat = entry.default_target
    },

    async refresh() {
      if (!isDesktop()) return
      try {
        this.state = await api.getState()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async onSourceChange(format: string) {
      this.sourceFormat = format
      const entry = this.catalog.find((item) => item.source === format)
      const available = entry?.targets.find((item) => item.available)
      this.targetFormat = entry?.default_target || available?.target || ''
    },

    async pickFiles() {
      if (!this.ensureDesktop()) return
      try {
        this.selection = await api.selectFiles()
        this.applySelectionNotes()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async pickFolder() {
      if (!this.ensureDesktop()) return
      try {
        this.selection = await api.selectFolder()
        this.applySelectionNotes()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async pickOutput() {
      if (!this.ensureDesktop()) return
      try {
        const result = await api.selectOutputDirectory()
        if (result.directory) {
          await api.saveSettings({ output_directory: result.directory })
          await this.refresh()
        }
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async drop(paths: string[]) {
      if (!this.ensureDesktop()) return
      try {
        this.selection = await api.setSelection({ files: paths })
        this.applySelectionNotes()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    applySelectionNotes() {
      if (this.selection.notes.length) {
        this.notify(this.selection.notes.join('；'), 'info')
      } else if (this.selection.count) {
        this.notify(`已选择 ${this.selection.count} 个文件`, 'success')
      }
    },

    applySelection(payload: SelectionPayload) {
      this.selection = payload
      this.applySelectionNotes()
    },

    async start() {
      if (!this.ensureDesktop()) return
      if (!this.selection.count) {
        this.notify('请先选择要转换的文件或目录', 'error')
        return
      }
      if (!this.targetFormat) {
        this.notify('请选择目标格式', 'error')
        return
      }
      const payload: StartPayload = {
        target: this.targetFormat,
        output_directory: this.state.output_directory,
        keep_structure: this.state.keep_structure,
        conflict_policy: this.state.conflict_policy,
        workers: this.state.max_workers,
      }
      try {
        const result = await api.startConversion(payload)
        this.notify(result.message, result.ok ? 'success' : 'error')
        this.rememberPreset()
        await this.refresh()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    /** 记录"最近使用"的设置（只存格式组合，存在浏览器本地，不含文件内容）。 */
    rememberPreset() {
      if (!this.sourceFormat || !this.targetFormat) return
      const key = `${this.sourceFormat}->${this.targetFormat}`
      const rest = this.presets.filter((item) => `${item.source}->${item.target}` !== key)
      this.presets = [
        { source: this.sourceFormat, target: this.targetFormat, at: Date.now() },
        ...rest,
      ].slice(0, PRESET_LIMIT)
      try {
        window.localStorage.setItem(PRESET_KEY, JSON.stringify(this.presets))
      } catch {
        /* 隐私模式等场景下写不了，忽略即可 */
      }
    },

    applyPreset(preset: RecentPreset) {
      void this.onSourceChange(preset.source)
      this.targetFormat = preset.target
    },

    // ------------------------------------------------------------------ PDF 工具
    async pickMergeFiles() {
      if (!this.ensureDesktop()) return
      const payload = await api.selectFiles()
      this.mergeFiles = payload.files.filter((path) => path.toLowerCase().endsWith('.pdf'))
      this.notify(
        this.mergeFiles.length ? `已选择 ${this.mergeFiles.length} 个 PDF` : '没有选择到 PDF 文件',
        this.mergeFiles.length ? 'success' : 'error',
      )
    },

    async pickSplitInput() {
      if (!this.ensureDesktop()) return
      const payload = await api.selectFiles()
      const pdf = payload.files.find((path) => path.toLowerCase().endsWith('.pdf'))
      if (!pdf) {
        this.notify('请选择一个 PDF 文件', 'error')
        return
      }
      this.splitInput = pdf
      this.notify(`已选择 ${pdf.split(/[\\/]/).pop()}`, 'success')
    },

    async mergePdfs() {
      if (!this.ensureDesktop()) return
      if (this.mergeFiles.length < 2) {
        this.notify('请至少选择两个 PDF 文件', 'error')
        return
      }
      this.pdfBusy = true
      try {
        const result: PdfTaskPayload = await api.mergePdfs({
          inputs: this.mergeFiles,
          output: undefined,
        })
        this.notify(result.message, result.ok ? 'success' : 'error')
        if (result.ok) this.mergeFiles = []
      } catch (error) {
        this.notify(String(error), 'error')
      } finally {
        this.pdfBusy = false
      }
    },

    async splitPdf(pages: string) {
      if (!this.ensureDesktop()) return
      if (!this.splitInput) {
        this.notify('请先选择要拆分的 PDF', 'error')
        return
      }
      this.pdfBusy = true
      try {
        const result: PdfTaskPayload = await api.splitPdf({
          input: this.splitInput,
          pages: pages || undefined,
          output_directory: this.state.output_directory,
          conflict_policy: this.state.conflict_policy,
        })
        this.notify(result.message, result.ok ? 'success' : 'error')
      } catch (error) {
        this.notify(String(error), 'error')
      } finally {
        this.pdfBusy = false
      }
    },

    async cancel() {
      if (!this.ensureDesktop()) return
      try {
        const result = await api.cancelConversion()
        this.notify(result.message, result.ok ? 'info' : 'error')
        await this.refresh()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async saveSettings(patch: Record<string, unknown>) {
      if (!this.ensureDesktop()) return
      try {
        const result = await api.saveSettings(patch)
        this.notify(result.message, result.ok ? 'success' : 'error')
        await this.refresh()
      } catch (error) {
        this.notify(String(error), 'error')
      }
    },

    async openPath(path: string) {
      if (!this.ensureDesktop()) return
      const result = await api.openPath(path)
      if (!result.ok) this.notify(result.message, 'error')
    },

    async revealOutput() {
      if (!this.ensureDesktop()) return
      const result = await api.revealOutput()
      if (!result.ok) this.notify(result.message, 'error')
    },

    async refreshLogs() {
      if (!this.ensureDesktop()) return
      this.state.log_tail = await api.getLogs(300)
    },

    ensureDesktop(): boolean {
      if (this.desktop) return true
      this.notify(desktopUnavailable, 'error')
      return false
    },
  },
})
