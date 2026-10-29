import { memo, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowDown, ArrowUp, Check, ChevronDown, Copy, FileText, LoaderCircle, RefreshCw, Search, ShieldCheck, Square, WandSparkles } from 'lucide-react'
import { act } from '../bridge'
import type { Activity, DesktopState, Message, Source } from '../types'
import { ActionsMenu, Badge, Button, IconButton, MenuItem } from './ui'
import { Markdown } from './Markdown'
import { SourceDialog, Sources } from './Sources'
import { inputLabel, toolName } from '../tool-presentation'

const activityLabels: Record<string, string> = { complete: 'Завершено', partial: 'Частичные данные', empty: 'Совпадений нет', unavailable: 'Недоступен', auth_required: 'Нужна авторизация', invalid_arguments: 'Запрос отклонён', blocked: 'Доступ запрещён', timeout: 'Истекло время', running: 'Выполняется', started: 'Выполняется', success: 'Завершено', completed: 'Завершено', done: 'Завершено', error: 'Ошибка', failed: 'Ошибка', cancelled: 'Остановлено', stopped: 'Остановлено', pending: 'Ожидание', waiting: 'Ожидание' }
export function ActivityBlock({ activity, busy }: { activity: Activity[]; busy: boolean }) {
  const [expanded, setExpanded] = useState(true)
  const [source, setSource] = useState<Source | null>(null)
  if (!activity.length && !busy) return null
  const running = activity.filter(item => ['running', 'started'].includes(item.status))
  return <div className="activity-block"><button className="activity-heading" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{busy ? <LoaderCircle size={15} className="spin"/> : <ShieldCheck size={15}/>}<span>{running.at(-1)?.summary || (busy ? 'Гермиона работает над ответом' : 'Действия исследования')}</span>{!!activity.length && <span className="count">{activity.length}</span>}<ChevronDown size={14} className={expanded ? 'rotate' : ''}/></button><AnimatePresence initial={false}>{expanded && !!activity.length && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="activity-rows">{activity.map(item => <div className="activity-row" key={item.id}><span className={`activity-dot status-${item.status}`}/><span><strong>{toolName(item.tool)}{item.inputType && <span className="activity-input"> · {inputLabel(item.inputType)}</span>}</strong><small>{item.summary}</small>{typeof item.resultCount === 'number' && <small>Результатов: {item.resultCount}</small>}{(item.error || item.details || item.evidenceIds?.length) && <details className="activity-details"><summary>Подробности вызова</summary>{item.error && <p className="text-danger">{item.error}</p>}{item.details && <pre>{JSON.stringify(item.details, null, 2)}</pre>}{item.evidenceIds?.map(id => <button key={id} onClick={() => void act('source_open', { evidence_id: id }).then(result => { if (result && typeof result === 'object' && 'evidence_id' in result) setSource(result as Source) })}>Открыть доказательство</button>)}</details>}</span><Badge tone={['error', 'failed'].includes(item.status) ? 'danger' : ['success', 'completed', 'done'].includes(item.status) ? 'success' : 'neutral'}>{activityLabels[item.status] || item.status}</Badge></div>)}</motion.div>}</AnimatePresence><SourceDialog source={source} onClose={() => setSource(null)}/></div>
}

const MessageRow = memo(function MessageRow({ message, lastModel, busy, onSource }: { message: Message; lastModel: boolean; busy: boolean; onSource(source: Source): void }) {
  const [copied, setCopied] = useState(false)
  const content = useRef<HTMLDivElement>(null)
  const copy = (markdown = false) => void act('copy', { text: markdown ? message.text : content.current?.innerText || message.text }).then(result => { if (result !== null) { setCopied(true); setTimeout(() => setCopied(false), 1800) } })
  if (message.role === 'status') return <div className="message-status" data-message-id={message.id}>{message.text}</div>
  return <motion.article className={`message message-${message.role}`} data-message-id={message.id} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}><div className="message-byline">{message.role === 'model' ? <><span className="hermione-mark"><WandSparkles size={12}/></span>Гермиона{message.streaming && <span className="streaming-label">отвечает</span>}</> : 'Вы'}</div><div ref={content} className="message-content">{message.role === 'user' ? <div className="user-text">{message.text}</div> : <Markdown text={message.text} onSource={id => { const source = message.sources?.find(item => item.evidence_id === id); if (source) onSource(source); else void act('source_open', { evidence_id: id }) }}/>}</div>{message.role === 'model' && !!message.sources?.length && <Sources sources={message.sources} onSelect={onSource}/>}<div className="message-actions"><IconButton label={copied ? 'Скопировано' : 'Копировать'} onClick={() => copy()}>{copied ? <Check size={14}/> : <Copy size={14}/>}</IconButton>{message.role === 'model' && <><IconButton label="Открыть в Canvas" disabled={!message.text} onClick={() => void act('canvas_open', { message_id: message.id })}><FileText size={14}/></IconButton>{lastModel && <IconButton label="Повторить ответ" disabled={busy} onClick={() => void act('chat_regenerate', { message_id: message.id })}><RefreshCw size={14}/></IconButton>}<ActionsMenu label="Ещё действия с ответом"><MenuItem onSelect={() => copy(true)}><Copy size={14}/>Скопировать Markdown</MenuItem>{message.streaming && <MenuItem onSelect={() => void act('chat_stop')}><Square size={13}/>Остановить ответ</MenuItem>}</ActionsMenu></>}</div></motion.article>
})

