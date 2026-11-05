import { forwardRef,useEffect,useImperativeHandle,useMemo,useRef } from 'react'
import type { GraphEntity,GraphPoint,GraphRelation,GraphViewport } from '../types'
import { entityLabel,fitViewport,readableViewport,hitNode,hitRelation,nodeBox,relationLabels,shortLabel,zoomAt } from '../graph-model'
import { CardIndex } from '../graph-geometry'
import {EdgeRouteIndex} from '../graph-route-index'
import {GraphGpuLayer,type GpuLine} from '../graph-gpu'
import {cardBadge,cardRows,cardTitle,cardVariant,cardVariants,withCardPresentation,type CardMode,type CardSize} from '../graph-cards'
import {GraphCamera} from '../graph-camera'
import {formatGraphAmount} from '../graph-money'
import {semanticGraph} from '../graph-semantic'
import {mediaThumbnail,visualMedia,type MediaReference} from '../canvas-media'

declare global {interface Window {
  __GRANGER_QA_GRAPH__?:boolean
  grangerGraphFileDrop?(phase:'hover'|'leave'|'drop',x:number,y:number,nativeWidth:number,nativeHeight:number,token?:string):void
}}
const metricsEnabled=()=>window.__GRANGER_QA_GRAPH__===true||import.meta.env.MODE==='test'

