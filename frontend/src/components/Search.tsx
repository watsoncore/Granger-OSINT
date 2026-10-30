import { useEffect, useState } from 'react'
import { ArrowUpRight, Copy, LoaderCircle, Search as SearchIcon, Square } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState, Source } from '../types'
import { Button, IconButton } from './ui'
import { ToolCatalog } from './ToolCatalog'
import { inputLabel, toolName } from '../tool-presentation'
import { SourceCard } from './Sources'
import { ActivityBlock } from './Chat'
import { StructuredToolFields, parseToolArguments } from './StructuredToolFields'
import { InvestigationWorkspace } from './InvestigationWorkspace'

const searchPhases: Record<string, string> = {
  queued: 'Подготовка поиска', preparing: 'Подготовка поиска', starting: 'Запуск инструмента',
  running: 'Выполняется поиск', working: 'Инструмент выполняется', searching: 'Поиск по открытым источникам',
  checking: 'Проверка источников', fetching: 'Получение результатов', reading: 'Чтение источников',
  processing: 'Обработка результатов', completed: 'Поиск завершён', completed_with_errors: 'Поиск завершён с ошибками',
  failed: 'Поиск не завершён', error: 'Ошибка поиска', cancelled: 'Поиск остановлен', stopped: 'Поиск остановлен',
}

