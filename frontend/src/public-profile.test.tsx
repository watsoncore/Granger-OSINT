import {render,screen} from '@testing-library/react'
import {describe,it,expect} from 'vitest'
import {PublicProfile} from './components/PublicProfile'
import type {Source} from './types'

describe('observed public profile fields',()=>{
  it('shows missing TikTok counters and account creation as unknown, preserving visible JSON',()=>{
    const source:Source={evidence_id:'ev_fixture',kind:'api',status:'partial',title:'TikTok fixture',url:'https://www.tiktok.com/@fixture',
      details:{capability:'tiktok_public_profile',uniqueId:'fixture',nickname:'Synthetic fixture',userId:null,video_id:'6718335390845095173',
        counters:null,region:null,accountCreationTimestamp:null,input_kind:'video'}}
    render(<PublicProfile source={source}/>)
    expect(screen.getByText('Счётчики не предоставлены этим ответом. Это не нулевые значения.')).toBeInTheDocument()
    expect(screen.getByText('Время video ID не является датой создания аккаунта.')).toBeInTheDocument()
    expect(screen.getByText('JSON полученных полей')).toBeInTheDocument()
    expect(screen.getAllByText('Не предоставлено').length).toBeGreaterThan(3)
    expect(document.querySelector('img')).toBeNull()
  })
})
