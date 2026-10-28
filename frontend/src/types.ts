export type Route = 'chat' | 'search' | 'history' | 'canvas' | 'settings'
export interface Source {
  evidence_id: string
  title: string
  url: string
  domain?: string
  excerpt?: string
  status: string
  kind: 'page' | 'snippet' | 'adapter'
  obtained_at?: string
  limitations?: string[] | string
  details?: Record<string, unknown>
}
export interface Message {
  id: string
  role: 'user' | 'model' | 'status'
  text: string
  streaming?: boolean
  sources?: Source[]
}
export interface Activity {
  id: string
  tool: string
  status: string
  summary: string
  evidenceIds?: string[]
}
export interface Tool {
  id: string
  name: string
  description: string
  inputTypes: string[]
  available: boolean
  state: string
  reason?: string
  sensitive?: boolean
}
export interface Usage {
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  [key: string]: unknown
}
export interface HistoryItem {
  id: string
  title: string
  updated_at?: string
  message_count?: number
  current?: boolean
  status?: string
}
export interface DesktopState {
  product: string
  version: string
  surface: 'main' | 'launcher'
  route: Route
  conversation_id?: string
  message_focus?: string | null
  connection: {
    provider: string
    model: string
    status: string
    statusText?: string
    canSend: boolean
    error?: string
    contextLimit?: number | null
    balance?: number | string | null
    balanceMessage?: string
  }
  messages: Message[]
  busy: boolean
  activity: Activity[]
  evidence: Source[]
  history: HistoryItem[]
  search: {
    query: string
    kind: string
    busy: boolean
    phase: string
    count: number
    checked: number
    checkedLabel?: string
    status?: string
    error?: string
    choices: { label: string; value: string }[]
    results: Record<string, unknown>[]
  }
  tools: Tool[]
  investigation: {
    id?: string
    goal?: string
    status?: string
    stop_reason?: string
    canResume?: boolean
    remaining_tasks?: string[]
    [key: string]: unknown
  }
  usage: { request?: Usage | null; conversation?: Usage | null; investigation?: Usage | null }
  settings: Record<string, string | number | boolean | null>
  canvas: { id: string; text: string; title: string; dirty: boolean }
  launcher: {
    state: 'ready' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error'
    running: boolean
    size: number
    fps: number
    cursorReaction: boolean
    error?: string
  }
  hermione: { state: string; visible: boolean; [key: string]: unknown }
  window: { maximized: boolean; fullscreen: boolean }
}

export const emptyState: DesktopState = {
  product: 'Granger-OSINT', version: '', surface: 'main', route: 'chat',
  connection: { provider: '', model: '', status: 'Подключение к приложению', canSend: false, contextLimit: null, balance: null },
  messages: [], busy: false, activity: [], evidence: [], history: [],
  search: { query: '', kind: '', busy: false, phase: '', count: 0, checked: 0, choices: [], results: [] },
  tools: [], investigation: {}, usage: {}, settings: {},
  canvas: { id: '', text: '', title: '', dirty: false },
  launcher: { state: 'ready', running: false, size: 195, fps: 24, cursorReaction: true },
  hermione: { state: '', visible: false }, window: { maximized: false, fullscreen: false },
}

// Missing backend fields are unavailable, never invented conversation/tool data.
export function parseState(raw: string | Partial<DesktopState>, previous = emptyState): DesktopState {
  const value = typeof raw === 'string' ? JSON.parse(raw) as Partial<DesktopState> & { patch?: boolean; message_updates?: { index: number; message: Message }[]; message_count?: number } : raw
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Некорректное состояние приложения')
  const patch = value as Partial<DesktopState> & { message_updates?: { index: number; message: Message }[]; message_count?: number }
  let messages = Array.isArray(value.messages) ? value.messages : previous.messages
  if (Array.isArray(patch.message_updates)) {
    messages = [...messages]
    for (const update of patch.message_updates) {
      if (Number.isInteger(update.index) && update.index >= 0 && update.index <= messages.length && update.message?.id) messages[update.index] = update.message
    }
  }
  if (Number.isInteger(patch.message_count) && patch.message_count! >= 0 && patch.message_count! < messages.length) messages = messages.slice(0, patch.message_count)
  return {
    ...previous, ...value,
    connection: { ...previous.connection, ...value.connection },
    search: { ...previous.search, ...value.search },
    canvas: { ...previous.canvas, ...value.canvas },
    launcher: { ...previous.launcher, ...value.launcher },
    hermione: { ...previous.hermione, ...value.hermione },
    window: { ...previous.window, ...value.window }, messages,
    activity: Array.isArray(value.activity) ? value.activity : previous.activity,
    history: Array.isArray(value.history) ? value.history : previous.history,
    evidence: Array.isArray(value.evidence) ? value.evidence : previous.evidence,
    tools: Array.isArray(value.tools) ? value.tools : previous.tools,
  }
}
