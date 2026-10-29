import { useSyncExternalStore } from 'react'
import { emptyState, parseState, type DesktopState } from './types'

interface Signal<T extends unknown[]> { connect(handler: (...args: T) => void): void }
interface NativeDesktop {
  request(id: string, action: string, payloadJson: string): void
  response: Signal<[string, string]>
  stateChanged: Signal<[string]>
}
declare global {
  interface Window {
    qt?: { webChannelTransport: unknown }
    QWebChannel?: new (transport: unknown, callback: (channel: { objects: { desktop: NativeDesktop } }) => void) => unknown
  }
}

export interface ViewState { state: DesktopState; connected: boolean; notice: string }
type Pending = { resolve(value: unknown): void; reject(error: Error): void; timeout?: ReturnType<typeof setTimeout> }
let desktop: NativeDesktop | undefined
let snapshot: ViewState = { state: emptyState, connected: false, notice: '' }
const listeners = new Set<() => void>()
const pending = new Map<string, Pending>()
let nextId = 0
let frame: ReturnType<typeof setTimeout> | undefined
let nextState: DesktopState | undefined

function publish(update: Partial<ViewState>) {
  snapshot = { ...snapshot, ...update }
  listeners.forEach(listener => listener())
}
function receiveState(raw: string) {
  try {
    nextState = parseState(raw, nextState || snapshot.state)
    // Tokens do not recreate the screen; backend snapshots are coalesced to20Hz.
    if (!frame) frame = setTimeout(() => {
      frame = undefined
      if (nextState) publish({ state: nextState, connected: true })
      nextState = undefined
    }, 50)
  } catch { publish({ notice: 'Приложение прислало некорректные данные. Повторите действие.' }) }
}
export function notify(message: string) { publish({ notice: message }) }
export function dismissNotice() { publish({ notice: '' }) }

export function request(action: string, payload: Record<string, unknown> = {}): Promise<unknown> {
  if (!desktop) return Promise.reject(new Error('Нет связи с настольным приложением. Откройте Granger-OSINT.exe.'))
  const id = `ui-${++nextId}`
  return new Promise((resolve, reject) => {
    // Native export/approval dialogs may stay open for as long as the user needs.
    const timeout = ['canvas_export', 'tool_run', 'credentials_edit', 'settings_path', 'vault_manage', 'attachment_choose'].includes(action) ? undefined : setTimeout(() => {
      pending.delete(id); reject(new Error('Приложение не ответило. Повторите действие.'))
    }, 30000)
    pending.set(id, { resolve, reject, timeout })
    try { desktop!.request(id, action, JSON.stringify(payload)) }
    catch { clearTimeout(timeout); pending.delete(id); reject(new Error('Не удалось передать действие приложению.')) }
  })
}

export async function act(action: string, payload: Record<string, unknown> = {}): Promise<unknown> {
  try { return (await request(action, payload)) ?? true }
  catch (error) { notify(error instanceof Error ? error.message : 'Действие не выполнено'); return null }
}

export function connectDesktop() {
  if (desktop) return
  if (!window.qt?.webChannelTransport || !window.QWebChannel) {
    publish({ notice: 'Интерфейс открыт без настольного приложения. Инструменты и чат недоступны.' })
    return
  }
  new window.QWebChannel(window.qt.webChannelTransport, channel => {
    desktop = channel.objects.desktop
    desktop.response.connect((id, raw) => {
      const call = pending.get(id)
      if (!call) return
      clearTimeout(call.timeout); pending.delete(id)
      try {
        const response = JSON.parse(raw) as { ok: boolean; result?: unknown; error?: string }
        if (response.ok) call.resolve(response.result)
        else call.reject(new Error(typeof response.error === 'string' ? response.error : 'Действие не выполнено'))
      } catch { call.reject(new Error('Некорректный ответ приложения')) }
    })
    desktop.stateChanged.connect(receiveState)
    request('snapshot').then(result => receiveState(JSON.stringify(result))).catch(error => notify(error.message))
  })
}

export function useDesktop() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, () => snapshot)
}
