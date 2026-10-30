import type { GraphEntity, GraphPoint, GraphRelation, GraphView, GraphViewport } from './types'

export const typeLabels: Record<string,string> = { root_entity:'Цель',telegram_channel:'Telegram-канал',social_profile:'Публичный профиль',public_profile:'Публичный профиль',github_profile:'Профиль GitHub',github_repository:'Репозиторий GitHub',repository:'Репозиторий',username:'Никнейм',organization:'Организация',domain:'Домен',website:'Страница',email:'Email',phone:'Телефон',public_post:'Публикация',blockchain_address:'Адрес блокчейна',transaction:'Транзакция',service:'Метка сервиса',infrastructure_asset:'Инфраструктура',image:'Изображение',coordinate:'Координаты',geographic_candidate:'Географическая гипотеза',source:'Источник',asset:'Актив' }
export const verificationLabels: Record<string,string> = { verified:'Наблюдаемая связь',source_reported:'Сообщено источником',inferred:'Гипотеза',unverified:'Не подтверждено',contradicted:'Противоречие' }
export const relationLabels: Record<string,string> = { publishes_link:'Публикует ссылку',repository_namespace:'Namespace GitHub',supported_by:'Основание',published_on_domain:'Опубликовано на домене',uses_public_identifier:'Использует идентификатор',profile_mentions_organization:'Упоминает организацию',source_attributes_authorship:'Источник указывает автора',sent_from:'Отправитель',sent_to:'Получатель',transfers:'Операции',source_labels_address:'Метка источника',metadata_reports_coordinate:'GPS из метаданных',has_geographic_hypothesis:'Гипотеза модели',reference_source_reports_coordinate:'Координаты эталона',historically_published_contact:'Исторический контакт',investigates:'Объект исследования',returned_for_query:'Результат по запросу',uses_email_domain:'Домен email',map_source_reports_location:'Географический объект' }
export const entityType = (node:GraphEntity) => String(node.attributes?.display_type || node.type)
export const entityLabel = (node:GraphEntity) => typeLabels[entityType(node)] || node.type
export function shortLabel(node:GraphEntity) {
  if (node.type==='public_post' && typeof node.attributes.url==='string') {
    const id=node.attributes.url.split('/').filter(Boolean).at(-1)
    if (id && /^\d+$/.test(id)) return `Публикация #${id}`
  }
  if (node.type==='repository' && typeof node.attributes.url==='string') return node.attributes.url.split('/').filter(Boolean).at(-1) || node.label
  if (node.type==='blockchain_address') return node.label.length>22 ? `${node.label.slice(0,9)}…${node.label.slice(-7)}` : node.label
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
export function visibleGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,view:GraphView,limit=220) {
  const index=indexGraph(nodes,edges), filters=view.filters || {}, expanded=new Set(view.expanded || [])
  const expandedTransactions=new Set<string>()
  for (const edge of edges) if (edge.aggregate && (expanded.has(edge.from_id)||expanded.has(edge.to_id))) edge.aggregate.transaction_ids.forEach(id=>expandedTransactions.add(id))
  const query=(view.query || '').toLocaleLowerCase()
  let allowed=nodes.filter(node=> {
    if (node.id===root) return true
    const type=entityType(node)
    if (filters.types!==undefined&&!filters.types.includes(type)&&!filters.types.includes(node.type)) return false
    if (!filters.show_sources&&(node.type==='source'||node.attributes.technical===true)) return false
    if (!filters.show_transactions&&node.type==='transaction'&&!expandedTransactions.has(node.id)) return false
    if (!filters.show_sources&&['domain','username'].includes(node.type)&&!filters.types?.includes(node.type)) return false
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
    const matches=new Set(allowed.filter(node=>(node.label+' '+entityLabel(node)+' '+JSON.stringify(node.attributes)).toLocaleLowerCase().includes(query)).map(node=>node.id))
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
  const index=indexGraph(nodes,edges);const positions:Record<string,GraphPoint>={};const visited=new Set<string>()
  const ordered=[root,...nodes.map(node=>node.id).sort()].filter(id=>index.byId.has(id))
  let component=0
  for (const seed of ordered) {
    if (visited.has(seed)) continue
    const tiers:string[][]=[[seed]],queue=[seed],depth=new Map([[seed,0]]);visited.add(seed)
    for (let cursor=0;cursor<queue.length;cursor++) {
      const id=queue[cursor],level=depth.get(id)!
      for (const neighbor of index.neighbors.get(id) || []) if (!visited.has(neighbor)) {
        visited.add(neighbor);queue.push(neighbor);depth.set(neighbor,level+1);(tiers[level+1] ||= []).push(neighbor)
      }
    }
    const offsetX=component===0?0:((component-1)%5-2)*420, offsetY=component===0?0:650+Math.floor((component-1)/5)*280
    let top=0
    tiers.forEach(tier=> {
      if (mode==='tree') {
        const columns=Math.min(tier.length,Math.max(1,Math.ceil(Math.sqrt(tier.length)*1.8)))
        tier.forEach((id,i)=>{positions[id]={x:offsetX+(i%columns-(columns-1)/2)*145,y:offsetY+top+Math.floor(i/columns)*90}})
        top+=Math.ceil(tier.length/columns)*90+90
      }
    })
    if(mode==='graph') {
      positions[seed]={x:offsetX,y:offsetY}
      const ordered=tiers.flat().filter(id=>id!==seed)
      let cursor=0,ring=1
      while(cursor<ordered.length){const radius=ring*165,capacity=Math.max(8,Math.floor(2*Math.PI*radius/115)),count=Math.min(capacity,ordered.length-cursor)
        for(let index=0;index<count;index++){const angle=index/count*Math.PI*2-Math.PI/2+ring*.17;positions[ordered[cursor+index]]={x:offsetX+Math.cos(angle)*radius,y:offsetY+Math.sin(angle)*radius}}
        cursor+=count;ring++
      }
    }
    component++
  }
  for (const node of nodes) if (saved[node.id]&&(preserve||saved[node.id].pinned)) positions[node.id]={...saved[node.id]}
  return positions
}
export function fitViewport(points:Record<string,GraphPoint>,width:number,height:number):GraphViewport {
  const rows=Object.values(points)
  if (!rows.length)return {x:width/2,y:height/2,scale:1}
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity
  for(const point of rows){minX=Math.min(minX,point.x);maxX=Math.max(maxX,point.x);minY=Math.min(minY,point.y);maxY=Math.max(maxY,point.y)}
  const scale=Math.max(.001,Math.min(1.35,(width-100)/Math.max(160,maxX-minX+90),(height-90)/Math.max(160,maxY-minY+70)))
  return {x:width/2-(minX+maxX)/2*scale,y:height/2-(minY+maxY)/2*scale,scale}
}
export function zoomAt(view:GraphViewport,x:number,y:number,factor:number):GraphViewport {
  const scale=Math.max(.001,Math.min(8,view.scale*factor))
  return {x:x-(x-view.x)/view.scale*scale,y:y-(y-view.y)/view.scale*scale,scale}
}
export function hitNode(nodes:GraphEntity[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number) {
  let best:GraphEntity|undefined, distance=Infinity
  for (const node of nodes) {const p=positions[node.id];if(!p)continue;const d=Math.hypot(p.x*view.scale+view.x-x,p.y*view.scale+view.y-y);if(d<Math.max(11,13*Math.sqrt(view.scale))&&d<distance){best=node;distance=d}}
  return best
}
export function hitRelation(edges:GraphRelation[],positions:Record<string,GraphPoint>,view:GraphViewport,x:number,y:number) {
  let best:GraphRelation|undefined,distance=7
  for(const edge of edges){const a=positions[edge.from_id],b=positions[edge.to_id];if(!a||!b)continue;const ax=a.x*view.scale+view.x,ay=a.y*view.scale+view.y,bx=b.x*view.scale+view.x,by=b.y*view.scale+view.y;const dx=bx-ax,dy=by-ay;const t=Math.max(0,Math.min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy||1)));const d=Math.hypot(x-ax-t*dx,y-ay-t*dy);if(d<distance){distance=d;best=edge}}
  return best
}
