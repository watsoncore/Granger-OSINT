import { forwardRef,useEffect,useImperativeHandle,useRef,useState } from 'react'
import type { GraphEntity,GraphPoint,GraphRelation,GraphViewport } from '../types'
import { entityLabel,entityType,readableViewport,hitNode,hitRelation,nodeBox,relationLabels,shortLabel,zoomAt } from '../graph-model'
import { routeEdges } from '../graph-geometry'

export interface GraphCanvasHandle { fit():void; zoom(factor:number):void; center(id:string):void }
interface Props {
  nodes:GraphEntity[];edges:GraphRelation[];positions:Record<string,GraphPoint>;viewport:GraphViewport
  selected:string;second:string;selectedEdge:string;root:string;theme?:unknown;mode?:'tree'|'graph'
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
  const thumbnails=useRef(new Map<string,HTMLImageElement>())
  const drag=useRef<{id?:string;startX:number;startY:number;point?:GraphPoint;view:GraphViewport;moved:boolean}|undefined>(undefined)
  function draw() {
    frame.current=undefined
    const element=canvas.current,ctx=element?.getContext('2d');if(!element||!ctx)return
    const started=performance.now(),{width,height}=sizeRef.current,p=latest.current,v=viewport.current,positions=points.current,dpr=Math.min(devicePixelRatio||1,2)
    if(element.width!==Math.round(width*dpr)||element.height!==Math.round(height*dpr)){element.width=Math.round(width*dpr);element.height=Math.round(height*dpr)}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height)
    const style=getComputedStyle(element),color=(name:string)=>style.getPropertyValue(name).trim()
    const text=color('--text'),muted=color('--muted'),accent=color('--accent'),border=color('--border'),panel=color('--panel'),raised=color('--panel-raised'),warning=color('--warning'),danger=color('--danger')
    const screen=(id:string)=>{const point=positions[id];return point?{x:point.x*v.scale+v.x,y:point.y*v.scale+v.y}:null}
    const onScreen=(point:{x:number;y:number},margin=160)=>point.x>=-margin&&point.x<=width+margin&&point.y>=-margin&&point.y<=height+margin
    const clipped=(value:string,space:number)=>{let output=value;if(space<12)return '';if(ctx.measureText(output).width<=space)return output;const tail=value.length>10?value.slice(-7):'';let head=value.slice(0,-tail.length||undefined);while(head.length>1&&ctx.measureText(head+'…'+tail).width>space)head=head.slice(0,-1);output=head+'…'+tail;if(ctx.measureText(output).width>space)return '…';return output}
    const cards=p.nodes.flatMap(node=>{const point=screen(node.id);return point&&onScreen(point)?[{node,point,box:nodeBox(node,v.scale)}]:[]})
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
    const routes=routeEdges(p.edges,positions,v,p.nodes,p.mode).filter(route=>route.points.some(point=>onScreen(point,20)))
    const occupied=cards.map(({point,box})=>({x:point.x-box.width/2-4,y:point.y-box.height/2-4,w:box.width+8,h:box.height+8}))
    for(const {edge,points}of routes){
      const selected=edge.id===p.selectedEdge,related=edge.from_id===p.selected||edge.to_id===p.selected
      ctx.strokeStyle=selected?accent:edge.verification_status==='contradicted'?danger:edge.verification_status==='inferred'?warning:related?muted:border
      ctx.lineWidth=selected?2.4:edge.aggregate?1.6:1;ctx.globalAlpha=p.selected&&!related&&!selected ? .25 : selected ? 1 : .65
      ctx.setLineDash(['inferred','unverified'].includes(edge.verification_status)?[5,5]:[])
      ctx.beginPath();ctx.moveTo(points[0].x,points[0].y);points.slice(1).forEach(point=>ctx.lineTo(point.x,point.y));ctx.stroke();ctx.setLineDash([])
      const end=points.at(-1)!,prior=points.at(-2)!,angle=Math.atan2(end.y-prior.y,end.x-prior.x)
      ctx.fillStyle=selected?accent:muted;ctx.beginPath();ctx.moveTo(end.x,end.y);ctx.lineTo(end.x-Math.cos(angle-.45)*8,end.y-Math.sin(angle-.45)*8);ctx.lineTo(end.x-Math.cos(angle+.45)*8,end.y-Math.sin(angle+.45)*8);ctx.closePath();ctx.fill();ctx.globalAlpha=1
      if(selected||v.scale>.45&&p.nodes.length<=45&&(edge.aggregate||related)){
        const asset=edge.aggregate?.asset_label||edge.aggregate?.asset||'',label=edge.aggregate?`${edge.aggregate.count} · ${edge.aggregate.amount??'?'} ${asset.length>12?'актив':asset}`:relationLabels[edge.relation_type]||edge.relation_type
        ctx.font='11px Manrope, sans-serif';const caption=clipped(label,190),w=ctx.measureText(caption).width+12
        for(const fraction of [.5,.32,.68]){const point=points[Math.round((points.length-1)*fraction)],box={x:point.x-w/2,y:point.y-10,w,h:21}
          if(occupied.some(other=>box.x<other.x+other.w&&box.x+box.w>other.x&&box.y<other.y+other.h&&box.y+box.h>other.y))continue
          occupied.push(box);ctx.fillStyle=panel;ctx.fillRect(box.x,box.y,box.w,box.h);ctx.fillStyle=selected?accent:muted;ctx.fillText(caption,box.x+6,box.y+14);break
        }
      }
    }
    const qaNodes:{id:string;x:number;y:number;label:string}[]=[]
    let drawnLabels=0,drawnImages=0
    for(const {node,point,box}of cards){
      const selected=node.id===p.selected||node.id===p.second,root=node.id===p.root,type=entityType(node),x=point.x-box.width/2,y=point.y-box.height/2
      ctx.fillStyle=selected?raised:panel;ctx.strokeStyle=selected||root?accent:node.verification_status==='inferred'?warning:border;ctx.lineWidth=selected||root?1.8:1
      const corner=node.type==='public_profile'?18:node.type==='image'?3:node.type==='entity_group'?11:6
      ctx.beginPath();ctx.roundRect(x,y,box.width,box.height,Math.min(corner,box.height/4));ctx.fill();ctx.stroke()
      {
        const font=Math.max(10,Math.min(14,12*Math.sqrt(v.scale))),padding=Math.max(6,12*v.scale),media=node.attributes.media as Record<string,unknown>|undefined
        let left=x+padding,space=box.width-padding*2
        if(media){const key=String(media.id),preview=media.thumbnail
          if(typeof preview==='string'&&/^data:image\/(?:jpeg|png|webp);base64,/.test(preview)&&!thumbnails.current.has(key)){
            if(thumbnails.current.size>=64)thumbnails.current.delete(thumbnails.current.keys().next().value!)
            const picture=new Image();thumbnails.current.set(key,picture);picture.onload=requestDraw;picture.src=preview
          }
          const picture=thumbnails.current.get(key)
          if(picture?.complete&&picture.naturalWidth&&box.width>105){
            const side=Math.min(48,box.height-padding*2),ratio=Math.max(side/picture.naturalWidth,side/picture.naturalHeight)
            ctx.save();ctx.beginPath();ctx.roundRect(left,y+(box.height-side)/2,side,side,5);ctx.clip()
            ctx.drawImage(picture,left+(side-picture.naturalWidth*ratio)/2,y+(box.height-picture.naturalHeight*ratio)/2,picture.naturalWidth*ratio,picture.naturalHeight*ratio);ctx.restore();left+=side+8;space-=side+8;drawnImages++
          }
        }
        const badge=node.type==='blockchain_address'?String(node.attributes.chain||'сеть').toUpperCase()+(root?'':` · ${node.attributes.transaction_count??'—'} событий`):type==='github_profile'||type==='github_repository'?'GitHub':type==='telegram_channel'?'Telegram':node.type==='entity_group'?`Группа · ${node.attributes.member_count}`:node.attributes.reference_photo?'Эталон':entityLabel(node)
        if(box.height>=48){ctx.font=`${Math.max(8,font-2)}px Manrope, sans-serif`;ctx.fillStyle=muted;ctx.fillText(clipped(badge,space),left,y+Math.max(14,box.height*.25))}
        ctx.font=`600 ${font}px Manrope, sans-serif`;ctx.fillStyle=selected||root?text:muted;ctx.fillText(clipped(shortLabel(node),space),left,y+box.height*.53+(box.height<48?4:0));drawnLabels++
        let subtitle=String(node.attributes.reference_photo?'Место исходника не подтверждено':node.attributes.scope_only?'Область исследования':node.attributes.scene_description||node.attributes.url||'')
        if(node.type==='blockchain_address')subtitle=`${node.attributes.transaction_count??'—'} событий · ${node.attributes.counterparty_count??'—'} контрагентов`
        if(node.type==='blockchain_address'&&!root&&Array.isArray(node.attributes.flow_summaries)){const flow=node.attributes.flow_summaries[0] as {direction:string;amount:string|null;asset:string};if(flow)subtitle=`${flow.direction==='to_target'?'К цели':'От цели'}: ${flow.amount??'?'} ${flow.asset}${node.attributes.flow_summaries.length>1?' · + активы':''}`}
        if(node.type==='entity_group')subtitle='Раскройте группу для просмотра'
        if(node.type==='geographic_candidate')subtitle='Географическая гипотеза'
        if(box.height>=48){ctx.font=`${Math.max(9,font-1)}px Manrope, sans-serif`;ctx.fillStyle=muted;ctx.fillText(clipped(subtitle,space),left,y+box.height*.79)}
      }
      if(positions[node.id]?.pinned){ctx.fillStyle=accent;ctx.fillRect(x+box.width-8,y+4,4,4)}
      if(qaNodes.length<30)qaNodes.push({id:node.id,x:point.x,y:point.y,label:shortLabel(node)})
    }
    element.dataset.drawnLabels=String(drawnLabels);element.dataset.drawnImages=String(drawnImages)
    element.dataset.qaNodes=JSON.stringify(qaNodes)
    element.dataset.qaEdges=JSON.stringify(routes.slice(0,20).map(({edge,points})=>({id:edge.id,...points[Math.floor(points.length*.6)]})))
    element.dataset.zoom=String(v.scale);element.dataset.panX=String(v.x);element.dataset.panY=String(v.y)
    element.dataset.drawnNodes=String(p.nodes.length);element.dataset.drawnEdges=String(routes.length);element.dataset.paintMs=String(performance.now()-started)
    element.dataset.modelEdges=String(p.edges.length);element.dataset.onScreenNodes=String(cards.length)
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
  useImperativeHandle(forwarded,()=>({fit(){latest.current.onViewport(readableViewport(points.current,sizeRef.current.width,sizeRef.current.height,latest.current.root,latest.current.mode||'graph'))},zoom(factor){latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,factor))},center(id){const p=points.current[id];if(p)latest.current.onViewport({x:sizeRef.current.width/2-p.x,y:sizeRef.current.height/2-p.y,scale:1})}}),[])
  const local=(event:React.PointerEvent)=>{const rect=canvas.current!.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top}}
  return <canvas ref={canvas} className="investigation-graph-canvas" role="application" aria-label="Интерактивный граф расследования" tabIndex={0}
    onPointerDown={event=>{if(event.button!==0)return;const point=local(event),node=hitNode(latest.current.nodes,points.current,viewport.current,point.x,point.y);canvas.current?.focus();event.currentTarget.setPointerCapture?.(event.pointerId);drag.current={id:node?.id,startX:point.x,startY:point.y,point:node?{...points.current[node.id]}:undefined,view:{...viewport.current},moved:false};if(node)latest.current.onSelect(node.id,event.ctrlKey||event.metaKey);else{const edge=hitRelation(latest.current.edges,points.current,viewport.current,point.x,point.y,latest.current.nodes,latest.current.mode);if(edge)latest.current.onEdge(edge.id)}}}
    onPointerMove={event=>{const current=drag.current;if(!current)return;const point=local(event),dx=point.x-current.startX,dy=point.y-current.startY;if(Math.hypot(dx,dy)<3&&!current.moved)return;current.moved=true;if(current.id&&current.point)points.current={...points.current,[current.id]:{x:current.point.x+dx/current.view.scale,y:current.point.y+dy/current.view.scale,pinned:true}};else viewport.current={...current.view,x:current.view.x+dx,y:current.view.y+dy};requestDraw()}}
    onPointerUp={event=>{const current=drag.current;drag.current=undefined;event.currentTarget.releasePointerCapture?.(event.pointerId);if(current?.moved){if(current.id)latest.current.onCommitPositions({...points.current});else latest.current.onViewport({...viewport.current})}}}
    onPointerCancel={()=>{drag.current=undefined}}
    onKeyDown={event=>{const key=event.key;if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(key)){event.preventDefault();if(key==='Home')latest.current.onViewport(readableViewport(points.current,sizeRef.current.width,sizeRef.current.height,latest.current.root,latest.current.mode||'graph'));else if(key==='+'||key==='='||key==='-')latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,key==='-'?.8:1.25));else latest.current.onViewport({...viewport.current,x:viewport.current.x+(key==='ArrowLeft'?40:key==='ArrowRight'?-40:0),y:viewport.current.y+(key==='ArrowUp'?40:key==='ArrowDown'?-40:0)})}}}/>
})
