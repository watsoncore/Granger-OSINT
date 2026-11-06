import { Clock3, X } from 'lucide-react'
import type { CanvasActivityEvent } from '../types'
import { toolName } from '../tool-presentation'
import { Button } from './ui'

const labels:Record<CanvasActivityEvent['kind'],string> = {
  created:'Создано расследование',node:'Добавлен объект',link:'Сохранена связь',group:'Создана группа',
  image:'Добавлено изображение',rename:'Изменено название',findings:'Добавлены наблюдения',
}

export function CanvasActivity({events,onClose,onFocus,available}:{
  events:CanvasActivityEvent[];onClose():void;onFocus(ids:string[]):void;available(id:string):boolean
}) {
  return <aside className="canvas-activity" aria-label="История расследования">
    <header><Clock3 size={17}/><h3>История расследования</h3><Button size="sm" variant="ghost" aria-label="Закрыть историю"
      onClick={onClose}><X size={15}/></Button></header>
    {!events.length?<p className="field-hint">Новые действия появятся здесь после сохранения.</p>:
      <ol>{[...events].reverse().map(event=>{
        const ids=event.ids.filter(available),date=new Date(event.at)
        return <li key={event.id}><time dateTime={event.at}>{Number.isFinite(date.valueOf())?date.toLocaleString('ru-RU'):event.at}</time>
          <strong>{labels[event.kind]}</strong>
          {event.kind==='findings'&&<small>{event.count} · {event.tool?toolName(event.tool):'Источник расследования'}</small>}
          {!!ids.length&&<Button size="sm" variant="ghost" onClick={()=>onFocus(ids)}>Показать связанные объекты</Button>}
        </li>
      })}</ol>}
  </aside>
}