export function Chat({ state, draft, setDraft, onSource, onRoute }: { state: DesktopState; draft: string; setDraft(value: string): void; onSource(source: Source): void; onRoute(route: DesktopState['route']): void }) {
  const scroll = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const pinned = useRef(true)
  const previousConversation = useRef(state.conversation_id)
  const [away, setAway] = useState(false)
  const [sending, setSending] = useState(false)
  const seenIds = useRef(new Set<string>())
  const seenConversation = useRef(state.conversation_id)
  const visibility = useRef<{ observer: IntersectionObserver; elements: Map<string, Element> } | null>(null)
  const observedRows = useRef<Message[]>([])
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
  useLayoutEffect(() => { if (textarea.current) { textarea.current.style.height = 'auto'; textarea.current.style.height = `${Math.min(148, textarea.current.scrollHeight)}px` } }, [draft])
  useEffect(() => { if (!state.busy) setSending(false) }, [state.busy])
  useEffect(() => {
    if (!state.message_focus) return
    const target = scroll.current?.querySelector(`[data-message-id="${CSS.escape(state.message_focus)}"]`)
    if (target) { pinned.current = false; target.scrollIntoView({ block: 'center', behavior: 'smooth' }) }
  }, [state.message_focus])
  const send = async () => {
    if (!draft.trim() || state.busy || sending || !state.connection.canSend) return
    setSending(true)
    const value = draft
    pinned.current = true; setAway(false)
    const result = await act('chat_send', { text: value })
    if (result !== null) setDraft('')
    setSending(false)
  }
  return <div className="chat-workspace"><div className="chat-scroll" ref={scroll} onScroll={() => { const el = scroll.current; if (el) { pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 90; setAway(!pinned.current) } }}><div className="conversation">{!state.messages.length ? <div className="chat-welcome"><span className="eyebrow">ВАШЕ ИССЛЕДОВАНИЕ НАЧИНАЕТСЯ ЗДЕСЬ</span><h1>Давайте разберёмся.</h1><p>Гермиона поможет проверить открытые сведения,<br className="wide-only"/> сопоставить источники и увидеть главное.</p><div className="welcome-actions"><button onClick={() => { setDraft('Гермиона, помоги составить план исследования по открытым источникам.'); textarea.current?.focus() }}><FileText size={17}/><span>Составить план<small>С чего начать исследование</small></span></button><button onClick={() => onRoute('search')}><Search size={17}/><span>Проверить сведения<small>Открыть OSINT-инструменты</small></span></button></div>{!state.connection.canSend && <div className="connect-hint"><span className="status-dot"/>Настройте подключение к ИИ, чтобы начать диалог.<button onClick={() => onRoute('settings')}>Настроить</button></div>}</div> : state.messages.map(message => <MessageRow key={message.id} message={message} lastModel={message.id === lastModel} busy={message.id === lastModel && state.busy} onSource={onSource}/>)}<ActivityBlock activity={state.activity} busy={state.busy}/>{state.investigation.canResume && !state.busy && <div className="resume-card"><div><strong>Исследование можно продолжить</strong><p>{state.investigation.stop_reason || 'План и собранные доказательства сохранены.'}</p></div><Button variant="secondary" size="sm" onClick={() => void act('investigation_continue')}>Продолжить<ArrowUp size={13}/></Button></div>}</div></div><AnimatePresence>{away && <motion.div className="jump-latest" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><Button variant="secondary" size="sm" onClick={() => { pinned.current = true; setAway(false); scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'smooth' }) }}><ArrowDown size={14}/>К последнему сообщению</Button></motion.div>}</AnimatePresence><div className="composer-zone">{state.archiveError && <div className="notice-inline notice-error" role="alert">{state.archiveError}</div>}<div className="composer"><textarea ref={textarea} value={draft} onChange={event => setDraft(event.target.value)} placeholder="Спросите Гермиону или опишите задачу…" aria-label="Сообщение Гермионе" rows={1} disabled={sending} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send() } }}/><div className="composer-bottom"><span className="composer-provider"><span className={`status-dot ${state.connection.status === 'connected' ? 'is-connected' : ''}`}/>{state.connection.model || 'ИИ не подключён'}</span>{state.busy ? <IconButton label="Остановить ответ" className="send-button stop-button" onClick={() => void act('chat_stop')}><Square size={15} fill="currentColor"/></IconButton> : <IconButton label="Отправить сообщение" className="send-button" disabled={!draft.trim() || !state.connection.canSend || sending} onClick={() => void send()}>{sending ? <LoaderCircle size={17} className="spin"/> : <ArrowUp size={18}/>}</IconButton>}</div></div><div className="composer-caption"><span>Enter — отправить<span className="caption-divider">·</span>Shift+Enter — новая строка</span><span>Проверяйте важные сведения</span></div></div></div>
}
