import {useEffect,useRef,useState} from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {Expand,ExternalLink,Minus,Plus,RotateCcw,X} from 'lucide-react'
import {act} from '../bridge'
import type {GraphEntity} from '../types'
import {Button} from './ui'

interface MediaContext {canvas_id?:string;investigation_id?:string;entity_id:string}
interface MediaDetail {preview?:string;original_available?:boolean;width?:number;height?:number;mime?:string;bytes?:number;sha256?:string;exif?:Record<string,unknown>;original_reference?:string;name?:string;error?:string}
export function mediaThumbnail(value:unknown){const m=value as Record<string,unknown>|undefined;return typeof m?.thumbnail==='string'&&/^data:image\/(?:jpeg|png|webp);base64,/.test(m.thumbnail)?m.thumbnail:''}
export function NodeMedia({node,onOpen}:{node:GraphEntity;onOpen():void}){
  const value=node.attributes.media as Record<string,unknown>|undefined
  if(!value)return null
  const preview=mediaThumbnail(value)
  return <figure className="graph-node-media"><button className="media-preview-button" onClick={onOpen} aria-label={`Открыть изображение ${node.label}`}>{preview?<img src={preview} alt={node.label}/>:<span>{value.state==='loading'?'Загрузка…':value.state==='unavailable'?'Изображение недоступно':'Предпросмотр изображения'}</span>}<span><Expand size={14}/>Открыть</span></button><figcaption>{value.width&&value.height?`${value.width} × ${value.height}`:'Размеры не загружены'} · {value.kind==='local_attachment'?'Исходное вложение':'Публичный источник'}</figcaption></figure>
}
export function MediaViewer({node,context,onClose}:{node:GraphEntity|null;context:Omit<MediaContext,'entity_id'>;onClose():void}){
  const [detail,setDetail]=useState<MediaDetail>({}),[busy,setBusy]=useState(false),[zoom,setZoom]=useState(1)
  const generation=useRef(0),media=node?.attributes.media as Record<string,unknown>|undefined
  useEffect(()=>{
    const token=++generation.current;setDetail({});setZoom(1)
    if(!node)return
    setBusy(true)
    void act('canvas_media_view',{...context,entity_id:node.id}).then(result=>{if(generation.current===token)setDetail(result&&typeof result==='object'?result as MediaDetail:{error:'Не удалось открыть сохранённое изображение.'})}).catch(error=>{if(generation.current===token)setDetail({error:error instanceof Error?error.message:'Просмотр изображения недоступен.'})}).finally(()=>{if(generation.current===token)setBusy(false)})
    return()=>{generation.current++}
  },[node?.id,context.canvas_id,context.investigation_id])
  const preview=detail.preview&&/^data:image\/(?:jpeg|png|webp);base64,/.test(detail.preview)?detail.preview:mediaThumbnail(media)
  return <Dialog.Root open={!!node} onOpenChange={open=>{if(!open)onClose()}}><Dialog.Portal><Dialog.Overlay className="dialog-overlay media-viewer-overlay"/><Dialog.Content className="media-viewer" aria-describedby="media-viewer-description"><header><div><Dialog.Title>{detail.name||node?.label||'Изображение'}</Dialog.Title><Dialog.Description id="media-viewer-description">{String(detail.width||media?.width||'—')} × {String(detail.height||media?.height||'—')} · {String(detail.mime||media?.mime||'Изображение')}{detail.bytes?` · ${(detail.bytes/1024).toFixed(0)} КиБ`:''}</Dialog.Description></div><Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Закрыть изображение"><X size={18}/></Button></Dialog.Close></header><div className="media-viewer-toolbar"><Button variant="ghost" size="sm" aria-label="Уменьшить изображение" onClick={()=>setZoom(z=>Math.max(.25,z/1.25))}><Minus size={15}/></Button><span>{Math.round(zoom*100)}%</span><Button variant="ghost" size="sm" aria-label="Увеличить изображение" onClick={()=>setZoom(z=>Math.min(8,z*1.25))}><Plus size={15}/></Button><Button variant="ghost" size="sm" onClick={()=>setZoom(1)}><RotateCcw size={14}/>Вписать</Button><Button variant="secondary" size="sm" disabled={!detail.original_available||busy} onClick={()=>node&&void act('canvas_media_open',{...context,entity_id:node.id})}><ExternalLink size={14}/>Оригинал</Button>{busy&&<span role="status">Подготовка сохранённого изображения…</span>}</div><div className="media-viewer-stage">{preview?<img src={preview} alt={node?.label||'Сохранённое изображение'} style={{width:`${zoom*100}%`,maxWidth:zoom===1?'100%':'none',maxHeight:zoom===1?'100%':'none'}}/>:<p>{detail.error||'Предпросмотр недоступен'}</p>}</div><footer>{detail.error&&<p role="alert">{detail.error}</p>}<p className="monospace">{detail.original_reference||String(media?.source_url||media?.url||node?.attributes.attachment_id||'Сохранённое вложение')}</p>{detail.sha256&&<details><summary>Проверка целостности и метаданные</summary><p className="monospace">SHA-256 {detail.sha256}</p>{detail.exif&&<dl>{Object.entries(detail.exif).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>}</details>}</footer></Dialog.Content></Dialog.Portal></Dialog.Root>
}
