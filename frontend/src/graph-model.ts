import { nodeBox,routeEdges } from './graph-geometry'
export {nodeBox} from './graph-geometry'
import type { GraphEntity, GraphPoint, GraphRelation, GraphView, GraphViewport } from './types'

export const typeLabels: Record<string,string> = { entity_group:'Группа объектов',root_entity:'Цель',telegram_channel:'Telegram-канал',social_profile:'Публичный профиль',public_profile:'Публичный профиль',github_profile:'Профиль GitHub',github_repository:'Репозиторий GitHub',repository:'Репозиторий',username:'Никнейм',organization:'Организация',domain:'Домен',website:'Страница',email:'Email',phone:'Телефон',public_post:'Публикация',blockchain_address:'Адрес блокчейна',transaction:'Транзакция',service:'Метка сервиса',infrastructure_asset:'Инфраструктура',image:'Изображение',coordinate:'Координаты',geographic_candidate:'Географическая гипотеза',source:'Источник',asset:'Актив' }
export const verificationLabels: Record<string,string> = { verified:'Наблюдаемая связь',source_reported:'Сообщено источником',inferred:'Гипотеза',unverified:'Не подтверждено',contradicted:'Противоречие' }
export const relationLabels: Record<string,string> = { groups_observations:'Группа наблюдений',group_contains:'Включает объект',reference_for_candidate:'Эталон для гипотезы',locally_compared_with:'Сопоставлены локально',source_reports_asset:'Источник сообщает об активе',publishes_link:'Публикует ссылку',repository_namespace:'Namespace GitHub',supported_by:'Основание',published_on_domain:'Опубликовано на домене',uses_public_identifier:'Использует идентификатор',profile_mentions_organization:'Упоминает организацию',source_attributes_authorship:'Источник указывает автора',sent_from:'Отправитель',sent_to:'Получатель',transfers:'Операции',source_labels_address:'Метка источника',metadata_reports_coordinate:'GPS из метаданных',has_geographic_hypothesis:'Гипотеза модели',reference_source_reports_coordinate:'Координаты эталона',historically_published_contact:'Исторический контакт',investigates:'Объект исследования',returned_for_query:'Результат по запросу',uses_email_domain:'Домен email',map_source_reports_location:'Географический объект' }
export const entityType = (node:GraphEntity) => String(node.attributes?.display_type || node.type)
Object.assign(relationLabels, {
  resolves_to:'DNS указывает адрес', uses_nameserver:'Использует NS', dns_alias_of:'DNS-псевдоним',
  uses_mail_exchange:'Почтовый сервер', within_announced_prefix:'В анонсируемом префиксе',
  announced_by:'Анонсируется AS', within_registered_range:'В зарегистрированном диапазоне',
  registered_to:'Регистрант по реестру', reverse_dns_reports:'PTR сообщает имя',
  public_friend_link:'Публичная ссылка в списке друзей',
})
export const entityLabel = (node:GraphEntity) => typeLabels[entityType(node)] || node.type
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
export function visibleGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,view:GraphView,limit=220) {
  const index=indexGraph(nodes,edges), filters=view.filters || {}, expanded=new Set(view.expanded || [])
  const expandedTransactions=new Set<string>()
  for (const edge of edges) if (edge.aggregate && view.expanded_relations?.includes(edge.id)) edge.aggregate.transaction_ids.forEach(id=>expandedTransactions.add(id))
  const query=(view.query || '').toLocaleLowerCase()
  const researchedImages=new Set(nodes.filter(node=>node.type==='geographic_candidate'&&node.attributes.candidate_id).map(node=>node.attributes.attachment_id))
  let allowed=nodes.filter(node=> {
    if (node.id===root) return true
    const type=entityType(node)
    if (filters.types!==undefined&&!filters.types.includes(type)&&!filters.types.includes(node.type)) return false
    if (!filters.show_sources&&(node.type==='source'||node.attributes.technical===true||node.type==='service'&&!filters.types?.includes('service'))) return false
    if(!filters.show_sources&&node.type==='geographic_candidate'&&node.attributes.raw_prediction_only&&researchedImages.has(node.attributes.attachment_id))return false
    const group=node.attributes.parent_group_id
    if (typeof group==='string'&&!expanded.has(group)&&!query&&node.id!==view.selected_id) return false
    if (!filters.show_transactions&&node.type==='transaction'&&!expandedTransactions.has(node.id)) return false
    if (!filters.show_sources&&['domain','username','coordinate'].includes(node.type)&&!filters.types?.includes(node.type)) return false
    if (!filters.include_background&&node.relevance?.level==='background') return false
    if (filters.statuses!==undefined&&node.verification_status&&!filters.statuses.includes(node.verification_status)) return false
    return true
  })
  const allowedIds=new Set(allowed.map(node=>node.id))
  const collapsed=new Set(view.collapsed || [])
  if (collapsed.size&&root&&allowedIds.has(root)) {
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
    const context=new Set(matches);matches.forEach(id=>index.neighbors.get(id)?.forEach(neighbor=>context.add(neighbor)))
    if (root) context.add(root)
    allowed=allowed.filter(node=>context.has(node.id))
  }
  const ranked=[...allowed].sort((a,b)=> (a.id===root?-1:b.id===root?1:a.id===view.selected_id?-1:b.id===view.selected_id?1:expanded.has(a.id)?-1:expanded.has(b.id)?1:(b.relevance?.score||0)-(a.relevance?.score||0)))
  const selected=ranked.slice(0,Math.max(limit,Math.min(1200,expanded.size*50+limit)))
  const selectedIds=new Set(selected.map(node=>node.id))
  let relations=edges.filter(edge=>selectedIds.has(edge.from_id)&&selectedIds.has(edge.to_id)&&(filters.statuses===undefined||filters.statuses.includes(edge.verification_status)))
  const totalRelations=relations.length
  if(relations.length>selected.length*3){
    const parent=new Map(selected.map(node=>[node.id,node.id]))
    const find=(id:string):string=>{let current=id;while(parent.get(current)!==current)current=parent.get(current)!;return current}
    const backbone=new Set<string>()
    for(const edge of relations){const a=find(edge.from_id),b=find(edge.to_id);if(a!==b){parent.set(a,b);backbone.add(edge.id)}}
    relations=relations.filter(edge=>backbone.has(edge.id)||edge.id===view.selected_relation||expanded.has(edge.from_id)||expanded.has(edge.to_id)||edge.from_id===view.selected_id||edge.to_id===view.selected_id)
  }
  return {nodes:selected,edges:relations,available:allowed.length,truncated:allowed.length>selected.length,hiddenRelations:totalRelations-relations.length}
}
export function layoutGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,mode:'tree'|'graph',saved:Record<string,GraphPoint>={},preserve=true):Record<string,GraphPoint> {
  const index=indexGraph(nodes,edges),positions:Record<string,GraphPoint>={}
  const ordered=[root,...nodes.map(node=>node.id).sort()].filter(id=>index.byId.has(id)),visited=new Set<string>()
  let component=0
  for(const seed of ordered){
    if(visited.has(seed))continue
    const queue=[seed],depth=new Map([[seed,0]]);visited.add(seed)
    for(let cursor=0;cursor<queue.length;cursor++)for(const neighbor of index.neighbors.get(queue[cursor])||[])if(!visited.has(neighbor)){
      visited.add(neighbor);queue.push(neighbor);depth.set(neighbor,depth.get(queue[cursor])!+1)
    }
    const originX=component?Math.max(0,...Object.values(positions).map(point=>point.x))+360:0,originY=0
    positions[seed]={x:originX,y:originY}
    if(mode==='tree'){
      const tiers=new Map<number,string[]>()
      for(const id of queue.slice(1)){const level=depth.get(id)!;const tier=tiers.get(level)||[];tier.push(id);tiers.set(level,tier)}
      let left=360
      for(const [,tier]of tiers){
        tier.sort((a,b)=>entityType(index.byId.get(a)!).localeCompare(entityType(index.byId.get(b)!))||a.localeCompare(b))
        const columns=Math.min(5,Math.max(1,Math.ceil(Math.sqrt(tier.length)))),rows=Math.ceil(tier.length/columns)
        tier.forEach((id,i)=>{positions[id]={x:originX+left+(i%columns)*280,y:originY+(Math.floor(i/columns)-(rows-1)/2)*132}})
        left+=columns*280+100
      }

    }else{
      const members=queue.slice(1)
      if(members.length<=7){
        const columns=members.length>3?3:2,rows=Math.ceil(members.length/columns)
        members.forEach((id,i)=>{positions[id]={x:originX+520+(i%columns-(columns-1)/2)*280,y:originY+(Math.floor(i/columns)-(rows-1)/2)*132}})
      }else{
        const buckets=new Map<string,string[]>()
        for(const id of members){const node=index.byId.get(id)!,kind=String(node.attributes.parent_group_id||entityType(node)),list=buckets.get(kind)||[];list.push(id);buckets.set(kind,list)}
        let main=[...buckets].filter(([,ids])=>ids.length>=3),auxiliary=[...buckets].filter(([,ids])=>ids.length<3).flatMap(([,ids])=>ids)
        if(!main.length||auxiliary.length>4||main.reduce((sum,[,ids])=>sum+ids.length,0)<members.length/2){main=[['objects',members]];auxiliary=[]}
        const groups=main.map(([kind,ids])=>{const columns=Math.min(6,Math.max(1,Math.ceil(Math.sqrt(ids.length*2.2))));return{kind,ids,columns,rows:Math.ceil(ids.length/columns)}})
        const total=groups.reduce((sum,group)=>sum+group.rows*132+60,0)-60
        let top=-total/2
        for(const group of groups){
          group.ids.sort((a,b)=>(index.byId.get(b)!.relevance?.score||0)-(index.byId.get(a)!.relevance?.score||0)||a.localeCompare(b))
          group.ids.forEach((id,i)=>{positions[id]={x:originX+360+(i%group.columns)*280,y:originY+top+66+Math.floor(i/group.columns)*132}})
          top+=group.rows*132+60
        }
        auxiliary.forEach((id,i)=>{positions[id]={x:originX,y:originY+(i%2?1:-1)*(Math.floor(i/2)+1)*150}})
      }
    }

    component++
  }
  for(const node of nodes)if(saved[node.id]&&(preserve||saved[node.id].pinned))positions[node.id]={...saved[node.id]}
  if(preserve){
    // A newly expanded collection must not occupy positions reserved by the
    // existing cards. Preserve the user's layout and place new cards beside it.
    const occupied=nodes.filter(node=>saved[node.id]).map(node=>positions[node.id])
    const anchorX=occupied.length?Math.min(...occupied.map(point=>point.x)):0
    const anchorY=occupied.length?Math.max(...occupied.map(point=>point.y))+192:0
    let slot=0
    for(const node of nodes.filter(node=>!saved[node.id])){
      let point=positions[node.id]
      if(occupied.some(other=>Math.abs(other.x-point.x)<260&&Math.abs(other.y-point.y)<120)){
        do{point={x:anchorX+(slot%5)*280,y:anchorY+Math.floor(slot/5)*132};slot++}
        while(occupied.some(other=>Math.abs(other.x-point.x)<260&&Math.abs(other.y-point.y)<120))
        positions[node.id]=point
      }
      occupied.push(point)
    }
  }
  return positions
}
export function fitViewport(points:Record<string,GraphPoint>,width:number,height:number):GraphViewport {
  const rows=Object.values(points)
  if (!rows.length)return {x:width/2,y:height/2,scale:1}
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity
  for(const point of rows){minX=Math.min(minX,point.x);maxX=Math.max(maxX,point.x);minY=Math.min(minY,point.y);maxY=Math.max(maxY,point.y)}
  const scale=Math.max(.001,Math.min(1.35,(width-100)/Math.max(160,maxX-minX+280),(height-90)/Math.max(160,maxY-minY+130)))
  return {x:width/2-(minX+maxX)/2*scale,y:height/2-(minY+maxY)/2*scale,scale}
}
export function zoomAt(view:GraphViewport,x:number,y:number,factor:number):GraphViewport {
  const scale=Math.max(.001,Math.min(8,view.scale*factor))
  return {x:x-(x-view.x)/view.scale*scale,y:y-(y-view.y)/view.scale*scale,scale}
}
export function hitNode(nodes:GraphEntity[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number) {
  for(const node of [...nodes].reverse()){
    const point=positions[node.id];if(!point)continue
    const box=nodeBox(node,view.scale),dx=Math.abs(point.x*view.scale+view.x-x),dy=Math.abs(point.y*view.scale+view.y-y)
    if(dx<=box.width/2+3&&dy<=box.height/2+3)return node
  }
  return undefined
}
export function hitRelation(edges:GraphRelation[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number,nodes:GraphEntity[]=[]) {
  let best:GraphRelation|undefined,distance=7
  for(const {edge,points}of routeEdges(edges,positions,view,nodes))for(let i=1;i<points.length;i++){
    const a=points[i-1],b=points[i],dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy||1)))
    const d=Math.hypot(x-a.x-t*dx,y-a.y-t*dy);if(d<distance){distance=d;best=edge}
  }
  return best
}
