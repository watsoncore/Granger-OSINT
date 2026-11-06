import {Details,Summary} from './ui'
import { memo, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowDown, ArrowUp, Check, ChevronDown, Copy, FileText, LoaderCircle, RefreshCw, Search, ShieldCheck, Square, WandSparkles } from 'lucide-react'
import { act } from '../bridge'
import type { Activity, DesktopState, Message, Source } from '../types'
import { ActionsMenu, Badge, Button, IconButton, MenuItem } from './ui'
import { Markdown } from './Markdown'
import { SourceDialog, Sources } from './Sources'
import { inputLabel, toolName } from '../tool-presentation'
import { VirtualMessages, VIRTUAL_MESSAGE_THRESHOLD } from './VirtualMessages'
import { AttachmentComposer, AttachmentPicker, importDroppedImage } from './AttachmentComposer'
import { GeoInvestigation } from './GeoInvestigation'
import { ResearchBrowser } from './ResearchBrowser'

const activityLabels: Record<string, string> = { complete: 'Завершено', partial: 'Частичные данные', empty: 'Совпадений нет', unavailable: 'Недоступен', auth_required: 'Нужна авторизация', invalid_arguments: 'Запрос отклонён', blocked: 'Доступ запрещён', timeout: 'Истекло время', running: 'Выполняется', started: 'Выполняется', success: 'Завершено', completed: 'Завершено', done: 'Завершено', error: 'Ошибка', failed: 'Ошибка', cancelled: 'Остановлено', stopped: 'Остановлено', pending: 'Ожидание', waiting: 'Ожидание' }
export function ActivityBlock({ activity, busy }: { activity: Activity[]; busy: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const [source, setSource] = useState<Source | null>(null)
  if (!activity.length && !busy) return null
  const running = activity.filter(item => ['running', 'started'].includes(item.status))
  return <div className="activity-block"><button className="activity-heading" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{busy ? <LoaderCircle size={15} className="spin"/> : <ShieldCheck size={15}/>}<span>{running.at(-1)?.summary || (busy ? 'Гермиона работает над ответом' : 'Действия исследования')}</span>{!!activity.length && <span className="count">{activity.length}</span>}<ChevronDown size={14} className={expanded ? 'rotate' : ''}/></button><AnimatePresence initial={false}>{expanded && !!activity.length && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="activity-rows">{activity.map(item => <div className="activity-row" key={item.id}><span className={`activity-dot status-${item.status}`}/><span><strong>{toolName(item.tool)}{item.inputType && <span className="activity-input"> · {inputLabel(item.inputType)}</span>}</strong><small>{item.summary}</small>{typeof item.resultCount === 'number' && <small>Результатов: {item.resultCount}</small>}{(item.error || item.details || item.evidenceIds?.length) && <Details className="activity-details"><Summary>Подробности вызова</Summary>{item.error && <p className="text-danger">{item.error}</p>}{item.details && <pre>{JSON.stringify(item.details, null, 2)}</pre>}{item.evidenceIds?.map(id => <button key={id} onClick={() => void act('source_open', { evidence_id: id }).then(result => { if (result && typeof result === 'object' && 'evidence_id' in result) setSource(result as Source) })}>Открыть доказательство</button>)}</Details>}</span><Badge tone={['error', 'failed'].includes(item.status) ? 'danger' : ['success', 'completed', 'done'].includes(item.status) ? 'success' : 'neutral'}>{activityLabels[item.status] || item.status}</Badge></div>)}</motion.div>}</AnimatePresence><SourceDialog source={source} onClose={() => setSource(null)}/></div>
}

const MessageRow = memo(function MessageRow({ message, lastModel, busy, state, onSource }: { message: Message; lastModel: boolean; busy: boolean; state?:DesktopState; onSource(source: Source): void }) {
  const [copied, setCopied] = useState(false)
  const content = useRef<HTMLDivElement>(null)
  const copy = (markdown = false) => void act('copy', { text: markdown ? message.text : content.current?.innerText || message.text }).then(result => { if (result !== null) { setCopied(true); setTimeout(() => setCopied(false), 1800) } })
  if (message.role === 'status') return <div className="message-status" data-message-id={message.id}>{message.text}</div>
  return <motion.article className={`message message-${message.role}`} data-message-id={message.id} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}><div className="message-byline">{message.role === 'model' ? <><span className="hermione-mark"><WandSparkles size={12}/></span>Гермиона{message.streaming && <span className="streaming-label">отвечает</span>}</> : 'Вы'}</div><div ref={content} className="message-content">{message.role === 'user' ? <div className="user-text">{message.text}{!!message.attachments?.length && <div className="attachment-previews">{message.attachments.map(image => <span className="attachment-preview" key={image.id}>{image.name} · {image.width} × {image.height} · {image.format}</span>)}</div>}</div> : <Markdown text={message.text} onSource={id => { const source = message.sources?.find(item => item.evidence_id === id); if (source) onSource(source); else void act('source_open', { evidence_id: id }) }}/>}</div>{state && lastModel && message.investigation_id && message.sources?.some(source => source.kind === 'image' || source.kind === 'map') && <GeoInvestigation state={state} id={message.investigation_id}/>}{message.role === 'model' && !!message.sources?.length && <Sources sources={message.sources} onSelect={onSource}/>}<div className="message-actions"><IconButton label={copied ? 'Скопировано' : 'Копировать'} onClick={() => copy()}>{copied ? <Check size={14}/> : <Copy size={14}/>}</IconButton>{message.role === 'model' && <><IconButton label="Открыть в Canvas" disabled={!message.text} onClick={() => void act('canvas_open', { message_id: message.id })}><FileText size={14}/></IconButton>{lastModel && <IconButton label="Повторить ответ" disabled={busy} onClick={() => void act('chat_regenerate', { message_id: message.id })}><RefreshCw size={14}/></IconButton>}<ActionsMenu label="Ещё действия с ответом"><MenuItem onSelect={() => copy(true)}><Copy size={14}/>Скопировать Markdown</MenuItem>{message.streaming && <MenuItem onSelect={() => void act('chat_stop')}><Square size={13}/>Остановить ответ</MenuItem>}</ActionsMenu></>}</div></motion.article>
})

