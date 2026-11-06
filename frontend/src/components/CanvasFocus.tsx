import {Select} from './ui'
import { ArrowLeft, Focus, RotateCcw, X } from 'lucide-react'
import { Button } from './ui'

export function CanvasFocus({label,depth,count,canBack,onDepth,onBack,onReset}:{
  label:string; depth:number; count:number; canBack:boolean
  onDepth(value:number):void; onBack():void; onReset():void
}) {
  return <div className="canvas-focus" aria-label="Режим фокуса">
    <Focus size={16}/><span><strong>{label}</strong><small>{count} объектов в фокусе</small></span>
    <Select aria-label="Глубина фокуса" value={depth} onValueChange={selectedValue=>onDepth(Number(selectedValue))}>
      <option value={1}>1 шаг</option><option value={2}>2 шага</option>
      <option value={3}>3 шага</option><option value={4}>Всё</option>
    </Select>
    <Button size="sm" variant="ghost" disabled={depth>=4} onClick={()=>onDepth(depth+1)}>Раскрыть соседей</Button>
    <Button size="sm" variant="ghost" aria-label="Предыдущий фокус" title="Предыдущий фокус" disabled={!canBack} onClick={onBack}><ArrowLeft size={15}/></Button>
    <Button size="sm" variant="ghost" aria-label="Сбросить глубину" title="Сбросить глубину" onClick={()=>onDepth(1)}><RotateCcw size={14}/></Button>
    <Button size="sm" variant="ghost" aria-label="Выйти из фокуса" title="Выйти из фокуса" onClick={onReset}><X size={15}/></Button>
  </div>
}
