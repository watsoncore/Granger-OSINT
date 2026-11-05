import {useEffect,useRef,useState} from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {ChevronLeft,ChevronRight,Expand,ExternalLink,Minus,Plus,RotateCcw,X} from 'lucide-react'
import {act,request} from '../bridge'
import {imageData,linkedMedia,loadThumbnail,mediaPayload,mediaThumbnail,visualMedia,type MediaContext} from '../canvas-media'
import type {GraphEntity} from '../types'
import {Button} from './ui'

interface MediaDetail {
  preview?:string; original_available?:boolean; width?:number; height?:number
  mime?:string; bytes?:number; sha256?:string; exif?:Record<string,unknown>
  original_reference?:string; name?:string
}

export function NodeMedia({node,context,onOpen}:{node:GraphEntity;context?:MediaContext;onOpen():void}){
  const media=visualMedia(node),embedded=mediaThumbnail(media)
  const [loaded,setLoaded]=useState<{id:string;src:string}>()
  useEffect(()=>{
    if(!context||!media||embedded||media.kind!=='local_attachment')return
    let active=true
    void loadThumbnail(context,node,media).then(src=>{if(active)setLoaded({id:media.id,src})}).catch(()=>{if(active)setLoaded({id:media.id,src:''})})
    return()=>{active=false}
  },[node.id,media?.id,embedded,context?.canvas_id,context?.investigation_id])
  if(!media)return null
  const preview=embedded||(loaded?.id===media.id?loaded.src:'')
  const count=linkedMedia(node).length
  return <figure className="graph-node-media">
    <button className="media-preview-button" onClick={onOpen} aria-label={'Открыть изображение '+node.label}>
      {preview?<img src={preview} alt={media.name||node.label}/>:<span>{media.state==='unavailable'||loaded?.id===media.id?'Предпросмотр недоступен':'Подготовка предпросмотра…'}</span>}
      <span><Expand size={14}/>Открыть{count>1?' · '+count:''}</span>
    </button>
    <figcaption>{media.width&&media.height?media.width+' × '+media.height:'Размеры не загружены'} · {media.kind==='local_attachment'?'Сохранённое вложение':'Публичный источник'}</figcaption>
  </figure>
}

