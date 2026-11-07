import { Details, Summary, Select } from './ui'
import { useEffect, useMemo, useState } from 'react'
import { AtSign, Braces, ChevronDown, Globe2, LoaderCircle, Mail, Phone, Play, RefreshCw, Search, Settings2, ShieldCheck, UserRound, Wrench } from 'lucide-react'
import { act } from '../bridge'
import type { Tool } from '../types'
import { executionLabel, inputLabel, stateLabel, toolName, toolRemedy } from '../tool-presentation'
import { formatDate } from './Sources'
import { Badge, Button, EmptyState, IconButton } from './ui'
import { CryptoIcon } from '../crypto-icons'

const accessLabels: Record<string, string> = {
  LOCAL_PYTHON: 'Локальное вычисление', LOCAL_MODEL: 'Локальная модель',
  PUBLIC_API_NO_KEY: 'Публичный API без ключа', PERMITTED_HTTP_PARSER: 'HTML-парсер',
  PERMITTED_BROWSER_PARSER: 'Браузерный парсер', LOCAL_CLI: 'Локальный CLI',
  PERMITTED_HTTP: 'HTML-парсер', PERMITTED_BROWSER: 'Браузерный парсер',
  OFFICIAL_API: 'Публичный API', OPEN_DATASET: 'Открытый набор данных',
}
const categoryLabels: Record<string, string> = {
  people: 'Люди и ФИО', username: 'Никнеймы', email: 'Email', phone: 'Телефоны',
  socmint: 'Социальные сети', company: 'Компании и реестры', infrastructure: 'Домены и инфраструктура',
  blockchain: 'Криптовалюты', geoint: 'GEOINT', documents: 'Документы и открытые данные',
  media: 'Медиа', academic: 'Научные публикации', software: 'Репозитории и пакеты',
  threat_intelligence: 'Сетевая безопасность', other: 'Прочие инструменты',
}
const regionNames = new Intl.DisplayNames(['ru'], { type: 'region' })
const regionLabel = (code: string) => code === 'global' ? 'Весь мир' : /^[A-Z]{2}$/.test(code) ? regionNames.of(code) || code : code
const category = (tool: Tool) => tool.source_contract?.category || String(tool.manifest?.category || tool.inputTypes[0] || 'other')
const title = (tool: Tool) => toolName(tool.id, tool.displayName || (tool.name !== tool.id ? tool.name : undefined))

function ToolIcon({ tool }: { tool: Tool }) {
  if (tool.id === 'blockchain_gansar') return <CryptoIcon id="generic:wallet" size={20}/>
  const kinds = tool.inputTypes
  const Icon = kinds.includes('email') ? Mail : kinds.includes('phone') ? Phone :
    kinds.some(kind => ['web', 'url', 'domain'].includes(kind)) ? Globe2 :
    kinds.includes('blockchain') ? Braces : kinds.includes('username') ? AtSign : UserRound
  return <Icon size={19}/>
}

function LastExecution({ tool }: { tool: Tool }) {
  const execution = tool.last_execution
  const checkedAt = tool.lastChecked || tool.diagnostic?.checked_at
  return <>
    {checkedAt && <small>Готовность проверена: {formatDate(checkedAt)}</small>}
    {execution && <div className="tool-last-execution">
      <strong>Последнее выполнение</strong>
      <p>{executionLabel(execution.status)}{typeof execution.result_count === 'number' && <> · Результатов: {execution.result_count}</>}</p>
      {execution.obtained_at && <small>{formatDate(execution.obtained_at)}</small>}
      {execution.error_code && <Details><Summary>Технический код</Summary><code>{execution.error_code}</code></Details>}
    </div>}
  </>
}

