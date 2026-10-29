import type { CSSProperties } from 'react'
import { Clock3, FileText, MessageSquare, Minus, PanelLeftClose, PanelLeftOpen, Search, Settings2, Square, X, Copy } from 'lucide-react'

// No additional user navigation icon files are present. These existing SVG
// components remain the fallback. Add reviewed local imports here when supplied.
export const iconMap = {
  chat: MessageSquare, search: Search, history: Clock3, canvas: FileText,
  settings: Settings2, navigationCollapse: PanelLeftClose, navigationExpand: PanelLeftOpen,
  windowClose: X, windowMinimize: Minus, windowMaximize: Square, windowRestore: Copy,
} as const
export type IconName = keyof typeof iconMap
export function AppIcon({ name, size = 18, className, style }: { name: IconName; size?: 16 | 18 | 20 | 24; className?: string; style?: CSSProperties }) {
  const Icon = iconMap[name]
  return <Icon size={size} strokeWidth={1.7} aria-hidden="true" className={className} style={style}/>
}
