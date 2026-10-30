import { fireEvent, render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { describe, expect, it, vi } from 'vitest'
import { GeoInvestigation } from './components/GeoInvestigation'
import { emptyState, type GeoView } from './types'
import { act } from './bridge'

vi.mock('./bridge',()=>({act:vi.fn().mockResolvedValue(true)}))
const view:GeoView={state:'ready',has_geoint:true,originals:[{attachment_id:'one',state:'ready',thumbnail:'data:image/jpeg;base64,YQ=='},{attachment_id:'two',state:'ready',thumbnail:'data:image/jpeg;base64,Yg=='}],
  scenes:[{evidence_id:'ev_scene',attachment_id:'two',description:'Описание тестового снимка'}],
  candidates:[{candidate_id:'geo_two',attachment_id:'two',latitude:55.75,longitude:37.62,verification_status:'geographically_plausible'}],
  images:[{evidence_id:'ev_reference',candidate_id:'geo_two',attachment_id:'two',source_url:'https://example.org/archive',title:'Тестовый эталон',provider:'Public fixture',license:'CC0',media:{state:'ready',thumbnail:'data:image/jpeg;base64,Yw=='},comparison:{match_count:3,geolocation_verified:false}}]}

describe('evidence-bound geographic photographs',()=>{
  it('shows cached photos and compares the correct original among several attachments',()=>{
    const state={...emptyState,geo_views:{test:view}}
    render(<Tooltip.Provider><GeoInvestigation id="test" state={state}/></Tooltip.Provider>)
    expect(screen.getByAltText('Тестовый эталон')).toHaveAttribute('src','data:image/jpeg;base64,Yw==')
    expect(screen.getByText(/CC0/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Сравнить с исходным'}))
    expect(screen.getByAltText('Исходная фотография пользователя')).toHaveAttribute('src','data:image/jpeg;base64,Yg==')
    expect(screen.getByText(/Это не вероятность/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'В граф'}))
    expect(act).toHaveBeenCalledWith('investigation_graph_get',{id:'test',mode:'graph'})
  })
  it('never turns a remote image URL or SVG into a renderer network request',()=>{
    render(<Tooltip.Provider><GeoInvestigation id="test" state={{...emptyState,geo_views:{test:{...view,images:[{...view.images![0],media:{state:'ready',thumbnail:'https://example.org/tracker.png'}}]}}}}/></Tooltip.Provider>)
    expect(screen.queryByAltText('Тестовый эталон')).toBeNull()
    expect(screen.getByRole('button',{name:'Сравнить с исходным'})).toBeDisabled()
  })
  it('conceals cached previews when the portable vault is locked',()=>{
    const {container}=render(<Tooltip.Provider><GeoInvestigation id="test" state={{...emptyState,geo_views:{test:view},vault:{...emptyState.vault,enabled:true,unlocked:false}}}/></Tooltip.Provider>)
    expect(container.querySelector('img')).toBeNull()
  })
})