export function Chat({ state, draft, setDraft, onSource, onRoute }: { state: DesktopState; draft: string; setDraft(value: string): void; onSource(source: Source): void; onRoute(route: DesktopState['route']): void }) {
  const scroll = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const pinned = useRef(true)
  const previousConversation = useRef(state.conversation_id)
  const [away, setAway] = useState(false)
  const [sending, setSending] = useState(false)
  const restoreInputFocus = useRef(false)
  const previousBusy = useRef(state.busy)
  const [dropError, setDropError] = useState('')
  const seenIds = useRef(new Set<string>())
  const seenConversation = useRef(state.conversation_id)
  const visibility = useRef<{ observer: IntersectionObserver; elements: Map<string, Element> } | null>(null)
  const observedRows = useRef<Message[]>([])
  const observeMounted = () => {
    const current = visibility.current
    if (!current || !scroll.current) return
    const completed = new Set(state.messages.filter(message => !message.streaming && (message.role === 'model' || message.role === 'status')).map(message => message.id))
    for (const [id, element] of current.elements) if (!element.isConnected) { current.observer.unobserve(element); current.elements.delete(id) }
    scroll.current.querySelectorAll<HTMLElement>('[data-message-id]').forEach(element => {
      const id = element.dataset.messageId!
      if (completed.has(id) && !current.elements.has(id) && !seenIds.current.has(`${state.conversation_id}:${id}`)) {
        current.elements.set(id, element); current.observer.observe(element)
      }
    })
  }
  useEffect(() => {
    if (seenConversation.current !== state.conversation_id) {
      seenIds.current.clear()
      seenConversation.current = state.conversation_id
    }
    if (!state.window.active || state.route !== 'chat' || !state.conversation_id || !scroll.current) return
    const conversation = state.conversation_id
    const pending = new Set<string>()
    const elements = new Map<string, Element>()
    const observer = new IntersectionObserver(entries => {
      const ids = entries.filter(entry => entry.isIntersecting).map(entry => (entry.target as HTMLElement).dataset.messageId!).filter(id => elements.has(id) && !pending.has(id) && !seenIds.current.has(`${conversation}:${id}`))
      if (ids.length) {
        ids.forEach(id => pending.add(id))
        void act('messages_seen', { conversation_id: conversation, message_ids: ids }).then(result => {
          if (result !== null && result !== false) ids.forEach(id => {
            if (seenConversation.current === conversation) seenIds.current.add(`${conversation}:${id}`)
            const element = elements.get(id)
            if (element) observer.unobserve(element)
            elements.delete(id)
          })
        }).finally(() => ids.forEach(id => pending.delete(id)))
      }
    }, { root: scroll.current, rootMargin: '-32px 0px', threshold: 0 })
    visibility.current = { observer, elements }
    observedRows.current = []
    return () => { observer.disconnect(); elements.clear(); visibility.current = null; observedRows.current = [] }
  }, [state.window.active, state.route, state.conversation_id])
  useEffect(() => {
    const current = visibility.current
    if (!current || !scroll.current) return
    const remove = (id: string) => { const element = current.elements.get(id); if (element) current.observer.unobserve(element); current.elements.delete(id) }
    // A streaming delta preserves old message identities. Only changed/new
    // rows need DOM lookup; retain one observer instead of rescanning and
    // re-observing the whole transcript for every token batch.
    state.messages.forEach((message, index) => {
      const previous = observedRows.current[index]
      if (message === previous) return
      if (previous && previous.id !== message.id) remove(previous.id)
      if ((message.role === 'model' || message.role === 'status') && !message.streaming) {
        if (!current.elements.has(message.id) && !seenIds.current.has(`${state.conversation_id}:${message.id}`)) {
          const element = scroll.current!.querySelector(`[data-message-id="${CSS.escape(message.id)}"]`)
          if (element) { current.elements.set(message.id, element); current.observer.observe(element) }
        }
      } else remove(message.id)
    })
    observedRows.current.slice(state.messages.length).forEach(message => remove(message.id))
    observedRows.current = state.messages
  }, [state.window.active, state.route, state.conversation_id, state.messages])
  const lastModel = state.messages.findLast(item => item.role === 'model')?.id
  const end = state.messages.at(-1)
  useLayoutEffect(() => {
    const el = scroll.current
    if (previousConversation.current !== state.conversation_id) { pinned.current = true; previousConversation.current = state.conversation_id; setAway(false) }
    if (el && pinned.current && !window.getSelection()?.toString()) el.scrollTop = el.scrollHeight
  }, [end?.text, state.messages.length, state.activity, state.conversation_id])
  useLayoutEffect(() => {
    const element = textarea.current
    const parent = element?.parentElement
    if (!element || !parent) return
    const resize = () => { element.style.height = 'auto'; element.style.height = draft ? `${Math.min(148, element.scrollHeight)}px` : '' }
    resize()
    let previousWidth = parent.clientWidth
    const observer = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width
      if (typeof width === 'number' && width !== previousWidth) { previousWidth = width; resize() }
    })
    observer.observe(parent)
    return () => observer.disconnect()
  }, [draft])
  useEffect(() => {
    if (!state.busy) {
      setSending(false)
      if (previousBusy.current && restoreInputFocus.current && state.window.active && state.route === 'chat') {
        const active = document.activeElement
        // Preserve a deliberate selection of another control while an answer runs.
        if (!active || active === document.body || active === textarea.current || active.closest('.composer')) textarea.current?.focus({ preventScroll: true })
      }
      restoreInputFocus.current = false
    }
    previousBusy.current = state.busy
  }, [state.busy, state.window.active, state.route])
  useLayoutEffect(() => {
    if (sending || !restoreInputFocus.current) return
    const active = document.activeElement
    if (!active || active === document.body || active.closest('.composer')) textarea.current?.focus({ preventScroll: true })
  }, [sending])
  useEffect(() => {
    if (!state.message_focus) return
    const target = scroll.current?.querySelector(`[data-message-id="${CSS.escape(state.message_focus)}"]`)
    if (target) { pinned.current = false; target.scrollIntoView({ block: 'center', behavior: 'smooth' }) }
  }, [state.message_focus])
  const send = async () => {
    if ((!draft.trim() && !state.attachments?.length) || state.attachment_busy || state.busy || sending || !state.connection.canSend) return
    restoreInputFocus.current = document.activeElement === textarea.current || !!document.activeElement?.closest('.composer')
    setSending(true)
    const value = draft.trim() || 'Проанализируй выбранные изображения: метаданные, надписи и доступные географические признаки.'
    pinned.current = true; setAway(false)
    const result = await act('chat_send', { text: value, attachment_ids: state.attachments?.map(image => image.id) || [] })
    if (result !== null && result !== false) setDraft('')
    setSending(false)
    if (restoreInputFocus.current) textarea.current?.focus({ preventScroll: true })
  }
  return <div className="chat-workspace chat-layout" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file && !state.busy && !state.attachment_busy) { setDropError(''); void importDroppedImage(file).catch(error => setDropError(error instanceof Error ? error.message : 'Не удалось загрузить изображение.')) } }}><div className="chat-scroll" ref={scroll} onScroll={() => { const el = scroll.current; if (el) { pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 90; setAway(!pinned.current) } }}><div className="conversation chat-content-width">{!state.messages.length ? <div className="chat-welcome"><span className="eyebrow">Ваше исследование начинается здесь</span><h1>Давайте разберёмся.</h1><p>Гермиона поможет проверить открытые сведения,<br className="wide-only"/> сопоставить источники и увидеть главное.</p><div className="welcome-actions"><button onClick={() => { setDraft('Гермиона, помоги составить план исследования по открытым источникам.'); textarea.current?.focus() }}><FileText size={17}/><span>Составить план<small>С чего начать исследование</small></span></button><button onClick={() => onRoute('search')}><Search size={17}/><span>Проверить сведения<small>Открыть OSINT-инструменты</small></span></button></div>{!state.connection.canSend && <div className="connect-hint"><span className="status-dot"/>Настройте подключение к ИИ, чтобы начать диалог.<button onClick={() => onRoute('settings')}>Настроить</button></div>}</div> : state.messages.length > VIRTUAL_MESSAGE_THRESHOLD ? <VirtualMessages key={state.conversation_id} messages={state.messages} conversation={state.conversation_id} focus={state.message_focus} scroll={scroll} pinned={pinned} onRange={observeMounted} render={message => <MessageRow state={message.id === lastModel ? state : undefined} key={message.id} message={message} lastModel={message.id === lastModel} busy={message.id === lastModel && state.busy} onSource={onSource}/>}/> : state.messages.map(message => <MessageRow state={message.id === lastModel ? state : undefined} key={message.id} message={message} lastModel={message.id === lastModel} busy={message.id === lastModel && state.busy} onSource={onSource}/>)}<ResearchBrowser state={state}/><ActivityBlock activity={state.activity} busy={state.busy}/>{state.investigation.canResume && !state.busy && <section className="resume-card task-status" role="status" aria-label="Состояние исследования"><div><strong>Исследование приостановлено</strong><p>{state.investigation.stop_reason || 'План и собранные доказательства сохранены.'}</p></div><Button variant="secondary" size="sm" onClick={() => void act('investigation_continue')}>Продолжить<ArrowUp size={13}/></Button></section>}</div></div><AnimatePresence>{away && <motion.div className="jump-latest" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><Button variant="secondary" size="sm" onClick={() => { pinned.current = true; setAway(false); scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'smooth' }) }}><ArrowDown size={14}/>К последнему сообщению</Button></motion.div>}</AnimatePresence><div className="composer-zone"><div className="composer-content chat-content-width"><AttachmentComposer state={state} showPicker={false}/>{dropError && <p role="alert" className="notice-inline notice-error">{dropError}</p>}{state.archiveError && <div className="notice-inline notice-error" role="alert">{state.archiveError}</div>}<div className="composer"><textarea ref={textarea} value={draft} onChange={event => setDraft(event.target.value)} placeholder="Сообщение Гермионе…" aria-label="Сообщение Гермионе" rows={1} disabled={sending} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send() } }}/><div className="composer-bottom"><div className="composer-tools"><AttachmentPicker state={state}/><span className="composer-provider"><span className={`status-dot ${state.connection.status === 'connected' ? 'is-connected' : ''}`}/>{state.connection.model || 'ИИ не подключён'}</span></div>{state.busy ? <IconButton label="Остановить ответ" className="send-button stop-button" onClick={() => void act('chat_stop')}><Square size={15} fill="currentColor"/></IconButton> : <IconButton label="Отправить сообщение" className="send-button" disabled={(!draft.trim() && !state.attachments?.length) || !state.connection.canSend || sending || state.attachment_busy} onClick={() => void send()}>{sending ? <LoaderCircle size={17} className="spin"/> : <ArrowUp size={18}/>}</IconButton>}</div></div><div className="composer-caption"><span>Enter — отправить<span className="caption-divider">·</span>Shift+Enter — новая строка</span><span>Проверяйте важные сведения</span></div></div></div></div>
}
