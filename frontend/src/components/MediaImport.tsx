import {useEffect,useState} from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {Clipboard,FileImage,Globe,ImagePlus,X} from 'lucide-react'
import type {ImageInput} from '../canvas-media'
import {Button} from './ui'

export function MediaImport({open,target,busy,error,onClose,onImport}:{
  open:boolean;target:string;busy:boolean;error:string;onClose():void;onImport(input:ImageInput):void
}){
  const [value,setValue]=useState('')
  useEffect(()=>{if(open)setValue('')},[open])
  return <Dialog.Root open={open} onOpenChange={next=>{if(!next)onClose()}}>
    <Dialog.Portal>
      <Dialog.Overlay className="dialog-overlay"/>
      <Dialog.Content className="dialog media-import">
        <div className="media-import-heading">
          <ImagePlus size={22}/>
          <div>
            <Dialog.Title>{target?'Прикрепить изображение':'Добавить изображение'}</Dialog.Title>
            <Dialog.Description>{target||'Новая карточка на полотне'}</Dialog.Description>
          </div>
          <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Закрыть импорт"><X size={18}/></Button></Dialog.Close>
        </div>
        <div className="media-import-actions">
          <Button variant="secondary" disabled={busy} onClick={()=>onImport({mode:'picker'})}><FileImage size={16}/>Выбрать файл</Button>
          <Button variant="secondary" disabled={busy} onClick={()=>onImport({mode:'clipboard'})}><Clipboard size={16}/>Из буфера</Button>
        </div>
        <form onSubmit={event=>{event.preventDefault();const input=value.trim();if(input)onImport(/^https?:/i.test(input)?{mode:'url',url:input}:{mode:'path',path:input})}}>
          <label>Путь на диске или публичный HTTPS-адрес<input aria-label="Путь на диске или публичный HTTPS-адрес" value={value} onChange={event=>setValue(event.target.value)} maxLength={4096} spellCheck={false} placeholder="C:\\Фото\\кадр.png или https://…"/></label>
          <Button type="submit" disabled={!value.trim()||busy}><Globe size={15}/>Загрузить</Button>
        </form>
        {busy&&<p role="status">Проверка и сохранение оригинала…</p>}
        {error&&<p role="alert" className="notice-inline notice-error">{error}</p>}
        <p className="field-hint">JPEG, PNG и WebP до 20 МиБ. Можно перетащить файл прямо на полотно.</p>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
