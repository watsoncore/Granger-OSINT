import { memo, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy } from 'lucide-react'
import { act } from '../bridge'
import { IconButton } from './ui'

export function safeUrl(value: string): string {
  if (/^#(?:ev_[a-zA-Z0-9_-]+|source-[a-zA-Z0-9_-]+)$/.test(value)) return value
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}
export function plainText(children: ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(plainText).join('')
  if (children && typeof children === 'object' && 'props' in children) return plainText((children.props as { children?: ReactNode }).children)
  return ''
}
function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false)
  const value = plainText(children).replace(/\n$/, '')
  return <div className="code-block"><div className="code-toolbar"><span>КОД</span><IconButton label={copied ? 'Скопировано' : 'Копировать код'} onClick={() => { void act('copy', { text: value }).then(result => { if (result !== null) { setCopied(true); setTimeout(() => setCopied(false), 1800) } }) }}>{copied ? <Check size={14}/> : <Copy size={14}/>}</IconButton></div><pre>{children}</pre></div>
}
export const Markdown = memo(function Markdown({ text, onSource }: { text: string; onSource?(id: string): void }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeUrl} components={{
    a: ({ href, children }) => href ? <a href={href} onClick={event => { event.preventDefault(); if (href.startsWith('#')) onSource?.(href.slice(1).replace(/^source-/, '')); else void act('open_url', { url: href }) }}>{children}</a> : <span>{children}</span>,
    img: ({ alt }) => <span className="image-placeholder">{alt ? `[Изображение: ${alt}]` : '[Изображение]'}</span>,
    pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
    table: ({ children }) => <div className="table-scroll" role="region" aria-label="Таблица" tabIndex={0}><table>{children}</table></div>,
  }}>{text}</ReactMarkdown></div>
})
