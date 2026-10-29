import { fireEvent, render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { describe, expect, it, vi } from 'vitest'
import { AttachmentComposer, importDroppedImage } from './components/AttachmentComposer'
import { emptyState } from './types'
import { act } from './bridge'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
describe('local image attachment controls', () => {
  it('chooses images through the native picker without reading an arbitrary path', () => {
    render(<Tooltip.Provider><AttachmentComposer state={emptyState}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать изображение' }))
    expect(act).toHaveBeenCalledWith('attachment_choose')
  })
  it('shows actual file metadata and lets the user remove the pending selection', () => {
    const image = { id:'img_'+'a'.repeat(64), name:'Тест.png',format:'PNG',mime:'image/png',width:400,height:200,bytes:1024,sha256:'a'.repeat(64) }
    render(<Tooltip.Provider><AttachmentComposer state={{...emptyState,attachments:[image]}}/></Tooltip.Provider>)
    expect(screen.getByText('400 × 200 · PNG · 1 КиБ')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Убрать Тест.png'}))
    expect(act).toHaveBeenCalledWith('attachment_remove',{id:image.id})
  })
  it('allows cancellation of asynchronous decoding and disables another import', () => {
    render(<Tooltip.Provider><AttachmentComposer state={{...emptyState,attachment_busy:true}}/></Tooltip.Provider>)
    expect(screen.getByRole('button',{name:'Выбрать изображение'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:'Отменить обработку изображения'}))
    expect(act).toHaveBeenCalledWith('attachment_cancel')
  })
  it('rejects a large dropped file before allocating its base64 representation', async () => {
    const file = new File(['x'],'too-large.png',{type:'image/png'})
    Object.defineProperty(file,'size',{value:21*1024*1024})
    await expect(importDroppedImage(file)).rejects.toThrow('20 МиБ')
  })
})
