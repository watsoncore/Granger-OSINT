import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {layoutGraph} from './graph-layout'

export function researchLayout(nodes:GraphEntity[],edges:GraphRelation[],root:string,saved:Record<string,GraphPoint>,mode:string){
  if(mode==='manual')return saved
  if(mode==='hierarchical'||mode==='radial'&&nodes.length<=400)return layoutGraph(nodes,edges,root,mode==='hierarchical'?'tree':'graph',saved,false)
  if(mode==='radial'){
    const adjacent=new Map(nodes.map(n=>[n.id,[] as string[]]));for(const e of edges){adjacent.get(e.from_id)?.push(e.to_id);adjacent.get(e.to_id)?.push(e.from_id)}
    const depth=new Map([[root,0]]),queue=[root];for(let i=0;i<queue.length;i++)for(const id of adjacent.get(queue[i])||[])if(!depth.has(id)){depth.set(id,(depth.get(queue[i])||0)+1);queue.push(id)}
    const levels=new Map<number,GraphEntity[]>();for(const n of nodes){const d=depth.get(n.id)??1,group=levels.get(d)||[];group.push(n);levels.set(d,group)}
    const result:Record<string,GraphPoint>={};let previous=0
    for(const [d,group]of [...levels].sort(([a],[b])=>a-b)){const r=d?Math.max(previous+350,group.length*310/(2*Math.PI)):0;previous=r;group.forEach((n,i)=>{const angle=i/group.length*Math.PI*2;result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:Math.cos(angle)*r,y:Math.sin(angle)*r}})}
    return result
  }
  const groups=new Map<string,GraphEntity[]>(),byId=new Map(nodes.map(n=>[n.id,n])),parents=new Map(nodes.map(n=>[n.id,n.id]))
  const find=(id:string):string=>{let p=parents.get(id)||id;while(parents.get(p)&&parents.get(p)!==p)p=parents.get(p)!;return p}
  if(mode==='communities')for(const e of edges)if(byId.has(e.from_id)&&byId.has(e.to_id)){const a=find(e.from_id),b=find(e.to_id);if(a!==b)parents.set(a,b)}
  for(const node of nodes){const raw=String(node.attributes.timestamp||node.attributes.observed_at||node.attributes.first_seen||'');const time=Date.parse(raw);const key=mode==='types'?node.type:mode==='communities'?find(node.id):Number.isFinite(time)?new Date(time).toISOString().slice(0,10):'Дата неизвестна';const group=groups.get(key)||[];group.push(node);groups.set(key,group)}
  const result:Record<string,GraphPoint>={};let x=0
  for(const [,group]of [...groups].sort(([a],[b])=>a.localeCompare(b))){const columns=Math.max(1,Math.ceil(Math.sqrt(group.length/3)));group.forEach((n,i)=>{result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:x+i%columns*310,y:Math.floor(i/columns)*145}});x+=columns*310+110}
  return result
}
