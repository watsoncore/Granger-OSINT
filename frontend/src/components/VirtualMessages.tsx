import { useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Message } from '../types'

// Retain the ordinary markup for short conversations. Long archives remain
// complete in state/DPAPI; only a viewport plus overscan mounts expensive
// Markdown, menus, tooltips and Motion components at once.
export const VIRTUAL_MESSAGE_THRESHOLD = 100

export function VirtualMessages({ messages, conversation, focus, scroll, pinned, render, onRange }: {
  messages: Message[]; conversation?: string; focus?: string | null
  scroll: RefObject<HTMLDivElement | null>; pinned: RefObject<boolean>
  render(message: Message): ReactNode
  onRange?(): void
}) {
  const container = useRef<HTMLDivElement>(null)
  const previousConversation = useRef(conversation)
  const virtualizer = useVirtualizer<HTMLDivElement, HTMLDivElement>({
    count: messages.length,
    getScrollElement: () => scroll.current,
    getItemKey: index => messages[index].id,
    estimateSize: index => 110 + Math.min(1200, Math.ceil(messages[index].text.length / 70) * 26),
    overscan: 6,
    initialRect: { width: 700, height: 700 },
    initialOffset: () => messages.reduce((total, message) => total + 110 + Math.min(1200, Math.ceil(message.text.length / 70) * 26), 0),
    scrollMargin: container.current?.offsetTop ?? 0,
  })
  const items = virtualizer.getVirtualItems()
  useLayoutEffect(() => { onRange?.() }, [items[0]?.index, items.at(-1)?.index, onRange])
  useLayoutEffect(() => {
    if (previousConversation.current !== conversation) {
      previousConversation.current = conversation
      virtualizer.measure()
    }
    if (pinned.current && messages.length) virtualizer.scrollToIndex(messages.length - 1, { align: 'end' })
  }, [conversation, messages.length, messages.at(-1)?.text, virtualizer, pinned])
  useLayoutEffect(() => {
    if (!focus) return
    const index = messages.findIndex(message => message.id === focus)
    if (index >= 0) {
      pinned.current = false
      virtualizer.scrollToIndex(index, { align: 'center' })
    }
  }, [focus, conversation, virtualizer, pinned])
  return <div ref={container} data-virtual-message-list style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
    {items.map(item => <div key={item.key} data-index={item.index} ref={virtualizer.measureElement}
      style={{ position: 'absolute', top: 0, left: 0, width: '100%', display: 'flow-root', transform: `translateY(${item.start - virtualizer.options.scrollMargin}px)` }}>
      {render(messages[item.index])}
    </div>)}
  </div>
}
