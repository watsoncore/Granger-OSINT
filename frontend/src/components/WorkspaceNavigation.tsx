import {useEffect,useId,useRef,useState} from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {ArrowDown,ArrowRight,ArrowUp,Clock3,Command,FileText,FolderOpen,LayoutGrid,MessageSquare,PanelLeftClose,PanelLeftOpen,Plus,Search,Settings2,Wrench,X} from 'lucide-react'
import {act} from '../bridge'
import type {DesktopState,Route} from '../types'
import {Button,IconButton} from './ui'

export const navigation=[
  {id:'chat',label:'Гермиона',icon:MessageSquare},
  {id:'search',label:'Поиск',icon:Search},
  {id:'history',label:'История',icon:Clock3},
  {id:'canvas',label:'Canvas',icon:FileText},
  {id:'settings',label:'Настройки',icon:Settings2},
] as const

export type SearchDestination={panel:'canvas'|'catalog';id?:string;create?:boolean}

export function WorkspaceNavigation({state,route,compact,onRoute,onCompact,onSearch}:{
  state:DesktopState;route:Route;compact:boolean;onRoute(route:Route):void;onCompact():void;onSearch(destination:SearchDestination):void
}){
  const cases=state.research_canvas?.choices?.slice(0,4)||[]
  return <aside className={'sidebar'+(compact?' sidebar-compact':'')}>
    <div className="sidebar-top">
      <div className="navigation-identity"><LayoutGrid size={17}/><span>РАБОЧАЯ СРЕДА</span></div>
      <IconButton label={compact?'Развернуть навигацию':'Свернуть навигацию'} className="collapse-sidebar" onClick={onCompact}>
        {compact?<PanelLeftOpen size={16}/>:<PanelLeftClose size={16}/>}
      </IconButton>
    </div>
    <nav aria-label="Основная навигация" className="workspace-nav">
      {navigation.filter(item=>item.id!=='settings').map(item=>
        <button key={item.id} className={'nav-item'+(route===item.id?' is-active':'')} aria-current={route===item.id?'page':undefined}
          aria-label={item.label} onClick={()=>onRoute(item.id)} title={item.label}><item.icon size={18}/><span>{item.label}</span></button>)}
    </nav>
    <div className="sidebar-cases">
      <div className="sidebar-section-label"><span>РАССЛЕДОВАНИЯ</span><IconButton label="Новое расследование" onClick={()=>onSearch({panel:'canvas',create:true})}><Plus size={16}/></IconButton></div>
      <button className="nav-item sidebar-open-cases" aria-label="Открыть мои расследования" title="Мои расследования"
        onClick={()=>onSearch({panel:'canvas'})}><FolderOpen size={17}/><span>Мои расследования</span></button>
      {cases.map(item=><button className="sidebar-case" key={item.id} title={item.title} onClick={()=>onSearch({panel:'canvas',id:item.id})}>
        <span className="sidebar-case-dot"/><span>{item.title}</span><ArrowRight size={13}/></button>)}
    </div>
    <div className="sidebar-bottom">
      <Button variant="secondary" className="new-chat" disabled={state.busy} onClick={()=>{onRoute('chat');void act('chat_new')}} aria-label="Новый диалог" title="Новый диалог"><Plus size={16}/><span>Новый диалог</span></Button>
      <button className={'nav-item'+(route==='settings'?' is-active':'')} onClick={()=>onRoute('settings')}
        aria-current={route==='settings'?'page':undefined} aria-label="Настройки" title="Настройки"><Settings2 size={17}/><span>Настройки</span></button>
      <div className="connection-mini" title={state.connection.error||state.connection.status}>
        <span className={'status-dot'+(state.busy?' is-working':state.connection.status==='connected'?' is-connected':'')}/>
        <div><strong>{state.busy?'Гермиона работает':state.connection.status==='connected'?'ИИ подключён':state.connection.canSend?'Готов к проверке':'ИИ не подключён'}</strong>
          <small>{state.connection.model||'Настройте провайдера'}</small></div>
      </div>
    </div>
  </aside>
}

