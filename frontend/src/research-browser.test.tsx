import {fireEvent,render,screen} from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import {describe,it,expect,vi} from 'vitest'
import {ResearchBrowser} from './components/ResearchBrowser'
import {emptyState,type DesktopState} from './types'
import {act} from './bridge'
vi.mock('./bridge',()=>({act:vi.fn().mockResolvedValue(true)}))
const state:DesktopState={...emptyState,browser:{status:'ready',url:'https://example.org/',title:'Открытые данные',image:'data:image/jpeg;base64,fixture',actions:[{action:'navigate',target:'https://example.org/',at:'2026-11-01T00:00:00Z',status:'complete'}]}}
describe('controlled research browser panel',()=>{
 it('is absent until a real page exists',()=>{const {container}=render(<ResearchBrowser state={emptyState}/>);expect(container).toBeEmptyDOMElement()})
 it('shows the current supplied screenshot, allows collapse and sends stop',()=>{
  render(<Tooltip.Provider><ResearchBrowser state={state}/></Tooltip.Provider>)
  expect(screen.getByRole('img')).toHaveAttribute('src',state.browser!.image)
  expect(screen.getByText('Открыла страницу')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Остановить'}));expect(act).toHaveBeenCalledWith('browser_stop')
  fireEvent.click(screen.getByRole('button',{name:'Открытые данные'}));expect(screen.queryByRole('img')).toBeNull()
 })
})
