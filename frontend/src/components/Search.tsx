import { useEffect, useId, useState } from 'react'
import { ArrowUpRight, ChevronDown, Copy, LoaderCircle, RotateCcw, Search as SearchIcon, Square } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState, Source } from '../types'
import { Button, IconButton } from './ui'
import { ToolCatalog } from './ToolCatalog'
import { inputLabel, toolName } from '../tool-presentation'
import { SourceCard } from './Sources'
import { ActivityBlock } from './Chat'
import { StructuredToolFields, parseToolArguments } from './StructuredToolFields'
import { InvestigationWorkspace } from './InvestigationWorkspace'
import { ResearchCanvas } from './ResearchCanvas'
import {SearchableSelect} from './SearchableSelect'
import {MaigretFields} from './MaigretFields'
import {GansarFields,useCryptoTarget} from './GansarFields'
import {DensityControl} from './WorkspaceDensity'

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
  const hasInvestigation=!!(state.search.investigation_id||state.investigation.id)
  const hasResearchContext=hasInvestigation||state.search.results.length>0
  const [formExpanded,setFormExpanded]=useState(()=>!hasResearchContext)
  const formId=useId()
  useEffect(()=>{if(hasResearchContext)setFormExpanded(false)},[hasResearchContext,state.search.investigation_id,state.investigation.id])
  const [workspace,setWorkspace]=useState<'results'|'canvas'|'catalog'|'activity'>('results')
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
  const crypto=useCryptoTarget(argumentsDraft.address||'',argumentsDraft.chain||'auto',tool==='blockchain_gansar')
  useEffect(()=>{if(tool==='blockchain_gansar')setArgumentsDraft({operation:'profile',chain:'auto'})},[tool])
  const isBusy = state.search.busy || state.busy
  const status = state.search.status?.trim()
  const progressLabel = state.busy ? (state.activity.findLast(item => item.status === 'running')?.tool || 'Гермиона сопоставляет сведения') : searchPhases[state.search.phase] || 'Инструмент выполняется'
  const checkedLabel = state.search.checkedLabel?.trim() || (state.search.checked > 0 ? `Проверено: ${state.search.checked}` : '')
  const run = (repeat=false) => {
    if (isBusy) return
    if (isStructured && schema) {
      try {
        const args = parseToolArguments(schema, argumentsDraft)
        setArgumentError('')
        void act('tool_run', { tool, arguments: args });if(hasResearchContext)setFormExpanded(false)
      } catch (error) { setArgumentError(error instanceof Error ? error.message : 'Проверьте параметры инструмента.');setFormExpanded(true) }
    } else {const value=query.trim()||(repeat?state.search.query.trim():'');if(value){void act(tool ? 'tool_run' : 'search_run', tool ? { tool, query:value } : { query:value, kind: kind || state.search.kind || undefined });if(hasResearchContext)setFormExpanded(false)}}
  }
  const results = state.search.results.map(resultSource)
  const canRepeat=isStructured?!!selected?.available&&!!Object.values(argumentsDraft).some(value=>!!value.trim()):!!(query.trim()||state.search.query.trim())
  const sourceIds = results.map(item => item.evidence_id).filter(Boolean).slice(0, 20)
  return <div className="workspace-scroll"><div className={`page-content search-workspace ${hasResearchContext?'has-research-context':''}`}>
    {!hasResearchContext&&<div className="search-workspace-heading"><div><span className="eyebrow">ОТКРЫТЫЕ ИСТОЧНИКИ</span><h1>Расследование</h1></div></div>}
    <div className="search-navigation"><nav className="search-primary-tabs" aria-label="Рабочая область поиска">{Object.entries({results:'Поиск и результаты',canvas:'Моё полотно',catalog:'Инструменты',activity:'Ход работы'}).map(([id,label])=><button key={id} aria-pressed={workspace===id} onClick={()=>setWorkspace(id as typeof workspace)}>{label}{id==='results'&&results.length>0&&<span>{results.length}</span>}{id==='activity'&&isBusy&&<LoaderCircle size={12} className="spin"/>}</button>)}</nav><DensityControl/></div>
    <div hidden={workspace!=='results'} className="search-primary-pane">
      <section className={`search-query-panel ${formExpanded?'is-open':'is-collapsed'}`} aria-label="Параметры поиска">
      {hasResearchContext&&<div className="search-query-summary"><button type="button" className="search-query-toggle" aria-label={formExpanded?'Свернуть параметры поиска':'Изменить запрос'} aria-expanded={formExpanded} aria-controls={formId} onClick={()=>{if(!formExpanded&&!query.trim()&&state.search.query)setQuery(state.search.query);setFormExpanded(value=>!value)}}><SearchIcon size={15}/><span><strong>{selected?toolName(selected.id,selected.displayName||selected.name):'Поиск по открытым источникам'}</strong><small>{query.trim()||state.search.query||state.investigation_graph?.goal||'Новый запрос'}</small></span><span className="search-query-toggle-caption">{formExpanded?'Свернуть параметры':'Изменить запрос'}</span><ChevronDown size={14}/></button>{isBusy?<Button size="sm" type="button" variant="danger" onClick={()=>void act(state.busy?'chat_stop':'search_stop')}><Square size={13}/>Остановить</Button>:<Button size="sm" type="button" variant="ghost" aria-label="Повторить поиск" disabled={!canRepeat} onClick={()=>run(true)}><RotateCcw size={13}/><span>Повторить</span></Button>}</div>}
      <form id={formId} hidden={!formExpanded} className="search-form" onSubmit={event=>{event.preventDefault();run()}}>
        {!isStructured&&<div className="query-input"><SearchIcon size={17}/><input id="osint-query" aria-label="Что исследуем?" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Никнейм, домен, IP, адрес или поисковый запрос" disabled={isBusy}/></div>}
        <div className="search-controls"><SearchableSelect label="Инструмент поиска" value={tool} disabled={isBusy} options={[{value:'',label:'Автоматический поиск',group:'Исследование'},...state.tools.filter(item=>item.implemented!==false).map(item=>({value:item.id,label:toolName(item.id,item.displayName||(item.name!==item.id?item.name:undefined)),disabled:!item.available,group:String(item.manifest?.category||'Инструменты')}))]} onChange={setTool}/>{!tool&&!!state.search.choices.length&&<SearchableSelect label="Тип запроса" value={kind||state.search.kind||''} options={state.search.choices.map(choice=>({value:choice.value,label:choice.label}))} onChange={setKind} disabled={isBusy}/>}
          {isBusy?<Button type="button" variant="danger" onClick={()=>void act(state.busy?'chat_stop':'search_stop')}><Square size={13}/>Остановить</Button>:<Button type="submit" disabled={(isStructured?!selected?.available:!query.trim())||tool==='blockchain_gansar'&&(crypto.pending||!crypto.result?.valid||!!crypto.result.requires_network)}><SearchIcon size={15}/>Найти</Button>}
        </div>
        {isStructured&&schema&&(tool==='blockchain_gansar'?<GansarFields schema={schema} draft={argumentsDraft} capability={crypto.result} disabled={isBusy} onChange={(name,value)=>{setArgumentsDraft(previous=>({...previous,[name]:value}));setArgumentError('')}}/>:tool==='username_maigret'?<MaigretFields schema={schema} draft={argumentsDraft} disabled={isBusy} onChange={(name,value)=>{setArgumentsDraft(previous=>({...previous,[name]:value}));setArgumentError('')}}/>:<StructuredToolFields schema={schema} draft={argumentsDraft} disabled={isBusy} onChange={(name,value)=>{setArgumentsDraft(previous=>({...previous,[name]:value}));setArgumentError('')}}/>)}
        {argumentError&&<p className="notice-inline notice-error" role="alert">{argumentError}</p>}{selected&&<details className="search-tool-help"><summary>Об инструменте и входных данных</summary><p className="field-hint">{selected.description} {selected.inputTypes?.length?`Входные данные: ${selected.inputTypes.map(inputLabel).join(', ')}.`:''}</p></details>}
      </form></section>
      {state.search.error&&<div className="notice-inline notice-error" role="alert">{state.search.error}</div>}{!state.search.error&&status&&<div className="notice-inline" role="status">{status}</div>}
      {isBusy?<div className="search-progress" role="status"><LoaderCircle size={16} className="spin"/><span>{progressLabel}{checkedLabel&&<small>{checkedLabel}</small>}</span></div>:checkedLabel&&<p className="field-hint">{checkedLabel}</p>}
      {state.search.maigret_progress&&<div className="maigret-progress" role="status"><span>Выбрано <strong>{state.search.maigret_progress.selected??'—'}</strong></span><span>Запланировано <strong>{state.search.maigret_progress.scheduled??'—'}</strong></span><span>Проверено <strong>{state.search.maigret_progress.checked??0}</strong></span><span>Найдено <strong>{state.search.maigret_progress.found??0}</strong></span><span>Неопределённо <strong>{state.search.maigret_progress.unknown??0}</strong></span><span>Заблокировано <strong>{state.search.maigret_progress.blocked??0}</strong></span><span>Пропущено <strong>{state.search.maigret_progress.skipped??0}</strong></span><span>Ошибки <strong>{state.search.maigret_progress.errors??0}</strong></span><small>{state.search.maigret_progress.cancelled?'Проверка остановлена':state.search.maigret_progress.complete?'Проверка завершена':'Проверка выполняется'} · база {state.search.maigret_progress.database_total??'—'} · активных записей {state.search.maigret_progress.enabled_username??'—'}. Пропуски и ошибки не считаются проверенным отсутствием.</small>{state.search.maigret_progress.skipped_reasons&&Object.keys(state.search.maigret_progress.skipped_reasons).length>0&&<details><summary>Причины пропусков</summary>{Object.entries(state.search.maigret_progress.skipped_reasons).map(([reason,count])=><p key={reason}>{reason}: {count}</p>)}</details>}</div>}
      <InvestigationWorkspace state={state} onSource={onSource}/>
      {!hasInvestigation&&results.length>0?<section className="search-results"><div className="section-heading"><h2>Результаты<span className="count">{results.length}</span></h2><div><IconButton label="Копировать результаты" onClick={()=>void act('copy',{text:results.map(item=>`${item.title}\n${item.url}\n${item.excerpt||''}`).join('\n\n')})}><Copy size={15}/></IconButton><Button variant="secondary" size="sm" disabled={!sourceIds.length||state.busy||!state.connection.canSend} onClick={()=>void act('search_analyze',{evidence_ids:sourceIds})}>Гермионе<ArrowUpRight size={15}/></Button></div></div><div className="result-grid">{results.map((source,index)=><SourceCard source={source} onSelect={onSource} key={source.evidence_id||`${source.url}-${index}`}/>)}</div></section>:!hasInvestigation&&!!state.search.query&&!isBusy&&!state.search.error&&!status&&<div className="no-results"><SearchIcon size={22}/><strong>По этому запросу результатов нет</strong><p>Попробуйте другой запрос или доступный инструмент.</p></div>}
      {!hasInvestigation&&!results.length&&!state.search.query&&!isBusy&&<div className="search-start"><SearchIcon size={23}/><h2>Начните с публичного объекта</h2><p>Результаты, связи и основания появятся здесь. Ручная работа доступна в «Моём полотне».</p><Button variant="secondary" size="sm" onClick={()=>setWorkspace('canvas')}>Открыть полотно</Button></div>}
    </div>
    <div hidden={workspace!=='canvas'} className="search-primary-pane"><ResearchCanvas state={state} onSource={onSource} active={workspace==='canvas'}/></div>
    <div hidden={workspace!=='catalog'} className="search-primary-pane"><ToolCatalog tools={state.tools} checking={state.toolsChecking} selected={tool} busy={isBusy} onSelect={item=>{setTool(item.id);setWorkspace('results');setFormExpanded(true);if(!item.manifest?.input_schema)setTimeout(()=>document.getElementById('osint-query')?.focus(),0)}} onSettings={()=>void act('route',{route:'settings',category:'tools'})}/><div className="search-workspace-actions"><Button variant="ghost" size="sm" onClick={()=>void act('route',{route:'settings',category:'tools'})}>Настройки источников<ArrowUpRight size={13}/></Button><Button variant="ghost" size="sm" disabled={isBusy} onClick={()=>void act('search_dorks',{query})}>Операторы Google<ArrowUpRight size={13}/></Button><Button variant="ghost" size="sm" disabled={!query.trim()||isBusy} onClick={()=>void openAvito()}>Искать на Avito<ArrowUpRight size={13}/></Button></div>{publicSearchStatus&&<p className="notice-inline" role="status">{publicSearchStatus}</p>}</div>
    <div hidden={workspace!=='activity'} className="search-primary-pane"><ActivityBlock activity={state.activity} busy={false}/>{!state.activity.length&&<p className="field-hint">Инструменты ещё не запускались.</p>}</div>
  </div></div>
}
