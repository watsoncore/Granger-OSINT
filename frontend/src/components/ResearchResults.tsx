import {useEffect,useMemo,useRef,useState} from 'react'
import {ChevronLeft,ChevronRight,ListFilter,X} from 'lucide-react'
import type {ResearchCanvasState,Source} from '../types'
import {toolName,executionLabel} from '../tool-presentation'
import {Button,Badge} from './ui'
type Preview=NonNullable<ResearchCanvasState['preview']>

export function ResearchResults({preview,evidenceIds,onSource,onInsert}:{preview:Preview;evidenceIds:string[];onSource(source:Source):void;onInsert(ids:string[]):Promise<unknown>}){
  const [open,setOpen]=useState(false),[chosen,setChosen]=useState<string[]>([]),[query,setQuery]=useState(''),[page,setPage]=useState(0),[saving,setSaving]=useState(false),[error,setError]=useState('')
  const token=useRef(''),touched=useRef(false)
  useEffect(()=>{
    if(token.current!==preview.token){token.current=preview.token;touched.current=false;setOpen(false);setQuery('');setPage(0);setChosen([])}
    if(!touched.current){const ids=preview.results.slice(0,100).map(row=>row.evidence_id);setChosen(previous=>previous.join('|')===ids.join('|')?previous:ids)}
  },[preview.token,preview.results])
  const chosenSet=useMemo(()=>new Set(chosen),[chosen]),existing=useMemo(()=>new Set(evidenceIds),[evidenceIds])
  const rows=useMemo(()=>preview.results.filter(row=>(row.title+' '+row.url+' '+row.kind).toLocaleLowerCase().includes(query.toLocaleLowerCase())),[preview.results,query])
  const duplicateCount=chosen.filter(id=>existing.has(id)).length,pages=Math.max(1,Math.ceil(rows.length/100)),currentPage=Math.min(page,pages-1)
  const setSelection=(ids:string[])=>{touched.current=true;setChosen(ids)}
  async function insert(){setSaving(true);setError('');try{if(await onInsert(chosen))setOpen(false)}catch(reason){setError(reason instanceof Error?reason.message:'Сохранение не подтверждено. Выбор оставлен для повторной попытки.')}finally{setSaving(false)}}
  return <section className={`research-preview results-drawer ${open?'is-open':''}`} aria-label="Находки исследования">
    <header><button className="research-preview-toggle" aria-label="Результаты для добавления" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>
      <ListFilter size={16}/><strong>{preview.running?'Поиск продолжается':'Найденные сведения'}</strong><Badge>{preview.results.length}</Badge>
    </button><span>{executionLabel(preview.status)}</span>{open&&<Button variant="ghost" size="sm" aria-label="Закрыть результаты" onClick={()=>setOpen(false)}><X size={15}/></Button>}</header>
    <div hidden={!open}>
      <p className="field-hint">Источник: {toolName(preview.tool)}. Выберите сведения для сохранения в расследовании.</p>
      {preview.error&&<p role="alert" className="notice-inline notice-error">{preview.error} Полученные записи доступны для добавления.</p>}
      {error&&<p role="alert">{error}</p>}
      {preview.limitations.map((text,index)=><p className="field-hint" key={index}>{text}</p>)}
      <input className="results-filter" aria-label="Найти в результатах" placeholder="Название, ссылка или тип…" value={query} onChange={event=>{setQuery(event.target.value);setPage(0)}}/>
      <div className="research-preview-actions"><Button size="sm" variant="ghost" onClick={()=>setSelection(rows.map(row=>row.evidence_id))}>Выбрать все ({rows.length})</Button>
        <Button size="sm" variant="ghost" onClick={()=>setSelection([])}>Снять выбор</Button>
        <Button size="sm" disabled={!chosen.length||saving} onClick={()=>void insert()}>Добавить выбранные ({chosen.length})</Button></div>
      <p className="results-selection-count" role="status">Выбрано {chosen.length} · новых наблюдений {chosen.length-duplicateCount} · уже сохранено {duplicateCount}</p>
      {!touched.current&&preview.results.length>100&&<p className="field-hint">Автоматически выбраны первые 100 записей. «Выбрать все» включает весь отфильтрованный список.</p>}
      <div className="research-preview-list">{rows.slice(currentPage*100,currentPage*100+100).map(row=><label key={row.evidence_id}>
        <input type="checkbox" aria-label={'Добавить: '+row.title} checked={chosenSet.has(row.evidence_id)} onChange={event=>setSelection(event.target.checked?[...chosen,row.evidence_id]:chosen.filter(id=>id!==row.evidence_id))}/>
        <button onClick={()=>onSource(row)}>{row.title}</button><small>{row.url||row.kind}{existing.has(row.evidence_id)?' · сохранено':''}</small>
      </label>)}</div>
      <footer><Button size="sm" variant="ghost" aria-label="Предыдущая страница результатов" disabled={!currentPage} onClick={()=>setPage(currentPage-1)}><ChevronLeft size={14}/></Button>
        <span>{currentPage+1} / {pages} · {rows.length} записей</span>
        <Button size="sm" variant="ghost" aria-label="Следующая страница результатов" disabled={currentPage>=pages-1} onClick={()=>setPage(currentPage+1)}><ChevronRight size={14}/></Button></footer>
    </div>
  </section>
}
