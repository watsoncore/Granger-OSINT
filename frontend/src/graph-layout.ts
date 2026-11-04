import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {hierarchy} from './graph-hierarchy'
import {cardSize} from './graph-cards'

export function layoutGraph(nodes:GraphEntity[],edges:GraphRelation[],root:string,mode:'tree'|'graph',saved:Record<string,GraphPoint>={},preserve=true):Record<string,GraphPoint>{
  if(!nodes.length)return {}
  if(!nodes.some(n=>n.id===root))root=nodes[0].id
  const sizes=new Map(nodes.map(n=>[n.id,cardSize(n)])),maxWidth=Math.max(...nodes.map(n=>sizes.get(n.id)!.width))+48,maxHeight=Math.max(...nodes.map(n=>sizes.get(n.id)!.height))+32
  const tree=hierarchy(nodes,edges,root),positions:Record<string,GraphPoint>={}
  const order=tree.path(root),spans=new Map<string,number>()
  for(let i=0;i<order.length;i++)order.push(...(tree.children.get(order[i])||[]))
  for(const id of [...order].reverse())spans.set(id,Math.max(1,(tree.children.get(id)||[]).reduce((sum,child)=>sum+spans.get(child)!,0)))
  if(mode==='tree'){
    const starts=new Map([[root,0]])
    for(const id of order){
      const start=starts.get(id)||0,span=spans.get(id)||1
      positions[id]={x:(tree.depth.get(id)||0)*Math.max(330,maxWidth),y:(start+(span-1)/2)*Math.max(120,maxHeight)}
      let cursor=start;for(const child of tree.children.get(id)||[]){starts.set(child,cursor);cursor+=spans.get(child)||1}
    }
    const center=positions[root].y;for(const p of Object.values(positions))p.y-=center
  }else{
    // Radial thematic sectors, followed by bounded constrained network settling.
    // No animation loop: positions are deterministic and calculated in the worker.
    const sectors=new Map([[root,{start:-Math.PI,end:Math.PI}]])
    for(const id of order){
      const sector=sectors.get(id)!,level=tree.depth.get(id)||0,angle=(sector.start+sector.end)/2
      const radius=level?Math.max(350,maxWidth)+Math.min(3,Math.max(0,level-1))*Math.max(200,maxHeight):0
      positions[id]={x:Math.cos(angle)*radius,y:Math.sin(angle)*radius*.42}
      let cursor=sector.start
      for(const child of tree.children.get(id)||[]){const width=(sector.end-sector.start)*(spans.get(child)||1)/(spans.get(id)||1);sectors.set(child,{start:cursor,end:cursor+width});cursor+=width}
    }
    if(nodes.length>400){
      const levels=new Map<number,string[]>();for(const id of order){const level=tree.depth.get(id)||0,row=levels.get(level)||[];row.push(id);levels.set(level,row)}let prior=0
      for(const [level,rows]of [...levels].sort(([a],[b])=>a-b)){const radius=level?Math.max(prior+maxWidth,rows.length*maxWidth/(2*Math.PI)):0;prior=radius;rows.forEach((id,i)=>{const angle=i/rows.length*Math.PI*2;positions[id]={x:Math.cos(angle)*radius,y:Math.sin(angle)*radius}})}
    }
    const anchors=structuredClone(positions),ids=nodes.map(n=>n.id).sort(),rounds=nodes.length>400?0:80
    for(let step=0;step<rounds;step++){
      const bins=new Map<string,string[]>()
      for(const id of ids){const p=positions[id],key=`${Math.floor(p.x/maxWidth)},${Math.floor(p.y/maxHeight)}`,list=bins.get(key)||[];list.push(id);bins.set(key,list)}
      const moves=new Map(ids.map(id=>[id,{x:(anchors[id].x-positions[id].x)*.035,y:(anchors[id].y-positions[id].y)*.035}]))
      for(const id of ids){
        if(id===root)continue
        const p=positions[id],bx=Math.floor(p.x/maxWidth),by=Math.floor(p.y/maxHeight),move=moves.get(id)!,size=sizes.get(id)!
        for(let x=bx-1;x<=bx+1;x++)for(let y=by-1;y<=by+1;y++)for(const other of bins.get(`${x},${y}`)||[]){
          if(other===id)continue
          let dx=p.x-positions[other].x,dy=p.y-positions[other].y
          const otherSize=sizes.get(other)!,gapX=(size.width+otherSize.width)/2+38,gapY=(size.height+otherSize.height)/2+28
          if(Math.abs(dx)>=gapX||Math.abs(dy)>=gapY)continue
          if(Math.abs(dx)+Math.abs(dy)<.001){dx=id<other?-1:1;dy=.5}
          const overlapX=gapX-Math.abs(dx),overlapY=gapY-Math.abs(dy)
          if(overlapX/gapX<overlapY/gapY)move.x+=Math.sign(dx)*overlapX*.27
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
    const bottom=occupied.length?Math.max(...occupied.map(p=>p.y))+maxHeight:0
    for(const node of nodes.filter(n=>!saved[n.id])){
      let point=positions[node.id]
      if(occupied.some(p=>Math.abs(p.x-point.x)<maxWidth&&Math.abs(p.y-point.y)<maxHeight)){
        do{point={x:(cursor%5)*maxWidth,y:bottom+Math.floor(cursor/5)*maxHeight};cursor++}while(occupied.some(p=>Math.abs(p.x-point.x)<maxWidth&&Math.abs(p.y-point.y)<maxHeight))
        positions[node.id]=point
      }
      occupied.push(point)
    }
  }
  return mode==='graph'?avoidCardOverlaps(nodes,positions,saved,preserve):positions
}

/** Spatial bins bound overlap work; saved/manual positions are never silently moved. */
export function avoidCardOverlaps(nodes:GraphEntity[],positions:Record<string,GraphPoint>,saved:Record<string,GraphPoint>={},preserve=false){
  const sizes=new Map(nodes.map(n=>[n.id,cardSize(n)])),w=Math.max(280,...nodes.map(n=>sizes.get(n.id)!.width+42)),h=Math.max(130,...nodes.map(n=>sizes.get(n.id)!.height+30)),bins=new Map<string,string[]>(),result:Record<string,GraphPoint>={}
  const add=(id:string,p:GraphPoint)=>{result[id]=p;const key=`${Math.floor(p.x/w)},${Math.floor(p.y/h)}`,rows=bins.get(key)||[];rows.push(id);bins.set(key,rows)}
  const collides=(id:string,p:GraphPoint)=>{const size=sizes.get(id)!,x=Math.floor(p.x/w),y=Math.floor(p.y/h);for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)for(const other of bins.get(`${x+dx},${y+dy}`)||[]){const b=result[other],s=sizes.get(other)!;if(Math.abs(p.x-b.x)<(size.width+s.width)/2+38&&Math.abs(p.y-b.y)<(size.height+s.height)/2+28)return true}return false}
  const fixed=new Set(nodes.filter(n=>saved[n.id]&&(saved[n.id].pinned||preserve)).map(n=>n.id))
  for(const node of nodes)if(fixed.has(node.id))add(node.id,{...saved[node.id]})
  const base=Math.max(0,...Object.values(positions).map(p=>p.y))+h;let grid=0
  for(const node of nodes){if(fixed.has(node.id))continue;const anchor=positions[node.id]||{x:0,y:0};let point={...anchor},attempt=0
    while(collides(node.id,point)&&attempt<24){attempt++;const angle=attempt*2.399963,radius=Math.sqrt(attempt)*Math.max(w,h)*.7;point={x:anchor.x+Math.cos(angle)*radius,y:anchor.y+Math.sin(angle)*radius}}
    if(collides(node.id,point)){do{point={x:grid%12*w,y:base+Math.floor(grid/12)*h};grid++}while(collides(node.id,point))}
    add(node.id,point)
  }
  return result
}
