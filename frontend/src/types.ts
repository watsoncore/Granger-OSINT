export type Route = 'chat' | 'search' | 'history' | 'canvas' | 'settings'
export interface Source {
  evidence_id: string
  title: string
  url: string
  domain?: string
  excerpt?: string
  status: string
  kind: 'page' | 'snippet' | 'adapter' | 'api' | 'image' | 'map' | 'archive' | 'repository' | 'document' | 'tool_result'
  obtained_at?: string
  limitations?: string[] | string
  details?: Record<string, unknown>
  related_evidence_ids?: string[]
  message_ids?: string[]
  relevance?: { level: string; score: number; reason: string; via_evidence_ids?: string[] }
  duplicate_count?: number
}
export type GraphMode = 'overview' | 'tree' | 'graph' | 'evidence' | 'geo'
export type Verification = 'verified' | 'source_reported' | 'inferred' | 'unverified' | 'contradicted'
export interface GraphPoint { x:number; y:number; pinned?:boolean }
export interface GraphViewport { x:number; y:number; scale:number }
export interface GraphEntity {
  id:string; type:string; label:string; attributes:Record<string,unknown>; evidence_ids:string[]; source?:string[]
  verification_status?:Verification; relevance?: {level:string;score:number;reason?:string}
}
export interface GraphRelation {
  id:string; from_id:string; to_id:string; relation_type:string; direction:string; evidence_ids:string[]
  verification_status:Verification; source_urls?:string[]; attributes?:Record<string,unknown>; claim_kind?:string
  provenance?:{subject:string;predicate:string;object:string;source_url:string;source_record_id?:string|null;observed_text_or_field:string;observed_field?:string;extraction_method:string;verification_status:Verification;observed_at?:string|null}[]
  aggregate?: { count:number; amount:string|null; asset:string;asset_label?:string; asset_key?:string;contract?:string|null;first_seen?:string|null;last_seen?:string|null;known_amount_count:number; unknown_amount_count:number; transaction_ids:string[]; coverage?:string; owner_verified:false }
}
export interface GraphView {
  version:1; mode?:GraphMode; positions?:Record<string,GraphPoint>; tree_positions?:Record<string,GraphPoint>
  layout_algorithm?:'semantic_cards';inspector_width?:number;inspector_hidden?:boolean
  viewport?:GraphViewport; tree_viewport?:GraphViewport; selected_id?:string; selected_relation?:string
  expanded?:string[]; expanded_relations?:string[]; collapsed?:string[]; query?:string
  filters?: {types?:string[];statuses?:Verification[];include_background?:boolean;show_sources?:boolean;show_transactions?:boolean}
}
export interface GraphFinding { evidence_id:string; title:string; description:string; url:string; status:string; relevance?:Source['relevance'] }
export interface InvestigationGraph {
  state:'idle'|'loading'|'ready'|'empty'|'locked'|'cancelled'|'error'; investigation_id?:string; goal?:string; status?:string
  revision?:string|number; root_id?:string; entities?:GraphEntity[]; relations?:GraphRelation[]; evidence?:Source[]
  warnings?:string[]; view?:GraphView; error?:string; synthetic?:boolean; total_entities?:number; total_relations?:number
  truncated_input?:boolean; relations_truncated?:boolean
  refreshing?:boolean;generation?:number
  has_geoint?:boolean
  steam_inventories?:SteamInventorySummary[]
  counts?:Record<string,number|null>
  summary?:{findings:GraphFinding[];hypotheses:GraphFinding[];background_count:number;limitations:string[];failed_sources:{tool:string;status:string;error?:string}[];report?:string;stop_reason?:string}
}
export interface SteamInventorySummary {
  steamid64:string;appid:number;contextid:string;observed_assets:number;observed_units:number;reported_total:number|null
  coverage_status:string;coverage_reason:string;categories:Record<string,number>;next_cursor?:string|null
  valuation:{currency:string;priced_assets:number;unpriced_assets:number;observed_subtotal_decimal:string|null;method:string;quote_first_observed_at?:string|null;quote_last_observed_at?:string|null}
}
export interface Message {
  id: string
  role: 'user' | 'model' | 'status'
  text: string
  streaming?: boolean
  sources?: Source[]
  attachments?: ImageAttachment[]
  investigation_id?:string
}
export interface GeoRegion { description:string; region:number[]; confidence_kind?:string }
export interface GeoComparison {
  status?:string; match_count?:number; input_sizes?:number[][]; spatial_coverage?:(number|null)[]; support_kind?:string
  matches?:{point0:number[];point1:number[];raw_score?:number}[]
  geometry?:{inliers?:number;inlier_indices?:number[]}; geolocation_verified?:boolean; interpretation?:string
}
export interface GeoCandidate {
  candidate_id:string; attachment_id?:string; latitude:number; longitude:number; region?:string; source_model?:string
  verification_status:string; evidence_id?:string; raw_score?:number|null
  model_observations?:{latitude:number;longitude:number;model_lat_std?:number|null;model_lon_std?:number|null;dateline_warning?:boolean}[]
  nearby_landmarks?:{name:string;url?:string;latitude:number;longitude:number}[]
}
export interface GeoImage {
  evidence_id:string; candidate_id?:string; attachment_id?:string; title:string; provider?:string; source_url:string; image_url?:string; original_image_url?:string
  license?:string; license_url?:string; author?:string; captured_at?:string; latitude?:number; longitude?:number; match_kind?:string
  comparison?:GeoComparison; reference_scene?:{description?:string;observations?:GeoRegion[]}
  media?:{state:string;thumbnail?:string;width?:number;height?:number;mime?:string;bytes?:number;fetched_at?:string;sha256?:string}
}
export interface GeoView {
  state:string; investigation_id?:string; revision?:number; has_geoint?:boolean; error?:string
  originals?:{attachment_id:string;thumbnail?:string;state:string}[]
  scenes?:{evidence_id:string;attachment_id:string;description:string;observations?:GeoRegion[]}[]
  candidates?:GeoCandidate[];images?:GeoImage[];limitations?:string[]
  diagnostics?:{stages?:{stage:string;status:string;error_code?:string}[];limitations?:string[]}[]
}
export interface ImageAttachment { id: string; name: string; mime: string; format: string; bytes: number; width: number; height: number; sha256: string; preview?: string }
export interface Activity {
  id: string
  tool: string
  status: string
  summary: string
  evidenceIds?: string[]
  inputType?: string
  resultCount?: number
  error?: string
  details?: Record<string, unknown>
}
export interface Tool {
  manifest?: { access_mode?: string; execution_mode?: string; input_schema?: InputSchema | null; capabilities?: string[]; accepted_inputs?: string[]; [key: string]: unknown }
  implemented?: boolean
  readiness_status?: string
  documentation_url?: string
  manual_url?: string
  id: string
  name: string
  description: string
  inputTypes: string[]
  available: boolean
  state: string
  reason?: string
  sensitive?: boolean
  displayName?: string
  stateLabel?: string
  remedy?: string
  settingsCategory?: string
  lastChecked?: string
  diagnostic?: { code?: string; remedy?: string; runtime_ready?: boolean; checked_at?: string; probe_seconds?: number; execution_verified?: boolean }
  last_execution?: { status: string; obtained_at?: string; error_code?: string; result_count?: number }
}
export interface InputSchema {
  type?: string
  description?: string
  properties?: Record<string, InputSchema>
  required?: string[]
  enum?: (string | number | boolean)[]
  items?: InputSchema
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
  minItems?: number
  maxItems?: number
  additionalProperties?: boolean
}
export interface ProviderBalance {
  status: string
  value?: number | string | null
  amount?: number | string | null
  label?: string
  unit?: string | null
  field?: string
  updated_at?: string
  error?: string
  message?: string
  stale?: boolean
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
  geo_views?:Record<string,GeoView>
  map_tiles?:Record<string,{key:string;state:string;image?:string;error_code?:string}>
  errors?: { id: string; message: string; code: string; count: number }[]
  investigation_graph?:InvestigationGraph
  investigation_choices?:{id:string;title:string;status:string;updated_at?:string}[]
  visual_models?: {
    state: string; installed: boolean; available: boolean; download_bytes?: number | null; disk_recommended_bytes?: number | null
    ram_recommended_bytes?: number | null; device?: string; components?: unknown; error?: string; probe?: unknown
    automatic_download: false; progress?: { downloaded_bytes?: number; total_bytes?: number | null; bytes_downloaded?: number; bytes_total?: number | null; [key: string]: unknown } | number | null
    installing?: boolean
  }
  tool_counts?: { candidates:number;implemented:number;ready_local:number;verified_execution:number }
  attachments?: ImageAttachment[]
  attachment_busy?: boolean
  attachment_error?: string
  product: string
  version: string
  surface: 'main' | 'launcher'
  route: Route
  conversation_id?: string
  message_focus?: string | null
  archiveError?: string
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
    testing?: boolean
    models?: { id: string; label?: string }[]
    modelsChecking?: boolean
    modelsError?: string
  }
  messages: Message[]
  busy: boolean
  activity: Activity[]
  evidence: Source[]
  task_sources?: Source[]
  history: HistoryItem[]
  search: {
    investigation_id?:string
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
  browser?: {status?:string;url?:string;title?:string;image?:string;snapshot_id?:string;error_code?:string;actions?:{action:string;target:string;at:string;status:string}[]}
  toolsChecking?: boolean
  settingsCategory?: 'ai' | 'tools' | 'investigation' | 'interface' | 'hermione' | 'notifications' | 'privacy'
  credentials?: Record<string, boolean>
  vault?: { enabled: boolean; unlocked: boolean; migration_complete?: boolean; error?: string }
  investigation: {
    id?: string
    goal?: string
    status?: string
    stop_reason?: string
    canResume?: boolean
    remaining_tasks?: string[]
    [key: string]: unknown
  }
  usage: { request?: Usage | null; conversation?: Usage | null; investigation?: Usage | null; balance?: ProviderBalance | null; provider_balance?: ProviderBalance | null }
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
  window: { maximized: boolean; fullscreen: boolean; active?: boolean }
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
  const object = (row: unknown): row is Record<string, unknown> => !!row && typeof row === 'object' && !Array.isArray(row)
  // The bridge is a data boundary, including historical state loaded by Python.
  // Reject corrupt rows before React components dereference their properties.
  for (const key of ['connection', 'search', 'canvas', 'launcher', 'hermione', 'window', 'settings', 'investigation', 'usage', 'investigation_graph'] as const) {
    if (value[key] !== undefined && value[key] !== null && !object(value[key])) throw new Error(`Некорректный объект: ${key}`)
  }
  for (const key of ['messages', 'activity', 'history', 'evidence', 'task_sources', 'tools', 'errors', 'investigation_choices'] as const) {
    const rows = value[key]
    if (rows !== undefined && (!Array.isArray(rows) || rows.some(row => !object(row)))) throw new Error(`Некорректные записи: ${key}`)
  }
  for (const row of value.messages || []) {
    if (typeof row.id !== 'string' || typeof row.text !== 'string' || !['user', 'model', 'status'].includes(row.role)) throw new Error('Некорректное сообщение')
  }
  for (const row of [...value.evidence || [], ...value.task_sources || []]) {
    if (typeof row.evidence_id !== 'string' || typeof row.title !== 'string' || typeof row.url !== 'string' || (row.details !== undefined && !object(row.details))) throw new Error('Некорректное доказательство')
  }
  const graph=value.investigation_graph
  if(graph){
    if(!['idle','loading','ready','empty','locked','cancelled','error'].includes(graph.state))throw new Error('Некорректное состояние графа')
    if(graph.state==='ready'){
      if(typeof graph.investigation_id!=='string'||!Array.isArray(graph.entities)||!Array.isArray(graph.relations)||!Array.isArray(graph.evidence))throw new Error('Некорректный граф')
      for(const node of graph.entities)if(!object(node)||typeof node.id!=='string'||typeof node.label!=='string'||typeof node.type!=='string'||!object(node.attributes)||!Array.isArray(node.evidence_ids)||node.evidence_ids.some(id=>typeof id!=='string'))throw new Error('Некорректный узел графа')
      const ids=new Set(graph.entities.map(node=>node.id))
      for(const edge of graph.relations)if(!object(edge)||typeof edge.id!=='string'||!ids.has(edge.from_id)||!ids.has(edge.to_id)||!Array.isArray(edge.evidence_ids)||!['verified','source_reported','inferred','unverified','contradicted'].includes(edge.verification_status))throw new Error('Некорректная связь графа')
      for(const edge of graph.relations)if(edge.aggregate&&(!object(edge.aggregate)||!Array.isArray(edge.aggregate.transaction_ids)||edge.aggregate.transaction_ids.some(id=>typeof id!=='string')||typeof edge.aggregate.count!=='number'||typeof edge.aggregate.asset!=='string'))throw new Error('Некорректная агрегация графа')
      for(const row of graph.evidence)if(!object(row)||typeof row.evidence_id!=='string'||typeof row.title!=='string'||typeof row.url!=='string')throw new Error('Некорректное доказательство графа')
      if(graph.summary){
        if(!object(graph.summary))throw new Error('Некорректный обзор графа')
        for(const key of ['findings','hypotheses','limitations','failed_sources'] as const)if(!Array.isArray(graph.summary[key]))throw new Error('Некорректные записи обзора графа')
        for(const row of [...graph.summary.findings,...graph.summary.hypotheses])if(!object(row)||typeof row.evidence_id!=='string'||typeof row.title!=='string'||typeof row.description!=='string')throw new Error('Некорректная находка графа')
      }
      if(graph.view&&(!object(graph.view)||graph.view.version!==1))throw new Error('Некорректное состояние представления графа')
    }
  }
  const patch = value as Partial<DesktopState> & { message_updates?: { index: number; message: Message }[]; message_count?: number }
  let messages = Array.isArray(value.messages) ? value.messages : previous.messages
  if (Array.isArray(patch.message_updates)) {
    messages = [...messages]
    for (const update of patch.message_updates) {
      if (!object(update) || !object(update.message) || typeof update.message.id !== 'string' || typeof update.message.text !== 'string') throw new Error('Некорректное обновление сообщения')
      if (Number.isInteger(update.index) && update.index >= 0 && update.index <= messages.length && update.message.id) messages[update.index] = update.message
    }
  }
  if (Number.isInteger(patch.message_count) && patch.message_count! >= 0 && patch.message_count! < messages.length) messages = messages.slice(0, patch.message_count)
  return {
    ...previous, ...value,
    connection: value.connection ? { ...previous.connection, ...value.connection } : previous.connection,
    search: value.search ? { ...previous.search, ...value.search } : previous.search,
    canvas: value.canvas ? { ...previous.canvas, ...value.canvas } : previous.canvas,
    launcher: value.launcher ? { ...previous.launcher, ...value.launcher } : previous.launcher,
    hermione: value.hermione ? { ...previous.hermione, ...value.hermione } : previous.hermione,
    window: value.window ? { ...previous.window, ...value.window } : previous.window, messages,
    activity: Array.isArray(value.activity) ? value.activity : previous.activity,
    history: Array.isArray(value.history) ? value.history : previous.history,
    evidence: Array.isArray(value.evidence) ? value.evidence : previous.evidence,
    tools: Array.isArray(value.tools) ? value.tools : previous.tools,
  }
}
