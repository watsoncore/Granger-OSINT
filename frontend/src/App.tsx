import { useCallback, useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { ArrowUpRight, Bell, BookOpen, ChevronRight, Clock3, Compass, FileText, LoaderCircle, Maximize, MessageSquare, Minimize2, Minus, PanelLeftClose, PanelLeftOpen, Plus, Search, Settings2, ShieldCheck, Square, Trash2, X } from 'lucide-react'
import { act, dismissNotice, useDesktop } from './bridge'
import type { DesktopState, Route, Source } from './types'
import { Chat } from './components/Chat'
import { SearchWorkspace } from './components/Search'
import { CanvasWorkspace } from './components/Canvas'
import { HistoryWorkspace } from './components/History'
import { SettingsWorkspace } from './components/Settings'
import { Launcher } from './components/Launcher'
import { Badge, Button, IconButton } from './components/ui'
import { SourceCard, SourceDialog } from './components/Sources'

const navigation = [
  { id: 'chat', label: 'Гермиона', icon: MessageSquare },
  { id: 'search', label: 'Поиск', icon: Search },
  { id: 'history', label: 'История', icon: Clock3 },
  { id: 'canvas', label: 'Canvas', icon: FileText },
] as const
const routeTitles: Record<Route, string> = { chat: 'Диалог с Гермионой', search: 'Поиск и OSINT-инструменты', history: 'История', canvas: 'Canvas', settings: 'Настройки' }
const hermioneStates: Record<string, string> = { idle: 'Рядом с вами', thinking: 'Обдумывает ответ', working: 'Исследует источники', reading: 'Читает', sleeping: 'Отдыхает', happy: 'Ответ готов', error: 'Нужно ваше внимание', walking: 'Прогуливается' }

function WindowTitlebar({ state }: { state: DesktopState }) {
  return <header className="titlebar" onPointerDown={event => { if (event.button === 0 && !(event.target as HTMLElement).closest('button')) void act('window', { mode: 'drag' }) }} onDoubleClick={event => { if (!(event.target as HTMLElement).closest('button')) void act('window', { mode: 'maximize' }) }}><div className="product-brand"><span className="product-icon"><Compass size={17}/></span><span>Granger<span className="brand-dash">-</span><strong>OSINT</strong></span></div><span className="titlebar-context">{state.surface === 'launcher' ? 'Настольный ассистент' : 'Рабочее пространство'}</span><div className="window-controls"><IconButton label="Свернуть окно" onClick={() => void act('window', { mode: 'minimize' })}><Minus size={15}/></IconButton><IconButton label={state.window.fullscreen ? 'Выйти из полноэкранного режима' : state.window.maximized ? 'Восстановить окно' : 'Развернуть окно'} onClick={() => void act('window', { mode: state.window.fullscreen ? 'fullscreen' : 'maximize' })}>{state.window.fullscreen || state.window.maximized ? <Minimize2 size={13}/> : <Square size={12}/>}</IconButton><IconButton label="Закрыть окно" className="window-close" onClick={() => void act('window', { mode: 'close' })}><X size={16}/></IconButton></div></header>
}

function Sidebar({ state, route, onRoute, compact, setCompact }: { state: DesktopState; route: Route; onRoute(route: Route): void; compact: boolean; setCompact(value: boolean): void }) {
  const history = state.history.slice(0, 5)
  return <aside className={`sidebar ${compact ? 'sidebar-compact' : ''}`}><div className="sidebar-top"><Button variant="secondary" className="new-chat" disabled={state.busy} onClick={() => void act('chat_new')}><Plus size={17}/><span>Новый диалог</span></Button><IconButton label={compact ? 'Развернуть навигацию' : 'Свернуть навигацию'} className="collapse-sidebar" onClick={() => setCompact(!compact)}>{compact ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}</IconButton></div><nav aria-label="Основная навигация">{navigation.map(item => <button key={item.id} className={`nav-item ${route === item.id ? 'is-active' : ''}`} onClick={() => onRoute(item.id)} title={item.label}><item.icon size={18}/><span>{item.label}</span>{route === item.id && <motion.span className="nav-indicator" layoutId="nav-indicator" transition={{ type: 'spring', stiffness: 480, damping: 38 }}/>}</button>)}</nav><div className="sidebar-divider"/>{!!history.length && <div className="sidebar-history"><span className="eyebrow">НЕДАВНИЕ ДИАЛОГИ</span>{history.map(item => <button key={item.id} disabled={state.busy} onClick={() => void act('history_load', { id: item.id })} title={item.title}><MessageSquare size={13}/><span>{item.title || 'Диалог с Гермионой'}</span></button>)}</div>}<div className="sidebar-bottom"><button className={`nav-item ${route === 'settings' ? 'is-active' : ''}`} onClick={() => onRoute('settings')} title="Настройки"><Settings2 size={18}/><span>Настройки</span></button><div className="connection-mini" title={state.connection.error || state.connection.status}><span className={`status-dot ${state.connection.canSend ? 'is-connected' : ''}`}/><div><strong>{state.connection.canSend ? 'ИИ подключён' : 'ИИ не подключён'}</strong><small>{state.connection.model || 'Настройте провайдера'}</small></div></div></div></aside>
}

function HermioneDock({ state, onSource, onRoute }: { state: DesktopState; onSource(source: Source): void; onRoute(route: Route): void }) {
  const dock = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const report = () => { if (timer) clearTimeout(timer); timer = setTimeout(() => { const rect = dock.current?.getBoundingClientRect(); if (rect) void act('layout', { dock: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } }) }, 100) }
    const observer = new ResizeObserver(report)
    if (dock.current) observer.observe(dock.current)
    window.addEventListener('resize', report); report()
    return () => { observer.disconnect(); window.removeEventListener('resize', report); if (timer) clearTimeout(timer) }
  }, [])
  return <aside className="hermione-sidebar"><div className="companion-heading"><span className="eyebrow">ВАШ АССИСТЕНТ</span><h2>Гермиона</h2><span className="companion-status"><span className={`status-dot ${state.busy ? 'is-working' : state.hermione.visible ? 'is-connected' : ''}`}/>{state.busy ? 'Работает над задачей' : hermioneStates[state.hermione.state] || state.hermione.state || 'Настольный ассистент'}</span></div><div className="companion-stage" id="hermione-dock" ref={dock} aria-label="Место для нативной анимированной Гермионы"><div className="companion-ground"/>{!state.hermione.visible && <div className="companion-absent"><BookOpen size={28}/><p>Настольная Гермиона<br/>сейчас не запущена</p><Button variant="secondary" size="sm" onClick={() => void act('launcher_start')}>Запустить</Button></div>}</div><div className="companion-caption"><ShieldCheck size={13}/><p>Выводы опираются на источники.<br/>Неуверенность остаётся видимой.</p></div><div className="dock-context">{!!state.evidence.length ? <><div className="dock-section-heading"><strong>Источники задачи</strong><Badge>{state.evidence.length}</Badge></div>{state.evidence.slice(-3).map(source => <SourceCard key={source.evidence_id} source={source} compact onSelect={onSource}/>)}</> : <div className="dock-guide"><span className="eyebrow">РАБОЧИЙ ПОДХОД</span><p>Вопрос. Проверка.<br/>Связи. Вывод.</p><button onClick={() => onRoute('search')}>Открыть инструменты<ArrowUpRight size={13}/></button></div>}</div><button className="dock-notification-settings" onClick={() => onRoute('settings')}><Bell size={13}/>Уведомления и анимации<ChevronRight size={13}/></button></aside>
}

