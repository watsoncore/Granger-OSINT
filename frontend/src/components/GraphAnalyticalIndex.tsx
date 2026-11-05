import {useEffect,useMemo,useRef,useState} from 'react'
import {ArrowDownLeft,ArrowUpRight,ChevronLeft,ChevronRight,Search,Users,Wallet} from 'lucide-react'
import type {GraphEntity,GraphRelation} from '../types'
import {walletSummary,socmintProfiles,type WalletCounterparty} from '../graph-model'
import {formatGraphAmount} from '../graph-money'
import {Button} from './ui'

export function GraphOverview({nodes,edges,root,social,partial,onIndex,onCenter}:{nodes:GraphEntity[];edges:GraphRelation[];root:string;social:boolean;partial:boolean;onIndex():void;onCenter():void}){
 const summary=useMemo(()=>walletSummary(nodes,edges,root),[nodes,edges,root]),profiles=useMemo(()=>social?socmintProfiles(nodes,edges,root):[],[nodes,edges,root,social])
 const owner=nodes.find(node=>node.id===root)
 return <section className="graph-overview" aria-label="Аналитический обзор">
  <div className="graph-overview-owner">{social?<Users size={20}/>:<Wallet size={20}/>}<span><small>{social?'ПОИСК ПО ИДЕНТИФИКАТОРУ':`${summary.chain.toUpperCase()||'БЛОКЧЕЙН'} · ЦЕНТР ИССЛЕДОВАНИЯ`}</small><strong title={summary.address}>{owner?.label||summary.address}</strong></span></div>
  <button className="overview-stat" onClick={onIndex}><strong>{social?profiles.length:summary.counterparty_count}</strong><span>{social?'публичных профилей':'контрагентов в данных'}</span></button>
  {!social&&<><div className="overview-stat"><strong>{summary.observed_transaction_count}</strong><span>наблюдаемых переводов</span></div><div className="overview-stat overview-assets"><strong>{summary.assets.join(' · ')||'Актив не установлен'}</strong><span>{summary.first_seen?`${summary.first_seen.slice(0,10)} — ${summary.last_seen?.slice(0,10)||'…'}`:'Период не установлен'}</span></div></>}
  <span className={`graph-coverage ${partial?'is-partial':''}`}>{partial?'Частичные данные':'По полученным наблюдениям'}<small>{social?'Совпадение username не доказывает общего владельца':'Суммы по активам раздельно · владение не установлено'}</small></span>
  <Button size="sm" variant="secondary" onClick={onCenter}>К центру</Button>
 </section>
}

export function GraphAnalyticalIndex({nodes,edges,root,social,selected,onWindow,onSelect}:{nodes:GraphEntity[];edges:GraphRelation[];root:string;social:boolean;selected:string;onWindow(ids:string[]):void;onSelect(id:string):void}){
 const [query,setQuery]=useState(''),[direction,setDirection]=useState('all'),[page,setPage]=useState(0)
 const callbacks=useRef({onWindow});callbacks.current={onWindow}
 const summary=useMemo(()=>walletSummary(nodes,edges,root),[nodes,edges,root]),profiles=useMemo(()=>social?socmintProfiles(nodes,edges,root):[],[nodes,edges,root,social])
 const rows=useMemo(()=>{
  const needle=query.toLocaleLowerCase().trim()
  return (social?profiles.map(node=>({id:node.id,label:node.label,address:String(node.attributes.url||''),platform:String(node.attributes.platform||''),flows:[],count:node.evidence_ids.length})):summary.counterparties.map(peer=>({...peer,platform:peer.chain,count:peer.transaction_ids.length}))).filter(row=>(!needle||`${row.label} ${row.address} ${row.platform}`.toLocaleLowerCase().includes(needle))&&(social||direction==='all'||row.flows.some(flow=>flow.direction===direction)))
 },[query,direction,social,profiles,summary])
 const pageSize=8,totalPages=Math.max(1,Math.ceil(rows.length/pageSize)),currentPage=Math.min(page,totalPages-1),visible=rows.slice(currentPage*pageSize,(currentPage+1)*pageSize),key=JSON.stringify([root,social,visible.map(row=>row.id)])
 useEffect(()=>{callbacks.current.onWindow(visible.map(row=>row.id))},[key])
 useEffect(()=>{setPage(0);setQuery('');setDirection('all')},[root,social])
 return <nav className="graph-analysis-index" aria-label={social?'Индекс публичных профилей':'Индекс контрагентов'}>
  <header><strong>{social?'Найденные профили':'Контрагенты'}</strong><span>{rows.length} / {social?profiles.length:summary.counterparty_count}</span></header>
  <label className="analysis-index-search"><Search size={14}/><input aria-label="Поиск в аналитическом индексе" value={query} onChange={event=>{setQuery(event.target.value);setPage(0)}} placeholder={social?'Платформа или URL…':'Адрес или метка…'}/></label>
  {!social&&<div className="analysis-direction" aria-label="Направление потока">{[['all','Все'],['incoming','Входящие'],['outgoing','Исходящие']].map(([value,label])=><button key={value} aria-pressed={direction===value} onClick={()=>{setDirection(value);setPage(0)}}>{label}</button>)}</div>}
  <div className="analysis-index-rows">{visible.map(row=><button key={row.id} className={selected===row.id?'is-selected':''} aria-label={`Исследовать ${row.address||row.label}`} onClick={()=>onSelect(row.id)}><small>{row.platform.toUpperCase()||'ПУБЛИЧНЫЙ ИСТОЧНИК'}</small><strong title={row.label}>{row.label}</strong><code title={row.address}>{row.address}</code>{!social&&<span>{row.flows.slice(0,2).map(flow=><span key={flow.id} title={flow.amount??'Сумма неизвестна'}>{flow.direction==='incoming'?<ArrowDownLeft size={12}/>:<ArrowUpRight size={12}/>} {formatGraphAmount(flow.amount)} {flow.asset} · {flow.count}</span>)}{!row.flows.length&&'Направление и суммы не установлены'}</span>}</button>)}{!rows.length&&<p>Нет объектов по этому фильтру.</p>}</div>
  <footer><Button size="sm" variant="ghost" aria-label="Предыдущая страница объектов" disabled={currentPage===0} onClick={()=>setPage(n=>Math.max(0,n-1))}><ChevronLeft size={15}/></Button><span>{currentPage+1} / {totalPages}</span><Button size="sm" variant="ghost" aria-label="Следующая страница объектов" disabled={currentPage+1>=totalPages} onClick={()=>setPage(n=>n+1)}><ChevronRight size={15}/></Button></footer>
  <small className="analysis-index-help">Все наблюдения сохранены. Страница меняет обзор; выбор открывает сведения и доказательства.</small>
 </nav>
}

