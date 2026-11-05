import {request} from './bridge'
import type {GraphEntity} from './types'

export interface MediaContext {canvas_id?:string;investigation_id?:string}
export interface MediaReference {
  id:string; kind?:string; name?:string; width?:number; height?:number; bytes?:number
  mime?:string; thumbnail?:string; state?:string; source_url?:string; url?:string; evidence_id?:string
}
export interface PreparedImage {id:string;width?:number;height?:number;provenance?:Record<string,string>}
export type ImageInput = {mode:'picker'|'clipboard'} | {mode:'path';path:string}
  | {mode:'url';url:string} | {mode:'evidence';entity_id:string;canvas_id:string}
  | {mode:'native_drop';token:string}
  | {mode:'file';file:File}

export function linkedMedia(node:GraphEntity):MediaReference[] {
  const images=node.attributes.image_attachments
  return Array.isArray(images)?images.filter((value):value is MediaReference=>!!value&&typeof value==='object'&&typeof value.id==='string'):[]
}

export function visualMedia(node:GraphEntity):MediaReference|undefined {
  const legacy=node.attributes.media as MediaReference|undefined
  return linkedMedia(node)[0]||legacy
}

export function imageData(value:unknown):string {
  return typeof value==='string'&&/^data:image\/(?:jpeg|png|webp);base64,/.test(value)?value:''
}

export function mediaThumbnail(value:unknown):string {
  return imageData((value as MediaReference|undefined)?.thumbnail)
}

export async function prepareImage(input:ImageInput):Promise<PreparedImage|null> {
  let payload:Record<string,unknown>=input
  if(input.mode==='file'){
    if(input.file.size>20*1024*1024)throw new Error('Изображение превышает ограничение 20 МиБ.')
    const data=await new Promise<string>((resolve,reject)=>{
      const reader=new FileReader()
      reader.onload=()=>resolve(String(reader.result).split(',',2)[1]||'')
      reader.onerror=()=>reject(new Error('Не удалось прочитать файл изображения.'))
      reader.readAsDataURL(input.file)
    })
    payload={mode:'bytes',name:input.file.name,data}
  }
  return await request('research_canvas_media_prepare',payload) as PreparedImage|null
}

export function mediaPayload(context:MediaContext,node:GraphEntity,media?:MediaReference) {
  return {...context,entity_id:node.id,...(media?.kind==='local_attachment'?{attachment_id:media.id}:{})}
}

export async function loadThumbnail(context:MediaContext,node:GraphEntity,media:MediaReference) {
  if(mediaThumbnail(media))return mediaThumbnail(media)
  if(media.kind!=='local_attachment')return ''
  const result=await request('canvas_media_thumbnail',mediaPayload(context,node,media)) as {preview?:string}|null
  return imageData(result?.preview)
}
