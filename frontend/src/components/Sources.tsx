import { useEffect, useMemo, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useVirtualizer } from '@tanstack/react-virtual'
import { BookOpen, ChevronDown, ExternalLink, FileSearch, Link2, ShieldCheck, X } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { act } from '../bridge'
import type { Source } from '../types'
import { Badge, Button, IconButton } from './ui'
import { safeUrl } from './Markdown'

const statuses: Record<string, string> = { detected: 'Обнаружено источником', verified: 'Сообщено источником', found: 'Сообщено источником', confirmed: 'Сообщено источником', read: 'Результат получен', readable: 'Результат получен', success: 'Получен результат', partial: 'Частичные данные', error: 'Ошибка получения', failed: 'Ошибка получения', blocked: 'Доступ ограничен', requires_browser: 'Нужен браузер', unavailable: 'Недоступен', not_found: 'Совпадений нет', unconfirmed: 'Не подтверждено', indexed: 'Поисковый сниппет', auth_required: 'Требуется авторизация', rate_limited: 'Ограничение сервиса', timeout: 'Превышено время ожидания', deleted: 'Профиль удалён', private: 'Доступ ограничен владельцем', invalid: 'Некорректный ответ', complete: 'Результат получен' }
export function isReadSource(source: Source) {
  return source.kind === 'page' && !source.details?.javascript_shell && !['failed', 'error', 'blocked', 'restricted', 'empty', 'timeout'].includes(source.status) && (typeof source.details?.content_fetched === 'boolean' ? source.details.content_fetched : ['read', 'readable', 'fetched', 'analyzed'].includes(source.status))
}
export function sourceLabel(source: Source) {
  if (source.status === 'metadata') return source.kind === 'image' ? 'Локальные данные изображения получены' : 'Наблюдение инструмента получено'
  if (source.kind === 'snippet') return 'Поисковый сниппет'
  if (source.kind === 'page' && source.details?.javascript_shell) return 'Доступен только HTTP-текст'
  if (isReadSource(source)) return source.status === 'analyzed' ? 'Прочитан и проанализирован' : 'Содержимое получено'
  if (['discovered', 'unverified'].includes(source.status)) return 'URL обнаружен · не прочитан'
  if (source.status === 'restricted') return 'Доступ ограничен'
  return statuses[source.status] || 'Статус не уточнён'
}
export function sourceKind(source: Source) { return source.kind === 'api' ? 'Ответ API' : source.kind === 'page' ? 'Публичная страница' : source.kind === 'snippet' ? 'Поисковая выдача' : source.kind === 'image' ? 'Изображение' : source.kind === 'map' ? 'Карта' : source.kind === 'archive' ? 'Архив' : source.kind === 'repository' ? 'Репозиторий' : source.kind === 'document' ? 'Документ' : 'Результат адаптера' }
export function domainOf(source: Source) {
  if (source.domain) return source.domain
  try { return new URL(source.url).hostname.replace(/^www\./, '') } catch { return 'Локальный результат' }
}
export function SourceCard({ source, onSelect, compact = false }: { source: Source; onSelect(source: Source): void; compact?: boolean }) {
  return <button className={`source-card ${compact ? 'source-compact' : ''}`} onClick={() => onSelect(source)}><span className="source-icon">{source.kind === 'page' ? <BookOpen size={15}/> : source.kind === 'snippet' ? <FileSearch size={15}/> : <Link2 size={15}/>}</span><span className="source-main"><span className="source-domain">{domainOf(source)}</span><strong>{source.title || source.url || 'Результат инструмента'}</strong>{!compact && source.excerpt && <span className="source-excerpt">{source.excerpt}</span>}<small>{sourceLabel(source)}</small>{!compact && <><span className="source-type">{sourceKind(source)}</span>{source.obtained_at && <time className="source-time" dateTime={source.obtained_at}>{formatDate(source.obtained_at)}</time>}</>}</span><ExternalLink size={13} className="source-open-icon"/></button>
}