export interface GraphCanvasHandle { fit(ids?:string[]):void; zoom(factor:number):void; center(id:string):void; insertPoint?(size:CardSize):GraphPoint }
interface Props {
  nodes:GraphEntity[];edges:GraphRelation[];positions:Record<string,GraphPoint>;viewport:GraphViewport;scopeKey?:string
  selected:string;second:string;selectedEdge:string;root:string;theme?:unknown;mode?:'tree'|'graph'
  onSelect(id:string,second:boolean):void;onEdge(id:string):void
  onCommitPositions(value:Record<string,GraphPoint>):void;onViewport(value:GraphViewport):void
  onResize(width:number,height:number):void
  selection?:string[];onSelection?(ids:string[]):void
  onCreate?(position:GraphPoint):void;onConnect?(from:string,to:string):void
  onContext?(id:string,position:GraphPoint):void
  cardSizes?:Record<string,CardSize>;cardMode?:CardMode
  onCardResize?(id:string,size:CardSize):void;onOpenMedia?(node:GraphEntity):void;onExpand?(id:string):void
  onDropImage?(file:File,position:GraphPoint):void
  onNativeDrop?(token:string,position:GraphPoint):void
  loadImage?(node:GraphEntity,media:MediaReference):Promise<string>
}
export const InvestigationCanvas=forwardRef<GraphCanvasHandle,Props>(function InvestigationCanvas(props,forwarded) {
  const presented=useMemo(()=>withCardPresentation(props.nodes,props.cardSizes,props.cardMode),[props.nodes,props.cardSizes,props.cardMode])
  const canvas=useRef<HTMLCanvasElement>(null),latest=useRef(props);latest.current={...props,nodes:presented}
  const gpuCanvas=useRef<HTMLCanvasElement>(null),gpu=useRef<GraphGpuLayer|undefined>(undefined)
  const geometry=useRef<EdgeRouteIndex|undefined>(undefined),uploaded=useRef<{index:EdgeRouteIndex;key:string}|undefined>(undefined)
  const edgeColors=useRef(new Map<string,[number,number,number,number]>())
  const points=useRef({...props.positions}),viewport=useRef(props.viewport)
  const camera=useRef(new GraphCamera(props.viewport)),pendingPoints=useRef<Record<string,GraphPoint>>({})
  const cameraFrames=useRef<{time:number;x:number;y:number;scale:number;event:string}[]>([]),lastCameraFrame=useRef('')
  const farClusters=useRef<{id:string;members:string[];x:number;y:number;width:number;height:number}[]>([])
  const semanticCache=useRef<{nodes:GraphEntity[];edges:GraphRelation[];positions:Record<string,GraphPoint>;scale:number;protected:string;value:ReturnType<typeof semanticGraph>}|undefined>(undefined)
  const spatial=useRef<{nodes:GraphEntity[];positions:Record<string,GraphPoint>;index:CardIndex}|undefined>(undefined)
  const textWidths=useRef(new Map<string,number>())
  const sizeRef=useRef({width:800,height:440})
  const visible=useRef(true)
  const frame=useRef<number|undefined>(undefined),wheelTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined)
  const thumbnails=useRef(new Map<string,HTMLImageElement|null>())
  const pendingThumbnails=useRef(new Set<string>())
  const dropPoint=useRef<GraphPoint|undefined>(undefined)
  const drag=useRef<{id?:string;startX:number;startY:number;point?:GraphPoint;view:GraphViewport;moved:boolean}|undefined>(undefined)
  const lastMediaClick=useRef<{id:string;x:number;y:number;at:number}|undefined>(undefined)
  const linkPoint=useRef<{x:number;y:number}|undefined>(undefined)
  const linking=useRef<string|undefined>(undefined),marquee=useRef<{x:number;y:number;endX:number;endY:number}|undefined>(undefined)
  const mini=useRef<{x:number;y:number;w:number;h:number;minX:number;minY:number;scale:number}|undefined>(undefined)
  const miniGeometry=useRef<{nodes:GraphEntity[];positions:Record<string,GraphPoint>;minX:number;minY:number;width:number;height:number;scale:number;marks:Path2D;groups:Path2D}|undefined>(undefined)
  const moving=useRef<Record<string,GraphPoint>>({})
  const hovered=useRef(''),resizing=useRef<{id:string;x:number;y:number;size:CardSize}|undefined>(undefined),resizeSizes=useRef<Record<string,CardSize>>({})
  const paints=useRef<number[]>([]),intervals=useRef<number[]>([]),latencies=useRef<number[]>([]),lastPaint=useRef(0),lastInput=useRef(0)
  function recordCamera(event:string){
    if(!metricsEnabled())return
    const v=viewport.current,key=`${v.x}|${v.y}|${v.scale}`
    if(key===lastCameraFrame.current&&event==='frame')return
    lastCameraFrame.current=key
    cameraFrames.current.push({time:performance.now(),...v,event})
    if(cameraFrames.current.length>120)cameraFrames.current.shift()
    if(canvas.current)canvas.current.dataset.qaCameraFrames=JSON.stringify(cameraFrames.current)
  }
  function moveViewport(next:GraphViewport){camera.current.move(next);viewport.current=camera.current.value;requestDraw()}
  function commitViewport(next=viewport.current){
    viewport.current=camera.current.commit(next);recordCamera('commit');requestDraw();latest.current.onViewport({...viewport.current})
  }
  function fit(ids?:string[]){
    const subset=ids?.length?new Set(ids):undefined
    const nodes=latest.current.nodes.filter(node=>!subset||subset.has(node.id))
    const visiblePositions=Object.fromEntries(nodes.filter(node=>points.current[node.id]).map(node=>[node.id,points.current[node.id]]))
    commitViewport(fitViewport(visiblePositions,sizeRef.current.width,sizeRef.current.height,nodes))
  }
  function zoomCluster(point:{x:number;y:number}){
    if(viewport.current.scale>=.38)return false
    const cluster=farClusters.current.find(row=>Math.abs(point.x-row.x)<=row.width/2&&Math.abs(point.y-row.y)<=row.height/2)
    if(!cluster)return false
    const ids=new Set(cluster.members),nodes=latest.current.nodes.filter(node=>ids.has(node.id)),positions=Object.fromEntries(cluster.members.filter(id=>points.current[id]).map(id=>[id,points.current[id]]))
    commitViewport(readableViewport(positions,sizeRef.current.width,sizeRef.current.height,cluster.members[0],latest.current.mode||'graph',nodes));return true
  }
  function nodeAt(point:{x:number;y:number}){
    const view=viewport.current,cache=semanticCache.current
    const area={left:point.x,top:point.y,right:point.x,bottom:point.y}
    if(view.scale<.38&&cache?.scale===view.scale&&cache.positions===points.current){
      const node=hitNode(cardIndex(cache.value.nodes,cache.value.positions).query(view,area),cache.value.positions,view,point.x,point.y)
      return node?.attributes.semantic_cluster?undefined:node
    }
    return hitNode(cardIndex(latest.current.nodes,points.current).query(view,area,moving.current),points.current,view,point.x,point.y)
  }
  function cardIndex(nodes:GraphEntity[],positions:Record<string,GraphPoint>){
    const cached=spatial.current
    if(cached?.nodes===nodes&&cached.positions===positions)return cached.index
    const index=new CardIndex(nodes,positions)
    spatial.current={nodes,positions,index}
    return index
  }
  function thumbnail(node:GraphEntity,media:MediaReference,visible:Set<string>){
    const cache=thumbnails.current,key=media.id
    if(cache.has(key)){
      const picture=cache.get(key)
      cache.delete(key);cache.set(key,picture||null)
      return picture
    }
    const pending=pendingThumbnails.current,embedded=mediaThumbnail(media),load=latest.current.loadImage
    if(pending.has(key)||pending.size>=2||!embedded&&(!load||media.kind!=='local_attachment'))return
    if(cache.size>=64){
      const discard=[...cache.keys()].find(id=>!visible.has(id))
      if(!discard)return
      cache.delete(discard)
    }
    pending.add(key)
    const source=embedded?Promise.resolve(embedded):load!(node,media)
    void source.then(async src=>{
      if(!src)return null
      const picture=new Image();picture.src=src
      await picture.decode()
      return picture
    }).catch(()=>null).then(picture=>{
      pending.delete(key)
      if(canvas.current){
        while(cache.size>=64)cache.delete(cache.keys().next().value!)
        cache.set(key,picture);requestDraw()
      }
    })
  }
  function drawMinimap(ctx:CanvasRenderingContext2D,nodes:GraphEntity[],positions:Record<string,GraphPoint>,view:GraphViewport,width:number,height:number,colors:{panel:string;border:string;muted:string;accent:string}){
    mini.current=undefined
    if(nodes.length<4||width<620||height<340||typeof Path2D==='undefined')return
    const w=128,h=76
    let geometry=miniGeometry.current
    if(!geometry||geometry.nodes!==nodes||geometry.positions!==positions){
      let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity
      for(const node of nodes){
        const point=positions[node.id];if(!point)continue
        const box=nodeBox(node,1)
        minX=Math.min(minX,point.x-box.width/2);minY=Math.min(minY,point.y-box.height/2)
        maxX=Math.max(maxX,point.x+box.width/2);maxY=Math.max(maxY,point.y+box.height/2)
      }
      if(!Number.isFinite(minX))return
      const worldWidth=maxX-minX+32,worldHeight=maxY-minY+32,scale=Math.min(w/worldWidth,h/worldHeight)
      minX-=16+(w/scale-worldWidth)/2;minY-=16+(h/scale-worldHeight)/2
      const marks=new Path2D(),groups=new Path2D()
      for(const node of nodes){
        const point=positions[node.id];if(!point)continue
        const x=(point.x-minX)*scale,y=(point.y-minY)*scale
        if(node.type==='entity_group')groups.rect(x-2,y-2,4,4)
        else marks.rect(x-1,y-1,2,2)
      }
      geometry={nodes,positions,minX,minY,width:worldWidth,height:worldHeight,scale,marks,groups}
      miniGeometry.current=geometry
    }
    if(width/view.scale>=geometry.width&&height/view.scale>=geometry.height&&
      -view.x/view.scale<=geometry.minX&&-view.y/view.scale<=geometry.minY)return
    const x=width-w-12,y=height-h-12,{minX,minY,scale}=geometry
    mini.current={x,y,w,h,minX,minY,scale}
    ctx.save();ctx.translate(x,y);ctx.fillStyle=colors.panel;ctx.fillRect(0,0,w,h)
    ctx.beginPath();ctx.rect(0,0,w,h);ctx.clip()
    ctx.fillStyle=colors.muted;ctx.globalAlpha=.6;ctx.fill(geometry.marks)
    ctx.fillStyle=colors.accent;ctx.fill(geometry.groups);ctx.globalAlpha=1
    for(const id of [latest.current.root,latest.current.selected]){
      const point=positions[id]
      if(point)ctx.fillRect((point.x-minX)*scale-2,(point.y-minY)*scale-2,4,4)
    }
    ctx.strokeStyle=colors.accent;ctx.lineWidth=1
    ctx.strokeRect((-view.x/view.scale-minX)*scale,(-view.y/view.scale-minY)*scale,width/view.scale*scale,height/view.scale*scale)
    ctx.restore();ctx.strokeStyle=colors.border;ctx.lineWidth=1;ctx.strokeRect(x,y,w,h)
  }
  function draw() {
    frame.current=undefined
    const element=canvas.current,ctx=element?.getContext('2d');if(!element||!ctx)return
    const qa=metricsEnabled()
    const started=qa?performance.now():0,{width,height}=sizeRef.current,original=latest.current,v=viewport.current,dpr=Math.min(devicePixelRatio||1,2)
    if(v.scale<.38){
      const protectedIds=new Set([original.root,original.selected,original.second,...(original.selection||[])])
      const selectedEdge=original.selectedEdge?original.edges.find(edge=>edge.id===original.selectedEdge):undefined
      if(selectedEdge){protectedIds.add(selectedEdge.from_id);protectedIds.add(selectedEdge.to_id)}
      const protectedKey=[...protectedIds].sort().join('|'),cached=semanticCache.current
      if(!cached||cached.nodes!==original.nodes||cached.edges!==original.edges||cached.positions!==points.current||cached.scale!==v.scale||cached.protected!==protectedKey){
        semanticCache.current={nodes:original.nodes,edges:original.edges,positions:points.current,scale:v.scale,protected:protectedKey,
          value:semanticGraph(original.nodes,original.edges,points.current,v.scale,protectedIds)}
      }
    }else semanticCache.current=undefined
    const semantic=semanticCache.current?.value
    const p=semantic?{...original,nodes:semantic.nodes,edges:semantic.edges}:original,positions=semantic?.positions||points.current
    if(element.width!==Math.round(width*dpr)||element.height!==Math.round(height*dpr)){element.width=Math.round(width*dpr);element.height=Math.round(height*dpr)}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height)
    const style=getComputedStyle(element),color=(name:string)=>style.getPropertyValue(name).trim()
    const text=color('--text'),muted=color('--muted'),accent=color('--accent'),border=color('--border'),panel=color('--panel'),raised=color('--panel-raised'),warning=color('--warning'),danger=color('--danger')
    const screen=(id:string)=>{const point=positions[id];return point?{x:point.x*v.scale+v.x,y:point.y*v.scale+v.y}:null}
    const measure=(value:string)=>{
      const key=ctx.font+'|'+value,cache=textWidths.current,known=cache.get(key)
      if(known!==undefined)return known
      const measured=ctx.measureText(value).width
      if(cache.size>=4096)cache.delete(cache.keys().next().value!)
      cache.set(key,measured);return measured
    }
    const fitText=(value:string,space:number)=>{if(measure(value)<=space)return value.length;let low=0,high=value.length;while(low<high){const mid=Math.ceil((low+high)/2);if(measure(value.slice(0,mid))<=space)low=mid;else high=mid-1}return low}
    const clipped=(value:string,space:number)=>{if(space<12)return '';if(measure(value)<=space)return value;const tail=value.length>10?value.slice(-7):'',suffix='…'+tail,available=space-measure(suffix);return available<=0?'…':value.slice(0,fitText(value.slice(0,value.length-tail.length),available))+suffix}
    const candidates=cardIndex(p.nodes,positions).query(v,{left:0,top:0,right:width,bottom:height},moving.current)
    const cards=candidates.flatMap(original=>{
      const node=resizeSizes.current[original.id]?{...original,attributes:{...original.attributes,_card_size:resizeSizes.current[original.id]}}:original
      const point=screen(node.id),box=nodeBox(node,v.scale),mx=box.width/2+24,my=box.height/2+24
      return point&&point.x>=-mx&&point.x<=width+mx&&point.y>=-my&&point.y<=height+my?[{node,point,box}]:[]
    })
    const clusterMembers=new Map(semantic?.clusters.map(cluster=>[cluster.id,cluster.members]))
    farClusters.current=cards.filter(card=>clusterMembers.has(card.node.id)).map(card=>({id:card.node.id,members:clusterMembers.get(card.node.id)!,...card.point,...card.box}))
    const visibleMedia=new Set(cards.flatMap(card=>{const media=visualMedia(card.node);return media?[media.id]:[]}))
    if(p.mode!=='tree'&&v.scale>.45){
      const clusters=new Map<string,typeof cards>()
      for(const card of cards){if(card.node.id===p.root||!card.node.attributes.parent_group_id)continue;const key=String(card.node.attributes.parent_group_id),rows=clusters.get(key)||[];rows.push(card);clusters.set(key,rows)}
      for(const rows of clusters.values())if(rows.length>=3){
        const minX=Math.min(...rows.map(row=>row.point.x-row.box.width/2))-16,maxX=Math.max(...rows.map(row=>row.point.x+row.box.width/2))+16
        const minY=Math.min(...rows.map(row=>row.point.y-row.box.height/2))-32,maxY=Math.max(...rows.map(row=>row.point.y+row.box.height/2))+16
        ctx.strokeStyle=border;ctx.fillStyle=raised;ctx.globalAlpha=.28;ctx.beginPath();ctx.roundRect(minX,minY,maxX-minX,maxY-minY,12);ctx.fill();ctx.stroke();ctx.globalAlpha=1
        ctx.font='11px Manrope, sans-serif';ctx.fillStyle=muted;ctx.fillText(`${entityLabel(rows[0].node)} · ${rows.length}`,minX+12,minY+18)
      }
    }
    const routeNodes=resizing.current?p.nodes.map(node=>resizeSizes.current[node.id]?{...node,attributes:{...node.attributes,_card_size:resizeSizes.current[node.id]}}:node):p.nodes
    const routingScale=v.scale<.38?v.scale:1
    let cachedRoutes=geometry.current
    if(!cachedRoutes||cachedRoutes.edges!==p.edges||cachedRoutes.nodes!==routeNodes||cachedRoutes.scale!==routingScale||cachedRoutes.mode!==(p.mode||'graph')){
      cachedRoutes=new EdgeRouteIndex(p.edges,routeNodes,positions,routingScale,p.mode);geometry.current=cachedRoutes
    }else if(cachedRoutes.positions!==positions)cachedRoutes.updatePositions(positions)
    const movingNodes=!!drag.current?.id&&drag.current.moved
    const worldRoutes=cachedRoutes.query(v,{left:-20,top:-20,right:width+20,bottom:height+20},movingNodes?moving.current:undefined)
    const projectRoute=(row:(typeof worldRoutes)[number])=>({edge:row.edge,points:row.points.map(point=>({x:point.x*v.scale+v.x,y:point.y*v.scale+v.y}))})
    const rgba=(value:string,alpha:number):[number,number,number,number]=>{
      const known=edgeColors.current.get(value)
      if(known)return [known[0],known[1],known[2],alpha]
      const probe=document.createElement('canvas');probe.width=probe.height=1;const context=probe.getContext('2d')!;context.fillStyle=value;context.fillRect(0,0,1,1);const bytes=context.getImageData(0,0,1,1).data
      const result:[number,number,number,number]=[bytes[0]/255,bytes[1]/255,bytes[2]/255,alpha];edgeColors.current.set(value,result);return result
    }
    const layer=gpu.current
    let gpuRendered=false
    if(layer?.available&&worldRoutes.length>=120){
      const key=[cachedRoutes.generation,p.root,p.selected,p.selectedEdge,accent,border,muted,danger,warning,movingNodes].join('|')
      if(uploaded.current?.index!==cachedRoutes||uploaded.current.key!==key||movingNodes||resizing.current){
        // The GPU clips the stationary mesh. Camera motion must not rebuild
        // it just because a different set of edges crosses the viewport.
        const lines:GpuLine[]=(movingNodes?worldRoutes:cachedRoutes.routes).map(({edge,points})=>{
          const selected=edge.id===p.selectedEdge,related=edge.from_id===p.selected||edge.to_id===p.selected,manual=edge.claim_kind==='analyst_assertion'
          const incoming=edge.to_id===p.root&&edge.from_id!==p.root,outgoing=edge.from_id===p.root&&edge.to_id!==p.root
          const flow=edge.aggregate&&(incoming||outgoing)?incoming?'#68aab4':'#cfaa73':null
          const custom=manual&&/^#[0-9a-f]{6}$/i.test(String(edge.attributes?.color))?String(edge.attributes?.color):null
          const color=selected?accent:custom|| (edge.verification_status==='contradicted'?danger:edge.verification_status==='inferred'?warning:flow||(related?muted:border))
          return {points,color:rgba(color,p.selected&&!related&&!selected ? .25 : selected?1:.65),width:selected?2.4:manual?Number(edge.attributes?.width)||1.6:edge.aggregate?1.6:1,
            dashed:manual?edge.attributes?.stroke!=='solid':['inferred','unverified'].includes(edge.verification_status),dotted:manual&&edge.attributes?.stroke==='dotted',arrowStart:edge.direction==='bidirectional',arrowEnd:edge.direction!=='undirected'}
        })
        layer.setLines(lines,{x:-v.x/v.scale,y:-v.y/v.scale});uploaded.current={index:cachedRoutes,key}
      }
      gpuRendered=layer.render(v,width,height,dpr)
    }
    if(gpuCanvas.current)gpuCanvas.current.style.visibility=gpuRendered?'visible':'hidden'
    if(qa)element.dataset.renderer=gpuRendered?'webgl2-edges-canvas-cards':'canvas2d'
    const showRelatedLabels=v.scale>.45&&p.nodes.length<=45
    const needsLabel=(edge:GraphRelation)=>edge.id===p.selectedEdge||showRelatedLabels&&(!!edge.aggregate||edge.from_id===p.selected||edge.to_id===p.selected)
    const routes=(gpuRendered?worldRoutes.filter(row=>needsLabel(row.edge)):worldRoutes).map(projectRoute)
    const occupied=p.selectedEdge||showRelatedLabels?cards.map(({point,box})=>({x:point.x-box.width/2-4,y:point.y-box.height/2-4,w:box.width+8,h:box.height+8})):[]
    for(const {edge,points}of routes){
      const selected=edge.id===p.selectedEdge,related=edge.from_id===p.selected||edge.to_id===p.selected
      const incoming=edge.to_id===p.root&&edge.from_id!==p.root,outgoing=edge.from_id===p.root&&edge.to_id!==p.root
      const flowColor=edge.aggregate&&(incoming||outgoing)?incoming?'#68aab4':'#cfaa73':null
      const manual=edge.claim_kind==='analyst_assertion',customColor=manual&&typeof edge.attributes?.color==='string'&&/^#[0-9a-f]{6}$/i.test(edge.attributes.color)?edge.attributes.color:null
      ctx.strokeStyle=selected?accent:customColor|| (edge.verification_status==='contradicted'?danger:edge.verification_status==='inferred'?warning:flowColor|| (related?muted:border))
      ctx.lineWidth=selected?2.4:manual?Number(edge.attributes?.width)||1.6:edge.aggregate?1.6:1;ctx.globalAlpha=p.selected&&!related&&!selected ? .25 : selected ? 1 : .65
      ctx.setLineDash(manual?edge.attributes?.stroke==='solid'?[]:edge.attributes?.stroke==='dotted'?[1,4]:[6,5]:['inferred','unverified'].includes(edge.verification_status)?[5,5]:[])
      if(!gpuRendered){ctx.beginPath();ctx.moveTo(points[0].x,points[0].y);points.slice(1).forEach(point=>ctx.lineTo(point.x,point.y));ctx.stroke();ctx.setLineDash([])
      if(edge.direction!=='undirected'){const end=points.at(-1)!,prior=points.at(-2)!,angle=Math.atan2(end.y-prior.y,end.x-prior.x)
        ctx.fillStyle=selected?accent:customColor||flowColor||muted;ctx.beginPath();ctx.moveTo(end.x,end.y);ctx.lineTo(end.x-Math.cos(angle-.45)*8,end.y-Math.sin(angle-.45)*8);ctx.lineTo(end.x-Math.cos(angle+.45)*8,end.y-Math.sin(angle+.45)*8);ctx.closePath();ctx.fill()}
      if(edge.direction==='bidirectional'){const end=points[0],prior=points[1],angle=Math.atan2(end.y-prior.y,end.x-prior.x);ctx.fillStyle=customColor||muted;ctx.beginPath();ctx.moveTo(end.x,end.y);ctx.lineTo(end.x-Math.cos(angle-.45)*8,end.y-Math.sin(angle-.45)*8);ctx.lineTo(end.x-Math.cos(angle+.45)*8,end.y-Math.sin(angle+.45)*8);ctx.closePath();ctx.fill()}
      }
      ctx.globalAlpha=1
      if(needsLabel(edge)){
        const asset=edge.aggregate?.asset_label||edge.aggregate?.asset||'',label=edge.aggregate?`${edge.aggregate.count} · ${formatGraphAmount(edge.aggregate.amount)} ${asset.length>12?'актив':asset}`:relationLabels[edge.relation_type]||edge.relation_type
        ctx.font='11px Manrope, sans-serif';const caption=clipped(label,190),w=ctx.measureText(caption).width+12
        for(const fraction of [.5,.32,.68]){
          const progress=(points.length-1)*fraction,segment=Math.floor(progress),offset=progress-segment
          const a=points[segment],b=points[segment+1]
          const point={x:a.x+(b.x-a.x)*offset,y:a.y+(b.y-a.y)*offset}
          const box={x:point.x-w/2,y:point.y-10,w,h:21}
          if(occupied.some(other=>box.x<other.x+other.w&&box.x+box.w>other.x&&box.y<other.y+other.h&&box.y+box.h>other.y))continue
          occupied.push(box);ctx.fillStyle=panel;ctx.fillRect(box.x,box.y,box.w,box.h);ctx.fillStyle=selected?accent:flowColor||text;ctx.fillText(caption,box.x+6,box.y+14);break
        }
      }
    }
    const qaNodes:{id:string;x:number;y:number;width:number;height:number;label:string}[]=[]
    const selectedIds=new Set([p.selected,p.second,...(p.selection||[])])
    let drawnLabels=0,drawnImages=0
    for(const {node,point,box}of [...cards].sort((a,b)=>Number(a.node.type!=='entity_group')-Number(b.node.type!=='entity_group'))){
      const selected=selectedIds.has(node.id),root=node.id===p.root,x=point.x-box.width/2,y=point.y-box.height/2
      const group=node.type==='entity_group'&&!node.attributes._collapsed
      ctx.fillStyle=group?'transparent':selected?raised:panel;ctx.strokeStyle=selected||root?accent:node.verification_status==='inferred'?warning:border;ctx.lineWidth=selected||root?1.8:1
      const variant=cardVariant(node),corner=variant==='social'?16:variant==='note'?3:variant==='group'?12:8
      if(variant==='hypothesis')ctx.setLineDash([4,3])
      if(selected){ctx.shadowColor=accent;ctx.shadowBlur=18}
      ctx.beginPath();ctx.roundRect(x,y,box.width,box.height,Math.min(corner,box.height/4));ctx.fill();ctx.stroke();ctx.shadowBlur=0
      ctx.setLineDash([])
      if(group&&v.scale>=.38){
        ctx.font=`600 ${Math.max(12,14*v.scale)}px Manrope, sans-serif`;ctx.fillStyle=selected?accent:text
        ctx.fillText(clipped(`${node.label} · ${node.attributes.member_count??'группа'}`,box.width-30),x+14,y+24)
        if(p.onCardResize&&selected&&v.scale>.55){ctx.strokeStyle=accent;ctx.beginPath();ctx.moveTo(x+box.width-16,y+box.height-5);ctx.lineTo(x+box.width-5,y+box.height-16);ctx.stroke()}
        if(p.onConnect&&v.scale>.55&&(selected||hovered.current===node.id)){for(const sign of [-1,1]){ctx.fillStyle=panel;ctx.strokeStyle=accent;ctx.beginPath();ctx.arc(point.x+sign*box.width/2,point.y,4,0,Math.PI*2);ctx.fill();ctx.stroke()}}
        drawnLabels++;if(qa&&qaNodes.length<30)qaNodes.push({id:node.id,x:point.x,y:point.y,width:box.width,height:box.height,label:shortLabel(node)})
        continue
      }
      if(v.scale<.38){
        // Far zoom represents an object with a readable symbol and label,
        // rather than shrinking a detailed card into an empty rectangle.
        const title=shortLabel(node),font=root||selected?12:11
        ctx.fillStyle=selected||root?accent:muted;ctx.font=`700 16px Manrope, sans-serif`
        ctx.fillText(cardVariants[variant].symbol,x+7,point.y+5)
        ctx.font=`600 ${font}px Manrope, sans-serif`;ctx.fillStyle=text
        ctx.fillText(clipped(title,box.width-35),x+29,point.y+4)
        if(variant==='group'){ctx.font='10px Manrope, sans-serif';ctx.fillStyle=muted;ctx.fillText(`${node.attributes.member_count??'—'} · раскрыть`,x+29,point.y+17)}
        drawnLabels++
        if(qa&&qaNodes.length<30)qaNodes.push({id:node.id,x:point.x,y:point.y,width:box.width,height:box.height,label:shortLabel(node)})
        continue
      }
      if(v.scale>.55){
        if(['wallet','transaction','contract','social','organization'].includes(variant)){ctx.save();ctx.beginPath();ctx.roundRect(x+1,y+1,box.width-2,box.height-2,Math.min(corner,box.height/4));ctx.clip();ctx.fillStyle=raised;ctx.fillRect(x+1,y+1,box.width-2,Math.min(27*v.scale,box.height/3));ctx.restore()}
        if(variant==='note'){ctx.strokeStyle=border;ctx.lineWidth=.7;for(let line=y+box.height*.6;line<y+box.height-10;line+=15*v.scale){ctx.beginPath();ctx.moveTo(x+10,line);ctx.lineTo(x+box.width-12,line);ctx.stroke()}}
        if(variant==='document'){ctx.strokeStyle=muted;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x+box.width-23,y+1);ctx.lineTo(x+box.width-23,y+18);ctx.lineTo(x+box.width-2,y+18);ctx.stroke()}
        if(variant==='group'){ctx.strokeStyle=border;ctx.lineWidth=1;ctx.beginPath();ctx.roundRect(x+6,y+box.height+3,box.width-12,4,2);ctx.stroke()}
      }
      ctx.fillStyle=node.verification_status==='contradicted'?danger:node.verification_status==='inferred'?warning:node.verification_status==='verified'?accent:muted
      ctx.beginPath();ctx.arc(x+box.width-11,y+11,3,0,Math.PI*2);ctx.fill()
      if(typeof node.attributes.analyst_color==='string'&&/^#[0-9a-f]{6}$/i.test(node.attributes.analyst_color)){ctx.fillStyle=node.attributes.analyst_color;ctx.fillRect(x+1,y+8,3,box.height-16)}
      {
        const font=Math.max(9,Math.min(16,13*v.scale)),padding=Math.max(6,12*v.scale),media=visualMedia(node),compact=p.cardMode==='compact'||p.cardMode==='auto'&&v.scale<.7||v.scale<.45
        let left=x+padding,space=box.width-padding*2
        if(media&&box.width>105){
          const picture=thumbnail(node,media,visibleMedia)
          if(picture?.complete&&picture.naturalWidth&&box.width>105){
            const mediaCard=variant==='media',w=mediaCard?space:Math.min(42*v.scale,box.height-padding*2),h=mediaCard?Math.max(24,box.height-padding*2-font*3.5):w,top=mediaCard?y+padding:y+(box.height-h)/2
            const cover=mediaCard&&node.attributes.image_fit==='cover'
            const ratio=cover?Math.max(w/picture.naturalWidth,h/picture.naturalHeight):Math.min(w/picture.naturalWidth,h/picture.naturalHeight)
            ctx.save();ctx.beginPath();ctx.roundRect(left,top,w,h,4);ctx.clip();ctx.fillStyle=raised;ctx.fillRect(left,top,w,h)
            ctx.drawImage(picture,left+(w-picture.naturalWidth*ratio)/2,top+(h-picture.naturalHeight*ratio)/2,picture.naturalWidth*ratio,picture.naturalHeight*ratio);ctx.restore();if(!mediaCard){left+=w+8;space-=w+8}drawnImages++
          }else if(variant==='media'){
            const h=Math.max(24,box.height-padding*2-font*3.5)
            ctx.fillStyle=raised;ctx.beginPath();ctx.roundRect(left,y+padding,space,h,5);ctx.fill()
            ctx.fillStyle=muted;ctx.font='11px Manrope, sans-serif'
            ctx.fillText(thumbnails.current.has(media.id)?'Изображение недоступно':'Предпросмотр…',left+8,y+padding+h/2)
          }
        }
        const mediaCard=variant==='media',badge=cardBadge(node),headingY=mediaCard?y+box.height-padding-font*2.1:y+padding+font*.75
        if(!mediaCard&&!compact){ctx.fillStyle=variant==='hypothesis'?warning:muted;ctx.font=`600 ${Math.max(8,font-2)}px Manrope, sans-serif`;ctx.fillText(clipped(`${cardVariants[variant].symbol}  ${badge}`,space-8),left,headingY)}
        ctx.font=`600 ${font}px Manrope, sans-serif`;ctx.fillStyle=text
        const title=cardTitle(node),split=fitText(title,space)
        const twoLines=split<title.length&&!compact&&!mediaCard&&variant!=='wallet'&&box.height>=90*v.scale,titleY=mediaCard?headingY:compact?y+box.height*.48:headingY+font*1.65
        ctx.fillText(twoLines?title.slice(0,split):clipped(title,space),left,titleY)
        if(twoLines)ctx.fillText(clipped(title.slice(split),space),left,titleY+font+3)
        drawnLabels++
        const rows=cardRows(node),technical=['wallet','transaction','ip','contract'].includes(variant)
        ctx.font=`${Math.max(8,font-1)}px ${technical?'Consolas, monospace':'Manrope, sans-serif'}`;ctx.fillStyle=muted
        const start=titleY+font*(twoLines?2.8:1.6),maxRows=compact?1:mediaCard?1:p.cardMode==='expanded'?4:2
        for(let row=0;row<Math.min(maxRows,rows.length);row++){const at=start+row*(font+5);if(at<y+box.height-padding/2)ctx.fillText(clipped(rows[row],space),left,at)}
      }
      if(positions[node.id]?.pinned){ctx.fillStyle=accent;ctx.fillRect(x+box.width-8,y+4,4,4)}
      if(p.onConnect&&v.scale>.55&&(selected||hovered.current===node.id||linking.current===node.id)){for(const sign of [-1,1]){ctx.fillStyle=panel;ctx.strokeStyle=accent;ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(point.x+sign*box.width/2,point.y,4,0,Math.PI*2);ctx.fill();ctx.stroke()}}
      if(p.onCardResize&&selected&&['media','group'].includes(variant)&&v.scale>.55){ctx.strokeStyle=accent;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x+box.width-13,y+box.height-4);ctx.lineTo(x+box.width-4,y+box.height-13);ctx.moveTo(x+box.width-8,y+box.height-4);ctx.lineTo(x+box.width-4,y+box.height-8);ctx.stroke()}
      if(qa&&qaNodes.length<30)qaNodes.push({id:node.id,x:point.x,y:point.y,width:box.width,height:box.height,label:shortLabel(node)})
    }
    // Selection handles remain above overlapping unselected cards.
    if(p.onCardResize&&v.scale>.55)for(const {node,point,box}of cards){
      if(!selectedIds.has(node.id)||!['media','group'].includes(cardVariant(node)))continue
      const x=point.x+box.width/2,y=point.y+box.height/2
      ctx.fillStyle=panel;ctx.strokeStyle=accent;ctx.lineWidth=1.5;ctx.beginPath();ctx.roundRect(x-13,y-13,18,18,4);ctx.fill();ctx.stroke()
      ctx.beginPath();ctx.moveTo(x-8,y);ctx.lineTo(x,y-8);ctx.stroke()
    }
    if(linking.current&&linkPoint.current){const at=screen(linking.current);if(at){ctx.strokeStyle=accent;ctx.lineWidth=2;ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(at.x,at.y);ctx.lineTo(linkPoint.current.x,linkPoint.current.y);ctx.stroke();ctx.setLineDash([])}}
    if(dropPoint.current){
      const point=dropPoint.current
      ctx.fillStyle=raised;ctx.strokeStyle=accent;ctx.lineWidth=2
      ctx.setLineDash([6,4]);ctx.beginPath();ctx.roundRect(point.x-62,point.y-38,124,76,9);ctx.fill();ctx.stroke();ctx.setLineDash([])
      ctx.font='600 12px Manrope, sans-serif';ctx.fillStyle=text;ctx.fillText('Добавить фото',point.x-45,point.y+4)
    }
    if(marquee.current){const r=marquee.current;ctx.strokeStyle=accent;ctx.setLineDash([4,3]);ctx.strokeRect(r.x,r.y,r.endX-r.x,r.endY-r.y);ctx.setLineDash([])}
    drawMinimap(ctx,p.nodes,positions,v,width,height,{panel,border,muted,accent})
    if(!qa)return
    element.dataset.drawnLabels=String(drawnLabels);element.dataset.drawnImages=String(drawnImages)
    element.dataset.qaNodes=JSON.stringify(qaNodes)
    element.dataset.qaEdges=JSON.stringify(worldRoutes.slice(0,20).map(projectRoute).map(({edge,points})=>({id:edge.id,...points[Math.floor(points.length*.6)]})))
    element.dataset.zoom=String(v.scale);element.dataset.panX=String(v.x);element.dataset.panY=String(v.y)
    element.dataset.semanticZoom=v.scale<.38?'far':v.scale<.75?'medium':'close'
    element.dataset.qaFarClusters=JSON.stringify(farClusters.current.slice(0,30).map(cluster=>({...cluster,count:cluster.members.length,members:cluster.members.slice(0,64)})))
    element.dataset.modelNodes=String(original.nodes.length)
    element.dataset.drawnNodes=String(p.nodes.length);element.dataset.drawnEdges=String(worldRoutes.length);element.dataset.paintMs=String(performance.now()-started)
    element.dataset.modelEdges=String(p.edges.length);element.dataset.onScreenNodes=String(cards.length)
    const now=performance.now();paints.current.push(now-started);if(lastPaint.current&&now-lastPaint.current<100)intervals.current.push(now-lastPaint.current)
    if(lastInput.current){latencies.current.push(now-lastInput.current);lastInput.current=0}lastPaint.current=now
    for(const array of [paints.current,intervals.current,latencies.current])if(array.length>240)array.splice(0,array.length-240)
    if(paints.current.length%5===0||!drag.current)element.dataset.frameMetrics=JSON.stringify({paint_ms:paints.current,active_intervals_ms:intervals.current,event_to_paint_ms:latencies.current})
    recordCamera('frame')
  }
  function requestDraw(){if(visible.current&&frame.current===undefined)frame.current=requestAnimationFrame(draw)}
  useEffect(()=>{
    const element=gpuCanvas.current
    if(!element||props.edges.length<120)return
    const layer=new GraphGpuLayer(element,()=>{uploaded.current=undefined;requestDraw()});gpu.current=layer;requestDraw()
    return()=>{layer.dispose();gpu.current=undefined;uploaded.current=undefined}
  },[props.edges.length>=120])
  useEffect(()=>{
    camera.current=new GraphCamera(props.viewport);viewport.current=camera.current.value
    points.current={...props.positions};pendingPoints.current={};drag.current=undefined;lastMediaClick.current=undefined;moving.current={};cameraFrames.current=[];recordCamera('scope');requestDraw()
  },[props.scopeKey??props.root])
  useEffect(()=>{
    const incoming={...props.positions}
    for(const [id,point]of Object.entries(pendingPoints.current))if(incoming[id]&&Math.abs(incoming[id].x-point.x)<.01&&Math.abs(incoming[id].y-point.y)<.01)delete pendingPoints.current[id]
    Object.assign(incoming,pendingPoints.current)
    if(drag.current?.id)for(const id of Object.keys(moving.current))if(points.current[id])incoming[id]=points.current[id]
    points.current=incoming;requestDraw()
  },[props.positions])
  useEffect(()=>{camera.current.receive(props.viewport);viewport.current=camera.current.value;recordCamera('ack');requestDraw()},[props.viewport])
  useEffect(()=>{if(!resizing.current)resizeSizes.current={};requestDraw()},[presented,props.edges,props.selected,props.second,props.selection,props.selectedEdge,props.theme])
  useEffect(()=> {
    const element=canvas.current;if(!element)return
    const observer=new ResizeObserver(entries=>{
      const rect=entries[0].contentRect
      visible.current=rect.width>0&&rect.height>0
      if(visible.current){
        sizeRef.current={width:rect.width,height:rect.height}
        latest.current.onResize(rect.width,rect.height);requestDraw()
      }
    })
    observer.observe(element)
    const wheel=(event:WheelEvent)=>{event.preventDefault();camera.current.active=true;lastInput.current=performance.now();const rect=element.getBoundingClientRect();moveViewport(zoomAt(viewport.current,event.clientX-rect.left,event.clientY-rect.top,Math.exp(-event.deltaY*.0015)));clearTimeout(wheelTimer.current);wheelTimer.current=setTimeout(()=>{camera.current.active=false;commitViewport()},140)}
    element.addEventListener('wheel',wheel,{passive:false})
    return()=>{observer.disconnect();element.removeEventListener('wheel',wheel);if(frame.current!==undefined)cancelAnimationFrame(frame.current);clearTimeout(wheelTimer.current)}
  },[])
  useEffect(()=>{
    let active=true
    void document.fonts?.ready.then(()=>{if(active){textWidths.current.clear();requestDraw()}})
    return()=>{active=false}
  },[])
  useEffect(()=>{
    if(!props.onNativeDrop)return
    const receive:NonNullable<Window['grangerGraphFileDrop']>=(phase,x,y,nativeWidth,nativeHeight,token)=>{
      const element=canvas.current
      const px=x*innerWidth/Math.max(1,nativeWidth),py=y*innerHeight/Math.max(1,nativeHeight)
      if(!element||phase==='leave'||document.elementFromPoint(px,py)!==element){
        dropPoint.current=undefined;requestDraw();return
      }
      const rect=element.getBoundingClientRect(),point={x:px-rect.left,y:py-rect.top},view=viewport.current
      dropPoint.current=phase==='hover'?point:undefined;requestDraw()
      if(phase==='drop'&&token)latest.current.onNativeDrop?.(token,{x:(point.x-view.x)/view.scale,y:(point.y-view.y)/view.scale})
    }
    window.grangerGraphFileDrop=receive
    return()=>{if(window.grangerGraphFileDrop===receive)delete window.grangerGraphFileDrop}
  },[!!props.onNativeDrop])
  useImperativeHandle(forwarded,()=>({
    fit,
    zoom(factor){commitViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,factor))},
    center(id){const p=points.current[id];if(p)commitViewport({x:sizeRef.current.width/2-p.x,y:sizeRef.current.height/2-p.y,scale:1})},
    insertPoint(size){
      const v=viewport.current,{width,height}=sizeRef.current
      const nodes=latest.current.nodes,positions=points.current
      const halfWidth=size.width*v.scale/2,halfHeight=size.height*v.scale/2
      const visible=cardIndex(nodes,positions).query(v,{left:0,top:0,right:width,bottom:height})
        .flatMap(node=>{
          const point=positions[node.id];if(!point)return []
          return [{x:point.x*v.scale+v.x,y:point.y*v.scale+v.y,box:nodeBox(node,v.scale)}]
        })
      const insetX=Math.min(width/2,halfWidth+18),insetY=Math.min(height/2,halfHeight+18)
      let point={x:width/2,y:height/2},score=Infinity
      for(const row of [.5,.25,.75,0,1])for(const col of [.5,.25,.75,0,1]){
        const x=insetX+col*(width-2*insetX),y=insetY+row*(height-2*insetY)
        const overlap=visible.reduce((sum,item)=>{
          const dx=Math.min(x+halfWidth,item.x+item.box.width/2+8)-Math.max(x-halfWidth,item.x-item.box.width/2-8)
          const dy=Math.min(y+halfHeight,item.y+item.box.height/2+8)-Math.max(y-halfHeight,item.y-item.box.height/2-8)
          return sum+Math.max(0,dx)*Math.max(0,dy)
        },0)
        if(overlap<score){score=overlap;point={x,y}}
      }
      return {x:(point.x-v.x)/v.scale,y:(point.y-v.y)/v.scale}
    },
  }),[])
  const local=(event:{clientX:number;clientY:number})=>{const rect=canvas.current!.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top}}
  return <div className="graph-render-stack"><canvas ref={gpuCanvas} className="graph-gpu-edges" aria-hidden="true"/><canvas ref={canvas} className="investigation-graph-canvas" role="application" aria-label="Интерактивный граф расследования" tabIndex={0}
    onDragOver={event=>{
      if(!latest.current.onDropImage||!event.dataTransfer.types.includes('Files'))return
      event.preventDefault();event.dataTransfer.dropEffect='copy';dropPoint.current=local(event);requestDraw()
    }}
    onDragLeave={()=>{if(dropPoint.current){dropPoint.current=undefined;requestDraw()}}}
    onDrop={event=>{
      const file=event.dataTransfer.files[0]
      if(!file||!latest.current.onDropImage)return
      event.preventDefault();dropPoint.current=undefined;requestDraw()
      const p=local(event),v=viewport.current
      latest.current.onDropImage(file,{x:(p.x-v.x)/v.scale,y:(p.y-v.y)/v.scale})
    }}
    onDoubleClick={event=>{
      const point=local(event);if(zoomCluster(point))return
      const v=viewport.current,node=nodeAt(point)
      if(node){if(!visualMedia(node))latest.current.onExpand?.(node.id)}
      else latest.current.onCreate?.({x:(point.x-v.x)/v.scale,y:(point.y-v.y)/v.scale})
    }}
    onContextMenu={event=>{event.preventDefault();const p=local(event);if(zoomCluster(p))return;const v=viewport.current,node=nodeAt(p);latest.current.onContext?.(node?.id||'',{x:(p.x-v.x)/v.scale,y:(p.y-v.y)/v.scale})}}
    onPointerDown={event=>{
      if(event.button!==0)return
      const point=local(event),v=viewport.current,p=latest.current
      canvas.current?.focus();event.currentTarget.setPointerCapture?.(event.pointerId)
      const m=mini.current
      if(m&&point.x>=m.x&&point.x<=m.x+m.w&&point.y>=m.y&&point.y<=m.y+m.h){commitViewport({...v,x:sizeRef.current.width/2-((point.x-m.x)/m.scale+m.minX)*v.scale,y:sizeRef.current.height/2-((point.y-m.y)/m.scale+m.minY)*v.scale});return}
      if(zoomCluster(point))return
      if(p.onCardResize&&v.scale>.55){
        const selected=new Set([p.selected,...(p.selection||[])])
        for(const node of p.nodes){
          if(!selected.has(node.id)||!['media','group'].includes(cardVariant(node)))continue
          const at=points.current[node.id];if(!at)continue
          const box=nodeBox(node,v.scale),x=at.x*v.scale+v.x+box.width/2,y=at.y*v.scale+v.y+box.height/2
          if(Math.abs(point.x-x)<=16&&Math.abs(point.y-y)<=16){resizing.current={id:node.id,x:point.x,y:point.y,size:{width:box.width/v.scale,height:box.height/v.scale}};return}
        }
      }
      if(p.onConnect&&v.scale>.55){const port=p.nodes.find(n=>{if(n.id!==p.selected&&n.id!==hovered.current&&!p.selection?.includes(n.id))return false;const pos=points.current[n.id];if(!pos)return false;const box=nodeBox(n,v.scale);return Math.abs(point.y-(pos.y*v.scale+v.y))<10&&Math.abs(Math.abs(point.x-(pos.x*v.scale+v.x))-box.width/2)<10});if(port){linking.current=port.id;requestDraw();return}}
      const node=nodeAt(point)
      if(node&&p.onCardResize&&(node.id===p.selected||p.selection?.includes(node.id))&&['media','group'].includes(cardVariant(node))){const box=nodeBox(node,v.scale),at=points.current[node.id];if(point.x>at.x*v.scale+v.x+box.width/2-18&&point.y>at.y*v.scale+v.y+box.height/2-18){resizing.current={id:node.id,x:point.x,y:point.y,size:{width:box.width/v.scale,height:box.height/v.scale}};return}}
      if(event.shiftKey&&!node&&p.onSelection){marquee.current={x:point.x,y:point.y,endX:point.x,endY:point.y};return}
      drag.current={id:node?.id,startX:point.x,startY:point.y,point:node?{...points.current[node.id]}:undefined,view:{...v},moved:false}
      camera.current.active=true
      moving.current={}
      if(node){
        const ids=new Set(p.selection?.includes(node.id)?p.selection:[node.id])
        // A group moves its descendants without rewriting semantic relations.
        let changed=true;while(changed){changed=false;for(const n of p.nodes)if(!ids.has(n.id)&&ids.has(String(n.attributes.parent_group_id))){ids.add(n.id);changed=true}}
        for(const id of ids)if(points.current[id])moving.current[id]={...points.current[id]}
        if(!p.selection?.includes(node.id)||event.ctrlKey||event.metaKey)p.onSelect(node.id,event.ctrlKey||event.metaKey)
      }
    }}
    onPointerMove={event=>{
      const point=local(event)
      if(linking.current){linkPoint.current=point;requestDraw();return}
      if(resizing.current){const r=resizing.current;resizeSizes.current[r.id]={width:Math.max(160,Math.min(latest.current.nodes.find(n=>n.id===r.id)?.type==='entity_group'?2400:720,r.size.width+(point.x-r.x)/viewport.current.scale)),height:Math.max(120,Math.min(latest.current.nodes.find(n=>n.id===r.id)?.type==='entity_group'?1800:640,r.size.height+(point.y-r.y)/viewport.current.scale))};lastInput.current=performance.now();requestDraw();return}
      if(marquee.current){marquee.current.endX=point.x;marquee.current.endY=point.y;requestDraw();return}
      const current=drag.current;if(!current){const node=nodeAt(point),id=node?.id||'';if(hovered.current!==id){hovered.current=id;requestDraw()}event.currentTarget.style.cursor=node?'grab':'default';return}
      const dx=point.x-current.startX,dy=point.y-current.startY;if(Math.hypot(dx,dy)<3&&!current.moved)return
      lastInput.current=performance.now()
      current.moved=true
      if(current.id&&current.point){
        for(const [id,p]of Object.entries(moving.current))points.current[id]={x:p.x+dx/current.view.scale,y:p.y+dy/current.view.scale,pinned:true}
        if(viewport.current.scale<.38)semanticCache.current=undefined
      }
      else moveViewport({...current.view,x:current.view.x+dx,y:current.view.y+dy})
      requestDraw()
    }}
    onPointerUp={event=>{
      const point=local(event),p=latest.current,v=viewport.current
      if(resizing.current){const r=resizing.current;resizing.current=undefined;if(resizeSizes.current[r.id])p.onCardResize?.(r.id,resizeSizes.current[r.id]);requestDraw()}
      if(linking.current){const target=hitNode(p.nodes,points.current,v,point.x,point.y),from=linking.current;linking.current=undefined;linkPoint.current=undefined;requestDraw();if(target&&target.id!==from)p.onConnect?.(from,target.id)}
      if(marquee.current){const r=marquee.current;marquee.current=undefined;p.onSelection?.(p.nodes.filter(n=>{const pos=points.current[n.id];if(!pos)return false;const x=pos.x*v.scale+v.x,y=pos.y*v.scale+v.y;return x>=Math.min(r.x,r.endX)&&x<=Math.max(r.x,r.endX)&&y>=Math.min(r.y,r.endY)&&y<=Math.max(r.y,r.endY)}).map(n=>n.id));requestDraw()}
      const current=drag.current;drag.current=undefined;camera.current.active=false;event.currentTarget.releasePointerCapture?.(event.pointerId)
      if(current?.moved){if(current.id){
        const updates=Object.fromEntries(Object.keys(moving.current).map(id=>[id,points.current[id]]))
        Object.assign(pendingPoints.current,updates);spatial.current=undefined;geometry.current?.updatePositions(points.current);semanticCache.current=undefined;miniGeometry.current=undefined
        p.onCommitPositions(updates)
      }else commitViewport()}
      else if(current&&!current.id){const edge=hitRelation(p.edges,points.current,v,point.x,point.y,p.nodes,p.mode);if(edge)p.onEdge(edge.id)}
      if(current?.id&&!current.moved){
        const node=nodeAt(point),previous=lastMediaClick.current,at=performance.now()
        if(node?.id===current.id&&visualMedia(node)){
          if(previous?.id===node.id&&at-previous.at<420&&Math.hypot(previous.x-point.x,previous.y-point.y)<8){
            lastMediaClick.current=undefined;p.onOpenMedia?.(node)
          }else lastMediaClick.current={id:node.id,...point,at}
        }else lastMediaClick.current=undefined
      }else lastMediaClick.current=undefined
      moving.current={}
    }}
    onPointerLeave={()=>{if(!drag.current){hovered.current='';requestDraw()}}}
    onPointerCancel={()=>{
      const current=drag.current;drag.current=undefined;camera.current.active=false
      if(current?.moved){
        if(current.id){Object.assign(points.current,moving.current);spatial.current=undefined;geometry.current?.updatePositions(points.current);semanticCache.current=undefined;miniGeometry.current=undefined}
        else commitViewport()
      }
      moving.current={};marquee.current=undefined;linking.current=undefined;resizing.current=undefined;resizeSizes.current={};requestDraw()
    }}
    onKeyDown={event=>{const key=event.key;if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(key)){event.preventDefault();if(key==='Home')fit();else if(key==='+'||key==='='||key==='-')commitViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,key==='-'?.8:1.25));else commitViewport({...viewport.current,x:viewport.current.x+(key==='ArrowLeft'?40:key==='ArrowRight'?-40:0),y:viewport.current.y+(key==='ArrowUp'?40:key==='ArrowDown'?-40:0)})}}}/></div>
})
