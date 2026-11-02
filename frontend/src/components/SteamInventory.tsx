import {useEffect,useMemo,useRef,useState} from 'react'
import {useVirtualizer} from '@tanstack/react-virtual'
import type {GraphEntity,SteamInventorySummary} from '../types'
import {Button} from './ui'
import './inventory.css'

const object=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{}
const text=(value:unknown)=>typeof value==='string'||typeof value==='number'?String(value):'—'
export function SteamInventory({summaries,nodes,onOpen,onMedia}:{summaries:SteamInventorySummary[];nodes:GraphEntity[];onOpen(id:string):void;onMedia(id:string):void}) {
  const [game,setGame]=useState(''),[category,setCategory]=useState(''),[query,setQuery]=useState(''),[mode,setMode]=useState<'table'|'gallery'>('table')
  const key=(view:SteamInventorySummary)=>`${view.steamid64}|${view.appid}|${view.contextid}`
  const summary=summaries.find(view=>key(view)===game)||summaries[0]
  const items=useMemo(()=>summary?nodes.filter(node=>node.type==='inventory_item'&&node.attributes.steamid64===summary.steamid64&&node.attributes.appid===summary.appid&&node.attributes.contextid===summary.contextid):[],[nodes,summary])
  const selected=useMemo(()=>items.filter(node=>(!category||node.attributes.category===category)&&(!query||[node.label,node.attributes.market_hash_name,node.attributes.rarity,node.attributes.exterior].join(' ').toLocaleLowerCase().includes(query.toLocaleLowerCase()))),[items,category,query])
  const scroll=useRef<HTMLDivElement>(null)
  const virtual=useVirtualizer({count:selected.length,getScrollElement:()=>scroll.current,getItemKey:index=>selected[index].id,estimateSize:()=>56,overscan:5,initialRect:{width:800,height:320},enabled:mode==='table'})
  useEffect(()=>{if(scroll.current)scroll.current.scrollTop=0},[query,category,game])
  useEffect(()=>{
    if(mode!=='gallery')return
    const first=selected.slice(0,6)
    if(first.some(node=>object(node.attributes.media).state==='loading'))return
    const pending=first.find(node=>{const media=object(node.attributes.media);return media.id&&!['ready','unavailable','loading'].includes(String(media.state||''))})
    if(pending)onMedia(pending.id)
  },[mode,selected,onMedia])
  if(!summary)return null
  const value=summary.valuation
  return <section className="steam-inventory" aria-label="Предметы публичного Steam-инвентаря"><header><div><h3>Предметы Steam</h3><p>{summary.observed_assets} уникальных asset ID; Steam сообщает {summary.reported_total??'неизвестное общее число'}. Покрытие {summary.coverage_status==='complete'?'подтверждено по счётчику и курсорам':'частичное'}.</p></div><div><Button variant={mode==='table'?'secondary':'ghost'} size="sm" onClick={()=>setMode('table')}>Таблица</Button><Button variant={mode==='gallery'?'secondary':'ghost'} size="sm" onClick={()=>setMode('gallery')}>Галерея</Button></div></header>
    {summary.coverage_reason==='server_exhausted_before_reported_count'&&<p className="notice-inline">Источник завершил пагинацию раньше заявленного числа. Недостающие предметы не выдумывались.</p>}
    <p>{value.observed_subtotal_decimal!==null?`Оценённая часть: ${value.observed_subtotal_decimal} ${value.currency}; цены получены для ${value.priced_assets} предметов.`:'Публичные цены не получены.'} Для {value.unpriced_assets} предметов цена неизвестна.</p>
    <p className="muted">{value.method} {value.quote_last_observed_at&&`Последняя котировка: ${value.quote_last_observed_at}`}</p>
    <div className="steam-inventory-filters"><select aria-label="Игра Steam" value={summary?key(summary):''} onChange={event=>{setGame(event.target.value);setCategory('')}}>{summaries.map(view=><option key={key(view)} value={key(view)}>{view.appid===730?'CS2':`Steam app ${view.appid}`} · {view.steamid64}</option>)}</select><select aria-label="Категория предметов" value={category} onChange={event=>setCategory(event.target.value)}><option value="">Все категории</option>{Object.entries(summary.categories).map(([name,count])=><option key={name} value={name}>{name} · {count}</option>)}</select><input aria-label="Поиск предмета" value={query} placeholder="Название, редкость, состояние" onChange={event=>setQuery(event.target.value)}/></div>
    <small>В текущем фильтре: {selected.length}. Полные первичные записи сохранены.</small>
    {mode==='table'?<div role="table" aria-label="Таблица предметов Steam"><div className="steam-item-row steam-item-header" role="row">{['Предмет','Категория / состояние','Float / pattern','Количество','Цена лота'].map(label=><span key={label} role="columnheader">{label}</span>)}</div><div className="steam-item-scroll" ref={scroll} role="rowgroup"><div style={{height:virtual.getTotalSize(),position:'relative'}}>{virtual.getVirtualItems().map(row=>{const node=selected[row.index],data=node.attributes,price=object(data.price);return <div key={node.id} role="row" className="steam-item-row" style={{position:'absolute',top:0,left:0,width:'100%',height:row.size,transform:`translateY(${row.start}px)`}}><span role="cell"><button onClick={()=>onOpen(node.id)} title={node.label}>{node.label}</button></span><span role="cell">{text(data.category)}<small>{text(data.exterior)}</small></span><span role="cell" className="monospace">{text(data.float_value)}<small>Pattern: {text(data.pattern_template)}</small></span><span role="cell">{text(data.amount)}</span><span role="cell">{price.amount_decimal!=null?`${text(price.amount_decimal)} ${text(price.currency)}`:'Неизвестна'}</span></div>})}</div></div></div>:<div className="steam-gallery">{selected.slice(0,24).map(node=>{const media=object(node.attributes.media),preview=typeof media.thumbnail==='string'&&media.thumbnail.startsWith('data:image/jpeg;base64,')?media.thumbnail:'';return <figure key={node.id}><div>{preview?<img src={preview} alt={node.label} loading="lazy"/>:<p>{media.state==='loading'?'Загрузка…':media.state==='unavailable'?'Изображение недоступно':'Изображение из публичного источника'}{media.state!=='loading'&&media.state!=='unavailable'&&<Button variant="ghost" size="sm" onClick={()=>onMedia(node.id)}>Загрузить изображение</Button>}</p>}</div><figcaption><button onClick={()=>onOpen(node.id)}>{node.label}</button><small>{text(node.attributes.exterior)} · Steam / Valve</small></figcaption></figure>})}{selected.length>24&&<p>Первые 24 предмета. Уточните категорию или поиск для остальных.</p>}</div>}
  </section>
}
