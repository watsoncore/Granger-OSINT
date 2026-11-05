import {useState} from 'react'
import {Plus} from 'lucide-react'
import {SearchableSelect} from './SearchableSelect'
import {Button} from './ui'
import {cryptoChains,useCryptoTarget} from './GansarFields'

export interface CompanyJurisdiction {id:string;label:string;identifiers:Record<string,string>}
const fields:Record<string,{label:string;placeholder:string;help?:string}>={
  person:{label:'Имя или подпись',placeholder:'Как обозначить человека'},
  username:{label:'Никнейм',placeholder:'Введите никнейм',help:'Совпадение никнейма не доказывает общего владельца.'},
  email:{label:'Email',placeholder:'name@example.com'},
  phone:{label:'Телефон',placeholder:'+7 700 123 45 67'},
  infrastructure_asset:{label:'IP-адрес',placeholder:'IPv4 или IPv6'},
  domain:{label:'Домен',placeholder:'example.org'},website:{label:'URL',placeholder:'https://example.org/page'},
  public_profile:{label:'Ссылка на профиль',placeholder:'https://github.com/username'},
  social_profile:{label:'Ссылка на профиль',placeholder:'https://…'},
  blockchain_address:{label:'Адрес кошелька',placeholder:'Адрес в выбранной сети'},
  transaction:{label:'Хеш транзакции',placeholder:'Полный хеш из публичного источника'},
  contract:{label:'Адрес контракта',placeholder:'Адрес в выбранной сети'},
  nft:{label:'Адрес NFT',placeholder:'Публичный адрес NFT'},token:{label:'Адрес токена',placeholder:'Адрес контракта токена'},
  collection:{label:'Адрес коллекции',placeholder:'Публичный адрес коллекции'},
  document:{label:'Ссылка или название документа',placeholder:'https://… или название'},
  coordinate:{label:'Координаты',placeholder:'43.2389, 76.8897'},
  analyst_note:{label:'Название заметки',placeholder:'Краткая тема'},
  hypothesis:{label:'Гипотеза',placeholder:'Какое предположение нужно проверить'},
  custom_entity:{label:'Название объекта',placeholder:'Понятное вам обозначение'},
}
const names:Record<string,string>={person:'Человек',organization:'Компания / организация',username:'Никнейм',email:'Email',phone:'Телефон',
  infrastructure_asset:'IP-адрес',domain:'Домен',website:'URL',public_profile:'Профиль',blockchain_address:'Криптокошелёк',
  transaction:'Транзакция',nft:'NFT',token:'Токен',contract:'Контракт',collection:'Коллекция',document:'Документ',
  coordinate:'Географическая точка',analyst_note:'Заметка',hypothesis:'Гипотеза',custom_entity:'Произвольный объект'}

export function EntityComposer({jurisdictions=[],busy,onCreate}:{jurisdictions?:CompanyJurisdiction[];busy?:boolean;onCreate(args:Record<string,unknown>):Promise<unknown>}){
  const [kind,setKind]=useState('person'),[value,setValue]=useState(''),[label,setLabel]=useState(''),[chain,setChain]=useState('auto')
  const [country,setCountry]=useState('KZ'),[method,setMethod]=useState('name'),[note,setNote]=useState(''),[error,setError]=useState('')
  const crypto=['blockchain_address','contract','nft','token','collection'].includes(kind)
  const target=useCryptoTarget(value,chain,crypto)
  const company=kind==='organization',region=jurisdictions.find(row=>row.id===country)||jurisdictions[0]
  const field:{label:string;placeholder:string;help?:string}=company?{label:region?.identifiers[method]||'Название компании',placeholder:method==='name'?'Название организации':method==='website'?'https://example.org':'Регистрационный идентификатор'}:fields[kind]||fields.custom_entity
  const changeKind=(next:string)=>{setKind(next);setValue('');setLabel('');setError('');setNote('')}
  async function submit(){
    if(!value.trim())return
    setError('')
    try{
      const args={type:kind,label:(label.trim()||value.trim()).slice(0,300),value:value.trim(),markdown:note,
        ...(crypto?{chain}:{}),...(company?{company:{jurisdiction:region?.id||'OTHER',identifier_type:method,identifier:value.trim(),legal_name:label.trim()}}:{})}
      await onCreate(args)
      setValue('');setLabel('');setNote('')
    }catch(reason){setError((reason as Error).message)}
  }
  return <form className="entity-composer" onSubmit={event=>{event.preventDefault();void submit()}}>
    <h3>Новый объект</h3>
    <label>Тип объекта<SearchableSelect label="Тип нового узла" value={kind} options={Object.entries(names).map(([value,label])=>({value,label}))} onChange={changeKind}/></label>
    {company&&<>
      <label>Юрисдикция<SearchableSelect label="Юрисдикция компании" value={region?.id||country} options={jurisdictions.map(row=>({value:row.id,label:row.label}))}
        onChange={next=>{setCountry(next);setMethod('name');setValue('')}}/></label>
      <label>Как искать компанию?<SearchableSelect label="Способ поиска компании" value={method} options={Object.entries(region?.identifiers||{name:'Название'}).map(([value,label])=>({value,label}))}
        onChange={next=>{setMethod(next);setValue('')}}/></label>
    </>}
    {crypto&&<label>Сеть<SearchableSelect label="Сеть нового объекта" value={chain} options={cryptoChains.map(row=>({value:row.id,label:row.label}))} onChange={setChain}/></label>}
    <label>{field.label}<input data-entity-input aria-label={field.label} value={value} onChange={event=>setValue(event.target.value)}
      placeholder={field.placeholder} maxLength={2000} spellCheck={false} autoFocus/></label>
    {field.help&&<p className="field-hint">{field.help}</p>}
    {company&&<p className="field-hint">По названию будут найдены кандидаты. Формат номера сам по себе не подтверждает регистрацию.</p>}
    {crypto&&target.result?.reason&&<p className="field-hint">{target.result.reason}</p>}
    {kind==='analyst_note'&&<label>Текст заметки<textarea aria-label="Текст новой заметки" value={note} onChange={event=>setNote(event.target.value)} maxLength={20000}/></label>}
    <details className="entity-advanced"><summary>Дополнительно</summary>
      <label>{company?'Юридическое название (если известно)':'Своя подпись'}<input aria-label="Своя подпись объекта" value={label} onChange={event=>setLabel(event.target.value)} maxLength={300}/></label>
      {kind!=='analyst_note'&&<label>Комментарий<textarea aria-label="Комментарий к новому объекту" value={note} onChange={event=>setNote(event.target.value)} maxLength={20000}/></label>}
    </details>
    {error&&<p className="notice-inline notice-error" role="alert">{error}</p>}
    <Button type="submit" disabled={busy||!value.trim()||crypto&&(target.pending||!target.result?.valid||!!target.result?.requires_network)}><Plus size={15}/>Добавить объект</Button>
  </form>
}
