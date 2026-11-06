import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {describe,it,expect,vi} from 'vitest'
import {ResearchResults} from './components/ResearchResults'
import type {ResearchCanvasState,Source} from './types'
const row=(n:number):Source=>({evidence_id:'ev_'+String(n).padStart(20,'0'),title:'Запись '+n,url:'https://example.org/'+n,status:'source_reported',kind:'adapter'})
const preview:NonNullable<ResearchCanvasState['preview']>={token:'token',canvas_id:'a'.repeat(32),node_id:'',tool:'blockchain_gansar',status:'running',running:true,limitations:[],results:[]}
describe('streamed evidence selection',()=>{
 it('keeps source warnings but omits redundant positive badges in a Maigret gallery',()=>{
  render(<ResearchResults evidenceIds={[]} onSource={()=>{}} onInsert={vi.fn()}
    preview={{...preview,tool:'username_maigret',results:[{...row(1),status:'detected'},row(2),{...row(3),status:'partial'}]}}/>)
  fireEvent.click(screen.getByRole('button',{name:'Результаты для добавления'}))
  expect(screen.queryByText('Есть находки')).toBeNull()
  expect(screen.queryByText('Сообщено источником')).toBeNull()
  expect(screen.getByText('Частичный результат')).toBeInTheDocument()
  expect(screen.getByLabelText('Добавить: Запись 1')).toBeChecked()
 })
 it('selects arriving records after the initial empty preview without inserting automatically',async()=>{
  const insert=vi.fn().mockResolvedValue(true),props={evidenceIds:[],onSource:()=>{},onInsert:insert}
  const view=render(<ResearchResults {...props} preview={preview}/>);
  view.rerender(<ResearchResults {...props} preview={{...preview,results:[row(1),row(2)]}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Результаты для добавления'}))
  expect(screen.getByRole('button',{name:'Добавить выбранные (2)'})).toBeEnabled();expect(insert).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Добавить выбранные (2)'}));await waitFor(()=>expect(insert).toHaveBeenCalledWith([row(1).evidence_id,row(2).evidence_id]))
 })
 it('does not override an explicit selection as more records arrive and keeps it after a rejected save',async()=>{
  const insert=vi.fn().mockRejectedValue(new Error('Нет подтверждения'))
  const props={evidenceIds:[],onSource:()=>{},onInsert:insert},view=render(<ResearchResults {...props} preview={{...preview,results:[row(1)]}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Результаты для добавления'}));fireEvent.click(screen.getByRole('button',{name:'Снять выбор'}))
  view.rerender(<ResearchResults {...props} preview={{...preview,results:[row(1),row(2)]}}/>);
  expect(screen.getByRole('button',{name:'Добавить выбранные (0)'})).toBeDisabled()
  fireEvent.click(screen.getByLabelText('Добавить: Запись 2'));fireEvent.click(screen.getByRole('button',{name:'Добавить выбранные (1)'}));await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Нет подтверждения'))
  expect(screen.getByLabelText('Добавить: Запись 2')).toBeChecked()
 })
})
