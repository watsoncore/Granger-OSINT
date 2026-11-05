import {describe,it,expect} from 'vitest'
import {GraphCamera} from './graph-camera'

describe('optimistic canvas camera',()=>{
  const original={x:0,y:0,scale:1}
  it('does not rewind a pan when selected/evidence state republishes the saved viewport',()=>{
    const camera=new GraphCamera(original);camera.active=true;camera.move({x:240,y:90,scale:1});camera.receive({...original})
    expect(camera.value).toEqual({x:240,y:90,scale:1})
    camera.active=false;camera.commit();camera.receive({...original})
    expect(camera.value.x).toBe(240)
    camera.receive({x:240,y:90,scale:1});expect(camera.value.x).toBe(240)
  })
  it('accepts ordered saves without letting an old ACK undo a later gesture',()=>{
    const camera=new GraphCamera(original),first={x:100,y:10,scale:.8},second={x:220,y:60,scale:.65}
    camera.commit(first);camera.commit(second);camera.receive(first)
    expect(camera.value).toEqual(second)
    camera.receive(second);expect(camera.value).toEqual(second)
  })
  it('keeps a gesture newer than the ACK and accepts explicit external navigation after it settles',()=>{
    const camera=new GraphCamera(original),first={x:100,y:10,scale:1}
    camera.commit(first);camera.active=true;camera.move({x:200,y:30,scale:1});camera.receive(first)
    expect(camera.value.x).toBe(200)
    camera.active=false;camera.commit();camera.receive({x:200,y:30,scale:1});camera.receive({x:50,y:60,scale:.7})
    expect(camera.value).toEqual({x:50,y:60,scale:.7})
  })
})
