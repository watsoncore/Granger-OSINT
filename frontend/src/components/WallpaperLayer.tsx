import { useEffect, useRef, useState, type CSSProperties, type Ref } from 'react'
import { request } from '../bridge'
import type { Wallpaper } from '../appearance'

const backgrounds: Partial<Record<Wallpaper['source'],string>> = {
  graphite:'radial-gradient(ellipse at 22% 4%, #252f3a 0%, #151b24 48%, #0a0e14 100%)',
  mist:'radial-gradient(ellipse at 30% 15%, #1c4864, #142535 44%, #0a121e 85%)',
  smoke:'radial-gradient(ellipse at 74% 16%, #5a2834, #261822 45%, #0d1017 87%)',
  depth:'radial-gradient(ellipse at 45% 14%, #3d305c, #211e37 47%, #10101a 85%)',
  black:'#08090a',
  grid:'radial-gradient(circle, #7790a53b 1px, transparent 1.2px) 0 0 / 22px 22px, #10151c',
}
type Asset = {url:string; width:number; height:number; sourceWidth:number; sourceHeight:number; original?:boolean}
let previewQueue:Promise<unknown>=Promise.resolve()
export function waitForWallpaperPreview(){return previewQueue}

export function WallpaperLayer({wallpaper,worldRef,preview=false,allowImage=true,onError}:{
  wallpaper:Wallpaper; worldRef?:Ref<HTMLDivElement>; preview?:boolean; allowImage?:boolean; onError?(message:string):void
}) {
  const identifier=allowImage&&wallpaper.source==='image'?wallpaper.image:''
  const layer=useRef<HTMLDivElement>(null)
  const [viewport,setViewport]=useState({width:0,height:0})
  const [asset,setAsset]=useState<{id:string;key:string;asset:Asset}>()
  const requestKey=[identifier,wallpaper.quality,wallpaper.fit,wallpaper.blur,viewport.width,viewport.height].join('|')
  const errorHandler=useRef(onError);errorHandler.current=onError
  useEffect(()=>{
    const element=layer.current
    if(!element)return
    const measure=()=>{
      const bounds=element.getBoundingClientRect(),dpr=window.devicePixelRatio||1
      if(bounds.width<1||bounds.height<1){
        setViewport(previous=>previous.width||previous.height?{width:0,height:0}:previous)
        return
      }
      const width=Math.min(16384,Math.max(64,Math.ceil(bounds.width*dpr*wallpaper.scale/100/64)*64))
      const height=Math.min(16384,Math.max(64,Math.ceil(bounds.height*dpr*wallpaper.scale/100/64)*64))
      setViewport(previous=>previous.width===width&&previous.height===height?previous:{width,height})
    }
    measure()
    const observer=new ResizeObserver(measure)
    observer.observe(element)
    window.addEventListener('resize',measure)
    return()=>{observer.disconnect();window.removeEventListener('resize',measure)}
  },[wallpaper.source,wallpaper.scale])
  useEffect(()=>{
    if(!identifier){setAsset(undefined);return}
    if(!viewport.width||!viewport.height)return
    let current=true
    const timer=setTimeout(()=>{
      previewQueue=previewQueue.then(()=>current?request('wallpaper_preview',{
        id:identifier,blur:wallpaper.blur,quality:wallpaper.quality||'auto',
        fit:wallpaper.fit,...viewport,
      }):undefined).then(value=>{
        if(!current||!value||typeof value!=='object')return
        const result=value as Asset
        if(typeof result.url!=='string'||result.url.length>28_000_000||!/^data:image\/(?:png|jpeg|webp);base64,[a-zA-Z0-9+/=]+$/.test(result.url))
          throw new Error('Обои не удалось подготовить в выбранном качестве.')
        setAsset({id:identifier,key:requestKey,asset:result})
        errorHandler.current?.('')
      }).catch(error=>{
        if(current){setAsset(undefined);errorHandler.current?.(error instanceof Error?error.message:'Обои недоступны.')}
      })
    },preview?180:120)
    return()=>{current=false;clearTimeout(timer)}
  },[identifier,wallpaper.blur,wallpaper.quality,wallpaper.fit,viewport,preview,requestKey])
  if(wallpaper.source==='theme')return null
  const image=asset?.id===identifier?asset.asset:undefined
  const position=`${wallpaper.x}% ${wallpaper.y}%`
  const natural=image?`${image.sourceWidth}px ${image.sourceHeight}px`:'auto'
  const size=wallpaper.fit==='stretch'?'100% 100%':['tile','center','original'].includes(wallpaper.fit)?natural:wallpaper.fit
  const background:CSSProperties=wallpaper.source==='image'?{
    backgroundImage:image?`url("${image.url}")`:undefined,backgroundSize:size,backgroundPosition:position,
    backgroundRepeat:wallpaper.fit==='tile'?'repeat':'no-repeat',opacity:wallpaper.opacity/100,imageOrientation:'from-image',
    transform:`scale(${wallpaper.scale/100})`,transformOrigin:position,
  }: {background:wallpaper.source==='solid'?wallpaper.color:wallpaper.source==='gradient'
    ?`linear-gradient(135deg,${wallpaper.color},${wallpaper.end})`:backgrounds[wallpaper.source],opacity:wallpaper.opacity/100}
  return <div ref={layer} className="wallpaper-layer" aria-hidden="true" data-wallpaper={wallpaper.source} data-loaded={!!image}
    data-current={asset?.key===requestKey} data-quality={wallpaper.quality} data-original={image?.original}
    data-render-width={image?.width} data-render-height={image?.height}
    data-source-width={image?.sourceWidth} data-source-height={image?.sourceHeight}>
    <div className="wallpaper-camera" ref={wallpaper.anchor==='world'&&!preview?worldRef:undefined}>
      <div className="wallpaper-art" style={background}/>
    </div>
    {wallpaper.source==='image'&&image&&<div className="wallpaper-dim" style={{opacity:wallpaper.dim/100}}/>}
  </div>
}
