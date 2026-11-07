import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import * as Tooltip from '@radix-ui/react-tooltip'
import { ToolCatalog } from './components/ToolCatalog'
import type { Tool } from './types'

it('finds sources by country and type while separating readiness from network success', async () => {
  const company: Tool = {
    id: 'source_brreg', name: 'Brønnøysundregistrene', description: 'Реестр организаций',
    inputTypes: ['organization'], available: true, state: 'ready',
    source_contract: {
      name: 'Brønnøysundregistrene', host: 'data.brreg.no', region: ['NO'],
      category: 'company', license: 'NLOD', parser_version: '1', formats: ['json'],
      authentication: 'none', status: 'implemented_unverified',
      health: { status: 'not_checked' },
    },
  }
  const others: Tool = { id: 'phone_metadata', name: 'PhoneInfoga', description: '', inputTypes: ['phone'], available: true, state: 'ready' }
  render(<Tooltip.Provider><ToolCatalog tools={[company, others]} inSettings/></Tooltip.Provider>)
  expect(screen.getByRole('heading', { name: /Источники и интеграции/ })).toHaveTextContent('2 локально готовы')
  expect(screen.getByText(/Свежий успешный ответ в этом запуске: 0/)).toBeVisible()
  const user = userEvent.setup()
  await user.type(screen.getByRole('textbox', { name: 'Найти инструмент' }), 'Норвегия компания')
  expect(screen.getAllByRole('article')).toHaveLength(1)
  const card = screen.getByRole('article')
  await user.click(within(card).getByRole('button', { name: 'Подробнее' }))
  expect(within(card).getByText('Ещё не запрашивался в этом запуске')).toBeVisible()
})
