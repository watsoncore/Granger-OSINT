import { useState } from 'react'
import { ArrowUpRight, Clock3, MessageSquare, Plus, Search, ShieldCheck } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState } from '../types'
import { Badge, Button, EmptyState } from './ui'
import { formatDate } from './Sources'

export function HistoryWorkspace({ state }: { state: DesktopState }) {
  const [query, setQuery] = useState('')
  const history = state.history.filter(item => item.title.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru')))
  return <div className="workspace-scroll"><div className="page-content"><div className="page-heading heading-with-action"><div><span className="eyebrow">РАБОЧАЯ БИБЛИОТЕКА</span><h1>История диалогов</h1><p>Возвращайтесь к вопросам, выводам и сохранённому контексту.</p></div><Button variant="secondary" size="sm" disabled={state.busy} onClick={() => void act('chat_new')}><Plus size={15}/>Новый диалог</Button></div><div className="history-search"><Search size={16}/><input aria-label="Найти диалог" placeholder="Найти в названиях диалогов" value={query} onChange={event => setQuery(event.target.value)}/></div>{!state.history.length ? <EmptyState icon={<Clock3 size={28}/>} title="Здесь появятся ваши диалоги">История хранится в зашифрованном архиве на этом компьютере.</EmptyState> : !history.length ? <EmptyState icon={<Search size={26}/>} title="Диалог не найден">Попробуйте изменить запрос.</EmptyState> : <div className="history-list">{history.map(item => <button key={item.id} className="history-row" disabled={state.busy} onClick={() => void act('history_load', { id: item.id })}><span className="history-icon"><MessageSquare size={17}/></span><span className="history-main"><strong>{item.title || 'Диалог с Гермионой'}</strong><small>{item.updated_at ? formatDate(item.updated_at) : 'Время не указано'}{typeof item.message_count === 'number' && <><span>·</span>{item.message_count} сообщ.</>}</small></span>{item.current && <Badge>Текущий</Badge>}<ArrowUpRight size={15}/></button>)}</div>}<p className="privacy-footnote"><ShieldIcon/>Переписка остаётся в существующем защищённом хранилище Granger-OSINT.</p></div></div>
}
function ShieldIcon() { return <ShieldCheck size={13}/> }
