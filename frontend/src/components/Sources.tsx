import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { BookOpen, ChevronDown, ExternalLink, FileSearch, Link2, ShieldCheck, X } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { act } from '../bridge'
import type { Source } from '../types'
import { Badge, Button, IconButton } from './ui'
import { safeUrl } from './Markdown'

const statuses: Record<string, string> = { verified: 'Сообщено источником', found: 'Сообщено источником', confirmed: 'Сообщено источником', read: 'Страница прочитана', readable: 'Страница прочитана', success: 'Получен результат', partial: 'Частичные данные', error: 'Ошибка получения', blocked: 'Доступ ограничен', requires_browser: 'Нужен браузер', unavailable: 'Недоступен', not_found: 'Совпадений нет', unconfirmed: 'Не подтверждено' }
export function sourceLabel(source: Source) {
  if (source.kind === 'snippet') return 'Поисковый сниппет'
  if (source.kind === 'page' && source.details?.javascript_shell) return 'Доступен только HTTP-текст'
  if (source.kind === 'page' && ['verified', 'read', 'readable', 'success', 'found', 'confirmed'].includes(source.status)) return 'Страница прочитана'
  return statuses[source.status] || source.status || 'Статус неизвестен'
}
export function domainOf(source: Source) {
  if (source.domain) return source.domain
  try { return new URL(source.url).hostname.replace(/^www\./, '') } catch { return 'Локальный результат' }
}
export function SourceCard({ source, onSelect, compact = false }: { source: Source; onSelect(source: Source): void; compact?: boolean }) {
  return <button className={`source-card ${compact ? 'source-compact' : ''}`} onClick={() => onSelect(source)}><span className="source-icon">{source.kind === 'page' ? <BookOpen size={15}/> : source.kind === 'snippet' ? <FileSearch size={15}/> : <Link2 size={15}/>}</span><span className="source-main"><span className="source-domain">{domainOf(source)}</span><strong>{source.title || source.url || 'Результат инструмента'}</strong>{!compact && source.excerpt && <span className="source-excerpt">{source.excerpt}</span>}<small>{sourceLabel(source)}</small></span><ExternalLink size={13} className="source-open-icon"/></button>
}
export function Sources({ sources, onSelect }: { sources: Source[]; onSelect(source: Source): void }) {
  const [open, setOpen] = useState(false)
  if (!sources.length) return null
  return <div className="sources-group"><button className="sources-trigger" aria-expanded={open} onClick={() => setOpen(!open)}><ShieldCheck size={14}/><span>Источники</span><span className="count">{sources.length}</span><ChevronDown size={14} className={open ? 'rotate' : ''}/></button><AnimatePresence initial={false}>{open && <motion.div className="sources-list" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }}>{sources.map((source, index) => <SourceCard key={source.evidence_id || index} source={source} onSelect={onSelect}/>)}</motion.div>}</AnimatePresence></div>
}
export function SourceDialog({ source: initialSource, onClose }: { source: Source | null; onClose(): void }) {
  const [record, setRecord] = useState<Source | null>(null)
  const technical = useRef<HTMLDetailsElement>(null)
  useEffect(() => setRecord(null), [initialSource])
  const source = record || initialSource
  const limitations = source?.limitations ? Array.isArray(source.limitations) ? source.limitations : [source.limitations] : []
  return <Dialog.Root open={!!initialSource} onOpenChange={open => { if (!open) onClose() }}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="dialog source-dialog"><div className="dialog-header"><div><span className="eyebrow">ИСТОЧНИК</span><Dialog.Title>{source?.title || 'Доказательство'}</Dialog.Title></div><Dialog.Close asChild><IconButton label="Закрыть источник"><X size={18}/></IconButton></Dialog.Close></div><Dialog.Description className="muted">{source ? domainOf(source) : ''}</Dialog.Description>{source && <div className="dialog-body"><Badge tone={source.kind === 'page' && ['success','read','readable','found','confirmed'].includes(source.status) && !source.details?.javascript_shell ? 'success' : 'neutral'}>{sourceLabel(source)}</Badge>{source.excerpt && <p className="source-summary">{source.excerpt}</p>}{source.kind === 'snippet' && <p className="notice-inline">Получен текст поисковой выдачи. Содержимое страницы не подтверждено чтением.</p>}{source.kind === 'adapter' && <p className="muted">Результат адаптера отражает наблюдение источника и сам по себе не подтверждает личность.</p>}{limitations.length > 0 && <div className="notice-inline"><strong>Ограничения</strong><ul>{limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}<dl className="details-list"><div><dt>Адрес</dt><dd>{source.url || 'Не указан'}</dd></div>{source.obtained_at && <div><dt>Получено</dt><dd>{formatDate(source.obtained_at)}</dd></div>}</dl>{(source.details || source.evidence_id) && <details className="technical-details" ref={technical}><summary>Детали доказательства</summary><p className="monospace">{source.evidence_id}</p>{source.details && <pre>{JSON.stringify(source.details, null, 2)}</pre>}</details>}<div className="dialog-actions">{source.evidence_id && <Button variant="secondary" onClick={() => void act('source_open', { evidence_id: source.evidence_id }).then(result => { if (result && typeof result === 'object' && 'evidence_id' in result) setRecord(result as Source); if (technical.current && result !== null) { technical.current.open = true; technical.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) } })}><ShieldCheck size={15}/>Доказательство</Button>}{safeUrl(source.url).startsWith('http') && <Button onClick={() => void act('open_url', { url: source.url })}><ExternalLink size={15}/>Открыть страницу</Button>}</div></div>}</Dialog.Content></Dialog.Portal></Dialog.Root>
}
export function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
