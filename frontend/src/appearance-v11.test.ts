import {describe,it,expect} from 'vitest'
import {defaults,applyAppearance,savedAppearance,graphAppearance} from './appearance'
import {emptyState} from './types'

describe('global material and independent graph profiles',()=>{
  it('defaults the whole application and graph to Minimal',()=>{
    const value=savedAppearance(emptyState.settings)
    expect(value.appStyle).toBe('minimal');expect(value.graphStyle).toBe('minimal')
    applyAppearance(value,false)
    expect(document.documentElement.dataset.appStyle).toBe('minimal')
    expect(document.documentElement.style.getPropertyValue('--user-frost')).toBe('0px')
  })
  it('restores saved glass material after a global Minimal preview without modifying it',()=>{
    const glass={...defaults('light'),appStyle:'glass' as const,graphStyle:'minimal' as const,frost:12,shadow:24,glow:8,
      wallpaper:{...defaults().wallpaper,source:'image' as const,image:'img_'+'a'.repeat(64)}}
    const before=JSON.stringify(glass)
    applyAppearance({...glass,appStyle:'minimal'},false)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.getPropertyValue('--user-frost')).toBe('0px')
    applyAppearance(glass,false)
    expect(document.documentElement.dataset.appStyle).toBe('glass')
    expect(document.documentElement.style.getPropertyValue('--user-frost')).toBe('12px')
    expect(graphAppearance(glass).frost).toBe(0)
    expect(JSON.stringify(glass)).toBe(before)
  })
})
