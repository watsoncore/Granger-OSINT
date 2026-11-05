import type { GraphEntity,GraphPoint,GraphRelation,GraphViewport } from './types'
import {cardSize} from './graph-cards'

export function nodeBox(node:GraphEntity,scale:number){
  const size=cardSize(node)
  // A distant object is a semantic glyph, not an unreadable thumbnail of its
  // detailed card. Rendering, hit-testing, routing and culling share its bounds.
  return scale<.38?{width:Math.max(110,size.width*scale),height:Math.max(42,size.height*scale)}:{width:size.width*scale,height:size.height*scale}
}
interface Point {x:number;y:number}
interface Rect {left:number;top:number;right:number;bottom:number}

/** World-space cells remain valid through pans and zooms. Preserve paint order
 * for overlapping cards. Active drags are a small overlay on the saved cells. */
export class CardIndex {
  private cells=new Map<string,number[]>()
  private order=new Map<string,number>()
  private readonly cellSize=400
  constructor(private nodes:GraphEntity[],positions:Record<string,GraphPoint>){
    nodes.forEach((node,index)=>{
      this.order.set(node.id,index)
      const position=positions[node.id]
      if(!position)return
      const key=this.cell(position.x)+','+this.cell(position.y)
      const bucket=this.cells.get(key)
      if(bucket)bucket.push(index)
      else this.cells.set(key,[index])
    })
  }
  private cell(value:number){return Math.floor(value/this.cellSize)}
  query(view:GraphViewport,rect:Rect,moving:Record<string,GraphPoint>={}){
    const margin=Math.max(360,75/view.scale)+26/view.scale
    const left=this.cell((rect.left-view.x)/view.scale-margin),right=this.cell((rect.right-view.x)/view.scale+margin)
    const top=this.cell((rect.top-view.y)/view.scale-margin),bottom=this.cell((rect.bottom-view.y)/view.scale+margin)
    if((right-left+1)*(bottom-top+1)>=this.nodes.length)return this.nodes
    const indexes=new Set<number>()
    for(let x=left;x<=right;x++)for(let y=top;y<=bottom;y++){
      const bucket=this.cells.get(x+','+y)
      if(bucket)for(const index of bucket)indexes.add(index)
    }
    for(const id of Object.keys(moving)){
      const index=this.order.get(id)
      if(index!==undefined)indexes.add(index)
    }
    return [...indexes].sort((a,b)=>a-b).map(index=>this.nodes[index])
  }
}
export interface EdgeRoute {edge:GraphRelation;points:Point[]}
const nodeIndexes=new WeakMap<GraphEntity[],Map<string,GraphEntity>>()
const edgeGroups=new WeakMap<GraphRelation[],Map<string,GraphRelation[]>>()
export function routeEdges(edges:GraphRelation[],positions:Record<string,GraphPoint>,view:GraphViewport,nodes:GraphEntity[]=[],mode:'tree'|'graph'='graph',clip?:Rect):EdgeRoute[]{
  let byId=nodeIndexes.get(nodes);if(!byId){byId=new Map(nodes.map(node=>[node.id,node]));nodeIndexes.set(nodes,byId)}
  let groups=edgeGroups.get(edges);if(!groups){groups=new Map<string,GraphRelation[]>();for(const edge of edges){const key=[edge.from_id,edge.to_id].sort().join('|');const list=groups.get(key)||[];list.push(edge);groups.set(key,list)}edgeGroups.set(edges,groups)}
  const screen=(id:string)=>{const point=positions[id];return point?{x:point.x*view.scale+view.x,y:point.y*view.scale+view.y}:null}
  const border=(id:string,center:Point,towards:Point)=>{
    const node=byId.get(id),box=node?nodeBox(node,view.scale):{width:16,height:16}
    const dx=towards.x-center.x,dy=towards.y-center.y,t=Math.min(1,1/Math.max(Math.abs(dx)/(box.width/2+4),Math.abs(dy)/(box.height/2+4),.0001))
    return {x:center.x+dx*t,y:center.y+dy*t}
  }
  const result:EdgeRoute[]=[]
  for(const list of groups.values())list.forEach((edge,index)=>{
    const a=screen(edge.from_id),b=screen(edge.to_id);if(!a||!b)return
    // Reject the whole conservative curve bounds before allocating samples.
    // The lane/control-point margin also retains loops and crossing edges
    // whose endpoints are both outside the viewport.
    const margin=Math.max(260,list.length*36+140)
    if(clip&&(Math.max(a.x,b.x)+margin<clip.left||Math.min(a.x,b.x)-margin>clip.right||Math.max(a.y,b.y)+margin<clip.top||Math.min(a.y,b.y)-margin>clip.bottom))return
    const points:Point[]=[]
    if(edge.from_id===edge.to_id){
      const node=byId.get(edge.from_id),box=node?nodeBox(node,view.scale):{width:24,height:24},x=a.x+box.width/2+4
      for(let step=0;step<=16;step++){const t=step/16,u=1-t;points.push({x:u*u*u*x+3*u*u*t*(x+90)+3*u*t*t*(x+90)+t*t*t*x,
        y:u*u*u*(a.y-15)+3*u*u*t*(a.y-110)+3*u*t*t*(a.y+110)+t*t*t*(a.y+15)})}
    }else if(mode==='tree'){
      const start=border(edge.from_id,a,{x:b.x,y:a.y}),end=border(edge.to_id,b,{x:a.x,y:b.y}),middle=(start.x+end.x)/2
      points.push(start,{x:middle,y:start.y},{x:middle,y:end.y},end)
    }else{
      // One deterministic lane per directed relation/asset; opposing flows remain pickable.
      const direction=edge.from_id<edge.to_id?1:-1,dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1
      const offset=(index-(list.length-1)/2)*36*direction
      const c={x:(a.x+b.x)/2-dy/d*offset*2,y:(a.y+b.y)/2+dx/d*offset*2}
      const start=border(edge.from_id,a,c),end=border(edge.to_id,b,c)
      const segments=offset===0?2:Math.min(12,Math.max(4,Math.ceil(Math.sqrt(Math.abs(offset))*1.3)))
      for(let step=0;step<=segments;step++){const t=step/segments,u=1-t;points.push({x:u*u*start.x+2*u*t*c.x+t*t*end.x,y:u*u*start.y+2*u*t*c.y+t*t*end.y})}
    }
    result.push({edge,points})
  })
  return result
}
