import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {layoutGraph,avoidCardOverlaps} from './graph-layout'
import {cardSize} from './graph-cards'

export function researchLayout(nodes:GraphEntity[],edges:GraphRelation[],root:string,saved:Record<string,GraphPoint>,mode:string){
  if(mode==='manual')return saved
  if(mode==='paths')return layoutGraph(nodes,edges,root,'tree',saved,false)
  if(['wallet','flow','counterparties'].includes(mode)){
    const result:Record<string,GraphPoint>={[root]:saved[root]?.pinned?saved[root]:{x:0,y:0}},incoming=new Set<string>(),outgoing=new Set<string>()
    for(const edge of edges){if(edge.direction==='undirected'||edge.attributes?.financial_transfer===false||['supported_by','published_on_domain'].includes(edge.relation_type))continue;if(edge.from_id===root)outgoing.add(edge.to_id);if(edge.to_id===root)incoming.add(edge.from_id)}
    const peers=nodes.filter(n=>n.id!==root).sort((a,b)=>String(a.attributes.chain||'').localeCompare(String(b.attributes.chain||''))||a.label.localeCompare(b.label))
    const width=Math.max(310,...nodes.map(n=>cardSize(n).width+55)),height=Math.max(150,...nodes.map(n=>cardSize(n).height+36))
    if(mode==='wallet'){const radius=Math.max(430,peers.length*width/(Math.PI*2));peers.forEach((n,i)=>{const angle=i/Math.max(1,peers.length)*Math.PI*2-Math.PI/2;result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:Math.cos(angle)*radius,y:Math.sin(angle)*radius}})}
    else if(mode==='flow'){
      const columns=new Map<string,GraphEntity[]>()
      for(const node of peers){const kind=incoming.has(node.id)&&outgoing.has(node.id)?'both':incoming.has(node.id)?'in':outgoing.has(node.id)?'out':'unresolved',rows=columns.get(kind)||[];rows.push(node);columns.set(kind,rows)}
      for(const [kind,rows]of columns){const x=kind==='in'?-width*1.65:kind==='out'?width*1.65:kind==='both'?0:width*3.2,start=kind==='both'?height*2:-(rows.length-1)*height/2;rows.forEach((node,i)=>{result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x,y:start+i*height}})}
    }else{
      const clusters=new Map<string,GraphEntity[]>()
      for(const node of peers){const direction=incoming.has(node.id)&&outgoing.has(node.id)?'both':incoming.has(node.id)?'in':outgoing.has(node.id)?'out':'unresolved',key=String(node.attributes.chain||'unknown')+'|'+direction,rows=clusters.get(key)||[];rows.push(node);clusters.set(key,rows)}
      let x=-Math.max(1,clusters.size)*width/2
      for(const rows of clusters.values()){const columns=Math.max(1,Math.ceil(Math.sqrt(rows.length))),clusterWidth=columns*width;rows.forEach((node,i)=>{result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x:x+i%columns*width,y:height*2+Math.floor(i/columns)*height}});x+=clusterWidth+width*.75}
    }
    const origin=result[root]
    if(origin&&(origin.x||origin.y))for(const node of peers)if(!saved[node.id]?.pinned){result[node.id].x+=origin.x;result[node.id].y+=origin.y}
    return avoidCardOverlaps(nodes,result,saved)
  }
  if(mode==='hierarchical'||mode==='radial'&&nodes.length<=400)return layoutGraph(nodes,edges,root,mode==='hierarchical'?'tree':'graph',saved,false)
  if(mode==='radial'){
    const adjacent=new Map(nodes.map(n=>[n.id,[] as string[]]));for(const e of edges){adjacent.get(e.from_id)?.push(e.to_id);adjacent.get(e.to_id)?.push(e.from_id)}
    const depth=new Map([[root,0]]),queue=[root];for(let i=0;i<queue.length;i++)for(const id of adjacent.get(queue[i])||[])if(!depth.has(id)){depth.set(id,(depth.get(queue[i])||0)+1);queue.push(id)}
    const levels=new Map<number,GraphEntity[]>();for(const n of nodes){const d=depth.get(n.id)??1,group=levels.get(d)||[];group.push(n);levels.set(d,group)}
    const result:Record<string,GraphPoint>={};let previous=0
    for(const [d,group]of [...levels].sort(([a],[b])=>a-b)){const spacing=Math.max(310,...group.map(n=>cardSize(n).width+45)),r=d?Math.max(previous+spacing,group.length*spacing/(2*Math.PI)):0;previous=r;group.forEach((n,i)=>{const angle=i/group.length*Math.PI*2;result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:Math.cos(angle)*r,y:Math.sin(angle)*r}})}
    return avoidCardOverlaps(nodes,result,saved)
  }
  const groups=new Map<string,GraphEntity[]>(),byId=new Map(nodes.map(n=>[n.id,n])),parents=new Map(nodes.map(n=>[n.id,n.id]))
  const find=(id:string):string=>{let p=parents.get(id)||id;while(parents.get(p)&&parents.get(p)!==p)p=parents.get(p)!;while(parents.get(id)!==id){const next=parents.get(id)!;parents.set(id,p);id=next}return p}
  if(mode==='communities')for(const e of edges)if(byId.has(e.from_id)&&byId.has(e.to_id)){const a=find(e.from_id),b=find(e.to_id);if(a!==b)parents.set(a,b)}
  for(const node of nodes){const raw=String(node.attributes.timestamp||node.attributes.observed_at||node.attributes.first_seen||'');const time=Date.parse(raw);const key=mode==='types'?node.type:mode==='communities'?find(node.id):Number.isFinite(time)?new Date(time).toISOString().slice(0,10):'Дата неизвестна';const group=groups.get(key)||[];group.push(node);groups.set(key,group)}
  const result:Record<string,GraphPoint>={};let x=0
  for(const [,group]of [...groups].sort(([a],[b])=>a.localeCompare(b))){const columns=Math.max(1,Math.ceil(Math.sqrt(group.length/3))),w=Math.max(310,...group.map(n=>cardSize(n).width+46)),h=Math.max(145,...group.map(n=>cardSize(n).height+30));group.forEach((n,i)=>{result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:x+i%columns*w,y:Math.floor(i/columns)*h}});x+=columns*w+110}
  return avoidCardOverlaps(nodes,result,saved)
}
