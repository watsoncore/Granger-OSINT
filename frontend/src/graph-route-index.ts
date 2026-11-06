import type {GraphEntity,GraphPoint,GraphRelation,GraphViewport} from './types'
import {routeEdges,type EdgeRoute,type EdgeStyle} from './graph-geometry'

interface Rect {left:number;top:number;right:number;bottom:number}
interface Entry extends Rect {route:EdgeRoute;order:number}
interface Branch extends Rect {entries?:Entry[];a?:Branch;b?:Branch}
const intersects=(a:Rect,b:Rect)=>a.left<=b.right&&a.right>=b.left&&a.top<=b.bottom&&a.bottom>=b.top
function tree(entries:Entry[]):Branch{
 const bounds={left:Math.min(...entries.map(row=>row.left)),right:Math.max(...entries.map(row=>row.right)),top:Math.min(...entries.map(row=>row.top)),bottom:Math.max(...entries.map(row=>row.bottom))}
 if(entries.length<=12)return {...bounds,entries}
 const horizontal=bounds.right-bounds.left>=bounds.bottom-bounds.top
 entries.sort((a,b)=>horizontal?a.left+a.right-b.left-b.right:a.top+a.bottom-b.top-b.bottom)
 const middle=Math.floor(entries.length/2)
 return {...bounds,a:tree(entries.slice(0,middle)),b:tree(entries.slice(middle))}
}
function refit(branch:Branch):void{
 if(branch.entries){branch.left=Math.min(...branch.entries.map(row=>row.left));branch.right=Math.max(...branch.entries.map(row=>row.right));branch.top=Math.min(...branch.entries.map(row=>row.top));branch.bottom=Math.max(...branch.entries.map(row=>row.bottom));return}
 if(branch.a)refit(branch.a);if(branch.b)refit(branch.b)
 if(branch.a&&branch.b){branch.left=Math.min(branch.a.left,branch.b.left);branch.right=Math.max(branch.a.right,branch.b.right);branch.top=Math.min(branch.a.top,branch.b.top);branch.bottom=Math.max(branch.a.bottom,branch.b.bottom)}
}
/** World-space route cache + bounding hierarchy. No persistence or model copies. */
export class EdgeRouteIndex {
 private root?:Branch
 private incident=new Map<string,GraphRelation[]>()
 private entries=new Map<string,Entry>()
 private saved=new Map<string,GraphPoint>()
 generation=0
 readonly routes:EdgeRoute[]
 constructor(readonly edges:GraphRelation[],readonly nodes:GraphEntity[],public positions:Record<string,GraphPoint>,readonly scale:number,readonly mode:'tree'|'graph'='graph',readonly style:EdgeStyle='curved'){
  this.routes=routeEdges(edges,positions,{x:0,y:0,scale},nodes,mode,undefined,style).map(row=>({edge:row.edge,points:row.points.map(point=>({x:point.x/scale,y:point.y/scale}))}))
  const entries=this.routes.map((route,order)=>({route,order,left:Math.min(...route.points.map(p=>p.x)),right:Math.max(...route.points.map(p=>p.x)),top:Math.min(...route.points.map(p=>p.y)),bottom:Math.max(...route.points.map(p=>p.y))}))
  this.entries=new Map(entries.map(entry=>[entry.route.edge.id,entry]))
  if(entries.length)this.root=tree(entries)
  for(const [id,p]of Object.entries(positions))this.saved.set(id,{x:p.x,y:p.y})
  for(const edge of edges)for(const id of new Set([edge.from_id,edge.to_id])){const rows=this.incident.get(id)||[];rows.push(edge);this.incident.set(id,rows)}
 }
 updatePositions(positions:Record<string,GraphPoint>){
  const dirty=new Map<string,GraphRelation>();this.positions=positions
  for(const [id,p]of Object.entries(positions)){
   const before=this.saved.get(id)
   if(before?.x===p.x&&before.y===p.y)continue
   this.saved.set(id,{x:p.x,y:p.y});for(const edge of this.incident.get(id)||[])dirty.set(edge.id,edge)
  }
  if(!dirty.size)return
  for(const route of routeEdges([...dirty.values()],positions,{x:0,y:0,scale:this.scale},this.nodes,this.mode,undefined,this.style)){
   const entry=this.entries.get(route.edge.id);if(!entry)continue
   const points=route.points.map(p=>({x:p.x/this.scale,y:p.y/this.scale}))
   entry.route={edge:route.edge,points};this.routes[entry.order]=entry.route
   Object.assign(entry,{left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),top:Math.min(...points.map(p=>p.y)),bottom:Math.max(...points.map(p=>p.y))})
  }
  if(this.root)refit(this.root);this.generation++
 }
 query(view:GraphViewport,rect:Rect,moving:Record<string,GraphPoint>={}){
  const world={left:(rect.left-view.x-12)/view.scale,right:(rect.right-view.x+12)/view.scale,top:(rect.top-view.y-12)/view.scale,bottom:(rect.bottom-view.y+12)/view.scale}
  const movingEdges=new Map<string,GraphRelation>()
  for(const id of Object.keys(moving))for(const edge of this.incident.get(id)||[])movingEdges.set(edge.id,edge)
  const found:Entry[]=[]
  const visit=(branch:Branch)=>{if(!intersects(branch,world))return;if(branch.entries){for(const entry of branch.entries)if(!movingEdges.has(entry.route.edge.id)&&intersects(entry,world))found.push(entry)}else{if(branch.a)visit(branch.a);if(branch.b)visit(branch.b)}}
  if(this.root)visit(this.root)
  const routes=found.sort((a,b)=>a.order-b.order).map(row=>row.route)
  if(movingEdges.size){
   const dynamic=routeEdges([...movingEdges.values()],this.positions,view,this.nodes,this.mode,rect,this.style)
   routes.push(...dynamic.map(row=>({edge:row.edge,points:row.points.map(p=>({x:(p.x-view.x)/view.scale,y:(p.y-view.y)/view.scale}))})))
  }
  return routes
 }
}