export function resultSource(result: Record<string, unknown>): Source {
  const provenance = (result.provenance || {}) as Record<string, unknown>
  const detail = (result.details || {}) as Record<string, unknown>
  return {
    evidence_id: typeof result.evidence_id === 'string' ? result.evidence_id : '',
    title: String(result.title || result.platform || result.name || result.url || 'Результат инструмента'),
    url: String(result.url || ''), excerpt: String(result.excerpt || result.description || ''),
    status: String(result.status || 'unconfirmed'), domain: typeof result.domain === 'string' ? result.domain : undefined,
    kind: result.type === 'image_analysis' ? 'image' : result.type === 'evidence_graph' || result.type === 'local_computation' ? 'tool_result' : result.kind === 'api' ? 'api' : provenance.acquisition === 'search_index' || result.kind === 'snippet' ? 'snippet' : provenance.acquisition === 'direct_page' || result.kind === 'page' ? 'page' : 'adapter',
    obtained_at: typeof result.obtained_at === 'string' ? result.obtained_at : typeof provenance.obtained_at === 'string' ? provenance.obtained_at : typeof result.checked_at === 'string' ? result.checked_at : undefined,
    details: detail, limitations: Array.isArray(result.limitations) ? result.limitations.map(String) : undefined,
  }
}
export function SearchWorkspace({ state, query, setQuery, onSource }: { state: DesktopState; query: string; setQuery(value: string): void; onSource(source: Source): void }) {
  const [kind, setKind] = useState('')
  const [tool, setTool] = useState('')
  const [publicSearchStatus, setPublicSearchStatus] = useState('')
  const [argumentsDraft, setArgumentsDraft] = useState<Record<string, string>>({})
  const [argumentError, setArgumentError] = useState('')
  useEffect(() => { setArgumentsDraft({}); setArgumentError('') }, [tool])
  const openAvito = async () => {
    const result = await act('public_search_open', { source: 'avito', query: query.trim() })
    if (result && typeof result === 'object' && 'opened' in result) setPublicSearchStatus(result.opened ? 'Поиск Avito открыт в вашем браузере. Приложение не получало и не анализировало результаты этой страницы.' : 'Браузер не подтвердил открытие поиска Avito.')
  }
  const selected = state.tools.find(item => item.id === tool)
  const schema = selected?.manifest?.input_schema
  const isStructured = schema?.type === 'object'
  const isBusy = state.search.busy || state.busy
  const status = state.search.status?.trim()
  const progressLabel = state.busy ? (state.activity.findLast(item => item.status === 'running')?.tool || 'Гермиона сопоставляет сведения') : searchPhases[state.search.phase] || 'Инструмент выполняется'
  const checkedLabel = state.search.checkedLabel?.trim() || (state.search.checked > 0 ? `Проверено: ${state.search.checked}` : '')
  const run = () => {
    if (isBusy) return
    if (isStructured && schema) {
      try {
        const args = parseToolArguments(schema, argumentsDraft)
        setArgumentError('')
        void act('tool_run', { tool, arguments: args })
      } catch (error) { setArgumentError(error instanceof Error ? error.message : 'Проверьте параметры инструмента.') }
    } else if (query.trim()) void act(tool ? 'tool_run' : 'search_run', tool ? { tool, query: query.trim() } : { query: query.trim(), kind: kind || state.search.kind || undefined })
  }
  const results = state.search.results.map(resultSource)
  const hasInvestigation=!!(state.search.investigation_id||state.investigation.id)
  const sourceIds = results.map(item => item.evidence_id).filter(Boolean).slice(0, 20)
  return <div className="workspace-scroll"><div className="page-content search-workspace"><div className="page-heading"><span className="eyebrow">ОТКРЫТЫЕ ИСТОЧНИКИ</span><h1>Поиск и инструменты</h1><p>Проверяйте сведения и передавайте реальные находки Гермионе.</p></div><form className="search-form" onSubmit={event => { event.preventDefault(); run() }}>{!isStructured && <><label htmlFor="osint-query">Что исследуем?</label><div className="query-input"><SearchIcon size={18}/><input id="osint-query" value={query} onChange={event => setQuery(event.target.value)} placeholder="Никнейм, домен, адрес или поисковый запрос" disabled={isBusy}/></div></>}<div className="search-controls"><select aria-label="Инструмент поиска" value={tool} onChange={event => setTool(event.target.value)} disabled={isBusy}><option value="">Автоматический поиск</option>{state.tools.filter(item => item.implemented !== false).map(item => <option value={item.id} disabled={!item.available} key={item.id}>{toolName(item.id, item.displayName || (item.name !== item.id ? item.name : undefined))}{!item.available ? ' · недоступен' : ''}</option>)}</select>{!tool && !!state.search.choices.length && <select aria-label="Тип запроса" value={kind || state.search.kind || ''} onChange={event => setKind(event.target.value)} disabled={isBusy}>{state.search.choices.map(choice => <option value={choice.value} key={choice.value}>{choice.label}</option>)}</select>}{isBusy ? <Button type="button" variant="danger" onClick={() => void act(state.busy ? 'chat_stop' : 'search_stop')}><Square size={13}/>Остановить</Button> : <Button type="submit" disabled={isStructured ? !selected?.available : !query.trim()}><SearchIcon size={15}/>Найти</Button>}</div>{isStructured && schema && <StructuredToolFields schema={schema} draft={argumentsDraft} disabled={isBusy} onChange={(name, value) => { setArgumentsDraft(current => ({ ...current, [name]: value })); setArgumentError('') }}/>} {argumentError && <p className="notice-inline notice-error" role="alert">{argumentError}</p>}{selected && <p className="field-hint">{selected.description} {selected.inputTypes?.length ? `Входные данные: ${selected.inputTypes.map(inputLabel).join(', ')}.` : ''}</p>}</form>{state.search.error && <div className="notice-inline notice-error" role="alert">{state.search.error}</div>}{!state.search.error && status && <div className="notice-inline" role="status">{status}</div>}{isBusy ? <div className="search-progress" role="status"><LoaderCircle size={16} className="spin"/><span>{progressLabel}{checkedLabel && <small>{checkedLabel}</small>}</span></div> : checkedLabel && <p className="field-hint">{checkedLabel}</p>}<InvestigationWorkspace state={state} onSource={onSource}/>{!hasInvestigation && results.length > 0 ? <section className="search-results"><div className="section-heading"><h2>Результаты<span className="count">{results.length}</span></h2><div><IconButton label="Копировать результаты" onClick={() => void act('copy', { text: results.map(item => `${item.title}\n${item.url}\n${item.excerpt || ''}`).join('\n\n') })}><Copy size={15}/></IconButton><Button variant="secondary" size="sm" disabled={!sourceIds.length || state.busy || !state.connection.canSend} onClick={() => void act('search_analyze', { evidence_ids: sourceIds })}>Гермионе<ArrowUpRight size={15}/></Button></div></div><div className="result-grid">{results.map((source, index) => <SourceCard source={source} onSelect={onSource} key={source.evidence_id || `${source.url}-${index}`}/>)}</div></section> : !hasInvestigation && !!state.search.query && !isBusy && !state.search.error && !status && <div className="no-results"><SearchIcon size={22}/><strong>По этому запросу результатов нет</strong><p>Попробуйте другой запрос или доступный инструмент.</p></div>}<ActivityBlock activity={state.activity} busy={false}/><ToolCatalog tools={state.tools} checking={state.toolsChecking} selected={tool} busy={isBusy} onSelect={item => { setTool(item.id); if (!item.manifest?.input_schema) document.getElementById('osint-query')?.focus() }} onSettings={() => void act('route', { route: 'settings', category: 'tools' })}/><div className="search-workspace-actions"><Button variant="ghost" size="sm" onClick={() => void act('route', { route: 'settings', category: 'tools' })}>Настройки источников<ArrowUpRight size={13}/></Button><Button variant="ghost" size="sm" disabled={isBusy} onClick={() => void act('search_dorks', { query })}>Операторы Google<ArrowUpRight size={13}/></Button><Button variant="ghost" size="sm" disabled={!query.trim() || isBusy} onClick={() => void openAvito()}>Искать на Avito<ArrowUpRight size={13}/></Button></div>{publicSearchStatus && <p className="notice-inline" role="status">{publicSearchStatus}</p>}</div></div>
}
