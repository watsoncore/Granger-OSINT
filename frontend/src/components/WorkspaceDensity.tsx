import {useEffect,useState} from 'react'
import {Rows3,StretchHorizontal} from 'lucide-react'
import {Button} from './ui'
export function DensityControl(){
  const [density,setDensity]=useState<'compact'|'comfortable'>(()=>{try{return localStorage.getItem('granger.workspace.density')==='comfortable'?'comfortable':'compact'}catch{return 'compact'}})
  useEffect(()=>{document.documentElement.dataset.density=density;try{localStorage.setItem('granger.workspace.density',density)}catch{}},[density])
  return <Button variant="ghost" size="sm" aria-label="Плотность интерфейса" title={density==='compact'?'Компактная плотность':'Свободная плотность'} onClick={()=>setDensity(value=>value==='compact'?'comfortable':'compact')}>{density==='compact'?<Rows3 size={15}/>:<StretchHorizontal size={15}/>}<span>{density==='compact'?'Компактно':'Свободно'}</span></Button>
}
