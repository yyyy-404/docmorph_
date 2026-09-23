/**
 * 与 Python 后端的通信层。
 *
 * 桌面壳（pywebview）会把 `docmorph.ui.bridge.Api` 暴露成 `window.pywebview.api`；
 * 在浏览器里开发（`npm run dev`）时退化为可交互的模拟实现，便于纯前端调试。
 */

import type {
  AppState,
  CapabilityPayload,
  OperationResult,
  SelectionPayload,
  SourceEntry,
  StartPayload,
} from './types'

export interface PywebviewApi {
  get_state(): Promise<AppState>
  get_catalog(): Promise<SourceEntry[]>
  get_capabilities(): Promise<CapabilityPayload>
  get_logs(limit?: number): Promise<string[]>
  select_files(): Promise<SelectionPayload>
  select_folder(): Promise<SelectionPayload>
  select_output_directory(): Promise<SelectionPayload>
  set_selection(payload: { files?: string[]; directory?: string }): Promise<SelectionPayload>
  start_conversion(payload: StartPayload): Promise<OperationResult>
  cancel_conversion(): Promise<OperationResult>
  save_settings(payload: Record<string, unknown>): Promise<OperationResult>
  open_path(path: string): Promise<OperationResult>
  reveal_output(): Promise<OperationResult>
  quit(): Promise<OperationResult>
}

type ApiBridge = Partial<PywebviewApi>

interface PywebviewWindow {
  pywebview?: { api?: ApiBridge }
}

const BRIDGE_MISSING =
  '当前不是桌面窗口环境（浏览器预览模式）。请在桌面应用中执行该操作。'

function bridge(): ApiBridge | null {
  const host = window as unknown as PywebviewWindow
  const api = host.pywebview?.api
  return api && typeof api.get_state === 'function' ? api : null
}

export function isDesktop(): boolean {
  return bridge() !== null
}

async function call<K extends keyof PywebviewApi>(
  name: K,
  ...args: unknown[]
): Promise<ReturnType<PywebviewApi[K]> extends Promise<infer R> ? R : never> {
  const api = bridge()
  if (!api || typeof api[name] !== 'function') {
    throw new Error(BRIDGE_MISSING)
  }
  const fn = api[name] as unknown as (...inner: unknown[]) => Promise<unknown>
  return (await fn(...args)) as never
}

/** pywebview 注入的 API 不会同步就绪，启动时轮询等待。 */
export async function waitForBridge(timeoutMs = 8000): Promise<boolean> {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    if (bridge()) return true
    await new Promise((resolve) => setTimeout(resolve, 120))
  }
  return bridge() !== null
}

export const api = {
  getState: () => call('get_state'),
  getCatalog: () => call('get_catalog'),
  getCapabilities: () => call('get_capabilities'),
  getLogs: (limit = 300) => call('get_logs', limit),
  selectFiles: () => call('select_files'),
  selectFolder: () => call('select_folder'),
  selectOutputDirectory: () => call('select_output_directory'),
  setSelection: (payload: { files?: string[]; directory?: string }) =>
    call('set_selection', payload),
  startConversion: (payload: StartPayload) => call('start_conversion', payload),
  cancelConversion: () => call('cancel_conversion'),
  saveSettings: (payload: Record<string, unknown>) => call('save_settings', payload),
  openPath: (path: string) => call('open_path', path),
  revealOutput: () => call('reveal_output'),
  quit: () => call('quit'),
}

export const desktopUnavailable = BRIDGE_MISSING