export default function App() {
  const { state, connected, notice } = useDesktop()
  const [route, setRoute] = useState<Route>(state.route)
  const [compact, setCompact] = useState(false)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<Source | null>(null)
  const [clearOpen, setClearOpen] = useState(false)
  useEffect(() => setRoute(state.route), [state.route])
  useEffect(() => { if (connected) void act('ui_ready', { surface: state.surface }) }, [connected, state.surface])
  const onRoute = useCallback((next: Route) => { setRoute(next); void act('route', { route: next }) }, [])
  const onSource = useCallback((next: Source) => setSource(next), [])
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'F11') { event.preventDefault(); void act('window', { mode: 'fullscreen' }) }
      if (event.key === 'Escape' && state.window.fullscreen) { event.preventDefault(); void act('window', { mode: 'fullscreen' }) }
      if (event.ctrlKey && event.key.toLowerCase() === 'b') { event.preventDefault(); setCompact(previous => !previous) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [state.window.fullscreen])
  if (!connected) return <Tooltip.Provider delayDuration={350}><div className="desktop-app surface-loading"><WindowTitlebar state={state}/><div className="app-bootstrap" role="status">{notice ? <Compass size={27}/> : <LoaderCircle size={25} className="spin"/>}<h1>Granger-OSINT</h1><p>{notice || 'Подключение к приложению…'}</p></div></div></Tooltip.Provider>
  return <MotionConfig reducedMotion={state.settings.reduced_motion ? 'always' : 'user'} transition={{ duration: 0.18 }}><Tooltip.Provider delayDuration={350}><div className={`desktop-app surface-${state.surface} ${compact ? 'is-compact' : ''}`}><WindowTitlebar state={state}/>{state.surface === 'launcher' ? <Launcher state={state}/> : <div className="main-layout"><Sidebar state={state} route={route} onRoute={onRoute} compact={compact} setCompact={setCompact}/><main className="main-workspace"><header className="workspace-header"><div><h2>{routeTitles[route]}</h2><span>{route === 'chat' ? state.busy ? 'Гермиона отвечает' : state.connection.canSend ? 'Готова помочь с исследованием' : state.connection.status : route === 'canvas' ? 'Документы и выводы исследования' : 'Granger-OSINT'}</span></div><div className="workspace-header-actions">{route === 'chat' && <IconButton label="Очистить текущий диалог" disabled={state.busy || !state.messages.length} onClick={() => setClearOpen(true)}><Trash2 size={16}/></IconButton>}<IconButton label={state.window.fullscreen ? 'Выйти из полного экрана' : 'Полный экран · F11'} onClick={() => void act('window', { mode: 'fullscreen' })}><Maximize size={15}/></IconButton><IconButton label="Настройки" onClick={() => onRoute('settings')}><Settings2 size={17}/></IconButton></div></header><div className="route-container"><AnimatePresence mode="wait" initial={false}><motion.section key={route} className={`route route-${route}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -3 }} transition={{ duration: 0.12 }}>{route === 'chat' && <Chat state={state} draft={draft} setDraft={setDraft} onSource={onSource} onRoute={onRoute}/>} {route === 'search' && <SearchWorkspace state={state} query={query} setQuery={setQuery} onSource={onSource}/>} {route === 'history' && <HistoryWorkspace state={state}/>} {route === 'canvas' && <CanvasWorkspace state={state}/>} {route === 'settings' && <SettingsWorkspace state={state}/>}</motion.section></AnimatePresence></div></main><HermioneDock state={state} onSource={onSource} onRoute={onRoute}/></div>}{!connected && <div className="offline-indicator" role="status">Связь с приложением не установлена</div>}<AnimatePresence>{notice && <motion.div className="toast" role="alert" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}><span>{notice}</span><IconButton label="Закрыть сообщение" onClick={dismissNotice}><X size={15}/></IconButton></motion.div>}</AnimatePresence><SourceDialog source={source} onClose={() => setSource(null)}/><Dialog.Root open={clearOpen} onOpenChange={setClearOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="dialog confirm-dialog"><Dialog.Title>Очистить текущий диалог?</Dialog.Title><Dialog.Description>Сообщения текущей беседы и её контекст будут удалены. Остальные диалоги в истории останутся.</Dialog.Description><div className="dialog-actions"><Dialog.Close asChild><Button variant="secondary">Отмена</Button></Dialog.Close><Button variant="danger" onClick={() => { void act('chat_clear'); setClearOpen(false) }}>Очистить диалог</Button></div></Dialog.Content></Dialog.Portal></Dialog.Root></div></Tooltip.Provider></MotionConfig>
}