function GeoObservation({ source }: { source: Source }) {
  if (!['image','map'].includes(source.kind)) return null
  const data = source.details || {}
  const metadata = data.metadata as Record<string, unknown> | undefined
  const gps = metadata?.gps as Record<string, unknown> | null | undefined
  const gpsLabel = gps && typeof gps.latitude === 'number' && typeof gps.longitude === 'number'
    ? `${gps.latitude}, ${gps.longitude}`
    : metadata?.status === 'no_gps_metadata' ? 'GPS отсутствует'
    : metadata?.status === 'invalid_gps_metadata' ? 'Некорректные GPS-поля'
    : 'Не удалось прочитать GPS-метаданные'
  const image = data.image as Record<string, unknown> | undefined
  const segments = Array.isArray(data.segments) ? data.segments as Record<string, unknown>[] : []
  return <section className="geoint-observation" aria-label="Результат GEOINT-инструмента"><h3>Полученные данные</h3><dl className="details-list">
    {image && <><div><dt>Изображение</dt><dd>{String(image.width)} × {String(image.height)} · {String(image.format)}</dd></div><div><dt>SHA-256</dt><dd className="monospace">{String(image.sha256)}</dd></div></>}
    {metadata && <div><dt>GPS из метаданных</dt><dd>{gpsLabel}<small>Метаданные могут быть изменены; подлинность не подтверждена.</small></dd></div>}
    {typeof data.duration_ms === 'number' && <div><dt>Обработка</dt><dd>{data.duration_ms.toLocaleString('ru-RU')} мс</dd></div>}
  </dl>{segments.length > 0 && <details><summary>Распознанные области · {segments.length}</summary><div className="markdown-table"><table><thead><tr><th>Текст</th><th>Уверенность OCR</th><th>Область</th></tr></thead><tbody>{segments.slice(0,20).map((segment,index) => <tr key={index}><td>{String(segment.text || '')}</td><td>{typeof segment.confidence === 'number' ? `${Math.round(segment.confidence * 100)}%` : 'Нет оценки'}</td><td>{Array.isArray(segment.bbox) ? segment.bbox.join(', ') : ''}</td></tr>)}</tbody></table></div>{segments.length > 20 && <p>Первые20 областей. Полный результат сохранён в доказательстве.</p>}</details>}</section>
}

