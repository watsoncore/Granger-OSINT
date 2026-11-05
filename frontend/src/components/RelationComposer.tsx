import {useEffect,useRef,useState} from 'react'
import type {GraphEntity,GraphRelation,Source} from '../types'
import {Button} from './ui'

const kinds={potentially_related:'Возможная связь',same_owner_hypothesis:'Предположительно общий владелец',works_for:'Работает в организации',associated_with:'Связан с',references:'Ссылается на',transferred_to:'Перевод средств',custom:'Другая связь'}
export function RelationComposer({from,to,relation,evidence,onSave,onClose}:{from:GraphEntity;to:GraphEntity;relation?:GraphRelation;evidence:Source[];onSave(args:Record<string,unknown>):Promise<unknown>;onClose():void}){
  const [kind,setKind]=useState(relation?.relation_type||'potentially_related'),[custom,setCustom]=useState('')
  const [direction,setDirection]=useState(relation?.direction||'directed'),[color,setColor]=useState(String(relation?.attributes?.color||'#d2b383'))
  const [stroke,setStroke]=useState(String(relation?.attributes?.stroke||'dashed')),[width,setWidth]=useState(Number(relation?.attributes?.width)||1.6)
  const [confidence,setConfidence]=useState(String(relation?.attributes?.analyst_confidence??'')),[source,setSource]=useState(relation?.source_urls?.[0]||'')
  const [note,setNote]=useState(String(relation?.attributes?.analyst_note||'')),[ids,setIds]=useState(relation?.evidence_ids||[])
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  const dialog=useRef<HTMLElement>(null)
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.querySelector<HTMLElement>('select')?.focus();return()=>{if(previous?.isConnected)previous.focus()}},[])
  async function save(){setBusy(true);setError('');try{const accepted=await onSave({from_id:from.id,to_id:to.id,relation_type:kind==='custom'?custom:kind,
    direction,color,stroke,width,confidence:confidence===''?null:Number(confidence),source_url:source,note,evidence_ids:ids,status:'inferred',...(relation?{relation_id:relation.id}:{})});if(accepted)onClose();else setError('Сохранение не подтверждено. Введённые значения оставлены.')}catch(reason){setError(reason instanceof Error?reason.message:'Не удалось сохранить связь.')}finally{setBusy(false)}}
  return <div className="canvas-modal-shade" onKeyDown={event=>{event.stopPropagation();if(event.key==='Escape'){onClose();return}if(event.key==='Tab'){const items=[...dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary')||[]].filter(item=>item.getClientRects().length);const index=items.indexOf(document.activeElement as HTMLElement),next=event.shiftKey?index-1:index+1;if(next<0||next>=items.length){event.preventDefault();items[event.shiftKey?items.length-1:0]?.focus()}}}}>
    <section ref={dialog} role="dialog" aria-modal="true" aria-label={relation?'Изменить связь':'Новая связь'} className="relation-composer">
      <header><h3>{relation?'Изменить связь':'Новая связь'}</h3><Button variant="ghost" aria-label="Закрыть связь" onClick={onClose}>×</Button></header>
      <p className="relation-endpoints"><strong>{from.label}</strong><span>→</span><strong>{to.label}</strong></p>
      <label>Что связывает объекты<select autoFocus aria-label="Вид связи" value={kind in kinds?kind:'custom'} onChange={event=>setKind(event.target.value)}>{Object.entries(kinds).map(([id,label])=><option value={id} key={id}>{label}</option>)}</select></label>
      {(kind==='custom'||!(kind in kinds))&&<label>Описание связи<input aria-label="Своя связь" value={kind==='custom'?custom:kind} maxLength={100} onChange={event=>{setKind('custom');setCustom(event.target.value)}}/></label>}
      <div className="relation-fields"><label>Направление<select aria-label="Направление связи" value={direction} onChange={event=>setDirection(event.target.value)}><option value="directed">От первого ко второму →</option><option value="undirected">Без направления —</option><option value="bidirectional">В обе стороны ↔</option></select></label>
        <label>Линия<select aria-label="Стиль связи" value={stroke} onChange={event=>setStroke(event.target.value)}><option value="solid">Сплошная</option><option value="dashed">Штриховая</option><option value="dotted">Точечная</option></select></label>
        <label>Цвет<input aria-label="Цвет связи" type="color" value={color} onChange={event=>setColor(event.target.value)}/></label><label>Толщина<input aria-label="Толщина связи" type="number" min={0.5} max={6} step={0.5} value={width} onChange={event=>setWidth(Number(event.target.value))}/></label></div>
      <label>Уверенность аналитика, 0–100<input aria-label="Уверенность аналитика" type="number" min={0} max={100} value={confidence} onChange={event=>setConfidence(event.target.value)} placeholder="Не оценена"/></label>
      <small>Субъективная оценка. Ручная связь остаётся гипотезой и не становится подтверждённым фактом.</small>
      <label>Ссылка на основание<input aria-label="Источник связи" type="url" placeholder="https://…" value={source} onChange={event=>setSource(event.target.value)}/></label>
      {!!evidence.length&&<details><summary>Наблюдения в расследовании ({evidence.length})</summary><div className="relation-evidence">{evidence.map(row=><label key={row.evidence_id}><input type="checkbox" checked={ids.includes(row.evidence_id)} onChange={event=>setIds(event.target.checked?[...ids,row.evidence_id]:ids.filter(id=>id!==row.evidence_id))}/>{row.title}</label>)}</div></details>}
      <label>Комментарий<textarea aria-label="Комментарий к связи" value={note} onChange={event=>setNote(event.target.value)} maxLength={10000}/></label>
      {error&&<p role="alert">{error}</p>}<footer><Button variant="ghost" disabled={busy} onClick={onClose}>Отмена</Button><Button disabled={busy||kind==='custom'&&!custom.trim()} onClick={()=>void save()}>{busy?'Сохранение…':'Сохранить связь'}</Button></footer>
    </section>
  </div>
}
