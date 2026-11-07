import {useSyncExternalStore} from 'react'
import {CircleHelp,Wallet,Coins,Network,Gift,FileBadge,ServerCog,Send,Building2} from 'lucide-react'
import {request} from './bridge'
import type {GraphEntity} from './types'

const networks:Record<string,string>={btc:'btc',bitcoin:'btc',eth:'eth',ethereum:'eth',ton:'ton',doge:'doge',dogecoin:'doge',sol:'solana',solana:'solana',trx:'tron',tron:'tron'}
const services=new Set(['cryptobot','bybit','xrocket']),wallets=new Set(['openmask','tonkeeper'])
const normalized=(value:unknown)=>typeof value==='string'?value.trim().toLowerCase():''
export function networkIcon(chain:unknown){const id=networks[normalized(chain)];return id?'network:'+id:''}
/** Only explicit typed fields identify networks/services. Labels never imply attribution. */
export function entityCryptoIcon(node:Pick<GraphEntity,'type'|'attributes'>):string {
  const a=node.attributes
  const kind=normalized(a.display_type||node.type)
  if(['wallet_application','wallet_app'].includes(kind)&&wallets.has(normalized(a.wallet_application)))return 'wallet:'+normalized(a.wallet_application)
  if(['service','platform_service','exchange'].includes(kind)&&services.has(normalized(a.service_id)))return 'service:'+normalized(a.service_id)
  if(['token','asset','transaction','nft','contract','blockchain_address','collection'].includes(node.type)||/nft|token/.test(node.type)){
    if(normalized(a.asset_symbol||a.symbol||a.asset)==='usdt')return 'asset:usdt'
    return networkIcon(a.chain||a.network)||'generic:wallet'
  }
  if(normalized(a.platform)==='telegram')return 'platform:telegram'
  return ''
}
type IconData={url:string;sha256:string;local_only:boolean;raster_pixels?:number|null;monochrome?:boolean;opaque_canvas?:boolean}
let data:Record<string,IconData>={},version=0,loading:Promise<void>|undefined
const listeners=new Set<()=>void>(),images=new Map<string,HTMLImageElement>()
const tinted=new Map<string,HTMLCanvasElement>()
export function subscribeCryptoIcons(callback:()=>void){listeners.add(callback);return()=>{listeners.delete(callback)}}
function changed(){version++;for(const callback of listeners)callback()}
export function loadCryptoIcons(){
  return loading??=request('crypto_icons').then(result=>{
    data=(result as {icons:Record<string,IconData>}).icons||{}
    tinted.clear()
    for(const [key,icon]of Object.entries(data)){
      if(!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(icon.url))continue
      const picture=new Image();picture.onload=changed;picture.onerror=()=>{images.delete(key);changed()};picture.src=icon.url;images.set(key,picture)
    }
    changed()
  }).catch(()=>{loading=undefined})
}
export function CryptoIcon({id,size=20}:{id:string;size?:number}){
  useSyncExternalStore(subscribeCryptoIcons,()=>version)
  const icon=usable(id,size)?data[id]:undefined
  const Fallback=id.startsWith('network:')?Network:id.startsWith('wallet:')||id==='generic:wallet'?Wallet:id.startsWith('service:')?Building2:id.startsWith('asset:')?Coins:id==='generic:gift'?Gift:id==='generic:document'?FileBadge:id==='generic:infrastructure'?ServerCog:id==='platform:telegram'?Send:CircleHelp
  return icon?icon.monochrome?<span className="crypto-icon crypto-icon-mask" aria-hidden="true" data-crypto-icon={id}
    style={{width:size,height:size,maskImage:`url(${icon.url})`,WebkitMaskImage:`url(${icon.url})`}}/>
    :<img className="crypto-icon" src={icon.url} width={size} height={size} alt="" data-crypto-icon={id} draggable={false}/>:<Fallback aria-hidden="true" size={size} data-crypto-fallback={id}/>
}
function usable(id:string,size:number){const pixels=data[id]?.raster_pixels;return !data[id]?.opaque_canvas&&(!pixels||pixels>=size*(window.devicePixelRatio||1)*.875)}
export function drawCryptoIcon(ctx:CanvasRenderingContext2D,id:string,x:number,y:number,size:number,ink='#d7dce4'){
  const picture=images.get(id)
  if(!picture?.complete||!picture.naturalWidth||!usable(id,size))return false
  let image:HTMLImageElement|HTMLCanvasElement=picture
  if(data[id]?.monochrome){
    const key=id+'|'+ink
    let mask=tinted.get(key)
    if(!mask){
      mask=document.createElement('canvas');mask.width=picture.naturalWidth;mask.height=picture.naturalHeight
      const paint=mask.getContext('2d');if(!paint)return false
      paint.drawImage(picture,0,0);paint.globalCompositeOperation='source-in';paint.fillStyle=ink;paint.fillRect(0,0,mask.width,mask.height)
      if(tinted.size>=64)tinted.delete(tinted.keys().next().value!)
      tinted.set(key,mask)
    }
    image=mask
  }
  ctx.drawImage(image,x,y,size,size)
  return true
}
