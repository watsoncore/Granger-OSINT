import type {GraphEntity} from '../types'
import type {CryptoCapability} from './GansarFields'
import {Button} from './ui'

export const userActions:Record<string,{label:string;hint:string}>={
 username_maigret:{label:'Найти публичные профили',hint:'Maigret · совпадение имени не устанавливает общего владельца'},
 email_research:{label:'Исследовать email',hint:'DNS домена, индекс публичного email GitHub и точные публичные упоминания'},
 company_research:{label:'Исследовать компанию',hint:'Реестры и независимые кандидаты с учётом юрисдикции'},
 blockchain_gansar:{label:'Исследовать криптообъект',hint:'Профиль, переводы, активы и NFT в поддерживаемой сети'},
 domain_lookup:{label:'Проверить домен',hint:'DNS и публичные регистрационные сведения'},
 network_rdap:{label:'Проверить сетевую регистрацию',hint:'IP, сеть, ASN и ответственный регистратор'},
 network_geoip:{label:'Оценить географию IP',hint:'Местоположение сети по источнику; не координаты человека'},
 telegram_public:{label:'Изучить публичный Telegram',hint:'Доступные сведения канала или профиля без сессии'},
 vk_public:{label:'Изучить публичный VK',hint:'Разрешённые сведения страницы и публикаций'},
 tiktok_public_profile:{label:'Изучить публичный TikTok',hint:'Документированный oEmbed и доступные метаданные'},
 github_profile:{label:'Изучить GitHub-профиль',hint:'Официальный API · профиль, публичные репозитории, организации, языки и релизы'},
 visual_geoint:{label:'Исследовать место съёмки',hint:'Метаданные, визуальные гипотезы и проверка независимыми источниками'},
 web_read:{label:'Прочитать публичную страницу',hint:'Текст и метаданные источника с сохранением происхождения'},
 phone_metadata:{label:'Проверить формат телефона',hint:'Код страны и метаданные нумерации; не поиск владельца'},
 publication_crossref:{label:'Найти публикации',hint:'Библиографические записи Crossref'},
}

export function EntityActions({node,capability,disabled,onChoose}:{node:GraphEntity;capability:CryptoCapability;disabled?:boolean;onChoose(id:string):void}){
 const compatible=capability.tools?.filter(row=>row.compatible)||[]
 const names=node.type==='username'||node.type==='nickname'?['username_maigret']:Object.keys(userActions)
 const rows=names.flatMap(id=>{const match=compatible.find(row=>row.id===id);return match?[match]:[]})
 return <div className="entity-actions" aria-label="Исследовать выбранный объект">{rows.map(row=><Button key={row.id} aria-label={userActions[row.id].label} variant="secondary" disabled={disabled||row.available===false} title={row.reason} onClick={()=>onChoose(row.id)}><strong>{userActions[row.id].label}</strong><small>{row.available===false?row.reason:userActions[row.id].hint}</small></Button>)}
  {!rows.length&&<p className="field-hint">Для этого типа доступны отдельные инструменты в расширенном выборе ниже.</p>}</div>
}
