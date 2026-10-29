import { useEffect, useState } from 'react'
import { act } from '../bridge'
import type { Source } from '../types'
import { Button } from './ui'
import './structured-tools.css'

type Row = Record<string, unknown>
const object = (value: unknown): Row => value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {}
const rows = (value: unknown): Row[] => Array.isArray(value) ? value.filter(item => item && typeof item === 'object' && !Array.isArray(item)) as Row[] : []
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : '—'
const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('ru-RU', { maximumFractionDigits: 5 }) : '—'
const labels: Record<string, string> = { username:'Никнейм', public_profile:'Публичный профиль', organization:'Организация', domain:'Домен', public_post:'Публикация', geographic_candidate:'Географическая гипотеза', image:'Изображение', coordinate:'Координаты', repository:'Репозиторий', uses_public_identifier:'Использует публичный идентификатор', published_on_domain:'Опубликовано на домене', profile_mentions_organization:'Профиль упоминает организацию', has_geographic_hypothesis:'Есть географическая гипотеза', metadata_reports_coordinate:'Метаданные сообщают координаты', source_attributes_authorship:'Источник указывает автора', historically_published_contact:'Исторически опубликованный контакт', source_labels_address:'Источник присвоил метку', source_reported:'Сообщено источником', self_reported:'Указано в профиле', model_hypothesis:'Гипотеза модели', unverified_metadata:'Метаданные не проверены', unverified_label:'Метка не проверена' }

function CoordinatePreview({ regions }: { regions: Row }) {
  const features = rows(regions.features)
  const polygons: string[] = []
  for (const feature of features.slice(0, 200)) {
    const geometry = object(feature.geometry)
    if (geometry.type !== 'Polygon' || !Array.isArray(geometry.coordinates)) continue
    const ring = geometry.coordinates[0]
    if (!Array.isArray(ring) || ring.length > 20) continue
    const points: string[] = []
    for (const point of ring) {
      if (!Array.isArray(point) || point.length < 2 || typeof point[0] !== 'number' || typeof point[1] !== 'number' || !Number.isFinite(point[0] + point[1]) || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) break
      points.push(`${point[0] + 180},${90 - point[1]}`)
    }
    if (points.length === ring.length && points.length >= 4) polygons.push(points.join(' '))
  }
  if (!polygons.length) return null
  return <><svg className="coordinate-preview" viewBox="0 0 360 180" role="img" aria-label="Координатная схема подходящих ячеек ShadowFinder"><title>Координатная схема, без картографической подложки</title>{[45,90,135].map(y => <line key={`y${y}`} x1="0" x2="360" y1={y} y2={y}/>)}{[90,180,270].map(x => <line key={`x${x}`} y1="0" y2="180" x1={x} x2={x}/>)}{polygons.map((points, index) => <polygon key={index} points={points}/>)}</svg><small className="muted">Координатная схема без подложки: запад −180° → восток 180°, север сверху. Первые {polygons.length} сохранённых ячеек; это неоднозначные геометрические кандидаты.</small></>
}

