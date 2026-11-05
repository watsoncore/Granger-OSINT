import { useCallback, useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { ArrowUpRight, Bell, BookOpen, ChevronRight, LoaderCircle, Maximize, PanelRightClose, PanelRightOpen, Search, ShieldCheck, Trash2, X } from 'lucide-react'
import { act, dismissNotice, request, useDesktop } from './bridge'
import type { DesktopState, Route, Source } from './types'
import { Chat } from './components/Chat'
import { SearchWorkspace } from './components/Search'
import { CanvasWorkspace } from './components/Canvas'
import { HistoryWorkspace } from './components/History'
import { SettingsWorkspace } from './components/Settings'
import { Launcher } from './components/Launcher'
import { Button, IconButton } from './components/ui'
import { SourceInspector, SourceDialog } from './components/Sources'
import { applyEffects, applyTheme } from './themes'
import { AppIcon } from './icons'

import { WorkspaceNavigation, CommandPalette, type SearchDestination } from './components/WorkspaceNavigation'
import { DensityControl } from './components/WorkspaceDensity'

const routeTitles: Record<Route, string> = { chat: 'Диалог с Гермионой', search: 'Поиск и OSINT-инструменты', history: 'История', canvas: 'Canvas', settings: 'Настройки' }
const hermioneStates: Record<string, string> = { idle: 'Рядом с вами', thinking: 'Обдумывает ответ', working: 'Исследует источники', reading: 'Читает', sleeping: 'Отдыхает', happy: 'Ответ готов', error: 'Нужно ваше внимание', walking: 'Прогуливается', listening: 'Слушает', searching: 'Ищет сведения', resting: 'Отдыхает', notification: 'Есть уведомление', shy: 'Смущена', annoyed: 'Недовольна' }

function WindowTitlebar({ state }: { state: DesktopState }) {
  return <header className="titlebar" onPointerDown={event => { if (event.button === 0 && !(event.target as HTMLElement).closest('button')) void act('window', { mode: 'drag' }) }} onDoubleClick={event => { if (!(event.target as HTMLElement).closest('button')) void act('window', { mode: 'maximize' }) }}><div className="product-brand"><span className="product-icon product-character-icon"><img src="./brand-hermione.png" alt="Гермиона · Granger-OSINT" draggable={false}/></span><span>Granger<span className="brand-dash">-</span><strong>OSINT</strong></span></div><span className="titlebar-context">{state.surface === 'launcher' ? 'Настольный ассистент' : 'Рабочее пространство'}</span><div className="window-controls"><IconButton label="Свернуть окно" onClick={() => void act('window', { mode: 'minimize' })}><AppIcon name="windowMinimize" size={16}/></IconButton><IconButton label={state.window.fullscreen ? 'Выйти из полноэкранного режима' : state.window.maximized ? 'Восстановить окно' : 'Развернуть окно'} onClick={() => void act('window', { mode: state.window.fullscreen ? 'fullscreen' : 'maximize' })}><AppIcon name={state.window.fullscreen || state.window.maximized ? 'windowRestore' : 'windowMaximize'} size={16}/></IconButton><IconButton label="Закрыть окно" className="window-close" onClick={() => void act('window', { mode: 'close' })}><AppIcon name="windowClose" size={16}/></IconButton></div></header>
}

function HermioneDock({ state, onSource, onRoute }: { state: DesktopState; onSource(source: Source): void; onRoute(route: Route): void }) {
  const dock = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const report = () => { if (timer) clearTimeout(timer); timer = setTimeout(() => { const rect = dock.current?.getBoundingClientRect(); if(document.querySelector('.investigation-workspace.is-expanded')) {void act('layout',{dock:null});return} if (rect) void act('layout', { dock: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } }) }, 100) }
    const observer = new ResizeObserver(report)
    if (dock.current) observer.observe(dock.current)
    window.addEventListener('resize', report);window.addEventListener('granger-workbench',report); report()
    return () => { observer.disconnect(); window.removeEventListener('resize', report);window.removeEventListener('granger-workbench',report); if (timer) clearTimeout(timer); void act('layout', { dock: null }) }
  }, [])
  return <aside className="hermione-sidebar"><div className="companion-heading"><h2>Гермиона</h2><span className="companion-status"><span className={`status-dot ${state.busy ? 'is-working' : state.hermione.visible ? 'is-connected' : ''}`}/>{state.busy ? 'Работает над задачей' : hermioneStates[state.hermione.state] || state.hermione.state || 'Настольный ассистент'}</span></div><div className="companion-stage" id="hermione-dock" ref={dock} aria-label="Место для нативной анимированной Гермионы"><div className="companion-ground"/>{!state.hermione.visible && <div className="companion-absent"><BookOpen size={28}/><p>Настольная Гермиона<br/>сейчас не запущена</p><Button variant="secondary" size="sm" onClick={() => void act('launcher_start')}>Запустить</Button></div>}</div><div className="companion-caption"><ShieldCheck size={13}/><p>Выводы опираются на источники. <br/>Неуверенность остаётся видимой.</p></div><div className="dock-context">{!!(state.task_sources ?? state.evidence).length ? <><SourceInspector sources={state.task_sources ?? state.evidence} onSelect={onSource} canFocus={source => state.messages.some(item => item.role === 'model' && item.sources?.some(record => record.evidence_id === source.evidence_id))} onFocus={source => { const message = state.messages.find(item => item.role === 'model' && item.sources?.some(record => record.evidence_id === source.evidence_id)); if (message) { onRoute('chat'); void act('message_focus', { message_id: message.id }) } }}/></> : <div className="dock-guide"><span className="eyebrow">РАБОЧИЙ ПОДХОД</span><p>Вопрос. Проверка.<br/>Связи. Вывод.</p><button onClick={() => onRoute('search')}>Открыть инструменты<ArrowUpRight size={13}/></button></div>}</div><button className="dock-notification-settings" onClick={() => onRoute('settings')}><Bell size={13}/>Уведомления и анимации<ChevronRight size={13}/></button></aside>
}

