import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { emptyState, type Tool, type InputSchema, type Source } from './types'
import { SearchWorkspace } from './components/Search'
import { parseToolArguments } from './components/StructuredToolFields'
import { SourceDialog, sourceLabel } from './components/Sources'
import { SourceSettings } from './components/ConnectionSettings'
import { act } from './bridge'
vi.mock('./bridge', () => ({ act:vi.fn().mockResolvedValue(true) }))
const schema: InputSchema = {type:'object',properties:{datetime_utc:{type:'string',minLength:1},object_height:{type:'number',exclusiveMinimum:0},shadow_length:{type:'number',exclusiveMinimum:0},max_cells:{type:'integer',minimum:1,maximum:2000},titles:{type:'array',minItems:1,maxItems:100,items:{type:'string',maxLength:256}}},required:['datetime_utc'],additionalProperties:false}
const tool: Tool = {id:'shadow_regions',name:'shadow_regions',description:'Реальная локальная геометрия',inputTypes:['geoint_geometry'],available:true,state:'ready',implemented:true,manifest:{execution_mode:'LOCAL_PYTHON',input_schema:schema}}
function workspace(tools: Tool[] = [tool]) {
 return render(<Tooltip.Provider><SearchWorkspace state={{...emptyState,tools}} query="" setQuery={() => {}} onSource={() => {}}/></Tooltip.Provider>)
}
function select(id = 'shadow_regions') { fireEvent.change(screen.getByRole('combobox',{name:'Инструмент поиска'}),{target:{value:id}}) }
function source(details: Record<string,unknown>): Source { return {evidence_id:'ev_local',kind:'tool_result',title:'Вычисление',url:'',status:'computed',details} }
function dialog(details: Record<string,unknown>) { return render(<Tooltip.Provider><SourceDialog source={source(details)} onClose={() => {}}/></Tooltip.Provider>) }
beforeEach(() => vi.clearAllMocks())

describe('manual structured tools use actual arguments protocol', () => {
 it('sends numbers as numbers, omits blank optional parameters and does not require the unrelated search query', () => {
  workspace();select()
  expect(screen.queryByLabelText('Что исследуем?')).toBeNull()
  fireEvent.change(screen.getByLabelText('Дата и время с часовым поясом'),{target:{value:'2024-02-29T13:59:59Z'}})
  fireEvent.change(screen.getByLabelText('Высота объекта'),{target:{value:'10'}})
  fireEvent.change(screen.getByLabelText('Длина тени'),{target:{value:'5'}})
  fireEvent.click(screen.getByRole('button',{name:'Найти'}))
  expect(act).toHaveBeenCalledWith('tool_run',{tool:'shadow_regions',arguments:{datetime_utc:'2024-02-29T13:59:59Z',object_height:10,shadow_length:5}})
  expect(screen.getByText('Локальное вычисление')).toBeInTheDocument()
 })
 it('permits an empty arguments object for a graph page with only optional fields', () => {
  workspace([{...tool,id:'evidence_graph',name:'evidence_graph',manifest:{input_schema:{type:'object',properties:{entity_id:{type:'string'}},required:[],additionalProperties:false}}}]);select('evidence_graph')
  fireEvent.click(screen.getByRole('button',{name:'Найти'}))
  expect(act).toHaveBeenCalledWith('tool_run',{tool:'evidence_graph',arguments:{}})
 })
 it('parses array inputs and prevents malformed JSON or nested schema violations from reaching backend', () => {
  const titles={...tool,id:'role_classify',name:'role_classify',manifest:{input_schema:{type:'object',properties:{titles:schema.properties!.titles},required:['titles'],additionalProperties:false}}}
  workspace([titles]);select('role_classify')
  fireEvent.change(screen.getByLabelText('Тексты должностей'),{target:{value:'["CEO",'}})
  fireEvent.click(screen.getByRole('button',{name:'Найти'}))
  expect(screen.getByRole('alert')).toHaveTextContent('некорректный JSON')
  expect(act).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Тексты должностей'),{target:{value:'["CEO", "Senior Engineer"]'}})
  fireEvent.click(screen.getByRole('button',{name:'Найти'}))
  expect(act).toHaveBeenCalledWith('tool_run',{tool:'role_classify',arguments:{titles:['CEO','Senior Engineer']}})
 })
 it('retains the legacy text-query protocol for existing tools and hides nonimplemented candidates', () => {
  const old={...tool,id:'username_maigret',name:'username_maigret',manifest:undefined}
  render(<Tooltip.Provider><SearchWorkspace state={{...emptyState,tools:[old,{...tool,id:'candidate',implemented:false}]}} query="example" setQuery={() => {}} onSource={() => {}}/></Tooltip.Provider>)
  select('username_maigret');fireEvent.click(screen.getByRole('button',{name:'Найти'}))
  expect(act).toHaveBeenCalledWith('tool_run',{tool:'username_maigret',query:'example'})
  expect(screen.queryByRole('option',{name:'candidate'})).toBeNull()
 })
 it('validates bounds, finite numbers, integers, required fields and hostile object properties', () => {
  expect(() => parseToolArguments(schema,{datetime_utc:'x',max_cells:'2.5'})).toThrow('целое')
  expect(() => parseToolArguments(schema,{datetime_utc:'x',object_height:'Infinity'})).toThrow('конечное')
  expect(() => parseToolArguments(schema,{datetime_utc:'x',object_height:'0'})).toThrow('меньше')
  expect(() => parseToolArguments(schema,{})).toThrow('обязательное')
  expect(() => parseToolArguments(schema,{datetime_utc:'x',titles:'[123]'})).toThrow('нужен текст')
  const nested: InputSchema={type:'object',properties:{value:{type:'object',properties:{safe:{type:'string'}},additionalProperties:false}},required:['value']}
  expect(() => parseToolArguments(nested,{value:'{"__proto__":{"secret":true}}'})).toThrow('имя поля')
 })
})

