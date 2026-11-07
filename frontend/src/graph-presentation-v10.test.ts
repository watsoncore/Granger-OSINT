import {describe,it,expect} from 'vitest'
import {defaults,graphAppearance,updateGraphSkin,savedAppearance} from './appearance'
import {entityCryptoIcon,networkIcon} from './crypto-icons'
import {emptyState} from './types'

describe('independent graph presentations',()=>{
  it('round trips both profiles without touching workspace data',()=>{
    let preferences=updateGraphSkin({...defaults('azure'),graphStyle:'glass'},{cardRadius:19,glow:8,arrows:true})
    preferences={...preferences,graphStyle:'minimal'}
    expect(graphAppearance(preferences)).toMatchObject({cardRadius:4,surface:100,shadow:0,density:'compact',arrows:false})
    preferences=updateGraphSkin(preferences,{cardRadius:3,arrows:true})
    preferences={...preferences,graphStyle:'glass'}
    expect(graphAppearance(preferences)).toMatchObject({cardRadius:19,glow:8,arrows:true})
    const restored=savedAppearance({...emptyState.settings,workspace_appearance:JSON.stringify(preferences)})
    expect(graphAppearance({...restored,graphStyle:'minimal'})).toMatchObject({cardRadius:3,arrows:true})
    expect(Object.keys(restored)).not.toContain('entities')
  })
  it('uses typed chain and service fields without guessing identity from a name',()=>{
    expect(networkIcon('Bitcoin')).toBe('network:btc')
    expect(networkIcon('telegram')).toBe('')
    expect(networkIcon('arbitraryTONlabel')).toBe('')
    expect(entityCryptoIcon({type:'blockchain_address',attributes:{label:'Bybit Telegram',chain:'eth'}})).toBe('network:eth')
    expect(entityCryptoIcon({type:'token',attributes:{chain:'ton',symbol:'USDT'}})).toBe('asset:usdt')
    expect(entityCryptoIcon({type:'public_profile',attributes:{platform:'telegram'}})).toBe('platform:telegram')
    expect(entityCryptoIcon({type:'blockchain_address',attributes:{chain:'ton',service_id:'bybit'}})).toBe('network:ton')
    expect(entityCryptoIcon({type:'service',attributes:{service_id:'bybit'}})).toBe('service:bybit')
  })
})
