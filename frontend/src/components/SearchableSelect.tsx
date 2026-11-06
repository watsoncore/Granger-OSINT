import {useEffect,useId,useRef,useState} from 'react'
import * as Dropdown from '@radix-ui/react-dropdown-menu'
import {Check,ChevronDown,Search} from 'lucide-react'

export interface SelectOption {value:string;label:string;group?:string;disabled?:boolean;description?:string}
interface Props {
  label?:string;value:string;options:SelectOption[];onChange(value:string):void;
  disabled?:boolean;className?:string;placeholder?:string;id?:string;
  autoFocus?:boolean;required?:boolean;
}
export function SearchableSelect({label,value,options,onChange,disabled,className='',placeholder='Выберите…',id:triggerId,autoFocus,required}:Props){
  const [open,setOpen]=useState(false),[query,setQuery]=useState('')
  const input=useRef<HTMLInputElement>(null),list=useRef<HTMLDivElement>(null),id=useId()
  const selected=options.find(option=>option.value===value)
  const needle=query.toLocaleLowerCase().trim()
  const matching=options.filter(option=>!needle||`${option.label} ${option.value} ${option.description||''} ${option.group||''}`.toLocaleLowerCase().includes(needle))
  const rows=matching.slice(0,150)
  useEffect(()=>{
    if(!open)return
    const timer=setTimeout(()=>input.current?.focus(),0)
    return()=>clearTimeout(timer)
  },[open])
  function choose(next:string){onChange(next);setOpen(false)}
  return <Dropdown.Root open={open} onOpenChange={next=>{setOpen(next);if(next)setQuery('')}}>
    <Dropdown.Trigger id={triggerId} value={value} className={`searchable-select ${className}`} aria-label={label} aria-controls={id}
      disabled={disabled} autoFocus={autoFocus} data-required={required||undefined}>
      <span>{selected?.label||placeholder}</span><ChevronDown size={14}/>
    </Dropdown.Trigger>
    <Dropdown.Portal><Dropdown.Content id={id} className="menu searchable-select-menu" align="start" sideOffset={5}
      collisionPadding={10} onCloseAutoFocus={()=>setQuery('')}>
      <label className="select-search"><Search size={14}/><input ref={input} aria-label={`Найти: ${label||selected?.label||'вариант'}`}
        value={query} onChange={event=>setQuery(event.target.value)} placeholder="Поиск…" onKeyDown={event=>{
          if(event.key==='ArrowDown'||event.key==='ArrowUp'){
            event.preventDefault()
            const items=list.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]:not([data-disabled])')
            items?.[event.key==='ArrowUp'?items.length-1:0]?.focus()
          }else if(event.key==='Enter'){
            event.preventDefault()
            const option=rows.find(option=>!option.disabled&&(needle||option.value===value))||rows.find(option=>!option.disabled)
            if(option)choose(option.value)
          }else if(event.key!=='Escape')event.stopPropagation()
        }}/></label>
      <div className="select-options" ref={list}>
        <Dropdown.RadioGroup value={value} onValueChange={choose}>
          {rows.map((option,index)=><div key={option.value}>
            {option.group&&rows[index-1]?.group!==option.group&&<Dropdown.Label className="select-group">{option.group}</Dropdown.Label>}
            <Dropdown.RadioItem value={option.value} className="menu-item select-option" disabled={option.disabled} textValue={option.label}>
              <span><strong>{option.label}</strong>{option.description&&<small>{option.description}</small>}</span>
              <Dropdown.ItemIndicator><Check size={14}/></Dropdown.ItemIndicator>
            </Dropdown.RadioItem>
          </div>)}
        </Dropdown.RadioGroup>
        {!rows.length&&<p className="select-empty">Нет подходящих вариантов</p>}
        {matching.length>rows.length&&<p className="select-empty">Уточните поиск · найдено {matching.length}</p>}
      </div>
    </Dropdown.Content></Dropdown.Portal>
  </Dropdown.Root>
}
