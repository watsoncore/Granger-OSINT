import {describe,it,expect} from 'vitest'
import {EdgeRouteIndex} from './graph-route-index'
import {routeEdges} from './graph-geometry'
import type {GraphEntity,GraphRelation} from './types'
const nodes:GraphEntity[]=['a','b','c'].map(id=>({id,type:'domain',label:id,attributes:{},evidence_ids:[]}))
const edge=(id:string,a:string,b:string):GraphRelation=>({id,from_id:a,to_id:b,relation_type:'references',direction:'directed',verification_status:'unverified',evidence_ids:[]})
describe('cached world routes',()=>{
 it('keeps viewport crossing lines even when both endpoints are outside',()=>{
  const positions={a:{x:-500,y:80},b:{x:1500,y:80},c:{x:3500,y:4000}}
  const index=new EdgeRouteIndex([edge('cross','a','b'),edge('outside','c','c')],nodes,positions,1)
  expect(index.query({x:0,y:0,scale:1},{left:0,top:0,right:1000,bottom:600}).map(row=>row.edge.id)).toEqual(['cross'])
 })
 it('matches original pixel lanes through camera translations and zoom',()=>{
  const positions={a:{x:120,y:160},b:{x:600,y:310}},edges=[edge('out','a','b'),edge('back','b','a')]
  for(const scale of [.3,1,2]){
   const view={x:130,y:-50,scale},cached=new EdgeRouteIndex(edges,nodes,positions,scale).query(view,{left:-5000,top:-5000,right:5000,bottom:5000})
   const original=routeEdges(edges,positions,view,nodes)
   expect(cached.map(row=>row.edge.id)).toEqual(original.map(row=>row.edge.id))
   cached.forEach((row,i)=>row.points.forEach((point,j)=>{expect(point.x*scale+view.x).toBeCloseTo(original[i].points[j].x);expect(point.y*scale+view.y).toBeCloseTo(original[i].points[j].y)}))
  }
 })
 it('recalculates only incident routes during drag without stale duplicate lines',()=>{
  const positions={a:{x:0,y:0},b:{x:500,y:0},c:{x:900,y:500}},edges=[edge('move','a','b'),edge('static','b','c')]
  const index=new EdgeRouteIndex(edges,nodes,positions,1)
  positions.a={x:100,y:300}
  const rows=index.query({x:0,y:0,scale:1},{left:-1000,top:-1000,right:2000,bottom:2000},{a:{x:0,y:0}})
  expect(rows).toHaveLength(2)
  expect(rows.find(row=>row.edge.id==='move')?.points).toEqual(routeEdges([edges[0]],positions,{x:0,y:0,scale:1},nodes)[0].points)
 })
 it('updates only affected route objects after drag and refits bounds without rebuilding',()=>{
  const positions={a:{x:0,y:0},b:{x:500,y:0},c:{x:900,y:500}},edges=[edge('move','a','b'),edge('static','b','c')]
  const index=new EdgeRouteIndex(edges,nodes,positions,1),unchanged=index.routes[1]
  positions.a={x:100,y:300};index.updatePositions(positions)
  expect(index.routes[1]).toBe(unchanged);expect(index.generation).toBe(1)
  const actual=index.query({x:0,y:0,scale:1},{left:-1000,top:-1000,right:2000,bottom:2000})
  expect(actual.find(row=>row.edge.id==='move')?.points).toEqual(routeEdges([edges[0]],positions,{x:0,y:0,scale:1},nodes)[0].points)
  index.updatePositions({...positions});expect(index.generation).toBe(1)
 })
})
