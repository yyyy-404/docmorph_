import { defineStore } from 'pinia'

import { api, desktopUnavailable, isDesktop, waitForBridge } from '@/api'
import type {
  AppState,
  BatchSummary,
  CapabilityPayload,
  SelectionPayload,
  SourceEntry,
  StartPayload,
  TaskResult,
} from '@/types'

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
      await this.refresh()
      this.applyDefaults()
      this.ready = true
      window.setInterval(async () => {
        if (this.state.running) await this.refresh()
      }, 600)
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
        await this.refresh()
      } catch (error) {
        this.notify(String(error), 'error')
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
