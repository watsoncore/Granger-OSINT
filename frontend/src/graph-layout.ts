import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {hierarchy} from './graph-hierarchy'

export function layoutGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,mode:'tree'|'graph',saved:Record<string,GraphPoint>={},preserve=true):Record<string,GraphPoint>{
  if(!nodes.length)return {}
  if(!nodes.some(n=>n.id===root))root=nodes[0].id
  const tree=hierarchy(nodes,edges,root),positions:Record<string,GraphPoint>={}
  const order=tree.path(root),spans=new Map<string,number>()
  for(let i=0;i<order.length;i++)order.push(...(tree.children.get(order[i])||[]))
  for(const id of [...order].reverse())spans.set(id,Math.max(1,(tree.children.get(id)||[]).reduce((sum,child)=>sum+spans.get(child)!,0)))
  if(mode==='tree'){
    const starts=new Map([[root,0]])
    for(const id of order){
      const start=starts.get(id)||0,span=spans.get(id)||1
      positions[id]={x:(tree.depth.get(id)||0)*330,y:(start+(span-1)/2)*100}
      let cursor=start;for(const child of tree.children.get(id)||[]){starts.set(child,cursor);cursor+=spans.get(child)||1}
    }
    const center=positions[root].y;for(const p of Object.values(positions))p.y-=center
  }else{
    // Radial thematic sectors, followed by bounded constrained network settling.
    // No animation loop: positions are deterministic and calculated in the worker.
    const sectors=new Map([[root,{start:-Math.PI,end:Math.PI}]])
    for(const id of order){
      const sector=sectors.get(id)!,level=tree.depth.get(id)||0,angle=(sector.start+sector.end)/2
      const radius=level?300+Math.min(3,Math.max(0,level-1))*180:0
      positions[id]={x:Math.cos(angle)*radius,y:Math.sin(angle)*radius*.42}
      let cursor=sector.start
      for(const child of tree.children.get(id)||[]){const width=(sector.end-sector.start)*(spans.get(child)||1)/(spans.get(id)||1);sectors.set(child,{start:cursor,end:cursor+width});cursor+=width}
    }
    const anchors=structuredClone(positions),ids=nodes.map(n=>n.id).sort(),rounds=nodes.length>400?35:80
    for(let step=0;step<rounds;step++){
      const bins=new Map<string,string[]>()
      for(const id of ids){const p=positions[id],key=`${Math.floor(p.x/290)},${Math.floor(p.y/135)}`,list=bins.get(key)||[];list.push(id);bins.set(key,list)}
      const moves=new Map(ids.map(id=>[id,{x:(anchors[id].x-positions[id].x)*.035,y:(anchors[id].y-positions[id].y)*.035}]))
      for(const id of ids){
        if(id===root)continue
        const p=positions[id],bx=Math.floor(p.x/290),by=Math.floor(p.y/135),move=moves.get(id)!
        for(let x=bx-1;x<=bx+1;x++)for(let y=by-1;y<=by+1;y++)for(const other of bins.get(`${x},${y}`)||[]){
          if(other===id)continue
          let dx=p.x-positions[other].x,dy=p.y-positions[other].y
          if(Math.abs(dx)>=285||Math.abs(dy)>=128)continue
          if(Math.abs(dx)+Math.abs(dy)<.001){dx=id<other?-1:1;dy=.5}
          const overlapX=285-Math.abs(dx),overlapY=128-Math.abs(dy)
          if(overlapX/285<overlapY/128)move.x+=Math.sign(dx)*overlapX*.27
          else move.y+=Math.sign(dy)*overlapY*.27
        }
      }
      // Cross-links affect the network layout while the radial anchors keep clusters stable.
      for(const edge of edges){const a=positions[edge.from_id],b=positions[edge.to_id];if(!a||!b)continue
        const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,force=Math.max(-5,Math.min(5,(d-360)*.006))
        for(const [id,sign]of [[edge.from_id,1],[edge.to_id,-1]] as const){const m=moves.get(id)!;m.x+=dx/d*force*sign;m.y+=dy/d*force*sign}
      }
      for(const id of ids)if(id!==root){const m=moves.get(id)!;positions[id].x+=Math.max(-30,Math.min(30,m.x));positions[id].y+=Math.max(-25,Math.min(25,m.y))}
    }
  }
  for(const node of nodes)if(saved[node.id]&&(preserve&&mode==='graph'||saved[node.id].pinned))positions[node.id]={...saved[node.id]}
  if(preserve&&mode==='graph'&&nodes.some(node=>saved[node.id])){
    const occupied=nodes.filter(n=>saved[n.id]).map(n=>positions[n.id]);let cursor=0
    const bottom=occupied.length?Math.max(...occupied.map(p=>p.y))+160:0
    for(const node of nodes.filter(n=>!saved[n.id])){
      let point=positions[node.id]
      if(occupied.some(p=>Math.abs(p.x-point.x)<275&&Math.abs(p.y-point.y)<115)){
        do{point={x:(cursor%5)*300,y:bottom+Math.floor(cursor/5)*130};cursor++}while(occupied.some(p=>Math.abs(p.x-point.x)<275&&Math.abs(p.y-point.y)<115))
        positions[node.id]=point
      }
      occupied.push(point)
    }
  }
  return positions
}
