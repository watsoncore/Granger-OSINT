import { nodeBox,routeEdges } from './graph-geometry'
import {hierarchy} from './graph-hierarchy'
import {identityProjection,profileTypes} from './graph-identity'
// Registration and document records remain distinct from legal entities.
export {nodeBox} from './graph-geometry'
import type { GraphEntity, GraphPoint, GraphRelation, GraphView, GraphViewport } from './types'

export const typeLabels: Record<string,string> = { entity_group:'Группа объектов',root_entity:'Цель',telegram_channel:'Telegram-канал',social_profile:'Публичный профиль',public_profile:'Публичный профиль',github_profile:'Профиль GitHub',github_repository:'Репозиторий GitHub',repository:'Репозиторий',username:'Никнейм',organization:'Организация',domain:'Домен',website:'Страница',email:'Email',phone:'Телефон',public_post:'Публикация',blockchain_address:'Адрес блокчейна',transaction:'Транзакция',service:'Метка сервиса',infrastructure_asset:'Инфраструктура',image:'Изображение',coordinate:'Координаты',geographic_candidate:'Географическая гипотеза',source:'Источник',asset:'Актив' }
export const verificationLabels: Record<string,string> = { verified:'Наблюдаемая связь',source_reported:'Сообщено источником',inferred:'Гипотеза',unverified:'Не подтверждено',contradicted:'Противоречие' }
export const relationLabels: Record<string,string> = { groups_observations:'Группа наблюдений',group_contains:'Включает объект',reference_for_candidate:'Эталон для гипотезы',locally_compared_with:'Сопоставлены локально',source_reports_asset:'Источник сообщает об активе',publishes_link:'Публикует ссылку',repository_namespace:'Namespace GitHub',supported_by:'Основание',published_on_domain:'Опубликовано на домене',uses_public_identifier:'Использует идентификатор',profile_mentions_organization:'Упоминает организацию',source_attributes_authorship:'Источник указывает автора',sent_from:'Отправитель',sent_to:'Получатель',transfers:'Операции',source_labels_address:'Метка источника',metadata_reports_coordinate:'GPS из метаданных',has_geographic_hypothesis:'Гипотеза модели',reference_source_reports_coordinate:'Координаты эталона',historically_published_contact:'Исторический контакт',investigates:'Объект исследования',returned_for_query:'Результат по запросу',uses_email_domain:'Домен email',map_source_reports_location:'Географический объект' }
export const entityType = (node:GraphEntity) => String(node.attributes?.display_type || node.type)
Object.assign(relationLabels, {
  public_organization_membership:'Публичное членство GitHub',
  profile_publishes_url:'Сайт из профиля',has_public_release:'Публичный релиз',
  source_reports_counterparty:'Контрагент по данным источника',
  has_public_inventory:'Опубликован инвентарь',contains_inventory_category:'Категория предметов',
  matched_parent_registration:'Родительский объект RDAP',overlaps_registered_range:'Частичное покрытие RDAP',
  maintained_by:'Реестровый maintainer',registry_administered_by:'Администратор реестра',has_registry_contact:'Контакт реестра',geoip_estimates_location:'Приблизительный GeoIP',
  contains_inventory_item:'Включает предмет',owns_public_item:'Предмет в публичном инвентаре',
  resolves_to:'DNS указывает адрес', uses_nameserver:'Использует NS', dns_alias_of:'DNS-псевдоним',
  uses_mail_exchange:'Почтовый сервер', within_announced_prefix:'В анонсируемом префиксе',
  announced_by:'Анонсируется AS', within_registered_range:'В зарегистрированном диапазоне',
  registered_to:'Регистрант по реестру', reverse_dns_reports:'PTR сообщает имя',
  public_friend_link:'Публичная ссылка в списке друзей',
})
Object.assign(typeLabels,{steam_inventory:'Инвентарь игры',inventory_category:'Категория инвентаря',inventory_item:'Предмет Steam'})
Object.assign(typeLabels,{geoip_estimate:'Оценка GeoIP',registry_maintainer:'Maintainer',registry_registry_authority:'Администратор реестра',registry_registry_contact:'Контакт реестра',registry_registry_reference:'Объект реестра'})
typeLabels.company_registration='Регистрация компании'
typeLabels.public_document='Публичный документ'
export const entityLabel = (node:GraphEntity) => node.type==='infrastructure_asset'?({ip:'IP-адрес',cidr:'BGP-префикс',asn:'Автономная система',registered_range:'Диапазон реестра'}[String(node.attributes.asset_type)]||'Инфраструктура'):typeLabels[entityType(node)] || node.type
export function shortLabel(node:GraphEntity) {
  if (node.type==='public_post' && typeof node.attributes.url==='string') {
    const id=node.attributes.url.split('/').filter(Boolean).at(-1)
    if (id && /^\d+$/.test(id)) return `Публикация #${id}`
  }
  if (node.type==='repository' && typeof node.attributes.url==='string') return node.attributes.url.split('/').filter(Boolean).at(-1) || node.label
  if (node.type==='blockchain_address') { const labels=node.attributes.labels; if(Array.isArray(labels)&&typeof labels[0]==='string')return labels[0].slice(0,28);return node.label.length>22 ? `${node.label.slice(0,9)}…${node.label.slice(-7)}` : node.label }
  return node.label.length>32 ? node.label.slice(0,30)+'…' : node.label
}
export function indexGraph(nodes:GraphEntity[],edges:GraphRelation[]) {
  const byId=new Map(nodes.map(node=>[node.id,node]))
  const neighbors=new Map<string,Set<string>>(); const incident=new Map<string,GraphRelation[]>()
  nodes.forEach(node=>{neighbors.set(node.id,new Set());incident.set(node.id,[])})
  for (const edge of edges) {
    if (!byId.has(edge.from_id)||!byId.has(edge.to_id)) continue
    neighbors.get(edge.from_id)!.add(edge.to_id);neighbors.get(edge.to_id)!.add(edge.from_id)
    incident.get(edge.from_id)!.push(edge);incident.get(edge.to_id)!.push(edge)
  }
  return {byId,neighbors,incident}
}
function searchText(node:GraphEntity){
  const fields=['url','address','username','repository','chain','asset_id','contract','scope']
  return [node.label,entityLabel(node),...fields.map(field=>node.attributes[field]),
    ...['labels','original_addresses'].flatMap(field=>Array.isArray(node.attributes[field])?node.attributes[field] as string[]:[])].join(' ').toLocaleLowerCase()
}
function visibleGraphBase(nodes:GraphEntity[],edges:GraphRelation[],root:string,view:GraphView,limit=220) {
  const index=indexGraph(nodes,edges), filters=view.filters || {}, expanded=new Set(view.expanded || [])
  const tree=hierarchy(nodes,edges,root),treeMode=view.mode==='tree'
  const substantive=new Set(edges.filter(edge=>!['supported_by','published_on_domain'].includes(edge.relation_type)).flatMap(edge=>[edge.from_id,edge.to_id]))
  const expandedTransactions=new Set<string>()
  for (const edge of edges) if (edge.aggregate && view.expanded_relations?.includes(edge.id)) edge.aggregate.transaction_ids.forEach(id=>expandedTransactions.add(id))
  const query=(view.query || '').toLocaleLowerCase()
  const researchedImages=new Set(nodes.filter(node=>node.type==='geographic_candidate'&&node.attributes.candidate_id).map(node=>node.attributes.attachment_id))
  let allowed=nodes.filter(node=> {
    if (node.id===root) return true
    const type=entityType(node)
    if(filters.sources!==undefined&&!node.source?.some(source=>filters.sources!.includes(source)))return false
    if (filters.types!==undefined&&!filters.types.includes(type)&&!filters.types.includes(node.type)) return false
    if (!filters.show_sources&&(node.type==='source'||node.attributes.technical===true||node.type==='service'&&!filters.types?.includes('service'))) return false
    if(!filters.show_sources&&node.type==='geographic_candidate'&&node.attributes.raw_prediction_only&&researchedImages.has(node.attributes.attachment_id))return false
    const group=node.attributes.parent_group_id
    if (!treeMode&&typeof group==='string'&&!expanded.has(group)&&!index.byId.get(group)?.attributes.topic_group&&!query&&node.id!==view.selected_id&&!expandedTransactions.has(node.id)) return false
    if (!filters.show_transactions&&node.type==='transaction'&&!expandedTransactions.has(node.id)) return false
    if (!filters.show_sources&&['domain','username','coordinate'].includes(node.type)&&!filters.types?.includes(node.type)&&!substantive.has(node.id)) return false
    if(!filters.show_sources&&node.type==='coordinate'&&!filters.types?.includes('coordinate'))return false
    if (!filters.include_background&&node.relevance?.level==='background') return false
    if (filters.statuses!==undefined&&node.verification_status&&!filters.statuses.includes(node.verification_status)) return false
    return true
  })
  const allowedIds=new Set(allowed.map(node=>node.id))
  const collapsed=new Set(view.collapsed || [])
  if(treeMode&&!query){
    const selectedPath=new Set(view.selected_id?tree.path(view.selected_id):[])
    allowed=allowed.filter(node=>{
      if(selectedPath.has(node.id))return true
      const parent=tree.parent.get(node.id),siblings=parent?(tree.children.get(parent)||[]).filter(id=>allowedIds.has(id)):[]
      if(parent&&!expanded.has(parent)&&siblings.length>6&&siblings.indexOf(node.id)>=5)return false
      if(parent&&!expanded.has(parent)&&(tree.depth.get(parent)||0)>=1&&siblings.length>3&&siblings.indexOf(node.id)>=2)return false
      for(const ancestor of tree.path(node.id).slice(0,-1)){
        if(collapsed.has(ancestor))return false
        const grouped=index.byId.get(ancestor)
        if(!expanded.has(ancestor)&&((tree.depth.get(ancestor)||0)>=2||grouped?.type==='entity_group'&&!grouped.attributes.topic_group))return false
      }
      return true
    })
  }else if (collapsed.size&&root&&allowedIds.has(root)) {
    const visited=new Set([root]), queue=[root]
    for (let cursor=0;cursor<queue.length;cursor++) {
      const current=queue[cursor]
      if (collapsed.has(current)) continue
      for (const neighbor of index.neighbors.get(current) || []) if (allowedIds.has(neighbor)&&!visited.has(neighbor)) {visited.add(neighbor);queue.push(neighbor)}
    }
    allowed=allowed.filter(node=>visited.has(node.id))
  }
  if (query) {
    const matches=new Set(allowed.filter(node=>searchText(node).includes(query)).map(node=>node.id))
    const context=new Set(matches);matches.forEach(id=>{index.neighbors.get(id)?.forEach(neighbor=>context.add(neighbor));if(treeMode)tree.path(id).forEach(ancestor=>context.add(ancestor))})
    if (root) context.add(root)
    allowed=allowed.filter(node=>context.has(node.id))
  }
  const focusPath=new Set(view.selected_id?tree.path(view.selected_id):[])
  const ranked=[...allowed].sort((a,b)=> (a.id===root?-1:b.id===root?1:focusPath.has(a.id)&&!focusPath.has(b.id)?-1:focusPath.has(b.id)&&!focusPath.has(a.id)?1:expanded.has(a.id)?-1:expanded.has(b.id)?1:(tree.depth.get(a.id)||0)-(tree.depth.get(b.id)||0)||(b.relevance?.score||0)-(a.relevance?.score||0)))
  const selected=ranked.slice(0,Math.max(limit,Math.min(1200,expanded.size*50+limit)))
  const baseIds=new Set(selected.map(node=>node.id))
  selected.push(...ranked.filter(node=>expandedTransactions.has(node.id)&&!baseIds.has(node.id)).slice(0,1000))
  const selectedIds=new Set(selected.map(node=>node.id))
  let relations=(treeMode?tree.treeEdges:edges).filter(edge=>selectedIds.has(edge.from_id)&&selectedIds.has(edge.to_id)&&(filters.statuses===undefined||filters.statuses.includes(edge.verification_status)))
  const totalRelations=relations.length
  if(relations.length>selected.length*3){
    const parent=new Map(selected.map(node=>[node.id,node.id]))
    const find=(id:string):string=>{let current=id;while(parent.get(current)!==current)current=parent.get(current)!;while(parent.get(id)!==id){const next=parent.get(id)!;parent.set(id,current);id=next}return current}
    const backbone=new Set<string>()
    for(const edge of relations){const a=find(edge.from_id),b=find(edge.to_id);if(a!==b){parent.set(a,b);backbone.add(edge.id)}}
    relations=relations.filter(edge=>backbone.has(edge.id)||edge.id===view.selected_relation||expanded.has(edge.from_id)||expanded.has(edge.to_id)||edge.from_id===view.selected_id||edge.to_id===view.selected_id)
  }
  return {nodes:selected,edges:relations,available:allowed.length,truncated:allowed.length>selected.length,hiddenRelations:totalRelations-relations.length,
    crossLinks:treeMode?tree.crossEdges:[],hierarchy:tree,hiddenNodes:nodes.length-selected.length}
}
export function visibleGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,view:GraphView,limit=220){
  const mode=view.projection_mode
  if(mode==='socmint'||mode==='infrastructure'||mode==='evidence'){
    const selectedProfiles=view.filters?.profile_ids?new Set(view.filters.profile_ids):null
    const profiles=socmintProfiles(nodes,edges,root).filter(node=>!selectedProfiles||selectedProfiles.has(node.id)||view.selected_id===node.id)
    const projected=identityProjection(nodes,edges,root,mode,profiles)
    const result=visibleGraphBase(projected.nodes,projected.edges,root,{...view,filters:{...view.filters,show_sources:mode!=='socmint',include_background:true}},limit)
    return {...result,hiddenNodes:nodes.length-result.nodes.length}
  }
  if(!mode||mode==='manual'||!nodes.some(node=>node.type==='blockchain_address'))return visibleGraphBase(nodes,edges,root,view,limit)
  const expandedTransactions=new Set(edges.filter(edge=>view.expanded_relations?.includes(edge.id)).flatMap(edge=>edge.aggregate?.transaction_ids||[]))
  const drillPeers=new Set(edges.filter(edge=>view.expanded_relations?.includes(edge.id)).flatMap(edge=>[edge.from_id,edge.to_id]))
  const direct=new Set([root]);for(const edge of edges)if(edge.aggregate||['transfers','source_reports_counterparty'].includes(edge.relation_type)){if(edge.from_id===root)direct.add(edge.to_id);if(edge.to_id===root)direct.add(edge.from_id)}
  // Inventory is a separate observed branch. Repeated NFT enrichment must not
  // disappear behind a projection which previously admitted only money flows.
  const inventory=new Set<string>()
  for(const edge of edges)if(edge.from_id===root&&edge.relation_type==='source_reports_asset')inventory.add(edge.to_id)
  for(const edge of edges)if(inventory.has(edge.from_id)&&['source_reports_collection','has_contract_observation'].includes(edge.relation_type))inventory.add(edge.to_id)
  let path:Set<string>|undefined
  if(mode==='paths'&&view.selected_id&&view.selected_id!==root){
    const adjacent=new Map<string,string[]>();for(const edge of edges){if(['supported_by','published_on_domain'].includes(edge.relation_type))continue;for(const [a,b]of [[edge.from_id,edge.to_id],[edge.to_id,edge.from_id]]){const row=adjacent.get(a)||[];row.push(b);adjacent.set(a,row)}}
    const previous=new Map<string,string|null>([[root,null]]),queue=[root]
    for(let i=0;i<queue.length&&!previous.has(view.selected_id);i++)for(const other of adjacent.get(queue[i])||[])if(!previous.has(other)){previous.set(other,queue[i]);queue.push(other)}
    path=new Set([root,view.selected_id]);let at:string|null|undefined=view.selected_id
    while(at&&previous.has(at)){path.add(at);at=previous.get(at)}
    for(const other of (adjacent.get(view.selected_id)||[]).slice(0,12))path.add(other)
  }
  const projected=nodes.filter(node=>{
    if((mode==='wallet'||mode==='assets')&&inventory.has(node.id))return true
    if(node.id===root||node.id===view.selected_id||expandedTransactions.has(node.id)||drillPeers.has(node.id))return true
    if(view.filters?.peer_ids&&node.type==='blockchain_address'&&!view.filters.peer_ids.includes(node.id))return false
    if(view.filters?.show_sources&&['source','service'].includes(node.type))return true
    if(view.filters?.types?.includes(node.type))return true
    if(path)return path.has(node.id)
    if(mode==='assets')return node.id===root
    if(mode==='counterparties')return direct.has(node.id)&&node.type==='blockchain_address'
    if(mode==='transactions')return ['blockchain_address','transaction','contract'].includes(node.type)
    if(mode==='flow')return ['blockchain_address','contract','token'].includes(node.type)
    // Overview is the researched wallet's actual neighborhood, not every
    // wallet from every imported observation. Expanded peers expose their
    // additional counterparties without mutating or discarding raw evidence.
    if(['wallet','counterparties'].includes(mode))return direct.has(node.id)||!!view.expanded?.some(id=>edges.some(edge=>(edge.aggregate||edge.relation_type==='source_reports_counterparty')&&((edge.from_id===id&&edge.to_id===node.id)||(edge.to_id===id&&edge.from_id===node.id))))
    return ['blockchain_address','contract','token','entity_group','analyst_note','hypothesis'].includes(node.type)
  })
  const ids=new Set(projected.map(node=>node.id)),relations=edges.filter(edge=>ids.has(edge.from_id)&&ids.has(edge.to_id)&&(mode!=='flow'||edge.aggregate||['transfers','sent_from','sent_to'].includes(edge.relation_type)||edge.id===view.selected_relation))
  const result=visibleGraphBase(projected,relations,root,{...view,filters:{...view.filters,show_transactions:mode==='transactions'||view.filters?.show_transactions}},limit)
  return {...result,hiddenNodes:nodes.length-result.nodes.length}
}

