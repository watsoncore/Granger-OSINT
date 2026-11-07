import type {ReactNode} from 'react'
import {Search,X} from 'lucide-react'
import {Button} from './ui'

export function GraphCommandBar({open,query,onQuery,types,filters,layout}:{
  open:boolean;query:string;onQuery(value:string):void;types:ReactNode;filters:ReactNode;layout:ReactNode
}) {
  return <div className={`research-toolbar graph-command-bar ${open?'is-open':''}`} aria-label="Команды графа">
    <label className="graph-command-search"><Search size={16}/><input aria-label="Поиск на графе" placeholder="Найти объект…"
      value={query} onChange={event=>onQuery(event.target.value)}/>
      {query&&<Button variant="ghost" size="sm" aria-label="Очистить поиск на графе" onClick={()=>onQuery('')}><X size={14}/></Button>}
    </label>
    <div className="graph-command-type">{types}</div>{filters}<div className="graph-command-layout"><span className="graph-command-caption">Раскладка</span>{layout}</div>
  </div>
}
