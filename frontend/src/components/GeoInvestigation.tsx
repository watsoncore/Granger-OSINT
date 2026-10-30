import { useEffect, useRef, useState } from 'react'
import * as L from 'leaflet'
import { ExternalLink, Image, Map as MapIcon, Network, ScanLine } from 'lucide-react'
import type { DesktopState, GeoCandidate, GeoImage, GeoView, Source } from '../types'
import { act } from '../bridge'
import { Button } from './ui'
import { SourceDialog, formatDate } from './Sources'
import 'leaflet/dist/leaflet.css'
import '../geoint.css'

const raster = (value?: string) => value && /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value) ? value : ''
const point = (latitude:unknown,longitude:unknown):latitude is number => typeof latitude==='number'&&typeof longitude==='number'&&Number.isFinite(latitude+longitude)&&Math.abs(latitude)<=85&&Math.abs(longitude)<=180
const statuses:Record<string,string>={model_candidate:'Кандидат модели',metadata_candidate:'Непроверенный EXIF',geographically_plausible:'Географически правдоподобно',visually_supported:'Есть визуальная поддержка',independently_corroborated:'Есть независимые подтверждения',contradicted:'Противоречит данным',exact_match_verified:'Совпадение проверено'}

function GeographicMap({view,state,onSelect,selected}:{view:GeoView;state:DesktopState;onSelect(id:string):void;selected:string}) {
  const container=useRef<HTMLDivElement>(null), map=useRef<L.Map|null>(null)
  const targets=useRef(new Map<string,Set<HTMLImageElement>>())
  const tiles=useRef(state.map_tiles);tiles.current=state.map_tiles
  const select=useRef(onSelect);select.current=onSelect
  useEffect(()=>{
    if(!container.current)return
    const instance=L.map(container.current,{zoomControl:true,attributionControl:true,scrollWheelZoom:false,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false,maxZoom:19})
    map.current=instance
    instance.attributionControl.setPrefix(false)
    instance.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors')
    class Layer extends L.GridLayer {
      createTile(coords:L.Coords,done:L.DoneCallback) {
        const tile=document.createElement('img'),key=`${coords.z}/${coords.x}/${coords.y}`
        tile.alt='Картографическая подложка OpenStreetMap';tile.width=tile.height=256
        const group=targets.current.get(key)||new Set<HTMLImageElement>();group.add(tile);targets.current.set(key,group)
        const cached=tiles.current?.[key]
        if(cached?.state==='ready'&&raster(cached.image)){tile.src=cached.image!;queueMicrotask(()=>done(undefined,tile))}
        else {tile.dataset.tileKey=key;tile.onload=()=>done(undefined,tile);void act('geoint_tile_get',{z:coords.z,x:coords.x,y:coords.y})}
        return tile
      }
    }
    const layer=new Layer({tileSize:256,keepBuffer:0,updateWhenIdle:true,minZoom:0,maxZoom:19,noWrap:true})
    layer.on('tileunload',(event:L.TileEvent)=>{const tile=event.tile as HTMLImageElement;if(tile.dataset.tileKey){targets.current.get(tile.dataset.tileKey)?.delete(tile)}})
    layer.addTo(instance)
    if(!(view.candidates||[]).some(candidate=>point(candidate.latitude,candidate.longitude)))instance.setView([20,0],2)
    const resize=new ResizeObserver(()=>instance.invalidateSize({animate:false}));resize.observe(container.current)
    return ()=>{resize.disconnect();instance.remove();map.current=null;targets.current.clear();void act('geoint_tiles_cancel',{})}
  },[])
  useEffect(()=>{
    for(const [key,images] of targets.current){const tile=state.map_tiles?.[key];if(!tile)continue
      for(const image of images)if(tile.state==='ready'&&raster(tile.image)&&image.getAttribute('src')!==tile.image)image.src=tile.image!
      else if(tile.state==='unavailable')image.classList.add('geo-tile-unavailable')
    }
  },[state.map_tiles])
  useEffect(()=>{
    const instance=map.current;if(!instance)return
    const layers=L.featureGroup().addTo(instance),coordinates:L.LatLngTuple[]=[]
    for(const candidate of view.candidates||[]){if(!point(candidate.latitude,candidate.longitude))continue
      const position:L.LatLngTuple=[candidate.latitude,candidate.longitude];coordinates.push(position)
      const label=document.createElement('span');label.textContent=`${candidate.region||'Кандидат'} · ${statuses[candidate.verification_status]||'Гипотеза'}`
      L.circleMarker(position,{radius:9,color:'#638fc8',fillColor:'#638fc8',weight:2,fillOpacity:.65}).bindTooltip(label).on('click',()=>select.current(candidate.candidate_id)).addTo(layers)
      for(const observation of candidate.model_observations||[]){const lat=observation.model_lat_std,lon=observation.model_lon_std
        if(typeof lat==='number'&&typeof lon==='number'&&lat>0&&lon>0&&lat<20&&lon<40&&!observation.dateline_warning&&Math.abs(observation.longitude)+lon<180){
          const label=document.createElement('span');label.textContent='Разброс сэмплов модели, не интервал точности'
          L.rectangle([[Math.max(-85,observation.latitude-lat),observation.longitude-lon],[Math.min(85,observation.latitude+lat),observation.longitude+lon]],{color:'#638fc8',weight:1,dashArray:'5 5',fillOpacity:.06}).bindTooltip(label).addTo(layers)
        }
      }
    }
    for(const image of view.images||[]){if(!point(image.latitude,image.longitude))continue
      coordinates.push([image.latitude,image.longitude!])
      const label=document.createElement('span');label.textContent=`Эталон: ${image.provider||''} · ${image.title}`
      L.circleMarker([image.latitude,image.longitude!],{radius:5,color:'#5a9c88',fillOpacity:.8}).bindTooltip(label).addTo(layers)
    }
    if(coordinates.length)instance.fitBounds(L.latLngBounds(coordinates).pad(.25),{maxZoom:16,animate:false})
    return ()=>{layers.remove()}
  },[view.candidates,view.images])
  useEffect(()=>{const candidate=view.candidates?.find(item=>item.candidate_id===selected),instance=map.current;if(instance&&candidate&&point(candidate.latitude,candidate.longitude))instance.setView([candidate.latitude,candidate.longitude],Math.max(14,instance.getZoom()),{animate:false})},[selected,view.candidates])
  return <div className="geo-map-wrap"><div className="geo-map" ref={container} aria-label="Географическая карта с подложкой OpenStreetMap"/><p>Синие маркеры — гипотезы, зелёные — точки съёмки эталонов. Области показывают разброс сэмплов, если он предоставлен моделью; это не точность адреса.</p>{Object.values(state.map_tiles||{}).some(tile=>tile.state==='unavailable')&&<p className="notice-inline">Часть картографической подложки недоступна. Координаты и доказательства сохранены.</p>}</div>
}

