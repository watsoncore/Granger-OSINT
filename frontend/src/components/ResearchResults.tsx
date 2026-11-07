import {Select,Details,Summary} from './ui'
import {useEffect,useMemo,useRef,useState} from 'react'
import {ChevronLeft,ChevronRight,ListFilter,X} from 'lucide-react'
import type {ResearchCanvasState,Source} from '../types'
import {toolName,executionLabel} from '../tool-presentation'
import {platformMark} from '../graph-cards'
import {Button,Badge} from './ui'
import {ResultsTable} from './ResultsTable'
import {CryptoIcon,entityCryptoIcon} from '../crypto-icons'

const ResultIcon=({row}:{row:Source})=>{const id=entityCryptoIcon({type:row.kind,attributes:row.details||{}});return id?<CryptoIcon id={id} size={20}/>:null}
type Preview=NonNullable<ResearchCanvasState['preview']>
const modes={gallery:'Галерея',table:'Таблица',graph:'Связи с запросом',timeline:'По времени'} as const
type Mode=keyof typeof modes
const observationTime=(row:Source)=>row.obtained_at&&Number.isFinite(Date.parse(row.obtained_at))?Date.parse(row.obtained_at):0

export function ResearchResults({preview,evidenceIds,onSource,onInsert,control,onExport,loadImage,toolLabel}:{preview:Preview;evidenceIds:string[];onSource(source:Source):void;onInsert(ids:string[]):Promise<unknown>;toolLabel?:string;
  control?:{open:boolean};onExport?(ids:string[]):Promise<unknown>;loadImage?(row:Source):Promise<string>
}){
  const [open,setOpen]=useState(false),[chosen,setChosen]=useState<string[]>([]),[query,setQuery]=useState(''),[page,setPage]=useState(0),[saving,setSaving]=useState(false),[error,setError]=useState('')
  const [mode,setMode]=useState<Mode>('table'),[sort,setSort]=useState<'source'|'title'|'date'>('source')
  const [images,setImages]=useState<Record<string,string>>({})
  const token=useRef(''),touched=useRef(false)
  useEffect(()=>{
    if(token.current!==preview.token){
      token.current=preview.token;touched.current=false;setOpen(false);setQuery('');setPage(0);setChosen([]);setImages({})
      setMode(preview.tool==='username_maigret'||preview.operation==='nft'?'gallery':'table')
    }
    if(!touched.current){const ids=preview.results.slice(0,100).map(row=>row.evidence_id);setChosen(previous=>previous.join('|')===ids.join('|')?previous:ids)}
  },[preview.token,preview.results])
  useEffect(()=>{if(control)setOpen(control.open)},[control])
  const chosenSet=useMemo(()=>new Set(chosen),[chosen]),existing=useMemo(()=>new Set(evidenceIds),[evidenceIds])
  const rows=useMemo(()=>{
    const term=query.toLocaleLowerCase()
    const visible=preview.results.filter(row=>(mode!=='timeline'||observationTime(row))&&
      (row.title+' '+row.url+' '+row.kind).toLocaleLowerCase().includes(term))
    if(mode==='timeline'||sort==='date')visible.sort((a,b)=>observationTime(b)-observationTime(a))
    else if(sort==='title')visible.sort((a,b)=>a.title.localeCompare(b.title))
    return visible
  },[preview.results,query,mode,sort])
  const pageSize=mode==='table'?100:24
  const duplicateCount=chosen.filter(id=>existing.has(id)).length,pages=Math.max(1,Math.ceil(rows.length/pageSize)),currentPage=Math.min(page,pages-1)
  const pageRows=useMemo(()=>rows.slice(currentPage*pageSize,(currentPage+1)*pageSize),[rows,currentPage,pageSize])
  useEffect(()=>{
    if(!open||mode!=='gallery'||!loadImage)return
    let alive=true
    const items=pageRows.filter(row=>row.details?.avatar_url||row.details?.image_url).slice(0,6)
    void (async()=>{
      for(const row of items){
        if(!alive)return
        const value=await loadImage(row).catch(()=>'')
        if(alive&&value)setImages(previous=>({...previous,[row.evidence_id]:value}))
      }
    })()
    return()=>{alive=false}
  },[open,mode,pageRows,loadImage])
  const setSelection=(ids:string[])=>{touched.current=true;setChosen(ids)}
  async function insert(){setSaving(true);setError('');try{if(await onInsert(chosen))setOpen(false)}catch(reason){setError(reason instanceof Error?reason.message:'Сохранение не подтверждено. Выбор оставлен для повторной попытки.')}finally{setSaving(false)}}
  return <section className={`research-preview results-drawer ${open?'is-open':''}`} aria-label="Находки исследования">
    <header><button className="research-preview-toggle" aria-label="Результаты для добавления" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>
      <ListFilter size={16}/><strong>{preview.running?'Поиск продолжается':'Найденные сведения'}</strong><Badge>{preview.results.length}</Badge>
    </button><span>{executionLabel(preview.status)}</span>{open&&<Button variant="ghost" size="sm" aria-label="Закрыть результаты" onClick={()=>setOpen(false)}><X size={15}/></Button>}</header>
    <div hidden={!open}>
      <p className="field-hint">Источник: {toolName(preview.tool,toolLabel)}. Выберите сведения для сохранения в расследовании.</p>
      {preview.error&&<p role="alert" className="notice-inline notice-error">{preview.error} Полученные записи доступны для добавления.</p>}
      {error&&<p role="alert">{error}</p>}
      {!!preview.limitations.length&&<Details><Summary>Ограничения источника · {preview.limitations.length}</Summary>
        {preview.limitations.map((text,index)=><p className="field-hint" key={index}>{text}</p>)}
      </Details>}
      <nav aria-label="Представление находок" className="results-modes">
        {(Object.keys(modes) as Mode[]).map(value=><Button key={value} size="sm" variant="ghost" aria-pressed={mode===value}
          onClick={()=>{setMode(value);setPage(0)}}>{modes[value]}</Button>)}
      </nav>
      <input className="results-filter" aria-label="Найти в результатах" placeholder="Название, ссылка или тип…" value={query} onChange={event=>{setQuery(event.target.value);setPage(0)}}/>
      {mode==='table'&&<label className="results-sort">Сортировка<Select aria-label="Сортировка" value={sort} onValueChange={selectedValue=>{setSort(selectedValue as typeof sort);setPage(0)}}>
        <option value="source">Порядок источника</option><option value="title">По названию</option><option value="date">По дате наблюдения</option>
      </Select></label>}
      <div className="research-preview-actions"><Button size="sm" variant="ghost" onClick={()=>setSelection(rows.map(row=>row.evidence_id))}>Выбрать все ({rows.length})</Button>
        <Button size="sm" variant="ghost" onClick={()=>setSelection([])}>Снять выбор</Button>
        {mode==='table'&&onExport&&<Button size="sm" variant="ghost" disabled={!chosen.length}
          onClick={()=>void onExport(chosen)}>Экспорт CSV</Button>}
        <Button size="sm" disabled={!chosen.length||saving} onClick={()=>void insert()}>Добавить выбранные ({chosen.length})</Button></div>
      <p className="results-selection-count" role="status">Выбрано {chosen.length} · новых наблюдений {chosen.length-duplicateCount} · уже сохранено {duplicateCount}</p>
      {!touched.current&&preview.results.length>100&&<p className="field-hint">Автоматически выбраны первые 100 записей. «Выбрать все» включает весь отфильтрованный список.</p>}
      {mode==='graph'&&<div className="results-query-hub">Объект поиска <span>→</span> Наблюдения по запросу</div>}
      {mode==='timeline'&&<p className="field-hint">Указано время получения наблюдения из источника.</p>}
      <div className={`research-preview-list results-mode-${mode}`}>{mode==='table'?<ResultsTable
        rows={pageRows} rowId={row=>row.evidence_id} label="Результаты исследования" selected={chosenSet}
        onActivate={onSource} rowLabel={row=>'Добавить: '+row.title}
        onToggle={(id,checked)=>setSelection(checked?[...chosen,id]:chosen.filter(value=>value!==id))}
        onTogglePage={(ids,checked)=>{const visible=new Set(ids);setSelection(checked?Array.from(new Set([...chosen,...ids])):chosen.filter(id=>!visible.has(id)))}}
        columns={[
          {id:'title',label:'Находка',value:row=>row.title,render:row=><div className="result-summary">
            <button className="select-option-title" onClick={()=>onSource(row)}><ResultIcon row={row}/>{row.title}</button><small title={row.url}>{row.url||row.kind}</small></div>},
          {id:'source',label:'Источник',width:'24%',value:row=>row.domain||row.kind},
          {id:'status',label:'Состояние',width:'20%',value:row=>existing.has(row.evidence_id)?'Сохранено':executionLabel(row.status)},
        ]}/>:pageRows.map(row=><article key={row.evidence_id}>
        <input type="checkbox" aria-label={'Добавить: '+row.title} checked={chosenSet.has(row.evidence_id)}
          onChange={event=>setSelection(event.target.checked?[...chosen,row.evidence_id]:chosen.filter(id=>id!==row.evidence_id))}/>
        {mode==='gallery'&&<span className="result-avatar" aria-hidden="true">
          {images[row.evidence_id]?<img alt="" src={images[row.evidence_id]}/>:platformMark(row.domain?.split('.')[0])}</span>}
        <div className="result-summary"><button className="select-option-title" onClick={()=>onSource(row)}><ResultIcon row={row}/>{row.title}</button>
          <small>{row.domain||row.kind}{existing.has(row.evidence_id)?' · сохранено':''}</small>
          {row.url&&<small title={row.url}>{row.url}</small>}
          {mode==='timeline'&&<time dateTime={row.obtained_at}>{new Date(observationTime(row)).toLocaleString('ru-RU')}</time>}
        </div>
        {!['found','detected','complete','completed','success','done','source_reported','read'].includes(row.status)&&<Badge>{executionLabel(row.status)}</Badge>}
      </article>)}</div>
      {!rows.length&&<p className="field-hint">{mode==='timeline'?'Нет наблюдений с датой.':'По текущему фильтру нет записей.'}</p>}
      <footer><Button size="sm" variant="ghost" aria-label="Предыдущая страница результатов" disabled={!currentPage} onClick={()=>setPage(currentPage-1)}><ChevronLeft size={14}/></Button>
        <span>{currentPage+1} / {pages} · {rows.length} записей</span>
        <Button size="sm" variant="ghost" aria-label="Следующая страница результатов" disabled={currentPage>=pages-1} onClick={()=>setPage(currentPage+1)}><ChevronRight size={14}/></Button></footer>
    </div>
  </section>
}