export function MediaViewer({node,context,onClose,onEvidence}:{node:GraphEntity|null;context:MediaContext;onClose():void;onEvidence?(id:string):void}){
  const [detail,setDetail]=useState<MediaDetail>({}),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [zoom,setZoom]=useState(1),[fullscreen,setFullscreen]=useState(false),[index,setIndex]=useState(0)
  const stage=useRef<HTMLDivElement>(null)
  const drag=useRef<{x:number;y:number;left:number;top:number}|undefined>(undefined)
  const gallery=node?linkedMedia(node):[]
  const media=node?(gallery[index]||visualMedia(node)):undefined
  useEffect(()=>{setIndex(0);setFullscreen(false)},[node?.id,context.canvas_id,context.investigation_id])
  useEffect(()=>{
    let active=true
    setDetail({});setError('');setZoom(1);drag.current=undefined
    if(!node||!media)return
    setBusy(true)
    void request('canvas_media_view',mediaPayload(context,node,media))
      .then(value=>{if(active)setDetail(value as MediaDetail)})
      .catch(reason=>{if(active)setError(reason instanceof Error?reason.message:'Изображение недоступно.')})
      .finally(()=>{if(active)setBusy(false)})
    return()=>{active=false}
  },[node?.id,media?.id,context.canvas_id,context.investigation_id])
  const preview=imageData(detail.preview)||mediaThumbnail(media)
  function scale(factor:number){setZoom(value=>Math.max(1,Math.min(8,value*factor)))}
  useEffect(()=>{
    const element=stage.current
    if(!element||!node)return
    const wheel=(event:WheelEvent)=>{event.preventDefault();scale(event.deltaY<0?1.2:1/1.2)}
    element.addEventListener('wheel',wheel,{passive:false})
    return()=>element.removeEventListener('wheel',wheel)
  },[node?.id])
  return <Dialog.Root open={!!node} onOpenChange={open=>{if(!open)onClose()}}>
    <Dialog.Portal>
      <Dialog.Overlay className="dialog-overlay media-viewer-overlay"/>
      <Dialog.Content className={'media-viewer'+(fullscreen?' is-fullscreen':'')}>
        <header>
          <div>
            <Dialog.Title>{detail.name||media?.name||node?.label||'Изображение'}</Dialog.Title>
            <Dialog.Description>{detail.width||media?.width||'—'} × {detail.height||media?.height||'—'} · {detail.mime||media?.mime||'Изображение'}{detail.bytes?' · '+(detail.bytes/1024).toFixed(0)+' КиБ':''}</Dialog.Description>
          </div>
          <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Закрыть изображение"><X size={18}/></Button></Dialog.Close>
        </header>
        <div className="media-viewer-toolbar">
          {gallery.length>1&&<>
            <Button variant="ghost" size="sm" aria-label="Предыдущее изображение" disabled={index===0} onClick={()=>setIndex(index-1)}><ChevronLeft size={16}/></Button>
            <span>{index+1} / {gallery.length}</span>
            <Button variant="ghost" size="sm" aria-label="Следующее изображение" disabled={index===gallery.length-1} onClick={()=>setIndex(index+1)}><ChevronRight size={16}/></Button>
          </>}
          <Button variant="ghost" size="sm" aria-label="Уменьшить изображение" onClick={()=>scale(1/1.25)}><Minus size={15}/></Button>
          <span>{Math.round(zoom*100)}%</span>
          <Button variant="ghost" size="sm" aria-label="Увеличить изображение" onClick={()=>scale(1.25)}><Plus size={15}/></Button>
          <Button variant="ghost" size="sm" onClick={()=>setZoom(1)}><RotateCcw size={14}/>Вписать</Button>
          <Button variant="ghost" size="sm" onClick={()=>setFullscreen(value=>!value)}><Expand size={14}/>{fullscreen?'Вернуть окно':'Развернуть'}</Button>
          <Button variant="secondary" size="sm" disabled={!detail.original_available||busy}
            onClick={()=>node&&void act('canvas_media_open',mediaPayload(context,node,media))}><ExternalLink size={14}/>Оригинал</Button>
          {busy&&<span role="status">Загрузка изображения…</span>}
        </div>
        <div ref={stage} className={'media-viewer-stage'+(zoom>1?' can-pan':'')}
          onPointerDown={event=>{
            if(zoom<=1||event.button!==0||!preview)return
            const element=event.currentTarget
            drag.current={x:event.clientX,y:event.clientY,left:element.scrollLeft,top:element.scrollTop}
            element.setPointerCapture(event.pointerId)
          }}
          onPointerMove={event=>{
            const origin=drag.current
            if(origin)event.currentTarget.scrollTo(origin.left+origin.x-event.clientX,origin.top+origin.y-event.clientY)
          }}
          onLostPointerCapture={()=>{drag.current=undefined}}>
          {preview?<img draggable={false} src={preview} alt={media?.name||node?.label||'Изображение'}
            style={zoom===1?{maxWidth:'100%',maxHeight:'100%'}:{width:(zoom*100)+'%',maxWidth:'none',maxHeight:'none'}}/>
            :<p>{error||(!busy?'Предпросмотр недоступен':'')}</p>}
        </div>
        <footer>
          {error&&preview&&<p role="alert">{error}</p>}
          <p className="monospace">{detail.original_reference||media?.source_url||media?.url||'Защищённое локальное вложение'}</p>
          {media?.evidence_id&&onEvidence&&<Button variant="ghost" size="sm" onClick={()=>onEvidence(media.evidence_id!)}>Показать основание</Button>}
          {detail.sha256&&<details><summary>Целостность и метаданные</summary>
            <p className="monospace">SHA-256 {detail.sha256}</p>
            {detail.exif&&<dl>{Object.entries(detail.exif).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>}
          </details>}
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
