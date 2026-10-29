import { useRef } from 'react'
import { act, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VirtualMessages } from './components/VirtualMessages'
import type { Message } from './types'

const messages: Message[] = Array.from({ length: 1000 }, (_, index) => ({ id: `message-${index}`, role: 'model', text: `Fixture ${index}` }))
function Harness({ focus, rows = messages }: { focus?: string; rows?: Message[] }) {
  const scroll = useRef<HTMLDivElement>(null)
  const pinned = useRef(false)
  return <div ref={scroll} data-testid="scroll"><VirtualMessages messages={rows} conversation="fixture" focus={focus}
    scroll={scroll} pinned={pinned} render={message => <article data-message-id={message.id}>{message.text}</article>}/></div>
}
describe('long conversation viewport', () => {
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(600)
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(700)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(700)
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(140000)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
      return { x: 0, y: 0, top: 0, left: 0, right: 700, bottom: 140, width: 700, height: 140, toJSON() {} }
    })
    HTMLElement.prototype.scrollTo = function (options?: ScrollToOptions | number) {
      this.scrollTop = typeof options === 'object' ? options.top ?? 0 : options ?? 0
      this.dispatchEvent(new Event('scroll'))
    }
  })
  afterEach(() => vi.restoreAllMocks())
  it('mounts a bounded viewport while retaining all 1000 message records', async () => {
    const { container } = render(<Harness/>)
    await waitFor(() => expect(container.querySelectorAll('[data-message-id]').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('[data-message-id]').length).toBeLessThan(40)
    expect(messages).toHaveLength(1000)
    expect(messages[0].text).toBe('Fixture 0')
  })
  it('can mount an earlier offscreen message for notification focus', async () => {
    const { container, rerender } = render(<Harness/>)
    rerender(<Harness focus="message-400"/>)
    await waitFor(() => expect(container.querySelector('[data-message-id="message-400"]')).not.toBeNull())
    expect(container.querySelectorAll('[data-message-id]').length).toBeLessThan(40)
  })
  it('updates the viewport after scrolling and streaming without mounting the archive', async () => {
    const { container, getByTestId, rerender } = render(<Harness/>)
    await act(async () => { getByTestId('scroll').scrollTop = 0; fireEvent.scroll(getByTestId('scroll')) })
    await waitFor(() => expect(container.querySelector('[data-message-id="message-0"]')).not.toBeNull())
    rerender(<Harness rows={[...messages, { id: 'stream', role: 'model', text: 'New text', streaming: true }]}/>)
    expect(container.querySelectorAll('[data-message-id]').length).toBeLessThan(40)
  })
})
