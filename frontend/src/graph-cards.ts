import type {GraphEntity} from './types'

export type CardMode='auto'|'compact'|'standard'|'expanded'
export type CardVariant='identity'|'social'|'organization'|'domain'|'ip'|'wallet'|'transaction'|'contract'|'media'|'geo'|'document'|'note'|'hypothesis'|'evidence'|'group'|'custom'
export interface CardSize {width:number;height:number}
export const cardVariants:Record<string,{label:string;symbol:string}>={identity:{label:'Личность',symbol:'◎'},social:{label:'Профиль',symbol:'@'},organization:{label:'Организация',symbol:'▥'},domain:{label:'Домен',symbol:'⊕'},ip:{label:'Инфраструктура',symbol:'⌘'},wallet:{label:'Кошелёк',symbol:'◈'},transaction:{label:'Транзакция',symbol:'⇄'},contract:{label:'Контракт',symbol:'◇'},media:{label:'Изображение',symbol:'▧'},geo:{label:'География',symbol:'⌖'},document:{label:'Документ',symbol:'▤'},note:{label:'Заметка',symbol:'✎'},hypothesis:{label:'Гипотеза',symbol:'?'},evidence:{label:'Источник',symbol:'↗'},group:{label:'Группа',symbol:'⊞'},custom:{label:'Объект',symbol:'◆'}}
export function cardVariant(node:GraphEntity):CardVariant {
  const type=String(node.attributes.display_type||node.type)
  if(node.type==='image'||node.attributes.original_image===true||type==='inventory_item')return 'media'
  if(node.type==='person'||type==='identity')return 'identity'
  if(/profile|telegram_channel|username/.test(type))return 'social'
  if(/organization|registry_maintainer|registry_registry_authority/.test(type))return 'organization'
  if(node.type==='blockchain_address')return 'wallet'
  if(node.type==='transaction')return 'transaction'
  if(/contract|nft|token|collection/.test(type))return 'contract'
  if(node.type==='entity_group'||/inventory_category|steam_inventory/.test(type))return 'group'
  if(/coordinate|geographic|geoip/.test(type))return 'geo'
  if(/domain|website/.test(type))return 'domain'
  if(node.type==='infrastructure_asset')return 'ip'
  if(node.type==='analyst_note')return 'note'
  if(node.type==='hypothesis')return 'hypothesis'
  if(node.type==='source')return 'evidence'
  if(/document|post|repository/.test(type))return 'document'
  return 'custom'
}
export function cardSize(node:GraphEntity):CardSize {
  const variant=cardVariant(node),custom=node.attributes._card_size as Partial<CardSize>|undefined
  if(custom&&Number.isFinite(custom.width)&&Number.isFinite(custom.height))return {width:Math.max(160,Math.min(720,Number(custom.width))),height:Math.max(72,Math.min(640,Number(custom.height)))}
  const mode=node.attributes._card_mode as CardMode|undefined
  if(variant==='media'){
    const media=node.attributes.media as Record<string,unknown>|undefined,w=Number(media?.width)||4,h=Number(media?.height)||3
    return {width:288,height:Math.max(172,Math.min(310,248*h/w+62))}
  }
  if(mode==='compact')return {width:216,height:72}
  const root=node.attributes.is_root===true
  return {width:root?274:variant==='note'||variant==='document'?252:240,height:mode==='expanded'?166:root?130:variant==='wallet'||variant==='transaction'?114:variant==='note'?138:100}
}
export function withCardPresentation(nodes:GraphEntity[],sizes:Record<string,CardSize>={},mode:CardMode='auto'):GraphEntity[] {
  return nodes.map(node=>({...node,attributes:{...node.attributes,_card_size:sizes[node.id],_card_mode:mode}}))
}
export function cardTitle(node:GraphEntity){
  const labels=node.attributes.labels
  if(node.type==='blockchain_address'&&Array.isArray(labels)&&typeof labels[0]==='string')return labels[0]
  return node.label||String(node.attributes.name||node.attributes.address||'Без названия')
}
const text=(value:unknown)=>value===undefined||value===null?'':Array.isArray(value)?value.map(String).join(' · '):typeof value==='object'?Object.entries(value as Record<string,unknown>).map(([k,v])=>`${k}: ${String(v)}`).join(' · '):String(value)
export function cardRows(node:GraphEntity):string[]{
  const a=node.attributes,variant=cardVariant(node)
  if(variant==='wallet'){
    const rows=[text(a.address||a.canonical_address||node.label),`${a.transaction_count??'—'} операций · ${a.counterparty_count??'—'} контрагентов`]
    if(Array.isArray(a.flow_summaries)){const flow=a.flow_summaries[0] as {direction:string;amount:string|null;asset:string}|undefined;if(flow)rows.push(`${flow.direction==='to_target'?'Получено':'Отправлено'} ${flow.amount??'?'} ${flow.asset}`)}
    return rows
  }
  if(variant==='transaction')return [text(a.amount?`${a.amount} ${a.asset||''}`:a.tx_hash||a.hash),text(a.timestamp||a.status||a.chain)]
  if(variant==='note')return [text(a.markdown||a.description).replace(/[#*_`>]/g,'').replace(/\s+/g,' ')]
  if(variant==='hypothesis')return ['Требует независимой проверки',text(a.markdown||a.description)]
  if(variant==='geo')return [a.latitude!=null&&a.longitude!=null?`${a.latitude}, ${a.longitude}`:text(a.region||a.description),a.reference_photo?'Эталон для проверки':a.scope_only?'Область исследования':'Координаты требуют проверки']
  if(variant==='group')return [`${a.member_count??'—'} объектов`,text(a.category||a.description)||'Двойной клик — раскрыть']
  if(variant==='media'){const m=a.media as Record<string,unknown>|undefined;return [m?.width&&m.height?`${m.width} × ${m.height}`:text(a.description),text(m?.kind==='local_attachment'?'Исходное вложение':m?.source_url||m?.url)]}
  if(variant==='ip')return [text(a.value||a.address||a.cidr||a.asn),text(a.organization||a.country||a.network_name)]
  if(variant==='social')return [text(a.username?`@${a.username}`:a.url),text(a.platform||a.description)]
  if(variant==='domain')return [text(a.url||a.domain),text(a.registrar||a.description)]
  if(variant==='contract')return [text(a.address||a.contract||a.contract_address),text(a.symbol||a.standard||a.chain)]
  return [text(a.description||a.url||a.value||a.scene_description),text(a.organization||a.published_at)]
}
export function cardBadge(node:GraphEntity){
  const variant=cardVariant(node)
  if(variant==='wallet'||variant==='transaction'||variant==='contract')return String(node.attributes.chain||'Сеть не указана').toUpperCase()
  if(variant==='social')return String(node.attributes.platform||node.attributes.display_type||'Публичный профиль').replace(/_/g,' ')
  return cardVariants[variant].label
}
