import { forwardRef,useEffect,useImperativeHandle,useRef,useState } from 'react'
import type { GraphEntity,GraphPoint,GraphRelation,GraphViewport } from '../types'
import { entityType,fitViewport,hitNode,hitRelation,relationLabels,shortLabel,zoomAt } from '../graph-model'

export interface GraphCanvasHandle { fit():void; zoom(factor:number):void; center(id:string):void }
interface Props {
  nodes:GraphEntity[];edges:GraphRelation[];positions:Record<string,GraphPoint>;viewport:GraphViewport
  selected:string;second:string;selectedEdge:string;root:string;theme?:unknown
  onSelect(id:string,second:boolean):void;onEdge(id:string):void
  onCommitPositions(value:Record<string,GraphPoint>):void;onViewport(value:GraphViewport):void
  onResize(width:number,height:number):void
}
export const InvestigationCanvas=forwardRef<GraphCanvasHandle,Props>(function InvestigationCanvas(props,forwarded) {
  const canvas=useRef<HTMLCanvasElement>(null),latest=useRef(props);latest.current=props
  const points=useRef(props.positions),viewport=useRef(props.viewport)
  const [size,setSize]=useState({width:800,height:440})
  const sizeRef=useRef(size);sizeRef.current=size
  const frame=useRef<number|undefined>(undefined),wheelTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined)
  const drag=useRef<{id?:string;startX:number;startY:number;point?:GraphPoint;view:GraphViewport;moved:boolean}|undefined>(undefined)
  function draw() {
    frame.current=undefined
    const element=canvas.current,ctx=element?.getContext('2d')
    if(!element||!ctx)return
    const started=performance.now(),{width,height}=sizeRef.current,p=latest.current,v=viewport.current,positions=points.current
    const dpr=Math.min(devicePixelRatio||1,2)
    if(element.width!==Math.round(width*dpr)||element.height!==Math.round(height*dpr)){element.width=Math.round(width*dpr);element.height=Math.round(height*dpr)}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height)
    const style=getComputedStyle(element),color=(name:string)=>style.getPropertyValue(name).trim()
    const text=color('--text'),muted=color('--muted'),accent=color('--accent'),border=color('--border'),panel=color('--panel'),warning=color('--warning'),danger=color('--danger')
    const screen=(id:string)=>{const point=positions[id];return point?{x:point.x*v.scale+v.x,y:point.y*v.scale+v.y}:null}
    const onScreen=(point:{x:number;y:number},margin=60)=>point.x>=-margin&&point.x<=width+margin&&point.y>=-margin&&point.y<=height+margin
    const groups=['verified','source_reported','inferred','unverified','contradicted']
    const visibleEdges:GraphRelation[]=[]
    for(const edge of p.edges){const a=screen(edge.from_id),b=screen(edge.to_id);if(!a||!b)continue;if(Math.max(a.x,b.x)<-30||Math.min(a.x,b.x)>width+30||Math.max(a.y,b.y)<-30||Math.min(a.y,b.y)>height+30)continue;visibleEdges.push(edge)}
    for(const status of groups){ctx.beginPath();ctx.strokeStyle=status==='contradicted'?danger:status==='inferred'?warning:border;ctx.lineWidth=1;ctx.globalAlpha=status==='verified'?.8:.55;ctx.setLineDash(['inferred','unverified'].includes(status)?[4,4]:[])
      for(const edge of visibleEdges){if(edge.verification_status!==status||edge.id===p.selectedEdge)continue;const a=screen(edge.from_id)!,b=screen(edge.to_id)!;ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y)}ctx.stroke()}
    ctx.globalAlpha=1;ctx.setLineDash([])
    for(const edge of visibleEdges){const a=screen(edge.from_id)!,b=screen(edge.to_id)!,angle=Math.atan2(b.y-a.y,b.x-a.x),distance=Math.hypot(b.x-a.x,b.y-a.y)
      const selected=edge.id===p.selectedEdge
      if(selected){ctx.strokeStyle=accent;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
      if(distance>24){const x=b.x-Math.cos(angle)*13,y=b.y-Math.sin(angle)*13;ctx.fillStyle=selected?accent:muted;ctx.globalAlpha=selected?1:.65;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-Math.cos(angle-.5)*6,y-Math.sin(angle-.5)*6);ctx.lineTo(x-Math.cos(angle+.5)*6,y-Math.sin(angle+.5)*6);ctx.closePath();ctx.fill()}
      if(selected||(edge.aggregate&&p.nodes.length<120)) {const label=edge.aggregate?`${edge.aggregate.count} операций · ${edge.aggregate.amount??'?'} ${edge.aggregate.asset}`:relationLabels[edge.relation_type]||edge.relation_type;ctx.font='11px Manrope, sans-serif';const measure=ctx.measureText(label),x=(a.x+b.x)/2,y=(a.y+b.y)/2;ctx.globalAlpha=.96;ctx.fillStyle=panel;ctx.fillRect(x-measure.width/2-4,y-10,measure.width+8,17);ctx.globalAlpha=1;ctx.fillStyle=selected?accent:muted;ctx.fillText(label,x-measure.width/2,y+2)}
    }
    ctx.globalAlpha=1
    const qaNodes:{id:string;x:number;y:number;label:string}[]=[]
    for(const node of p.nodes){const point=screen(node.id);if(!point||!onScreen(point))continue;const selected=node.id===p.selected||node.id===p.second,root=node.id===p.root,type=entityType(node),radius=Math.max(5,Math.min(root?14:11,(root?12:8)*Math.sqrt(v.scale)))
      ctx.fillStyle=selected?accent:panel;ctx.strokeStyle=selected||root?accent:node.verification_status==='inferred'?warning:border;ctx.lineWidth=selected?2:1.3;ctx.beginPath()
      if(['coordinate','geographic_candidate'].includes(node.type)){ctx.moveTo(point.x,point.y-radius);ctx.lineTo(point.x+radius,point.y);ctx.lineTo(point.x,point.y+radius);ctx.lineTo(point.x-radius,point.y);ctx.closePath()}
      else if(['repository','github_repository','website','image','transaction'].includes(type)){ctx.roundRect(point.x-radius,point.y-radius*.75,radius*2,radius*1.5,2)}
      else if(type==='telegram_channel'){ctx.moveTo(point.x-radius,point.y-radius*.6);ctx.lineTo(point.x+radius,point.y-radius);ctx.lineTo(point.x+radius*.25,point.y+radius);ctx.closePath()}
      else ctx.arc(point.x,point.y,radius,0,Math.PI*2)
      ctx.fill();ctx.stroke()
      if(positions[node.id]?.pinned){ctx.fillStyle=accent;ctx.fillRect(point.x+radius-2,point.y-radius-3,4,4)}
      if(selected||root||p.nodes.length<85||v.scale>1.25&&p.nodes.length<250){const label=shortLabel(node);ctx.font=`${selected||root?'600':'500'} ${root?12:11}px Manrope, sans-serif`;const measured=ctx.measureText(label);ctx.fillStyle=panel;ctx.globalAlpha=.93;ctx.fillRect(point.x-measured.width/2-3,point.y+radius+4,measured.width+6,17);ctx.globalAlpha=1;ctx.fillStyle=selected||root?text:muted;ctx.textAlign='center';ctx.fillText(label,point.x,point.y+radius+17);ctx.textAlign='left'}
      if(qaNodes.length<20)qaNodes.push({id:node.id,x:point.x,y:point.y,label:shortLabel(node)})
    }
    element.dataset.qaNodes=JSON.stringify(qaNodes)
    element.dataset.qaEdges=JSON.stringify(visibleEdges.slice(0,10).map(edge=>{const a=screen(edge.from_id)!,b=screen(edge.to_id)!;return{id:edge.id,x:a.x*.4+b.x*.6,y:a.y*.4+b.y*.6}}))
    element.dataset.zoom=String(v.scale);element.dataset.panX=String(v.x);element.dataset.panY=String(v.y)
    element.dataset.drawnNodes=String(p.nodes.length);element.dataset.drawnEdges=String(visibleEdges.length)
    element.dataset.paintMs=String(performance.now()-started)
  }
  function requestDraw(){if(frame.current===undefined)frame.current=requestAnimationFrame(draw)}
  useEffect(()=>{points.current=props.positions;viewport.current=props.viewport;requestDraw()},[props.positions,props.viewport,props.nodes,props.edges,props.selected,props.second,props.selectedEdge,props.theme])
  useEffect(()=> {
    const element=canvas.current;if(!element)return
    const observer=new ResizeObserver(entries=>{const rect=entries[0].contentRect;if(rect.width&&rect.height){const next={width:rect.width,height:rect.height};setSize(next);sizeRef.current=next;latest.current.onResize(next.width,next.height);requestDraw()}})
    observer.observe(element)
    const wheel=(event:WheelEvent)=>{event.preventDefault();const rect=element.getBoundingClientRect();viewport.current=zoomAt(viewport.current,event.clientX-rect.left,event.clientY-rect.top,Math.exp(-event.deltaY*.0015));requestDraw();clearTimeout(wheelTimer.current);wheelTimer.current=setTimeout(()=>latest.current.onViewport({...viewport.current}),100)}
    element.addEventListener('wheel',wheel,{passive:false})
    return()=>{observer.disconnect();element.removeEventListener('wheel',wheel);if(frame.current!==undefined)cancelAnimationFrame(frame.current);clearTimeout(wheelTimer.current)}
  },[])
  useImperativeHandle(forwarded,()=>({fit(){latest.current.onViewport(fitViewport(points.current,sizeRef.current.width,sizeRef.current.height))},zoom(factor){latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,factor))},center(id){const p=points.current[id];if(p)latest.current.onViewport({x:sizeRef.current.width/2-p.x,y:sizeRef.current.height/2-p.y,scale:1})}}),[])
  const local=(event:React.PointerEvent)=>{const rect=canvas.current!.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top}}
  return <canvas ref={canvas} className="investigation-graph-canvas" role="application" aria-label="Интерактивный граф расследования" tabIndex={0}
    onPointerDown={event=>{if(event.button!==0)return;const point=local(event),node=hitNode(latest.current.nodes,points.current,viewport.current,point.x,point.y);canvas.current?.focus();event.currentTarget.setPointerCapture?.(event.pointerId);drag.current={id:node?.id,startX:point.x,startY:point.y,point:node?{...points.current[node.id]}:undefined,view:{...viewport.current},moved:false};if(node)latest.current.onSelect(node.id,event.ctrlKey||event.metaKey);else{const edge=hitRelation(latest.current.edges,points.current,viewport.current,point.x,point.y);if(edge)latest.current.onEdge(edge.id)}}}
    onPointerMove={event=>{const current=drag.current;if(!current)return;const point=local(event),dx=point.x-current.startX,dy=point.y-current.startY;if(Math.hypot(dx,dy)<3&&!current.moved)return;current.moved=true;if(current.id&&current.point)points.current={...points.current,[current.id]:{x:current.point.x+dx/current.view.scale,y:current.point.y+dy/current.view.scale,pinned:true}};else viewport.current={...current.view,x:current.view.x+dx,y:current.view.y+dy};requestDraw()}}
    onPointerUp={event=>{const current=drag.current;drag.current=undefined;event.currentTarget.releasePointerCapture?.(event.pointerId);if(current?.moved){if(current.id)latest.current.onCommitPositions({...points.current});else latest.current.onViewport({...viewport.current})}}}
    onPointerCancel={()=>{drag.current=undefined}}
    onKeyDown={event=>{const key=event.key;if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(key)){event.preventDefault();if(key==='Home')latest.current.onViewport(fitViewport(points.current,sizeRef.current.width,sizeRef.current.height));else if(key==='+'||key==='='||key==='-')latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,key==='-'?.8:1.25));else latest.current.onViewport({...viewport.current,x:viewport.current.x+(key==='ArrowLeft'?40:key==='ArrowRight'?-40:0),y:viewport.current.y+(key==='ArrowUp'?40:key==='ArrowDown'?-40:0)})}}}/>
})