export default function App() {
  const { state, connected, notice } = useDesktop()
  const backendError = state.errors?.[0]
  const visibleNotice = notice || (backendError ? `${backendError.message}${backendError.count > 1 ? ` Повторений: ${backendError.count}.` : ''}` : '')
  const [route, setRoute] = useState<Route>(state.route)
  const [compact, setCompact] = useState(false)
  const [palette, setPalette] = useState(false)
  const [destination, setDestination] = useState<SearchDestination>()
  const effects=state.settings.ui_effects
  useEffect(()=>{if(connected)applyEffects(effects)},[connected,effects])
  useEffect(()=>{document.documentElement.dataset.motion=state.settings.reduced_motion?'reduced':'normal'},[state.settings.reduced_motion])
  useEffect(()=>{
    if(!connected||state.surface!=='main'||state.research_canvas||state.vault?.enabled&&!state.vault.unlocked)return
    const timer=setTimeout(()=>{void request('research_canvas_list').catch(()=>{})},400)
    return()=>clearTimeout(timer)
  },[connected,state.surface,!!state.research_canvas,state.vault?.enabled,state.vault?.unlocked])
  const [dockCollapsed, setDockCollapsed] = useState(() => window.innerWidth < 900)
  useEffect(() => { if (state.settings.ui_theme !== undefined) applyTheme(state.settings.ui_theme) }, [state.settings.ui_theme])
  useEffect(() => {
    const collapse = () => { if (window.innerWidth < 760) setDockCollapsed(true) }
    window.addEventListener('resize', collapse)
    return () => window.removeEventListener('resize', collapse)
  }, [])
  useEffect(() => { if (connected && state.surface === 'main' && dockCollapsed) void act('layout', { dock: null }) }, [dockCollapsed, connected, state.surface])
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<Source | null>(null)
  const [clearOpen, setClearOpen] = useState(false)
  useEffect(() => setRoute(state.route), [state.route])
  useEffect(() => setQuery(state.search.query), [state.search.query])
  useEffect(() => { if (connected) void act('ui_ready', { surface: state.surface }) }, [connected, state.surface])
  const onRoute = useCallback((next: Route) => { setRoute(next); void act('route', { route: next }) }, [])
  const onSearch=useCallback((next:SearchDestination)=>{setDestination(next);onRoute('search')},[onRoute])
  const clearDestination=useCallback((handled:SearchDestination)=>setDestination(current=>current===handled?undefined:current),[])
  const onSource = useCallback((next: Source) => setSource(next), [])
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&state.surface==='main') {
        event.preventDefault();setPalette(previous=>!previous);return
      }
      if (event.key === 'F11') { event.preventDefault(); void act('window', { mode: 'fullscreen' }) }
      if (event.key === 'Escape' && state.window.fullscreen) { event.preventDefault(); void act('window', { mode: 'fullscreen' }) }
      if (event.ctrlKey && event.key.toLowerCase() === 'b') { event.preventDefault(); setCompact(previous => !previous) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [state.window.fullscreen,state.surface])
  if (!connected) return <Tooltip.Provider delayDuration={350}><div className="desktop-app surface-loading"><WindowTitlebar state={state}/><div className="app-bootstrap" role="status">{notice ? <img className="bootstrap-character-icon" src="./brand-hermione.png" alt="Гермиона"/> : <LoaderCircle size={25} className="spin"/>}<h1>Granger-OSINT</h1><p>{notice || 'Подключение к приложению…'}</p></div></div></Tooltip.Provider>
  const working=state.busy||state.search.busy
  return <MotionConfig reducedMotion={state.settings.reduced_motion||effects==='off'?'always':'user'} transition={{duration:.16}}>
    <Tooltip.Provider delayDuration={350}>
      <div className={['desktop-app','surface-'+state.surface,compact?'is-compact':'',dockCollapsed?'is-dock-collapsed':''].join(' ')}>
        <WindowTitlebar state={state}/>
        {state.surface==='launcher'?<Launcher state={state}/>:<div className="main-layout">
          <WorkspaceNavigation state={state} route={route} compact={compact} onRoute={onRoute} onCompact={()=>setCompact(value=>!value)} onSearch={onSearch}/>
          <main className="main-workspace">
            <header className="workspace-header">
              <div className="workspace-identity">
                <div className="workspace-breadcrumb"><span>РАБОЧАЯ СРЕДА</span><ChevronRight size={12}/><span>{route==='canvas'?'Документы':route==='chat'?'Ассистент':route==='search'?'OSINT':route==='history'?'Архив':'Приложение'}</span></div>
                <h2>{routeTitles[route]}</h2>
              </div>
              <div className="workspace-header-actions">
                {working&&<span className="workspace-task" role="status"><span className="status-dot is-working"/>Идёт работа</span>}
                <Button className="command-trigger" variant="secondary" size="sm" aria-label="Быстрый переход" onClick={()=>setPalette(true)}>
                  <Search size={16}/><span>Быстрый переход</span><kbd>Ctrl K</kbd>
                </Button>
                <DensityControl/>
                <IconButton label={dockCollapsed?'Показать Гермиону и источники':'Свернуть панель Гермионы'} onClick={()=>setDockCollapsed(!dockCollapsed)}>
                  {dockCollapsed?<PanelRightOpen size={17}/>:<PanelRightClose size={17}/>}
                </IconButton>
                {route==='chat'&&<IconButton label="Очистить текущий диалог" disabled={state.busy||!state.messages.length} onClick={()=>setClearOpen(true)}><Trash2 size={16}/></IconButton>}
                <IconButton label={state.window.fullscreen?'Выйти из полного экрана':'Полный экран · F11'} onClick={()=>void act('window',{mode:'fullscreen'})}><Maximize size={15}/></IconButton>
              </div>
            </header>
            <div className="route-container">
              <section key={route} className={'route route-'+route}>
                {route==='chat'&&<Chat state={state} draft={draft} setDraft={setDraft} onSource={onSource} onRoute={onRoute}/>}
                {route==='search'&&<SearchWorkspace state={state} query={query} setQuery={setQuery} onSource={onSource} destination={destination} onDestinationHandled={clearDestination}/>}
                {route==='history'&&<HistoryWorkspace state={state}/>}
                {route==='canvas'&&<CanvasWorkspace state={state}/>}
                {route==='settings'&&<SettingsWorkspace state={state} category={state.settingsCategory}/>}
              </section>
            </div>
          </main>
          {!dockCollapsed&&<HermioneDock state={state} onSource={onSource} onRoute={onRoute}/>}
        </div>}
        {palette&&<CommandPalette open={palette} state={state} onClose={()=>setPalette(false)} onRoute={onRoute} onSearch={onSearch}/>}
        <AnimatePresence>{visibleNotice&&<motion.div className="toast" role="alert" initial={{opacity:0,y:6}} animate={{opacity:1,y:0}} exit={{opacity:0}}>
          <span>{visibleNotice}</span>
          <IconButton label="Закрыть сообщение" onClick={()=>{if(notice)dismissNotice();else if(backendError)void act('error_dismiss',{id:backendError.id})}}><X size={15}/></IconButton>
        </motion.div>}</AnimatePresence>
        <SourceDialog source={source} onClose={()=>setSource(null)}/>
        <Dialog.Root open={clearOpen} onOpenChange={setClearOpen}>
          <Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="dialog confirm-dialog">
            <Dialog.Title>Очистить текущий диалог?</Dialog.Title>
            <Dialog.Description>Сообщения текущей беседы и её контекст будут удалены. Остальные диалоги в истории останутся.</Dialog.Description>
            <div className="dialog-actions"><Dialog.Close asChild><Button variant="secondary">Отмена</Button></Dialog.Close>
              <Button variant="danger" onClick={()=>{void act('chat_clear');setClearOpen(false)}}>Очистить диалог</Button></div>
          </Dialog.Content></Dialog.Portal>
        </Dialog.Root>
      </div>
    </Tooltip.Provider>
  </MotionConfig>
}