export function CounterpartyFlows({peer,onFlow}:{peer:WalletCounterparty;onFlow(id:string):void}){
 return <section className="counterparty-flows" aria-label="Финансовые связи контрагента"><h4>Взаимодействия с центром</h4><code>{peer.address}</code><span>{peer.chain.toUpperCase()} · {peer.transaction_ids.length} наблюдаемых переводов</span>{peer.flows.map(flow=><button key={flow.id} onClick={()=>onFlow(flow.id)}><span>{flow.direction==='incoming'?'↙ К центральному кошельку':flow.direction==='outgoing'?'↗ От центрального кошелька':'↺ Внутренний перевод'}</span><strong title={flow.amount??'Сумма неизвестна'}>{formatGraphAmount(flow.amount,false)} {flow.asset}</strong><small>{flow.count} переводов · {flow.unknown_amount_count} с неизвестной суммой</small></button>)}{peer.first_seen&&<small>{peer.first_seen} — {peer.last_seen||'…'}</small>}</section>
}

export function FlowTransactions({relation,nodes,onSelect}:{relation:GraphRelation;nodes:GraphEntity[];onSelect(id:string):void}){
 const [query,setQuery]=useState(''),[page,setPage]=useState(0)
 const rows=useMemo(()=>{const ids=new Set(relation.aggregate?.transaction_ids||[]),needle=query.toLocaleLowerCase();return nodes.filter(node=>ids.has(node.id)&&(!needle||JSON.stringify([node.label,node.attributes.tx_hash,node.attributes.event_id]).toLocaleLowerCase().includes(needle)))},[relation,nodes,query])
 const count=20,pages=Math.max(1,Math.ceil(rows.length/count)),active=Math.min(page,pages-1)
 useEffect(()=>{setQuery('');setPage(0)},[relation.id])
 return <section className="flow-transactions" aria-label="Переводы выбранной связи"><h4>Исходные переводы · {rows.length}</h4><input aria-label="Найти транзакцию связи" value={query} placeholder="Hash или идентификатор…" onChange={event=>{setQuery(event.target.value);setPage(0)}}/>{rows.slice(active*count,(active+1)*count).map(node=><button key={node.id} aria-label={`Исследовать транзакцию ${String(node.attributes.tx_hash||node.label)}`} onClick={()=>onSelect(node.id)}><code>{String(node.attributes.tx_hash||node.label)}</code><span>{formatGraphAmount(node.attributes.amount_decimal??node.attributes.amount,false)} {String(node.attributes.asset||'')}</span><small>{String(node.attributes.timestamp||'Время неизвестно')} · {String(node.attributes.status||'Статус неизвестен')}</small></button>)}{pages>1&&<footer><Button size="sm" disabled={active===0} onClick={()=>setPage(n=>n-1)}>Назад</Button>{active+1} / {pages}<Button size="sm" disabled={active+1>=pages} onClick={()=>setPage(n=>n+1)}>Далее</Button></footer>}</section>
}
