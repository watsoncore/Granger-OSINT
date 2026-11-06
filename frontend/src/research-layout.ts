import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {layoutGraph,avoidCardOverlaps} from './graph-layout'
import {cardSize} from './graph-cards'

export function researchLayout(nodes:GraphEntity[],edges:GraphRelation[],root:string,saved:Record<string,GraphPoint>,mode:string){
  if(mode==='manual')return saved
  if(!nodes.length)return {}
  if(!nodes.some(node=>node.id===root))root=nodes[0].id
  if(mode==='paths')return layoutGraph(nodes,edges,root,'tree',saved,false)
  if(['wallet','flow','counterparties','identity'].includes(mode)){
    const result:Record<string,GraphPoint>={[root]:saved[root]?.pinned||mode==='identity'&&saved[root]?saved[root]:{x:0,y:0}},incoming=new Set<string>(),outgoing=new Set<string>()
    for(const edge of edges){if(edge.direction==='undirected'||edge.attributes?.financial_transfer===false||['supported_by','published_on_domain'].includes(edge.relation_type))continue;if(edge.from_id===root)outgoing.add(edge.to_id);if(edge.to_id===root)incoming.add(edge.from_id)}
    const sortKey=mode==='identity'?'platform':'chain'
    const peers=nodes.filter(n=>n.id!==root).sort((a,b)=>String(a.attributes[sortKey]||'').localeCompare(String(b.attributes[sortKey]||''))||a.label.localeCompare(b.label))
    const width=Math.max(310,...nodes.map(n=>cardSize(n).width+55)),height=Math.max(150,...nodes.map(n=>cardSize(n).height+36))
    if(mode==='wallet'||mode==='identity'){
      // Square shells keep a true centre and grow with sqrt(peers), unlike the
      // former single ring whose diameter grew linearly with every new address.
      const slots:{x:number;y:number}[]=[]
      for(let ring=1;slots.length<peers.length;ring++){
        for(let x=-ring;x<=ring;x++)slots.push({x,y:-ring})
        for(let y=-ring+1;y<=ring;y++)slots.push({x:ring,y})
        for(let x=ring-1;x>=-ring;x--)slots.push({x,y:ring})
        for(let y=ring-1;y>-ring;y--)slots.push({x:-ring,y})
      }
      peers.forEach((node,i)=>{result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x:slots[i].x*width,y:slots[i].y*height}})
    }
    else if(mode==='flow'){
      const columns=new Map<string,GraphEntity[]>()
      for(const node of peers){const kind=incoming.has(node.id)&&outgoing.has(node.id)?'both':incoming.has(node.id)?'in':outgoing.has(node.id)?'out':'unresolved',rows=columns.get(kind)||[];rows.push(node);columns.set(kind,rows)}
      for(const [kind,rows]of columns){
        const count=Math.max(1,Math.ceil(Math.sqrt(rows.length*height/width))),lines=Math.ceil(rows.length/count)
        rows.forEach((node,i)=>{const column=i%count,row=Math.floor(i/count),horizontal=kind==='in'||kind==='out'
          const x=horizontal?(kind==='in'?-1:1)*(1.65+column)*width:(column-(count-1)/2)*width
          const y=horizontal?(row-(lines-1)/2)*height:(kind==='both'?1:-1)*(1.8+row)*height
          result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x,y}
        })
      }
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
  if(mode==='hierarchical')return layoutGraph(nodes,edges,root,'tree',saved,false)
  if(mode==='radial'){
    const adjacent=new Map(nodes.map(n=>[n.id,[] as string[]]));for(const e of edges){adjacent.get(e.from_id)?.push(e.to_id);adjacent.get(e.to_id)?.push(e.from_id)}
    const depth=new Map([[root,0]]),queue=[root];for(let i=0;i<queue.length;i++)for(const id of adjacent.get(queue[i])||[])if(!depth.has(id)){depth.set(id,(depth.get(queue[i])||0)+1);queue.push(id)}
    const levels=new Map<number,GraphEntity[]>();for(const n of nodes){const d=depth.get(n.id)??1,group=levels.get(d)||[];group.push(n);levels.set(d,group)}
    const result:Record<string,GraphPoint>={};let previous=0
    for(const [depth,group]of [...levels].sort(([a],[b])=>a-b)){
      const spacing=Math.max(310,...group.map(n=>Math.hypot(cardSize(n).width,cardSize(n).height)+45))
      if(!depth){for(const node of group)result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x:0,y:0};continue}
      let cursor=0,radius=Math.max(previous+spacing,spacing*1.2)
      while(cursor<group.length){const capacity=Math.max(6,Math.floor(2*Math.PI*radius/spacing)),ring=group.slice(cursor,cursor+capacity)
        ring.forEach((node,i)=>{const angle=i/ring.length*Math.PI*2-Math.PI/2;result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x:Math.cos(angle)*radius,y:Math.sin(angle)*radius}})
        cursor+=ring.length;previous=radius;radius+=spacing
      }
    }
    const origin=result[root];if(origin&&(origin.x||origin.y))for(const node of nodes)if(node.id!==root&&!saved[node.id]?.pinned){result[node.id].x+=origin.x;result[node.id].y+=origin.y}
    return avoidCardOverlaps(nodes,result,saved)
  }
  const groups=new Map<string,GraphEntity[]>(),byId=new Map(nodes.map(n=>[n.id,n])),parents=new Map(nodes.map(n=>[n.id,n.id]))
  const find=(id:string):string=>{let p=parents.get(id)||id;while(parents.get(p)&&parents.get(p)!==p)p=parents.get(p)!;while(parents.get(id)!==id){const next=parents.get(id)!;parents.set(id,p);id=next}return p}
  // The scope/root links every result; including it in community detection
  // collapsed every counterparty into one useless component.
  if(mode==='communities')for(const e of edges)if(e.from_id!==root&&e.to_id!==root&&byId.has(e.from_id)&&byId.has(e.to_id)){const a=find(e.from_id),b=find(e.to_id);if(a!==b)parents.set(a,b)}
  const counts=new Map<string,number>();if(mode==='communities')for(const node of nodes){const key=find(node.id);counts.set(key,(counts.get(key)||0)+1)}
  for(const node of nodes){
    const raw=String(node.attributes.timestamp||node.attributes.observed_at||node.attributes.first_seen||''),time=Date.parse(raw),component=find(node.id)
    const cluster=node.id===root?'':node.attributes.parent_group_id||((counts.get(component)||0)>1?component:`${node.attributes.chain||node.attributes.platform||node.type}`)
    const key=mode==='types'?node.type:mode==='communities'?String(cluster):Number.isFinite(time)?new Date(time).toISOString().slice(0,10):'Дата неизвестна'
    const group=groups.get(key)||[];group.push(node);groups.set(key,group)
  }
  if(mode==='communities'||mode==='types'){
    const result:Record<string,GraphPoint>={},maxWidth=Math.max(310,...nodes.map(node=>cardSize(node).width+46)),maxHeight=Math.max(145,...nodes.map(node=>cardSize(node).height+30)),shelf=Math.max(maxWidth*4,Math.sqrt(nodes.length*maxWidth*maxHeight)*1.45)
    let x=0,y=0,rowHeight=0
    for(const [,group]of [...groups].sort(([a],[b])=>a.localeCompare(b))){
      const columns=Math.max(1,Math.ceil(Math.sqrt(group.length*maxHeight/maxWidth))),rows=Math.ceil(group.length/columns),groupWidth=columns*maxWidth,groupHeight=rows*maxHeight
      if(x&&x+groupWidth>shelf){x=0;y+=rowHeight+maxHeight;rowHeight=0}
      group.forEach((node,i)=>{result[node.id]=saved[node.id]?.pinned?saved[node.id]:{x:x+i%columns*maxWidth,y:y+Math.floor(i/columns)*maxHeight}})
      x+=groupWidth+maxWidth;rowHeight=Math.max(rowHeight,groupHeight)
    }
    return avoidCardOverlaps(nodes,result,saved)
  }
  const result:Record<string,GraphPoint>={};let x=0
  for(const [,group]of [...groups].sort(([a],[b])=>a.localeCompare(b))){const columns=Math.max(1,Math.ceil(Math.sqrt(group.length/3))),w=Math.max(310,...group.map(n=>cardSize(n).width+46)),h=Math.max(145,...group.map(n=>cardSize(n).height+30));group.forEach((n,i)=>{result[n.id]=saved[n.id]?.pinned?saved[n.id]:{x:x+i%columns*w,y:Math.floor(i/columns)*h}});x+=columns*w+110}
  return avoidCardOverlaps(nodes,result,saved)
}