describe('actual local computation evidence presentation', () => {
 it('shows derived TikTok UTC without treating it as independently verified publication', () => {
  dialog({capability:'tiktok_timestamp',video_id:'6854717870488702213',date_utc:'2020-07-29T02:06:13Z',timestamp_unix:1595988373})
  expect(screen.getByText('2020-07-29T02:06:13Z')).toBeInTheDocument()
  expect(screen.getByText(/Публикация, автор и существование видео независимо не проверены/)).toBeInTheDocument()
  expect(sourceLabel(source({capability:'tiktok_timestamp'}))).toBe('Локальное вычисление выполнено')
 })
 it('shows real shadow cells on a bounded coordinate SVG with residual not probability semantics', () => {
  dialog({capability:'shadow_regions',datetime_utc:'2024-02-29T13:59:59Z',observed_sun_altitude_deg:63.43,grid_step_deg:2,tolerance_fraction:.1,matching_cells_total:200,matching_cells_returned:1,truncated:true,regions:{type:'FeatureCollection',features:[{geometry:{type:'Polygon',coordinates:[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}}]},candidate_scores:[{latitude:1,longitude:1,compatibility_score:.8,matches_tolerance:true}]})
  expect(screen.getByRole('img',{name:'Координатная схема подходящих ячеек ShadowFinder'}).querySelectorAll('polygon')).toHaveLength(1)
  expect(screen.getByText(/Подходят: 200/)).toHaveTextContent('результат ограничен')
  expect(screen.getByText(/геометрический остаток, не вероятность/)).toBeInTheDocument()
 })
 it('bounds rendered polygons and rejects invalid coordinate output', () => {
  const features=Array.from({length:250},() => ({geometry:{type:'Polygon',coordinates:[[[0,0],[2,0],[2,2],[0,0]]]}}))
  dialog({capability:'shadow_regions',regions:{features:[{geometry:{type:'Polygon',coordinates:[[[999,0],[1,1],[2,2],[999,0]]]}},...features]}})
  expect(screen.getByRole('img').querySelectorAll('polygon')).toHaveLength(199)
 })
 it('shows evidence-backed directed graph relations and requests real neighbours through tool_run', async () => {
  dialog({capability:'evidence_graph',total_entities:2,total_relations:1,entities:[{id:'ent_profile',type:'public_profile',label:'Public profile',evidence_ids:['ev_one']},{id:'ent_name',type:'username',label:'same_nick',evidence_ids:['ev_one']}],relations:[{from_id:'ent_profile',to_id:'ent_name',relation_type:'uses_public_identifier',verification_status:'source_reported',evidence_ids:['ev_one']}]})
  expect(screen.getByText(/Граф отражает отношения источников/)).toBeInTheDocument()
  expect(screen.getByText('Использует публичный идентификатор →')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button',{name:'Показать соседей'})[0])
  await waitFor(() => expect(act).toHaveBeenCalledWith('tool_run',{tool:'evidence_graph',arguments:{offset:0,entity_id:'ent_profile',limit:50}}))
 })
 it('preserves graph filters and scope when loading the next backend page', async () => {
  dialog({capability:'evidence_graph',total_entities:80,total_relations:1,entities:[],relations:[],next_offset:50,request_arguments:{entity_id:'ent_scope',entity_types:['domain'],evidence_ids:['ev_source'],limit:50}})
  fireEvent.click(screen.getByRole('button',{name:'Следующая страница графа'}))
  await waitFor(() => expect(act).toHaveBeenCalledWith('tool_run',{tool:'evidence_graph',arguments:{entity_id:'ent_scope',entity_types:['domain'],evidence_ids:['ev_source'],offset:50,limit:50}}))
 })
 it('paginates classified titles instead of mounting hundreds of rows and preserves original title text', () => {
  dialog({capability:'role_classify',results:Array.from({length:60},(_,index) => ({title:`Actual title ${index}`,role_level:'Staff',division:'General'}))})
  expect(screen.getByText('Actual title 0')).toBeInTheDocument();expect(screen.queryByText('Actual title 20')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'Далее'}))
  expect(screen.getByText('Actual title 20')).toBeInTheDocument();expect(screen.queryByText('Actual title 0')).toBeNull()
 })
 it('shows model raw scores as hypotheses without invented confidence percentages', () => {
  dialog({capability:'geoclip_predict',predictions:[{rank:1,lat:55.75,lon:37.62,raw_score:.45}]})
  expect(screen.getByText(/не являются калиброванной вероятностью/)).toBeInTheDocument()
  expect(screen.getByText('55,75')).toBeInTheDocument()
  expect(screen.getByText('37,62')).toBeInTheDocument()
  expect(screen.queryByText('45%')).toBeNull()
  expect(screen.getByText('Географическая гипотеза модели')).toBeInTheDocument()
  expect(screen.getByRole('img',{name:'Координатная схема географических гипотез модели'}).querySelector('circle')).toHaveAttribute('cx','217.62')
  expect(screen.getByText(/Маркер не подтверждает место съёмки/)).toBeInTheDocument()
 })
 it('bounds model map markers and ignores out of range or nonfinite coordinates', () => {
  dialog({capability:'waypoint_predict',predictions:[{lat:91,lon:0},{lat:NaN,lon:0},...Array.from({length:30},(_,index) => ({lat:index,lon:-index}))]})
  expect(screen.getByRole('img',{name:'Координатная схема географических гипотез модели'}).querySelectorAll('circle')).toHaveLength(18)
 })
 it('displays only a local raster data preview for the analysed image', () => {
  const draw=dialog({capability:'geoclip_predict',preview:'data:image/jpeg;base64,AQIDBA==',predictions:[]})
  expect(screen.getByRole('img',{name:'Локальное изображение, использованное для визуального анализа'})).toHaveAttribute('src','data:image/jpeg;base64,AQIDBA==')
  draw.unmount()
  dialog({capability:'geoclip_predict',preview:'https://example.org/tracker.jpg',predictions:[]})
  expect(screen.queryByRole('img',{name:'Локальное изображение, использованное для визуального анализа'})).toBeNull()
 })
 it('shows actual matching and geometry counts without labelling them geographic predictions', () => {
  dialog({capability:'waypoint_match',match_count:12,keypoints:[40,50],geometry:{state:'estimated',method:'normalized_eight_point_ransac',inliers:9,inlier_ratio:.75,threshold_px:3}})
  expect(screen.getByText('Локальное сопоставление изображений')).toBeInTheDocument()
  expect(screen.getByText('12')).toBeInTheDocument()
  expect(screen.getByText('9')).toBeInTheDocument()
  expect(screen.getByText('40 / 50')).toBeInTheDocument()
  expect(screen.getByText('Модель геометрии рассчитана')).toBeInTheDocument()
  expect(screen.queryByText('75%')).toBeNull()
  expect(screen.queryByText('Визуальные географические кандидаты')).toBeNull()
  expect(sourceLabel({...source({capability:'waypoint_match'}),status:'hypothesis'})).toBe('Локальное сопоставление изображений')
 })
 it('shows measured model-to-metadata distance as a screening comparison without verifying metadata or declaring an error', () => {
  dialog({capability:'visual_geoint_comparison',review_threshold_km:100,distances:[{from_label:'EXIF GPS (не проверен)',to_label:'geoclip_predict #1',distance_km:111.195,screening_distance_only:true}]})
  expect(screen.getByText('111,195')).toBeInTheDocument()
  expect(screen.getByText('Расхождение для ручной проверки')).toBeInTheDocument()
  expect(screen.getByText(/Расхождение не устанавливает ошибку источника/)).toBeInTheDocument()
  expect(screen.getByText(/EXIF GPS может быть изменён/)).toBeInTheDocument()
  expect(screen.getByText(/модели не являются независимыми подтверждениями/)).toBeInTheDocument()
 })
})