export interface FinancialFlow {
  id:string;peer_id:string;direction:'incoming'|'outgoing'|'self';amount:string|null;asset:string;asset_key:string
  count:number;unknown_amount_count:number;first_seen:string|null;last_seen:string|null
  transaction_ids:string[];evidence_ids:string[];source_urls:string[]
}
export interface WalletCounterparty {
  id:string;label:string;address:string;chain:string;flows:FinancialFlow[];transaction_ids:string[]
  evidence_ids:string[];source_urls:string[];first_seen:string|null;last_seen:string|null
  source_claim_count:number|null;direction_unknown:boolean
}
const strings=(values:unknown[])=>[...new Set(values.filter((value):value is string=>typeof value==='string'&&!!value))]
const numberCount=(value:unknown)=>typeof value==='number'&&Number.isInteger(value)&&value>=0?value:null
function dated(values:unknown[],first:boolean){const list=strings(values).filter(value=>!Number.isNaN(Date.parse(value))).sort((a,b)=>Date.parse(a)-Date.parse(b));return (first?list[0]:list.at(-1))||null}
export function walletSummary(nodes:GraphEntity[],edges:GraphRelation[],root:string){
  const byId=new Map(nodes.map(node=>[node.id,node])),owner=byId.get(root),counterparties=new Map<string,WalletCounterparty>(),transactions=new Set<string>(),assets=new Set<string>()
  const peer=(identifier:string)=>{
    const node=byId.get(identifier)
    if(!node||node.type!=='blockchain_address')return
    if(!counterparties.has(identifier))counterparties.set(identifier,{id:identifier,label:node.label,address:String(node.attributes.address||node.attributes.value||node.label),chain:String(node.attributes.chain||''),flows:[],transaction_ids:[],evidence_ids:[],source_urls:[],first_seen:null,last_seen:null,source_claim_count:null,direction_unknown:false})
    return counterparties.get(identifier)!
  }
  for(const edge of edges){
    if(edge.from_id!==root&&edge.to_id!==root)continue
    const other=edge.from_id===root?edge.to_id:edge.from_id,row=peer(other)
    if(!row)continue
    if(edge.aggregate){
      const value=edge.aggregate,direction=edge.from_id===edge.to_id?'self':edge.from_id===root?'outgoing':'incoming'
      const flow:FinancialFlow={id:edge.id,peer_id:other,direction,amount:value.amount,asset:value.asset_label||value.asset,asset_key:value.asset_key||String(owner?.attributes.chain||'')+'|'+value.asset,count:value.count,unknown_amount_count:value.unknown_amount_count,first_seen:value.first_seen||null,last_seen:value.last_seen||null,transaction_ids:value.transaction_ids,evidence_ids:edge.evidence_ids,source_urls:edge.source_urls||[]}
      row.flows.push(flow);value.transaction_ids.forEach(id=>transactions.add(id));assets.add(flow.asset)
    }else if(edge.relation_type==='source_reports_counterparty'){
      const count=numberCount(edge.attributes?.count)
      if(count!==null)row.source_claim_count=Math.max(row.source_claim_count||0,count)
      row.direction_unknown=true
    }else continue
    row.evidence_ids=strings([...row.evidence_ids,...edge.evidence_ids]);row.source_urls=strings([...row.source_urls,...(edge.source_urls||[])])
    row.transaction_ids=strings(row.flows.flatMap(flow=>flow.transaction_ids))
    row.first_seen=dated([row.first_seen,edge.aggregate?.first_seen,edge.attributes?.first_seen],true)
    row.last_seen=dated([row.last_seen,edge.aggregate?.last_seen,edge.attributes?.last_seen],false)
  }
  // A source-reported peer without a resolved transfer remains a peer, with
  // direction explicitly unknown; UTXO totals never become pairwise amounts.
  const all=[...counterparties.values()].filter(row=>row.flows.length||row.direction_unknown),rows=all.filter(row=>row.id!==root).sort((a,b)=>b.transaction_ids.length-a.transaction_ids.length||(b.source_claim_count||0)-(a.source_claim_count||0)||a.address.localeCompare(b.address))
  return {root_id:root,address:String(owner?.attributes.address||owner?.attributes.value||owner?.label||''),chain:String(owner?.attributes.chain||''),counterparties:rows,self_flows:all.find(row=>row.id===root)?.flows||[],counterparty_count:rows.length,observed_transaction_count:transactions.size,source_reported_transaction_count:numberCount(owner?.attributes.transaction_count),assets:[...assets].sort(),first_seen:dated([owner?.attributes.first_seen,...all.map(row=>row.first_seen)],true),last_seen:dated([owner?.attributes.last_seen,...all.map(row=>row.last_seen)],false),coverage:'observed_sample_only' as const}
}
export function counterpartySummary(nodes:GraphEntity[],edges:GraphRelation[],root:string,peer:string){return walletSummary(nodes,edges,root).counterparties.find(row=>row.id===peer)}
export function socmintProfiles(nodes:GraphEntity[],edges:GraphRelation[],root:string){
  const owner=nodes.find(node=>node.id===root),linked=new Set(edges.filter(edge=>edge.from_id===root&&['returned_for_query','investigates'].includes(edge.relation_type)).map(edge=>edge.to_id)),proof=new Set(owner?.evidence_ids||[])
  return nodes.filter(node=>profileTypes.has(node.type)&&!node.attributes.reference_only&&(linked.has(node.id)||node.evidence_ids.some(id=>proof.has(id))||owner?.type==='root_entity')).sort((a,b)=>String(a.attributes.platform||'').localeCompare(String(b.attributes.platform||''))||a.label.localeCompare(b.label))
}
export {layoutGraph} from './graph-layout'
export function fitViewport(points:Record<string,GraphPoint>,width:number,height:number,nodes?:GraphEntity[]):GraphViewport {
  const rows=Object.values(points)
  if (!rows.length)return {x:width/2,y:height/2,scale:1}
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity
  const boxes=nodes?new Map(nodes.map(n=>[n.id,nodeBox(n,1)])):undefined
  for(const [id,point]of Object.entries(points)){const box=boxes?.get(id);minX=Math.min(minX,point.x-(box?.width||0)/2);maxX=Math.max(maxX,point.x+(box?.width||0)/2);minY=Math.min(minY,point.y-(box?.height||0)/2);maxY=Math.max(maxY,point.y+(box?.height||0)/2)}
  const scale=Math.max(.001,Math.min(1.35,(width-80)/Math.max(160,maxX-minX+(nodes?0:280)),(height-70)/Math.max(160,maxY-minY+(nodes?0:130))))
  return {x:width/2-(minX+maxX)/2*scale,y:height/2-(minY+maxY)/2*scale,scale}
}
export function readableViewport(points:Record<string,GraphPoint>,width:number,height:number,root:string,mode:'tree'|'graph',nodes?:GraphEntity[]):GraphViewport{
  const fit=fitViewport(points,width,height,nodes)
  if(fit.scale>=.62)return fit
  const anchor=points[root]||Object.values(points)[0]||{x:0,y:0}
  return {x:(mode==='tree'?140:width/2)-anchor.x*.62,y:height/2-anchor.y*.62,scale:.62}
}
export function zoomAt(view:GraphViewport,x:number,y:number,factor:number):GraphViewport {
  const scale=Math.max(.001,Math.min(8,view.scale*factor))
  return {x:x-(x-view.x)/view.scale*scale,y:y-(y-view.y)/view.scale*scale,scale}
}
export function hitNode(nodes:GraphEntity[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number) {
  for(let i=nodes.length-1;i>=0;i--){const node=nodes[i]
    const point=positions[node.id];if(!point)continue
    const box=nodeBox(node,view.scale),dx=Math.abs(point.x*view.scale+view.x-x),dy=Math.abs(point.y*view.scale+view.y-y)
    if(dx<=box.width/2+3&&dy<=box.height/2+3){if(node.type==='entity_group'&&!node.attributes._collapsed&&dy<box.height/2-26&&dx<box.width/2-12)continue;return node}
  }
  return undefined
}
export function hitRelation(edges:GraphRelation[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number,nodes:GraphEntity[]=[],mode:'tree'|'graph'='graph') {
  let best:GraphRelation|undefined,distance=7
  for(const {edge,points}of routeEdges(edges,positions,view,nodes,mode,{left:x-7,right:x+7,top:y-7,bottom:y+7}))for(let i=1;i<points.length;i++){
    const a=points[i-1],b=points[i],dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy||1)))
    const d=Math.hypot(x-a.x-t*dx,y-a.y-t*dy);if(d<distance){distance=d;best=edge}
  }
  return best
}