export function CommandPalette({open,state,onClose,onRoute,onSearch}:{
  open:boolean;state:DesktopState;onClose():void;onRoute(route:Route):void;onSearch(destination:SearchDestination):void
}){
  const [query,setQuery]=useState(''),[active,setActive]=useState(0)
  const list=useId()
  const field=useRef<HTMLInputElement>(null)
  useEffect(()=>{if(open){setQuery('');setActive(0)}},[open])
  const actions=[
    ...navigation.map(item=>({key:item.id,label:item.label,group:'Раздел',icon:item.icon,run:()=>onRoute(item.id)})),
    {key:'cases',label:'Мои расследования',group:'Полотно',icon:FolderOpen,run:()=>onSearch({panel:'canvas'})},
    {key:'new-case',label:'Новое расследование',group:'Полотно',icon:Plus,run:()=>onSearch({panel:'canvas',create:true})},
    {key:'tools',label:'Каталог инструментов',group:'OSINT',icon:Wrench,run:()=>onSearch({panel:'catalog'})},
    ...(state.research_canvas?.choices||[]).map(item=>({key:item.id,label:item.title,group:'Расследование',icon:FolderOpen,run:()=>onSearch({panel:'canvas',id:item.id})})),
  ]
  const terms=query.toLocaleLowerCase().trim().split(/\s+/)
  const visible=actions.filter(item=>terms.every(term=>(item.label+' '+item.group).toLocaleLowerCase().includes(term))).slice(0,25)
  const selected=Math.min(active,visible.length-1)
  const execute=(index:number)=>{if(!visible[index])return;visible[index].run();onClose()}
  return <Dialog.Root open={open} onOpenChange={next=>{if(!next)onClose()}}>
    <Dialog.Portal><Dialog.Overlay className="dialog-overlay"/>
      <Dialog.Content className="dialog command-palette" onOpenAutoFocus={event=>{event.preventDefault();field.current?.focus()}} onEscapeKeyDown={()=>onClose()}>
        <header><Command size={17}/><Dialog.Title>Быстрый переход</Dialog.Title><Dialog.Close asChild><IconButton label="Закрыть быстрый переход"><X size={16}/></IconButton></Dialog.Close></header>
        <Dialog.Description className="command-description">Разделы, расследования и каталог инструментов</Dialog.Description>
        <div className="command-input"><Search size={18}/><input ref={field} aria-label="Поиск команд" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls={list}
          aria-activedescendant={selected>=0?list+'-'+selected:undefined} value={query} placeholder="Куда перейти?"
          onChange={event=>{setQuery(event.target.value);setActive(0)}}
          onKeyDown={event=>{
            if(event.key==='Enter'){event.preventDefault();execute(selected)}
            if(event.key==='ArrowDown'||event.key==='ArrowUp'){
              event.preventDefault()
              const next=Math.max(0,Math.min(visible.length-1,selected+(event.key==='ArrowDown'?1:-1)))
              setActive(next);document.getElementById(list+'-'+next)?.scrollIntoView({block:'nearest'})
            }
          }}/></div>
        <div id={list} role="listbox" aria-label="Доступные команды" className="command-list">
          {visible.map((item,index)=><button id={list+'-'+index} role="option" tabIndex={-1} aria-selected={index===selected} key={item.key} onMouseEnter={()=>setActive(index)} onClick={()=>execute(index)}>
            <item.icon size={17}/><span>{item.label}</span><small>{item.group}</small></button>)}
          {!visible.length&&<p>Команды не найдены.</p>}
        </div>
        <footer><span><ArrowUp size={13}/><ArrowDown size={13}/>Выбор</span><span><kbd>Enter</kbd> Открыть</span><span><kbd>Esc</kbd> Закрыть</span></footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