function MatchingOverlay({image,side}:{image:GeoImage;side:0|1}) {
  const comparison=image.comparison,size=comparison?.input_sizes?.[side]
  if(!size?.length||!comparison?.matches?.length)return null
  const inliers=new Set(comparison.geometry?.inlier_indices||[])
  return <svg className="geo-match-overlay" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="xMidYMid meet" aria-label="Модельные совпадения деталей">{comparison.matches.slice(0,150).map((match,index)=>{const point=side===0?match.point0:match.point1;return point?.length===2?<circle key={index} cx={point[0]} cy={point[1]} r={Math.max(3,size[0]/180)} fill={inliers.has(index)?'#69c5a1':'#bbb'} fillOpacity=".7" stroke="#17262a" strokeWidth="1"/>:null})}</svg>
}

export function GeoInvestigation({state,id,initialMode='photos',onGraph}:{state:DesktopState;id:string;initialMode?:'photos'|'map';onGraph?():void}) {
  const [mode,setMode]=useState<'photos'|'map'|'compare'>(initialMode),[selected,setSelected]=useState(''),[compare,setCompare]=useState(''),[matches,setMatches]=useState(false),[source,setSource]=useState<Source|null>(null)
  const view=state.geo_views?.[id]
  const revision=state.investigation.id===id?state.investigation.checkpoint_revision:undefined
  useEffect(()=>{const timer=setTimeout(()=>void act('geoint_view_get',{id}),view?500:0);return ()=>clearTimeout(timer)},[id,revision])
  const openEvidence=async(evidence_id:string)=>{const value=await act('source_open',{evidence_id});if(value&&typeof value==='object'&&'evidence_id'in value)setSource(value as Source)}
  if(state.vault?.enabled&&!state.vault.unlocked)return null
  if(!view||view.state==='loading'&&!view.has_geoint)return <section className="geoint-view"><p>Подготавливаю фотографии и географические наблюдения…</p></section>
  if(view.state==='unavailable')return <section className="geoint-view"><p>{view.error}</p></section>
  if(!view.has_geoint)return null
  const images=(view.images||[]).filter(image=>!selected||image.candidate_id===selected)
  const compared=(view.images||[]).find(image=>image.evidence_id===compare)
  const attachment=compared?.attachment_id||view.candidates?.find(candidate=>candidate.candidate_id===selected)?.attachment_id
  const original=view.originals?.find(item=>item.state==='ready'&&(!attachment||item.attachment_id===attachment))
  const graph=()=>{if(onGraph)onGraph();else {void act('route',{route:'search'});void act('investigation_graph_get',{id,mode:'graph'})}}
  return <section className="geoint-view" aria-label="Фотографии и географические гипотезы"><header><div><h3>Фотография и географические гипотезы</h3><p>Проверяемые наблюдения одного расследования</p></div><div className="geo-view-tabs"><Button variant={mode==='photos'?'secondary':'ghost'} size="sm" onClick={()=>setMode('photos')}><Image size={14}/>Фото</Button><Button variant={mode==='map'?'secondary':'ghost'} size="sm" onClick={()=>setMode('map')}><MapIcon size={14}/>Карта</Button><Button variant="ghost" size="sm" onClick={graph}><Network size={14}/>В граф</Button></div></header>
    <div className="geo-candidates"><button className={!selected?'is-selected':''} onClick={()=>setSelected('')}>Все кандидаты</button>{view.candidates?.map((candidate:GeoCandidate,index)=><button className={selected===candidate.candidate_id?'is-selected':''} key={candidate.candidate_id} onClick={()=>setSelected(candidate.candidate_id)}><strong>{index+1}. {candidate.region||'Географический кандидат'}</strong><span>{candidate.latitude.toFixed(5)}, {candidate.longitude.toFixed(5)}</span><small>{statuses[candidate.verification_status]||'Непроверенная гипотеза'}</small></button>)}</div>
    {mode==='map'?<GeographicMap view={view} state={state} selected={selected} onSelect={setSelected}/>:mode==='compare'&&compared?<><div className="geo-compare-toolbar"><Button variant="ghost" size="sm" onClick={()=>setMode('photos')}>К фотографиям</Button><Button variant={matches?'secondary':'ghost'} size="sm" onClick={()=>setMatches(value=>!value)}><ScanLine size={14}/>Совпадения деталей</Button></div><div className="geo-comparison"><figure><div className="geo-image-frame">{raster(original?.thumbnail)?<img src={original!.thumbnail} alt="Исходная фотография пользователя"/>:<p>Исходный снимок недоступен</p>}{matches&&<MatchingOverlay image={compared} side={0}/>}</div><figcaption>Исходная фотография</figcaption></figure><figure><div className="geo-image-frame">{raster(compared.media?.thumbnail)?<img src={compared.media!.thumbnail} alt={compared.title}/>:<p>Эталон недоступен</p>}{matches&&<MatchingOverlay image={compared} side={1}/>}</div><figcaption>Эталон · {compared.provider} · {compared.title}</figcaption></figure></div><p>{compared.comparison?.interpretation||'Геометрическое сопоставление этого снимка не выполнено.'}</p>{compared.comparison?.match_count!==undefined&&<p>Совпадений: {compared.comparison.match_count}; геометрически согласованных: {compared.comparison.geometry?.inliers??'неизвестно'}. Это не вероятность совпадения локации.</p>}<Button variant="ghost" size="sm" onClick={()=>void openEvidence(compared.evidence_id)}>Открыть доказательство сравнения</Button></>:<><div className="geo-original">{raster(original?.thumbnail)&&<img src={original!.thumbnail} alt="Исходная фотография пользователя"/>}<div><h4>Что видно на исходном снимке</h4>{view.scenes?.length?view.scenes.map(scene=><div key={scene.evidence_id}><p>{scene.description}</p><small>Локальная vision-модель; описание может содержать ошибки.</small><button className="geo-source-button" onClick={()=>void openEvidence(scene.evidence_id)}>Доказательство описания</button></div>):<p>Семантическое описание не получено; по одним metadata содержимое кадра не установлено.</p>}</div></div><h4>Реальные сравнительные фотографии</h4>{!images.length?<p>Доступные сравнительные снимки не найдены. Координатные гипотезы сохранены без заявления о точном месте.</p>:<div className="geo-gallery">{images.map(image=><figure key={image.evidence_id}><div className="geo-reference-frame">{raster(image.media?.thumbnail)?<img src={image.media!.thumbnail} alt={image.title} loading="lazy"/>:<p>Ссылка архива получена, доступное изображение не загружено.</p>}</div><figcaption><strong>{image.title}</strong><span>{image.provider} · {image.captured_at?formatDate(image.captured_at):'дата не указана'}</span><span>{image.author||'Автор не указан'} · {image.license||'Лицензия не указана'}</span>{image.reference_scene?.description&&<p>{image.reference_scene.description}</p>}<small>Снимок предполагаемой местности; исходная точка съёмки не подтверждена.</small><div><Button variant="secondary" size="sm" disabled={!raster(image.media?.thumbnail)||!original?.thumbnail} onClick={()=>{setCompare(image.evidence_id);setMode('compare')}}>Сравнить с исходным</Button><Button variant="ghost" size="sm" onClick={()=>void openEvidence(image.evidence_id)}>Доказательство</Button><Button variant="ghost" size="sm" onClick={()=>void act('open_url',{url:image.source_url})}><ExternalLink size={13}/>Источник</Button></div></figcaption></figure>)}</div>}</>}
    <details className="geo-limitations"><summary>Покрытие и ограничения исследования</summary>{view.limitations?.map((text,index)=><p key={index}>{text}</p>)}{view.diagnostics?.flatMap(item=>item.stages||[]).filter(stage=>stage.status!=='complete').map((stage,index)=><p key={index}>{stage.stage}: {stage.error_code||stage.status}</p>)}</details><SourceDialog source={source} onClose={()=>setSource(null)}/>
  </section>
}