function PredictionCoordinatePreview({ predictions }: { predictions: Row[] }) {
  const points = predictions.slice(0, 20).flatMap((row, index) => {
    const lat = row.latitude ?? row.lat
    const lon = row.longitude ?? row.lon
    if (typeof lat !== 'number' || typeof lon !== 'number' || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return []
    return [{ lat, lon, rank: row.rank ?? index + 1 }]
  })
  if (!points.length) return null
  return <figure className="prediction-coordinate-figure"><svg className="coordinate-preview prediction-coordinate-preview" viewBox="0 0 360 180" role="img" aria-label="Координатная схема географических гипотез модели"><title>Гипотезы модели на координатной сетке без картографической подложки</title>{[45,90,135].map(y => <line key={`y${y}`} x1="0" x2="360" y1={y} y2={y}/>)}{[90,180,270].map(x => <line key={`x${x}`} y1="0" y2="180" x1={x} x2={x}/>)}{points.map((point, index) => <g key={index} className="prediction-coordinate-point"><title>Кандидат {text(point.rank)}: {number(point.lat)}, {number(point.lon)} · гипотеза</title><circle cx={point.lon + 180} cy={90 - point.lat} r="2.5"/><text x={Math.min(350, Math.max(4, point.lon + 184))} y={Math.min(174, Math.max(8, 87 - point.lat))}>{text(point.rank)}</text></g>)}</svg><figcaption className="muted">Гипотезы модели на координатной сетке без подложки. Номера соответствуют рангам таблицы; запад −180° → восток 180°, север сверху. Показано {points.length} кандидатов. Маркер не подтверждает место съёмки.</figcaption></figure>
}

export function LocalObservation({ source, onNavigate }: { source: Source; onNavigate?(): void }) {
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [source.evidence_id])
  const detail = source.details || {}
  const nested = object(detail.source_record)
  const data = Object.keys(nested).length ? nested : detail
  const capability = String(data.capability || detail.capability || data.tool || '')
  const previewValue = detail.preview ?? data.preview
  const preview = typeof previewValue === 'string' && previewValue.length <= 300000 && /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(previewValue) ? previewValue : ''
  const entities = rows(data.entities)
  const relations = rows(data.relations)
  const graph = capability === 'evidence_graph' || Array.isArray(data.entities) && Array.isArray(data.relations)
  const predictions = rows(data.predictions)
  const distances = rows(data.distances)
  const titleRows = rows(data.results)
  const geometry = object(data.geometry)
  const geometryStates: Record<string, string> = { estimated: 'Модель геометрии рассчитана', insufficient_matches: 'Недостаточно совпадений для геометрии', degenerate: 'Геометрия не определена' }
  const shadow = capability === 'shadow_regions'
  const openGraph = async (args: Record<string, unknown>) => {
    if (await act('route', { route: 'search' }) === null) return
    onNavigate?.()
    await act('tool_run', { tool: 'evidence_graph', arguments: args })
  }
  if (!graph && !shadow && capability !== 'tiktok_timestamp' && capability !== 'role_classify' && !predictions.length && !['geoclip_predict','waypoint_predict','waypoint_match','visual_geoint_comparison'].includes(capability)) return null
  return <section className="local-observation" aria-label="Структурированный результат инструмента">
    {preview && ['geoclip_predict','waypoint_predict','waypoint_match'].includes(capability) && <figure className="local-image-preview"><img src={preview} alt="Локальное изображение, использованное для визуального анализа"/><figcaption className="muted">Изображение, использованное для локального расчёта.</figcaption></figure>}
    {capability === 'tiktok_timestamp' && <><h3>Время из TikTok ID</h3><dl className="details-list"><div><dt>Video ID</dt><dd className="monospace">{text(data.video_id)}</dd></div><div><dt>Дата UTC</dt><dd>{text(data.date_utc)}</dd></div><div><dt>Unix seconds</dt><dd>{text(data.timestamp_unix)}</dd></div></dl><p className="muted">Время закодировано в поддержанном формате ID. Публикация, автор и существование видео независимо не проверены.</p></>}
    {capability === 'role_classify' && <><h3>Классификация должностей</h3><div className="markdown-table"><table><thead><tr><th>Исходный текст</th><th>Уровень</th><th>Направление</th></tr></thead><tbody>{titleRows.slice(page * 20, page * 20 + 20).map((row, index) => <tr key={index}><td>{text(row.title)}</td><td>{text(row.role_level)}</td><td>{text(row.division)}</td></tr>)}</tbody></table></div><Pages count={titleRows.length} page={page} setPage={setPage}/><p className="muted">Эвристика по тексту, не подтверждение трудоустройства или реальной оргструктуры.</p></>}
    {shadow && <><h3>ShadowFinder · солнечная геометрия</h3><dl className="details-list"><div><dt>Время UTC</dt><dd>{text(data.datetime_utc)}</dd></div><div><dt>Высота Солнца</dt><dd>{number(data.observed_sun_altitude_deg)}°</dd></div><div><dt>Шаг сетки</dt><dd>{number(data.grid_step_deg)}°</dd></div><div><dt>Относительный допуск</dt><dd>{number(data.tolerance_fraction)}</dd></div><div><dt>Ячейки</dt><dd>Подходят: {text(data.matching_cells_total)} · сохранено: {text(data.matching_cells_returned)}{data.truncated === true ? ' · результат ограничен' : ''}</dd></div></dl><CoordinatePreview regions={object(data.regions)}/>{rows(data.candidate_scores).length > 0 && <div className="markdown-table"><table><thead><tr><th>Кандидат</th><th>Широта, долгота</th><th>Совместимость</th></tr></thead><tbody>{rows(data.candidate_scores).slice(0, 20).map((row, index) => <tr key={index}><td>{text(row.label)}</td><td>{number(row.latitude)}, {number(row.longitude)}</td><td>{number(row.compatibility_score)} · {row.matches_tolerance ? 'в допуске' : 'вне допуска'}</td></tr>)}</tbody></table></div>}<p className="muted">Совместимость — геометрический остаток, не вероятность местоположения. Расчёт по известным времени и измерениям не устанавливает место фотографии.</p></>}
    {graph && <><h3>Сущности и связи свидетельств</h3><p>{text(data.total_entities)} сущностей · {text(data.total_relations)} связей{data.next_offset != null ? ' · есть следующая страница' : ''}</p><ul className="graph-entity-list">{entities.slice(page * 20, page * 20 + 20).map((entity, index) => <li key={String(entity.id || index)}><strong>{text(entity.label)}</strong><small>{labels[String(entity.type)] || text(entity.type)} · {text(entity.id)}</small><small>Основания: {Array.isArray(entity.evidence_ids) ? entity.evidence_ids.map(text).join(', ') : 'не указаны'}</small>{typeof entity.id === 'string' && <Button variant="ghost" size="sm" onClick={() => void openGraph({ ...object(data.request_arguments), offset: 0, entity_id: entity.id, limit: 50 })}>Показать соседей</Button>}</li>)}</ul><Pages count={entities.length} page={page} setPage={setPage}/><details><summary>Направленные связи · {relations.length}</summary><div className="markdown-table"><table><thead><tr><th>От</th><th>Отношение</th><th>К</th><th>Основание / статус</th></tr></thead><tbody>{relations.slice(0, 50).map((relation, index) => <tr key={index}><td>{text(entities.find(entity => entity.id === relation.from_id)?.label || relation.from_id)}</td><td>{labels[String(relation.relation_type)] || text(relation.relation_type)} →</td><td>{text(entities.find(entity => entity.id === relation.to_id)?.label || relation.to_id)}</td><td>{Array.isArray(relation.evidence_ids) ? relation.evidence_ids.map(text).join(', ') : '—'} · {labels[String(relation.verification_status)] || text(relation.verification_status)}</td></tr>)}</tbody></table></div>{relations.length > 50 && <small>Первые 50 связей; остальные сохранены в деталях доказательства.</small>}</details><p className="muted">Граф отражает отношения источников. Одинаковый никнейм, название сервиса или модельный score не устанавливают общую личность.</p>{typeof data.next_offset === 'number' && <Button variant="secondary" size="sm" onClick={() => void openGraph({ ...object(data.request_arguments), offset: data.next_offset, limit: 50 })}>Следующая страница графа</Button>}</>}
    {(predictions.length > 0 || ['geoclip_predict','waypoint_predict'].includes(capability)) && <><h3>Визуальные географические кандидаты</h3><PredictionCoordinatePreview predictions={predictions}/><div className="markdown-table"><table><thead><tr><th>Ранг</th><th>Широта</th><th>Долгота</th><th>Оценка модели</th></tr></thead><tbody>{predictions.slice(0, 20).map((row, index) => <tr key={index}><td>{text(row.rank ?? index + 1)}</td><td>{number(row.latitude ?? row.lat)}</td><td>{number(row.longitude ?? row.lon)}</td><td>{number(row.raw_score ?? row.score)}</td></tr>)}</tbody></table></div>{!predictions.length && <p>Модель не вернула географических кандидатов.</p>}<p className="muted">Ранг и raw score не являются калиброванной вероятностью. Координаты — гипотезы модели, а не подтверждённое место съёмки.</p></>}
    {capability === 'waypoint_match' && <><h3>Сопоставление изображений</h3><dl className="details-list"><div><dt>Совпадения признаков</dt><dd>{text(data.match_count)}</dd></div>{Array.isArray(data.keypoints) && <div><dt>Ключевые точки изображений</dt><dd>{data.keypoints.map(text).join(' / ')}</dd></div>}<div><dt>Геометрическая проверка</dt><dd>{geometryStates[String(geometry.state)] || text(geometry.state)}</dd></div><div><dt>Геометрически согласованные пары</dt><dd>{text(geometry.inliers)}</dd></div>{typeof geometry.method === 'string' && <div><dt>Метод</dt><dd>{text(geometry.method)}</dd></div>}{typeof geometry.threshold_px === 'number' && <div><dt>Порог геометрии</dt><dd>{number(geometry.threshold_px)} px</dd></div>}</dl><p className="muted">Сходство и согласованность признаков сами по себе не подтверждают координаты или одно место. Геометрия рассчитана в координатах уменьшенных изображений; оценки не являются вероятностью.</p></>}
    {capability === 'visual_geoint_comparison' && <><h3>Сравнение географических наблюдений</h3><div className="markdown-table"><table><thead><tr><th>Наблюдение</th><th>Сопоставлено с</th><th>Расстояние, км</th><th>Проверка</th></tr></thead><tbody>{distances.slice(0, 30).map((row, index) => <tr key={index}><td>{text(row.from_label)}</td><td>{text(row.to_label)}</td><td>{number(row.distance_km)}</td><td>{row.screening_distance_only === true ? 'Расхождение для ручной проверки' : 'В пределах порога сравнения'}</td></tr>)}</tbody></table></div>{!distances.length && <p>Недостаточно координат для сравнения.</p>}<p className="muted">Порог {number(data.review_threshold_km)} км используется только для предварительного сравнения расстояний. Расхождение не устанавливает ошибку источника. EXIF GPS может быть изменён и не подтверждает подлинность места съёмки; модели не являются независимыми подтверждениями.</p></>}
  </section>
}
function Pages({ count, page, setPage }: { count: number; page: number; setPage(page: number): void }) {
  if (count <= 20) return null
  return <nav className="local-result-pages" aria-label="Страницы вычисленного результата"><Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</Button><span>{page * 20 + 1}–{Math.min(page * 20 + 20, count)} из {count}</span><Button variant="ghost" size="sm" disabled={(page + 1) * 20 >= count} onClick={() => setPage(page + 1)}>Далее</Button></nav>
}


