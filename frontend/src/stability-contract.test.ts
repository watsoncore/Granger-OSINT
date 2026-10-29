import { describe, expect, it } from 'vitest'
import { emptyState, parseState } from './types'

describe('backend restoration contract', () => {
  it.each([
    { messages: ['not an object'] }, { evidence: ['HTML error'] },
    { investigation: 'bad checkpoint' }, { activity: [null] },
    { message_updates: [{ index: 0, message: 'bad update' }] },
    { evidence: [{ evidence_id: 'ev_fixture', title: 'Fixture', url: '', details: 'bad details' }] },
  ])('rejects malformed boundary data before rendering', value => {
    expect(() => parseState(JSON.stringify(value), emptyState)).toThrow()
  })
  it('accepts stopped recovery and one aggregated error', () => {
    const state = parseState({ investigation: { id: 'fixture', status: 'interrupted' }, errors: [{ id: 'one', message: 'Остановлено', code: 'AttributeError', count: 100 }] })
    expect(state.busy).toBe(false)
    expect(state.errors).toHaveLength(1)
  })
})
