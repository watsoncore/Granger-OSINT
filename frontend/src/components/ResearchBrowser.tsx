import { useState } from 'react'
import { ChevronDown, Globe, Square } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState } from '../types'
import { Button } from './ui'
import './research-browser.css'

const actions:Record<string,string>={navigate:'Открыла страницу',type:'Ввела поисковый запрос',click:'Нажала элемент',snapshot:'Прочитала страницу',screenshot:'Сохранила снимок',scroll:'Прокрутила страницу',back:'Вернулась назад'}
export function ResearchBrowser({state}:{state:DesktopState}){
  const [expanded,setExpanded]=useState(true)
  const browser=state.browser
  if(!browser?.url)return null
  return <section className="research-browser" aria-label="Исследовательский браузер">
    <div className="research-browser-heading"><button onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}><Globe size={16}/><span>{browser.title||'Браузер Гермионы'}</span><ChevronDown size={14}/></button><Button size="sm" variant="ghost" disabled={browser.status==='stopped'} onClick={()=>void act('browser_stop')}><Square size={12}/>Остановить</Button></div>
    <p className="research-browser-url" title={browser.url}>{browser.url}</p>
    {expanded&&<><img src={browser.image} alt="Настоящий снимок текущей страницы исследовательского браузера"/><ol>{browser.actions?.slice(-5).map((row,index)=><li key={row.at+index}>{actions[row.action]||'Действие браузера'}<span>{new Date(row.at).toLocaleTimeString('ru-RU')}</span></li>)}</ol></>}
    {browser.error_code&&<p role="status" className="notice-inline">Действие не завершено. Полученные сведения сохранены.</p>}
    {browser.status==='stopped'&&<small>Браузер остановлен</small>}
  </section>
}
