import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Check, Code2, Copy, Download, FileText, PanelLeftClose, PanelLeftOpen, Save } from 'lucide-react'
import { act } from '../bridge'
import type { DesktopState } from '../types'
import { Markdown } from './Markdown'
import { Badge, Button, EmptyState, IconButton } from './ui'

export function documentHeadings(text: string) {
  let fenced = false
  return text.split('\n').flatMap(line => {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; return [] }
    const match = !fenced && /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line)
    return match ? [{ level: match[1].length, text: match[2].replace(/[*_`]/g, '') }] : []
  })
}
export function CanvasWorkspace({ state }: { state: DesktopState }) {
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [outline, setOutline] = useState(true)
  const [text, setText] = useState(state.canvas.text)
  const [copied, setCopied] = useState(false)
  const preview = useRef<HTMLDivElement>(null)
  const textRef = useRef(text)
  const documentId = useRef(state.canvas.id)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const headings = useMemo(() => documentHeadings(text), [text])
  useEffect(() => {
    if (documentId.current !== state.canvas.id) {
      if (timer.current) clearTimeout(timer.current)
      documentId.current = state.canvas.id; setText(state.canvas.text); textRef.current = state.canvas.text
    }
  }, [state.canvas.id, state.canvas.text])
  useEffect(() => {
    const flushPending = () => {
      if (!timer.current) return
      clearTimeout(timer.current); timer.current = undefined
      void act('canvas_edit', { text: textRef.current, document_id: documentId.current })
    }
    const hide = () => { if (document.hidden) flushPending() }
    // Hand pending edits to the Python controller before Qt freezes this page.
    // The native save timer keeps running while renderer timers are paused.
    document.addEventListener('visibilitychange', hide)
    document.addEventListener('freeze', flushPending)
    return () => { document.removeEventListener('visibilitychange', hide); document.removeEventListener('freeze', flushPending); flushPending() }
  }, [])
  const change = (value: string) => { setText(value); textRef.current = value; if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => { timer.current = undefined; void act('canvas_edit', { text: value, document_id: documentId.current }) }, 350) }
  const flush = async () => { if (timer.current) { clearTimeout(timer.current); timer.current = undefined }; return act('canvas_edit', { text: textRef.current, document_id: documentId.current }) }
  if (!state.canvas.id && !state.canvas.text) return <EmptyState icon={<FileText size={30}/>} title="Отдельное пространство для выводов">Откройте ответ Гермионы в Canvas: редактируйте Markdown, проверяйте структуру и сохраняйте документ.</EmptyState>
  return <div className="canvas-workspace"><div className="canvas-toolbar"><div className="canvas-document-name"><FileText size={17}/><strong>{state.canvas.title || 'Документ исследования'}</strong><Badge>{state.canvas.dirty || text !== state.canvas.text ? 'Изменён' : 'Сохранён'}</Badge></div><div className="canvas-controls"><div className="segmented-control"><IconButton label="Предпросмотр" className={mode === 'preview' ? 'is-active' : ''} onClick={() => { void flush(); setMode('preview') }}><BookOpen size={15}/></IconButton><IconButton label="Редактировать Markdown" className={mode === 'edit' ? 'is-active' : ''} onClick={() => setMode('edit')}><Code2 size={15}/></IconButton></div><IconButton label="Сохранить документ" onClick={() => void flush().then(result => { if (result !== null) void act('canvas_save') })}><Save size={16}/></IconButton><IconButton label="Экспортировать Markdown" onClick={() => void flush().then(result => { if (result !== null) void act('canvas_export') })}><Download size={16}/></IconButton></div></div><div className="canvas-body">{!!headings.length && outline && mode === 'preview' && <nav className="canvas-outline" aria-label="Содержание документа"><span className="eyebrow">Содержание</span>{headings.map((heading, index) => <button style={{ paddingLeft: `${8 + Math.max(0, heading.level - 1) * 10}px` }} key={index} onClick={() => preview.current?.querySelectorAll('h1,h2,h3,h4,h5,h6')[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{heading.text}</button>)}</nav>}<div className="canvas-document" ref={preview}>{mode === 'preview' ? <Markdown text={text} onSource={id => void act('source_open', { evidence_id: id })}/> : <textarea aria-label="Текст Canvas в Markdown" className="canvas-editor" spellCheck={false} value={text} onChange={event => change(event.target.value)} onBlur={() => void flush()}/>}</div></div><div className="canvas-footer"><Button variant="ghost" size="sm" onClick={() => setOutline(!outline)}>{outline ? <PanelLeftClose size={14}/> : <PanelLeftOpen size={14}/>}Содержание</Button><span>Markdown<span className="caption-divider">·</span>{text.length.toLocaleString('ru-RU')} симв.</span><IconButton label={copied ? 'Markdown скопирован' : 'Копировать Markdown'} onClick={() => void act('copy', { text }).then(result => { if (result !== null) { setCopied(true); setTimeout(() => setCopied(false), 1800) } })}>{copied ? <Check size={14}/> : <Copy size={14}/>}</IconButton></div></div>
}