describe('optional local model settings preserve truthful state and explicit actions', () => {
 const draw=(visual: typeof emptyState.visual_models) => render(<Tooltip.Provider><SourceSettings state={{...emptyState,visual_models:visual}} value={(_,fallback) => fallback ?? ''} set={vi.fn()} save={vi.fn()}/></Tooltip.Provider>)
 it('does not claim missing models ready or manufacture download percentages', () => {
  draw({state:'not_installed',installed:false,available:false,automatic_download:false,download_bytes:1048576,device:'cpu'})
  fireEvent.click(screen.getByText('Локальные визуальные модели GEOINT'))
  expect(screen.getByText('Не установлен')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Установить модели'}))
  expect(act).toHaveBeenCalledWith('visual_install')
  expect(screen.getByRole('button',{name:'Проверить локальный запуск'})).toBeDisabled()
 })
 it('shows received bytes and allows cancellation during actual installation', () => {
  draw({state:'downloading',installed:false,available:false,automatic_download:false,installing:true,progress:{artifact:'geoclip_weights.pth',downloaded_bytes:1048576,total_bytes:4194304}})
  fireEvent.click(screen.getByText('Локальные визуальные модели GEOINT'))
  expect(screen.getByRole('status')).toHaveTextContent('geoclip_weights.pth: получено 1 МиБ из 4 МиБ')
  fireEvent.click(screen.getByRole('button',{name:'Остановить'}));expect(act).toHaveBeenCalledWith('visual_cancel')
  expect(screen.getByRole('button',{name:'Удалить локальные модели'})).toBeDisabled()
  expect(screen.queryByText('25%')).toBeNull()
 })
 it('requests runtime removal through the native confirmation action only when idle', () => {
  draw({state:'installed',installed:true,available:false,automatic_download:false,device:'cpu'})
  fireEvent.click(screen.getByText('Локальные визуальные модели GEOINT'))
  fireEvent.click(screen.getByRole('button',{name:'Удалить локальные модели'}))
  expect(act).toHaveBeenCalledWith('visual_remove')
 })
 it('keeps Nuclei opt-in disabled initially and explains restricted scope', () => {
  draw(undefined)
  expect(screen.getByLabelText(/Разрешить ограниченную проверку Nuclei/)).not.toBeChecked()
  expect(screen.getByText(/Только ограниченное HTTP HEAD-наблюдение/)).toBeInTheDocument()
 })
})
