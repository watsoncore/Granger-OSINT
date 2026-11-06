import {useMemo,useState,type ReactNode} from 'react'
import {ArrowDown,ArrowUp,ArrowUpDown} from 'lucide-react'
import {Checkbox} from './ui'

export interface ResultColumn<T> {
  id:string;label:string;width?:string;value(row:T):string|number;render?(row:T):ReactNode;
}
export function ResultsTable<T>({rows,columns,rowId,label,selected,onToggle,onTogglePage,rowLabel,onActivate}:{
  rows:T[];columns:ResultColumn<T>[];rowId(row:T):string;label:string;
  selected?:ReadonlySet<string>;onToggle?(id:string,checked:boolean):void;
  onTogglePage?(ids:string[],checked:boolean):void;rowLabel?(row:T):string;onActivate?(row:T):void;
}){
  const [sort,setSort]=useState<{id:string;direction:1|-1}>()
  const ordered=useMemo(()=>{
    const column=columns.find(column=>column.id===sort?.id)
    if(!column||!sort)return rows
    return [...rows].sort((a,b)=>{
      const av=column.value(a),bv=column.value(b)
      return (typeof av==='number'&&typeof bv==='number'?av-bv:String(av).localeCompare(String(bv),'ru'))*sort.direction
    })
  },[rows,columns,sort])
  const selectedCount=rows.filter(row=>selected?.has(rowId(row))).length
  return <table className="results-table" aria-label={label}>
    <colgroup>{onToggle&&<col className="results-check-column"/>}{columns.map(column=><col key={column.id} style={{width:column.width}}/>)}</colgroup>
    <thead><tr>
      {onToggle&&<th scope="col"><Checkbox aria-label="Выбрать страницу" checked={!!rows.length&&selectedCount===rows.length}
        indeterminate={selectedCount>0&&selectedCount<rows.length} disabled={!rows.length||!onTogglePage}
        onChange={event=>onTogglePage?.(rows.map(rowId),event.target.checked)}/></th>}
      {columns.map(column=><th key={column.id} scope="col" aria-sort={sort?.id===column.id
        ?sort.direction===1?'ascending':'descending':'none'}>
        <button type="button" onClick={()=>setSort({id:column.id,direction:sort?.id===column.id&&sort.direction===1?-1:1})}>
          <span>{column.label}</span>{sort?.id===column.id
            ?sort.direction===1?<ArrowUp size={12}/>:<ArrowDown size={12}/>:<ArrowUpDown size={12}/>}
        </button>
      </th>)}
    </tr></thead>
    <tbody>{ordered.map((row,index)=><tr key={rowId(row)} tabIndex={index? -1:0} aria-selected={selected?.has(rowId(row))}
      onKeyDown={event=>{
        if(event.key==='Enter'&&event.target===event.currentTarget){event.preventDefault();onActivate?.(row)}
        if(event.key===' '&&event.target===event.currentTarget&&onToggle){event.preventDefault();onToggle(rowId(row),!selected?.has(rowId(row)))}
        if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&event.target===event.currentTarget){
          event.preventDefault()
          const siblings=event.currentTarget.parentElement?.querySelectorAll<HTMLTableRowElement>('tr')
          const next=event.key==='Home'?0:event.key==='End'?ordered.length-1:Math.min(ordered.length-1,Math.max(0,index+(event.key==='ArrowDown'?1:-1)))
          siblings?.[next]?.focus()
        }
      }}>
      {onToggle&&<td><Checkbox aria-label={rowLabel?.(row)||'Выбрать запись'} checked={!!selected?.has(rowId(row))}
        onChange={event=>onToggle(rowId(row),event.target.checked)}/></td>}
      {columns.map(column=><td key={column.id} title={String(column.value(row))}>
        {column.render?column.render(row):String(column.value(row))}
      </td>)}
    </tr>)}
    {!ordered.length&&<tr><td colSpan={columns.length+(onToggle?1:0)}>По текущему фильтру нет записей.</td></tr>}</tbody>
  </table>
}