function SourceList({ sources, onSelect, onFocus, canFocus, group = 'none' }: {
  sources: Source[]; onSelect(source: Source): void; onFocus?(source: Source): void
  canFocus?(source: Source): boolean; group?: string
}) {
  const scroll = useRef<HTMLDivElement>(null)
  const virtual = useVirtualizer({ count: sources.length, getScrollElement: () => scroll.current,
    getItemKey: index => sources[index].evidence_id || `${sources[index].url}:${index}`,
    estimateSize: () => 142, overscan: 3, initialRect: { width: 240, height: 300 }, enabled: sources.length > 40 })
  const rows = sources.length > 40 ? virtual.getVirtualItems() : sources.map((source, index) => ({ index, key: source.evidence_id || index, start: 0 }))
  const render = (source: Source, index: number) => <>
    {group !== 'none' && (index === 0 || (group === 'kind' ? sourceKind(sources[index - 1]) !== sourceKind(source) : sourceLabel(sources[index - 1]) !== sourceLabel(source))) && <h3 className="source-group-label">{group === 'kind' ? sourceKind(source) : sourceLabel(source)}</h3>}
    <div className="source-inspector-row" data-source-id={source.evidence_id}>
      <div className="source-inspector-title"><button onClick={() => onSelect(source)}>{source.title || source.url || 'Результат инструмента'}</button>{safeUrl(source.url).startsWith('http') && <IconButton label="Открыть исходный URL" onClick={() => void act('open_url', { url: source.url })}><ExternalLink size={14}/></IconButton>}</div>
      <div className="source-inspector-meta"><span>{domainOf(source)}</span><span>· {sourceKind(source)}</span></div>
      <span className="source-inspector-status">{sourceLabel(source)}</span>
      {source.excerpt && <details onToggle={() => virtual.measure()}><summary>Выдержка</summary><p>{source.excerpt}</p></details>}
      {onFocus && (!canFocus || canFocus(source)) && <button className="source-focus" onClick={() => onFocus(source)}>К ответу с этим источником</button>}
    </div>
  </>
  return <div ref={scroll} className="source-inspector-scroll" aria-label="Список источников">
    <div style={sources.length > 40 ? { height: virtual.getTotalSize(), position: 'relative' } : undefined}>
      {rows.map(row => <div key={row.key} data-index={row.index} ref={sources.length > 40 ? virtual.measureElement : undefined} style={sources.length > 40 ? { position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${row.start}px)` } : undefined}>{render(sources[row.index], row.index)}</div>)}
    </div>
  </div>
}

export function SourceInspector({ sources, onSelect, onFocus, canFocus }: {
  sources: Source[]; onSelect(source: Source): void; onFocus?(source: Source): void; canFocus?(source: Source): boolean
}) {
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState('none')
  const visible = useMemo(() => {
    const result = sources.filter(source => (filter === 'all' || filter === 'read' && isReadSource(source) || filter === 'errors' && ['error','failed','blocked','restricted','timeout','rate_limited','unavailable','auth_required'].includes(source.status)) && `${source.title} ${source.url} ${source.excerpt || ''}`.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru')))
    if (group !== 'none') result.sort((a, b) => (group === 'kind' ? sourceKind(a).localeCompare(sourceKind(b), 'ru') : sourceLabel(a).localeCompare(sourceLabel(b), 'ru')))
    return result
  }, [sources, filter, query, group])
  return <section className="source-inspector" aria-label="Источники текущей задачи"><div className="source-inspector-heading"><span>Источники задачи</span><Badge>{sources.length}</Badge></div><div className="source-filters">{[['all','Все'],['read','Прочитаны'],['errors','Ошибки']].map(([id,label]) => <button key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}</div><input aria-label="Поиск по источникам задачи" placeholder="Найти источник" value={query} onChange={event => setQuery(event.target.value)}/><select aria-label="Группировка источников" value={group} onChange={event => setGroup(event.target.value)}><option value="none">Порядок получения</option><option value="kind">По типу</option><option value="status">По статусу</option></select>{visible.length ? <SourceList sources={visible} onSelect={onSelect} onFocus={onFocus} canFocus={canFocus} group={group}/> : <p className="source-inspector-empty">{sources.length ? 'Источников по этим условиям нет.' : 'У текущей задачи пока нет источников.'}</p>}</section>
}
export function Sources({ sources, onSelect }: { sources: Source[]; onSelect(source: Source): void }) {
  const [open, setOpen] = useState(false)
  if (!sources.length) return null
  return <div className="sources-group"><button className="sources-trigger" aria-expanded={open} onClick={() => setOpen(!open)}><ShieldCheck size={14}/><span>Источники</span><span className="count">{sources.length}</span><ChevronDown size={14} className={open ? 'rotate' : ''}/></button><AnimatePresence initial={false}>{open && <motion.div className="sources-list sources-bounded" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }}><SourceList sources={sources} onSelect={onSelect}/></motion.div>}</AnimatePresence></div>
}
export function SourceDialog({ source: initialSource, onClose }: { source: Source | null; onClose(): void }) {
  const [record, setRecord] = useState<Source | null>(null)
  const technical = useRef<HTMLDetailsElement>(null)
  useEffect(() => setRecord(null), [initialSource])
  const source = record || initialSource
  const limitations = source?.limitations ? Array.isArray(source.limitations) ? source.limitations : [source.limitations] : []
  return <Dialog.Root open={!!initialSource} onOpenChange={open => { if (!open) onClose() }}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="dialog source-dialog"><div className="dialog-header"><div><span className="eyebrow">ИСТОЧНИК</span><Dialog.Title>{source?.title || 'Доказательство'}</Dialog.Title></div><Dialog.Close asChild><IconButton label="Закрыть источник"><X size={18}/></IconButton></Dialog.Close></div><Dialog.Description className="muted">{source ? domainOf(source) : ''}</Dialog.Description>{source && <div className="dialog-body"><Badge tone={isReadSource(source) ? 'success' : 'neutral'}>{sourceLabel(source)}</Badge>{source.excerpt && <p className="source-summary">{source.excerpt}</p>}{source.kind === 'snippet' && <p className="notice-inline">Получен текст поисковой выдачи. Содержимое страницы не подтверждено чтением.</p>}{source.kind === 'adapter' && <p className="muted">Результат адаптера отражает наблюдение источника и сам по себе не подтверждает личность.</p>}{limitations.length > 0 && <div className="notice-inline"><strong>Ограничения</strong><ul>{limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}<GeoObservation source={source}/><dl className="details-list"><div><dt>Адрес</dt><dd>{source.url || 'Не указан'}</dd></div>{source.obtained_at && <div><dt>Получено</dt><dd>{formatDate(source.obtained_at)}</dd></div>}</dl>{(source.details || source.evidence_id) && <details className="technical-details" ref={technical}><summary>Детали доказательства</summary><p className="monospace">{source.evidence_id}</p>{source.details && <pre>{JSON.stringify(source.details, null, 2)}</pre>}</details>}<div className="dialog-actions">{source.evidence_id && <Button variant="secondary" onClick={() => void act('source_open', { evidence_id: source.evidence_id }).then(result => { if (result && typeof result === 'object' && 'evidence_id' in result) setRecord(result as Source); if (technical.current && result !== null) { technical.current.open = true; technical.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) } })}><ShieldCheck size={15}/>Доказательство</Button>}{safeUrl(source.url).startsWith('http') && <Button onClick={() => void act('open_url', { url: source.url })}><ExternalLink size={15}/>Открыть страницу</Button>}</div></div>}</Dialog.Content></Dialog.Portal></Dialog.Root>
}
export function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
