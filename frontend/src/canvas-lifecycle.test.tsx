import { fireEvent, render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CanvasWorkspace } from './components/Canvas'
import { emptyState } from './types'
import { act } from './bridge'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
const state = { ...emptyState, canvas: { id: 'canvas-fixture', text: 'Initial', title: 'Fixture', dirty: false } }
describe('Canvas renderer lifecycle', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
  it.each(['visibilitychange', 'freeze'])('hands pending edits to Python before %s suspends timers', event => {
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    const { unmount } = render(<Tooltip.Provider><CanvasWorkspace state={state}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Редактировать Markdown' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст Canvas в Markdown' }), { target: { value: 'Changed before minimize' } })
    expect(act).not.toHaveBeenCalled()
    fireEvent(document, new Event(event))
    expect(act).toHaveBeenCalledExactlyOnceWith('canvas_edit', { text: 'Changed before minimize', document_id: 'canvas-fixture' })
    vi.advanceTimersByTime(1000)
    unmount()
    expect(act).toHaveBeenCalledOnce()
  })
  it('cleans document lifecycle handlers across repeated mounts', () => {
    const add = vi.spyOn(document, 'addEventListener')
    const remove = vi.spyOn(document, 'removeEventListener')
    for (let index = 0; index < 3; index++) {
      const { unmount } = render(<Tooltip.Provider><CanvasWorkspace state={state}/></Tooltip.Provider>)
      unmount()
    }
    for (const name of ['visibilitychange', 'freeze']) {
      const handlers = add.mock.calls.filter(([event]) => event === name).map(([, handler]) => handler)
      expect(handlers).toHaveLength(3)
      handlers.forEach(handler => expect(remove).toHaveBeenCalledWith(name, handler))
    }
    fireEvent(document, new Event('freeze'))
    expect(act).not.toHaveBeenCalled()
  })
})
