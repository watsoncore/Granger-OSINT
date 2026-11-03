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
  selection?:string[];onSelection?(ids:string[]):void
  onCreate?(position:GraphPoint):void;onConnect?(from:string,to:string):void
  onContext?(id:string,position:GraphPoint):void
}
export const InvestigationCanvas=forwardRef<GraphCanvasHandle,Props>(function InvestigationCanvas(props,forwarded) {
  const canvas=useRef<HTMLCanvasElement>(null),latest=useRef(props);latest.current=props
  const points=useRef(props.positions),viewport=useRef(props.viewport)
  const [size,setSize]=useState({width:800,height:440})
  const sizeRef=useRef(size);sizeRef.current=size
  const frame=useRef<number|undefined>(undefined),wheelTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined)
  const thumbnails=useRef(new Map<string,HTMLImageElement>())
  const drag=useRef<{id?:string;startX:number;startY:number;point?:GraphPoint;view:GraphViewport;moved:boolean}|undefined>(undefined)
  const linking=useRef<string|undefined>(undefined),marquee=useRef<{x:number;y:number;endX:number;endY:number}|undefined>(undefined)
  const mini=useRef<{x:number;y:number;w:number;h:number;minX:number;minY:number;scale:number}|undefined>(undefined)
  const moving=useRef<Record<string,GraphPoint>>({})
  const paints=useRef<number[]>([]),intervals=useRef<number[]>([]),latencies=useRef<number[]>([]),lastPaint=useRef(0),lastInput=useRef(0)
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
    const visibleMedia=new Set(cards.map(c=>String((c.node.attributes.media as Record<string,unknown>|undefined)?.id||'')))
    for(const key of thumbnails.current.keys())if(!visibleMedia.has(key))thumbnails.current.delete(key)
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
      const selected=node.id===p.selected||node.id===p.second||p.selection?.includes(node.id),root=node.id===p.root,type=entityType(node),x=point.x-box.width/2,y=point.y-box.height/2
      ctx.fillStyle=selected?raised:panel;ctx.strokeStyle=selected||root?accent:node.verification_status==='inferred'?warning:border;ctx.lineWidth=selected||root?1.8:1
      const corner=node.type==='public_profile'?18:node.type==='image'?3:node.type==='entity_group'?11:6
      ctx.beginPath();ctx.roundRect(x,y,box.width,box.height,Math.min(corner,box.height/4));ctx.fill();ctx.stroke()
      ctx.fillStyle=node.verification_status==='contradicted'?danger:node.verification_status==='inferred'?warning:node.verification_status==='verified'?accent:muted
      ctx.beginPath();ctx.arc(x+box.width-11,y+11,3,0,Math.PI*2);ctx.fill()
      if(typeof node.attributes.analyst_color==='string'&&/^#[0-9a-f]{6}$/i.test(node.attributes.analyst_color)){ctx.fillStyle=node.attributes.analyst_color;ctx.fillRect(x+1,y+8,3,box.height-16)}
      {
        const font=Math.max(10,Math.min(14,12*Math.sqrt(v.scale))),padding=Math.max(6,12*v.scale),media=node.attributes.media as Record<string,unknown>|undefined
        let left=x+padding,space=box.width-padding*2
        if(media){const key=String(media.id),preview=media.thumbnail
          if(typeof preview==='string'&&/^data:image\/(?:jpeg|png|webp);base64,/.test(preview)&&!thumbnails.current.has(key)&&thumbnails.current.size<64){
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
        if(box.height>=48){ctx.font=`${Math.max(8,font-2)}px Manrope, sans-serif`;ctx.fillStyle=muted;ctx.fillText(clipped((({blockchain_address:'◈ ',person:'◎ ',public_profile:'● ',domain:'⊕ ',infrastructure_asset:'⌘ ',transaction:'⇄ ',image:'▧ ',source:'▤ ',analyst_note:'✎ ',hypothesis:'? ',entity_group:'⊞ '} as Record<string,string>)[node.type]||'◇ ')+badge,space),left,y+Math.max(14,box.height*.25))}
        ctx.font=`600 ${font}px Manrope, sans-serif`;ctx.fillStyle=text
        const title=shortLabel(node);let split=title.length
        while(split>1&&ctx.measureText(title.slice(0,split)).width>space)split--
        const twoLines=split<title.length&&box.height>=70
        ctx.fillText(twoLines?title.slice(0,split):clipped(title,space),left,y+box.height*.48+(box.height<48?4:0))
        if(twoLines)ctx.fillText(clipped(title.slice(split),space),left,y+box.height*.48+font+2)
        drawnLabels++
        let subtitle=String(node.attributes.reference_photo?'Место исходника не подтверждено':node.attributes.scope_only?'Область исследования':node.attributes.scene_description||node.attributes.url||'')
        if(node.type==='blockchain_address')subtitle=`${node.attributes.transaction_count??'—'} событий · ${node.attributes.counterparty_count??'—'} контрагентов`
        if(node.type==='blockchain_address'&&!root&&Array.isArray(node.attributes.flow_summaries)){const flow=node.attributes.flow_summaries[0] as {direction:string;amount:string|null;asset:string};if(flow)subtitle=`${flow.direction==='to_target'?'К цели':'От цели'}: ${flow.amount??'?'} ${flow.asset}${node.attributes.flow_summaries.length>1?' · + активы':''}`}
        if(node.type==='entity_group')subtitle='Раскройте группу для просмотра'
        if(node.type==='geographic_candidate')subtitle='Географическая гипотеза'
        if(box.height>=48){ctx.font=`${Math.max(9,font-1)}px Manrope, sans-serif`;ctx.fillStyle=muted;ctx.fillText(clipped(subtitle,space),left,y+box.height*.79)}
      }
      if(positions[node.id]?.pinned){ctx.fillStyle=accent;ctx.fillRect(x+box.width-8,y+4,4,4)}
      if(p.onConnect){for(const sign of [-1,1]){ctx.fillStyle=accent;ctx.beginPath();ctx.arc(point.x+sign*box.width/2,point.y,5,0,Math.PI*2);ctx.fill()}}
      if(qaNodes.length<30)qaNodes.push({id:node.id,x:point.x,y:point.y,label:shortLabel(node)})
    }
    if(marquee.current){const r=marquee.current;ctx.strokeStyle=accent;ctx.setLineDash([4,3]);ctx.strokeRect(r.x,r.y,r.endX-r.x,r.endY-r.y);ctx.setLineDash([])}
    if(p.nodes.length>3&&width>420){
      const values=p.nodes.flatMap(n=>positions[n.id]?[positions[n.id]]:[])
      if(values.length){const minX=Math.min(...values.map(p=>p.x))-150,minY=Math.min(...values.map(p=>p.y))-70,maxX=Math.max(...values.map(p=>p.x))+150,maxY=Math.max(...values.map(p=>p.y))+70,w=164,h=94,x=width-w-12,y=height-h-12,s=Math.min(w/(maxX-minX),h/(maxY-minY))
        mini.current={x,y,w,h,minX,minY,scale:s};ctx.fillStyle=panel;ctx.strokeStyle=border;ctx.globalAlpha=.92;ctx.fillRect(x,y,w,h);ctx.strokeRect(x,y,w,h);ctx.globalAlpha=1;ctx.fillStyle=muted
        for(const n of p.nodes){const point=positions[n.id];if(point)ctx.fillRect(x+(point.x-minX)*s-2,y+(point.y-minY)*s-1,4,2)}
        ctx.strokeStyle=accent;ctx.strokeRect(x+(-v.x/v.scale-minX)*s,y+(-v.y/v.scale-minY)*s,Math.min(w,width/v.scale*s),Math.min(h,height/v.scale*s))
      }
    }else mini.current=undefined
    element.dataset.drawnLabels=String(drawnLabels);element.dataset.drawnImages=String(drawnImages)
    element.dataset.qaNodes=JSON.stringify(qaNodes)
    element.dataset.qaEdges=JSON.stringify(routes.slice(0,20).map(({edge,points})=>({id:edge.id,...points[Math.floor(points.length*.6)]})))
    element.dataset.zoom=String(v.scale);element.dataset.panX=String(v.x);element.dataset.panY=String(v.y)
    element.dataset.drawnNodes=String(p.nodes.length);element.dataset.drawnEdges=String(routes.length);element.dataset.paintMs=String(performance.now()-started)
    element.dataset.modelEdges=String(p.edges.length);element.dataset.onScreenNodes=String(cards.length)
    const now=performance.now();paints.current.push(now-started);if(lastPaint.current&&now-lastPaint.current<100)intervals.current.push(now-lastPaint.current)
    if(lastInput.current){latencies.current.push(now-lastInput.current);lastInput.current=0}lastPaint.current=now
    for(const array of [paints.current,intervals.current,latencies.current])if(array.length>240)array.splice(0,array.length-240)
    element.dataset.frameMetrics=JSON.stringify({paint_ms:paints.current,active_intervals_ms:intervals.current,event_to_paint_ms:latencies.current})
  }
  function requestDraw(){if(frame.current===undefined)frame.current=requestAnimationFrame(draw)}
  useEffect(()=>{points.current=props.positions;viewport.current=props.viewport;requestDraw()},[props.positions,props.viewport,props.nodes,props.edges,props.selected,props.second,props.selection,props.selectedEdge,props.theme])
  useEffect(()=> {
    const element=canvas.current;if(!element)return
    const observer=new ResizeObserver(entries=>{const rect=entries[0].contentRect;if(rect.width&&rect.height){const next={width:rect.width,height:rect.height};setSize(next);sizeRef.current=next;latest.current.onResize(next.width,next.height);requestDraw()}})
    observer.observe(element)
    const wheel=(event:WheelEvent)=>{event.preventDefault();const rect=element.getBoundingClientRect();viewport.current=zoomAt(viewport.current,event.clientX-rect.left,event.clientY-rect.top,Math.exp(-event.deltaY*.0015));requestDraw();clearTimeout(wheelTimer.current);wheelTimer.current=setTimeout(()=>latest.current.onViewport({...viewport.current}),100)}
    element.addEventListener('wheel',wheel,{passive:false})
    return()=>{observer.disconnect();element.removeEventListener('wheel',wheel);if(frame.current!==undefined)cancelAnimationFrame(frame.current);clearTimeout(wheelTimer.current)}
  },[])
  useImperativeHandle(forwarded,()=>({fit(){latest.current.onViewport(readableViewport(points.current,sizeRef.current.width,sizeRef.current.height,latest.current.root,latest.current.mode||'graph'))},zoom(factor){latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,factor))},center(id){const p=points.current[id];if(p)latest.current.onViewport({x:sizeRef.current.width/2-p.x,y:sizeRef.current.height/2-p.y,scale:1})}}),[])
  const local=(event:{clientX:number;clientY:number})=>{const rect=canvas.current!.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top}}
  return <canvas ref={canvas} className="investigation-graph-canvas" role="application" aria-label="Интерактивный граф расследования" tabIndex={0}
    onDoubleClick={event=>{const r=event.currentTarget.getBoundingClientRect(),v=viewport.current;if(!hitNode(latest.current.nodes,points.current,v,event.clientX-r.left,event.clientY-r.top))latest.current.onCreate?.({x:(event.clientX-r.left-v.x)/v.scale,y:(event.clientY-r.top-v.y)/v.scale})}}
    onContextMenu={event=>{event.preventDefault();const p=local(event),v=viewport.current,node=hitNode(latest.current.nodes,points.current,v,p.x,p.y);latest.current.onContext?.(node?.id||'',{x:(p.x-v.x)/v.scale,y:(p.y-v.y)/v.scale})}}
    onPointerDown={event=>{
      if(event.button!==0)return
      const point=local(event),v=viewport.current,p=latest.current
      canvas.current?.focus();event.currentTarget.setPointerCapture?.(event.pointerId)
      const m=mini.current
      if(m&&point.x>=m.x&&point.x<=m.x+m.w&&point.y>=m.y&&point.y<=m.y+m.h){latest.current.onViewport({...v,x:sizeRef.current.width/2-((point.x-m.x)/m.scale+m.minX)*v.scale,y:sizeRef.current.height/2-((point.y-m.y)/m.scale+m.minY)*v.scale});return}
      if(p.onConnect){const port=p.nodes.find(n=>{const pos=points.current[n.id];if(!pos)return false;const box=nodeBox(n,v.scale);return Math.abs(point.y-(pos.y*v.scale+v.y))<10&&Math.abs(Math.abs(point.x-(pos.x*v.scale+v.x))-box.width/2)<10});if(port){linking.current=port.id;return}}
      const node=hitNode(p.nodes,points.current,v,point.x,point.y)
      if(event.shiftKey&&!node&&p.onSelection){marquee.current={x:point.x,y:point.y,endX:point.x,endY:point.y};return}
      drag.current={id:node?.id,startX:point.x,startY:point.y,point:node?{...points.current[node.id]}:undefined,view:{...v},moved:false}
      moving.current={}
      if(node){
        const ids=new Set(p.selection?.includes(node.id)?p.selection:[node.id])
        // A group moves its descendants without rewriting semantic relations.
        let changed=true;while(changed){changed=false;for(const n of p.nodes)if(!ids.has(n.id)&&ids.has(String(n.attributes.parent_group_id))){ids.add(n.id);changed=true}}
        for(const id of ids)if(points.current[id])moving.current[id]={...points.current[id]}
        if(!p.selection?.includes(node.id)||event.ctrlKey||event.metaKey)p.onSelect(node.id,event.ctrlKey||event.metaKey)
      }else{const edge=hitRelation(p.edges,points.current,v,point.x,point.y,p.nodes,p.mode);if(edge)p.onEdge(edge.id)}
    }}
    onPointerMove={event=>{
      const point=local(event)
      if(marquee.current){marquee.current.endX=point.x;marquee.current.endY=point.y;requestDraw();return}
      const current=drag.current;if(!current)return
      const dx=point.x-current.startX,dy=point.y-current.startY;if(Math.hypot(dx,dy)<3&&!current.moved)return
      lastInput.current=performance.now()
      current.moved=true
      if(current.id&&current.point){const updated={...points.current};for(const [id,p]of Object.entries(moving.current))updated[id]={x:p.x+dx/current.view.scale,y:p.y+dy/current.view.scale,pinned:true};points.current=updated}
      else viewport.current={...current.view,x:current.view.x+dx,y:current.view.y+dy}
      requestDraw()
    }}
    onPointerUp={event=>{
      const point=local(event),p=latest.current,v=viewport.current
      if(linking.current){const target=hitNode(p.nodes,points.current,v,point.x,point.y),from=linking.current;linking.current=undefined;if(target&&target.id!==from)p.onConnect?.(from,target.id)}
      if(marquee.current){const r=marquee.current;marquee.current=undefined;p.onSelection?.(p.nodes.filter(n=>{const pos=points.current[n.id];if(!pos)return false;const x=pos.x*v.scale+v.x,y=pos.y*v.scale+v.y;return x>=Math.min(r.x,r.endX)&&x<=Math.max(r.x,r.endX)&&y>=Math.min(r.y,r.endY)&&y<=Math.max(r.y,r.endY)}).map(n=>n.id));requestDraw()}
      const current=drag.current;drag.current=undefined;event.currentTarget.releasePointerCapture?.(event.pointerId)
      if(current?.moved){if(current.id)p.onCommitPositions({...points.current});else p.onViewport({...viewport.current})}
    }}
    onPointerCancel={()=>{drag.current=undefined;marquee.current=undefined;linking.current=undefined}}
    onKeyDown={event=>{const key=event.key;if(['+','=','-','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(key)){event.preventDefault();if(key==='Home')latest.current.onViewport(readableViewport(points.current,sizeRef.current.width,sizeRef.current.height,latest.current.root,latest.current.mode||'graph'));else if(key==='+'||key==='='||key==='-')latest.current.onViewport(zoomAt(viewport.current,sizeRef.current.width/2,sizeRef.current.height/2,key==='-'?.8:1.25));else latest.current.onViewport({...viewport.current,x:viewport.current.x+(key==='ArrowLeft'?40:key==='ArrowRight'?-40:0),y:viewport.current.y+(key==='ArrowUp'?40:key==='ArrowDown'?-40:0)})}}}/>
})
