import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import {ChevronDown,Check} from 'lucide-react'

export function ComboBox({label,value,options,onChange,name,placeholder}:{
  label:string;value:string;options:string[];onChange(value:string):void;name?:string;placeholder?:string;
}){
  const id=useId(),root=useRef<HTMLDivElement>(null),popup=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null)
  const [open,setOpen]=useState(false),[active,setActive]=useState(-1),[position,setPosition]=useState({left:0,top:0,width:0,maxHeight:240})
  const matches=options.filter(option=>option.toLocaleLowerCase().includes(value.toLocaleLowerCase())).slice(0,100)
  useLayoutEffect(()=>{
    if(!open)return
    const rect=root.current?.getBoundingClientRect()
    if(!rect)return
    const height=Math.min(240,Math.max(40,matches.length*36))
    const below=innerHeight-rect.bottom-12,above=rect.top-12,upward=below<height&&above>below
    setPosition({left:Math.max(8,Math.min(rect.left,innerWidth-rect.width-8)),
      top:upward?Math.max(8,rect.top-height-5):rect.bottom+5,width:Math.min(rect.width,innerWidth-16),
      maxHeight:Math.max(40,Math.min(height,upward?above:below))})
  },[open,matches.length])
  useEffect(()=>{
    if(!open)return
    const outside=(event:PointerEvent)=>{
      const node=event.target as Node
      if(!root.current?.contains(node)&&!popup.current?.contains(node))setOpen(false)
    }
    const close=()=>setOpen(false)
    const scroll=(event:Event)=>{if(!popup.current?.contains(event.target as Node))close()}
    document.addEventListener('pointerdown',outside)
    window.addEventListener('resize',close)
    document.addEventListener('scroll',scroll,true)
    return()=>{document.removeEventListener('pointerdown',outside);window.removeEventListener('resize',close);document.removeEventListener('scroll',scroll,true)}
  },[open])
  useEffect(()=>{popup.current?.querySelector('[aria-selected=true]')?.scrollIntoView?.({block:'nearest'})},[active])
  function choose(option:string){onChange(option);setOpen(false);input.current?.focus()}
  return <div ref={root} className="text-combobox">
    <input ref={input} role="combobox" aria-label={label} aria-expanded={open} aria-controls={id} aria-autocomplete="list"
      aria-activedescendant={open&&matches[active]?id+'-'+active:undefined} name={name} value={value} placeholder={placeholder}
      autoComplete="off" spellCheck={false} onFocus={()=>setOpen(true)}
      onChange={event=>{onChange(event.target.value);setActive(-1);setOpen(true)}}
      onKeyDown={event=>{
        if(event.key==='ArrowDown'||event.key==='ArrowUp'){
          event.preventDefault();setOpen(true)
          setActive(previous=>event.key==='ArrowDown'?Math.min(matches.length-1,previous+1)
            :previous<0?matches.length-1:Math.max(0,previous-1))
        }else if(event.key==='Enter'&&open&&matches[active]){
          event.preventDefault();choose(matches[active])
        }else if(event.key==='Escape'){event.preventDefault();setOpen(false)}
        else if(event.key==='Tab')setOpen(false)
      }}/>
    <button type="button" aria-label={'Варианты: '+label} tabIndex={-1}
      onMouseDown={event=>event.preventDefault()} onClick={()=>{setOpen(value=>!value);input.current?.focus()}}>
      <ChevronDown size={14}/>
    </button>
    {open&&createPortal(<div ref={popup} id={id} role="listbox" aria-label={label} className="menu text-combobox-options"
      style={position}>{matches.map((option,index)=><button type="button" role="option" id={id+'-'+index} key={option}
        aria-selected={active===index} onMouseDown={event=>event.preventDefault()} onClick={()=>choose(option)}>
        <span>{option}</span>{value===option&&<Check size={13}/>}
      </button>)}
      {!matches.length&&<p className="select-empty">Можно ввести своё значение.</p>}
    </div>,document.body)}
  </div>
}
