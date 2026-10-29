import { ImagePlus, LoaderCircle, X } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState } from '../types'
import { IconButton } from './ui'
import './attachments.css'

export async function importDroppedImage(file: File) {
  if (file.size > 20 * 1024 * 1024) throw new Error('Изображение должно занимать не более 20 МиБ.')
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('Не удалось прочитать изображение.'))
    reader.readAsDataURL(file)
  })
  await act('attachment_import', { name: file.name, base64: data })
}

export function AttachmentComposer({ state }: { state: DesktopState }) {
  return <div className="image-attachments">
    <div className="attachment-actions"><IconButton label="Выбрать изображение" disabled={state.busy || state.attachment_busy || (state.attachments?.length || 0) >= 4} onClick={() => void act('attachment_choose')}><ImagePlus size={17}/></IconButton><small>JPEG, PNG, WebP · до 20 МиБ · обработка локально</small></div>
    {state.attachment_busy && <div className="attachment-processing"><LoaderCircle size={14} className="spin"/>Проверка изображения<IconButton label="Отменить обработку изображения" onClick={() => void act('attachment_cancel')}><X size={14}/></IconButton></div>}
    {!!state.attachments?.length && <div className="attachment-previews">{state.attachments.map(image => <div className="attachment-preview" key={image.id}>{image.preview && <img src={image.preview} alt={`Вложение: ${image.name}`}/>}<span><strong>{image.name}</strong><small>{image.width} × {image.height} · {image.format} · {(image.bytes / 1024).toFixed(0)} КиБ</small></span><IconButton label={`Убрать ${image.name}`} onClick={() => void act('attachment_remove', { id: image.id })}><X size={14}/></IconButton></div>)}</div>}
    {state.attachment_error && <p className="notice-inline notice-error" role="alert">{state.attachment_error}</p>}
    {!!state.attachments?.length && <p className="attachment-consent">При отправке DeepSeek получит результаты локальных инструментов. Исходные фотографии внешним сервисам автоматически не передаются.</p>}
  </div>
}