function ContractDetails({ contract }: { contract: NonNullable<Tool['source_contract']> }) {
  const { health } = contract
  return <dl className="graph-properties">
    <div><dt>Источник и регион</dt><dd>{contract.host} · {contract.region.map(regionLabel).join(', ')}</dd></div>
    <div><dt>Доступ</dt><dd>{contract.authentication === 'none' ? 'Без ключа' : 'Требуется ключ'}</dd></div>
    <div><dt>Условия данных</dt><dd>{contract.license}</dd></div>
    {contract.limits && <div><dt>Ограничения</dt><dd>{contract.limits}</dd></div>}
    <div><dt>Последний ответ</dt><dd>{health.status === 'not_checked' ? 'Ещё не запрашивался в этом запуске' : executionLabel(health.status)}
      {health.result_count !== undefined && <> · Записей: {health.result_count}</>}</dd></div>
    {health.last_success_at && <div><dt>Последний успешный ответ</dt><dd>{formatDate(health.last_success_at)}</dd></div>}
  </dl>
}

export function ToolCatalog({ tools, checking, selected, busy = false, inSettings = false, onSelect, onSettings }: {
  tools: Tool[]; checking?: boolean; selected?: string; busy?: boolean; inSettings?: boolean
  onSelect?(tool: Tool): void; onSettings?(): void
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [group, setGroup] = useState('all')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const implemented = useMemo(() => tools.filter(tool => tool.implemented !== false), [tools])
  const reviewed = useMemo(() => implemented.filter(tool => tool.source_contract), [implemented])
  const groups = useMemo(() => [...new Set(implemented.map(category))].sort(), [implemented])
  useEffect(() => setPage(0), [query, filter, group, implemented.length])
  const visible = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase('ru').split(/\s+/)
    return implemented.filter(tool => {
      const contract = tool.source_contract
      if (group !== 'all' && category(tool) !== group) return false
      if (filter === 'ready' && !tool.available) return false
      if (filter === 'checking' && !['checking', 'unverified'].includes(tool.state)) return false
      if (filter === 'attention' && (tool.available || ['checking', 'unverified'].includes(tool.state))) return false
      const searchable = [title(tool), tool.description, categoryLabels[category(tool)],
        ...tool.inputTypes.map(inputLabel), ...(contract?.region || []).flatMap(code => [code, regionLabel(code)]),
        ...(tool.manifest?.capabilities || []).map(id => toolName(id)),
        ...(contract?.supported_entity_types || contract?.entity_types || []).map(inputLabel)].join(' ').toLocaleLowerCase('ru')
      return terms.every(term => searchable.includes(term))
    })
  }, [implemented, query, filter, group])
  const available = implemented.filter(tool => tool.available).length
  return <section className="tool-catalog">
    <div className="section-heading">
      <h2>{inSettings ? 'Источники и интеграции' : 'Инструментарий'}
        <Badge tone={available ? 'success' : 'neutral'}>{checking ? 'Проверяем доступность' : available + ' локально готовы · ' + implemented.length + ' операций'}</Badge>
      </h2>
      <IconButton label="Проверить доступность инструментов" disabled={checking || busy} onClick={() => void act('tools_refresh')}>
        {checking ? <LoaderCircle size={17} className="spin"/> : <RefreshCw size={17}/>}
      </IconButton>
    </div>
    {inSettings && <p className="field-hint">
      Проверенные контракты источников: {reviewed.length}. Свежий успешный ответ в этом запуске: {reviewed.filter(tool => tool.source_contract?.health.last_success_at).length}.
      {' '}Требуют ключа: {reviewed.filter(tool => tool.source_contract?.authentication !== 'none').length}.
      {' '}Сетевой сбой последней проверки: {reviewed.filter(tool => ['unavailable', 'timeout', 'blocked', 'rate_limited'].includes(tool.source_contract?.health.status || '')).length}.
    </p>}
    <div className="catalog-filters">
      <label><Search size={16}/><input placeholder="Найти инструмент" aria-label="Найти инструмент" value={query} onChange={event => setQuery(event.target.value)}/></label>
      {inSettings && <Select aria-label="Категория источника" value={group} onValueChange={setGroup}>
        <option value="all">Все категории</option>
        {groups.map(key => <option key={key} value={key}>{categoryLabels[key] || inputLabel(key)}</option>)}
      </Select>}
      <Select aria-label="Фильтр доступности" value={filter} onValueChange={setFilter}>
        <option value="all">Все состояния</option><option value="ready">Готовы к работе</option>
        <option value="attention">Нужно внимание</option><option value="checking">Проверяются</option>
      </Select>
    </div>
    {!implemented.length ? <EmptyState icon={<Wrench size={24}/>} title={checking ? 'Проверяем инструменты' : 'Реестр пока недоступен'}>
      Состояние приходит от проверки Python-движка.
    </EmptyState> : !visible.length ? <p className="catalog-empty">По выбранным условиям инструментов нет.</p> : <div className="catalog-grid">
      {visible.slice(page * 24, (page + 1) * 24).map(tool => {
        const access = tool.manifest?.execution_mode || tool.manifest?.access_mode || ''
        const docs = tool.documentation_url || tool.source_contract?.documentation
        const operations = tool.manifest?.capabilities || []
        return <article key={tool.id} className={selected === tool.id ? 'catalog-tool is-selected' : 'catalog-tool'}>
          <div className="catalog-tool-heading"><span className="tool-icon"><ToolIcon tool={tool}/></span>
            <Badge tone={tool.state === 'configured_unverified' ? 'warning' : tool.state === 'unverified' ? 'neutral' : tool.available ? 'success' : tool.state === 'checking' ? 'neutral' : 'warning'}>
              {tool.stateLabel || stateLabel(tool.state, tool.available)}
            </Badge>
          </div>
          <h3>{title(tool)}</h3>
          {access && <small className="tool-access-mode">{accessLabels[access] || access}</small>}
          <p>{tool.description}</p>
          <div className="tool-inputs">{(tool.source_contract?.supported_entity_types || tool.source_contract?.entity_types || tool.inputTypes).map(type => <span key={type}>{inputLabel(type)}</span>)}</div>
          {tool.sensitive && <span className="tool-sensitive"><ShieldCheck size={13}/>С подтверждением пользователя</span>}
          <div className="catalog-tool-actions">
            {onSelect && <Button variant={selected === tool.id ? 'default' : 'secondary'} size="sm" disabled={!tool.available || busy} onClick={() => onSelect(tool)}>
              <Play size={12}/>{selected === tool.id ? 'Выбран' : 'Выбрать'}
            </Button>}
            <Button variant="ghost" size="sm" aria-expanded={expanded === tool.id} onClick={() => setExpanded(expanded === tool.id ? null : tool.id)}>
              {tool.available ? 'Подробнее' : 'Что исправить'}<ChevronDown size={13} className={expanded === tool.id ? 'rotate' : ''}/>
            </Button>
          </div>
          {expanded === tool.id && <div className="tool-remedy">
            {tool.reason && <p>{tool.reason}</p>}
            <strong>Следующий шаг</strong><p>{toolRemedy(tool)}</p>
            {!!operations.length && <><strong>Поддерживаемые операции ({operations.length})</strong>
              <ul className="tool-capabilities">{operations.map(operation => <li key={operation}>{operation === tool.id ? title(tool) : toolName(operation)}</li>)}</ul>
            </>}
            {tool.source_contract && <ContractDetails contract={tool.source_contract}/>}
            <LastExecution tool={tool}/>
            {docs && <Button variant="ghost" size="sm" onClick={() => void act('open_url', { url: docs })}>Документация</Button>}
            {tool.manual_url && <Button variant="secondary" size="sm" onClick={() => void act('open_url', { url: tool.manual_url })}>Открыть сервис вручную</Button>}
            {onSettings && <Button variant="ghost" size="sm" onClick={onSettings}><Settings2 size={13}/>Настройки источников</Button>}
          </div>}
        </article>
      })}
    </div>}
    {visible.length > 24 && <nav className="catalog-pagination" aria-label="Страницы каталога">
      <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</Button>
      <span>{page * 24 + 1}–{Math.min((page + 1) * 24, visible.length)} из {visible.length}</span>
      <Button variant="secondary" size="sm" disabled={(page + 1) * 24 >= visible.length} onClick={() => setPage(page + 1)}>Далее</Button>
    </nav>}
  </section>
}
