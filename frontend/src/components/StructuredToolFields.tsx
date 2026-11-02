import type { InputSchema } from '../types'
import './structured-tools.css'

export const parameterLabels: Record<string, string> = {
  target: 'Профиль или публичная ссылка', names: 'Названия операций',
  value: 'URL или идентификатор', datetime_utc: 'Дата и время с часовым поясом', object_height: 'Высота объекта', shadow_length: 'Длина тени',
  sun_altitude_deg: 'Высота Солнца над горизонтом, °', tolerance_fraction: 'Относительная погрешность', grid_step_deg: 'Шаг координатной сетки, °',
  bounds: 'Область [запад, юг, восток, север]', max_cells: 'Максимум ячеек в результате', candidates: 'Географические кандидаты', titles: 'Тексты должностей',
  entity_id: 'ID сущности для просмотра соседей', evidence_ids: 'ID сохранённых свидетельств', entity_types: 'Типы сущностей', limit: 'Лимит результатов', offset: 'Пропустить записей',
  email: 'Email', domain: 'Домен', max_snapshots: 'Максимум архивных снимков', url: 'Публичный URL', query: 'Поисковая фраза', author: 'Автор', subreddit: 'Subreddit',
  after: 'После даты UTC', before: 'До даты UTC', attachment_id: 'Идентификатор выбранного изображения', top_k: 'Число кандидатов',
  reference_id: 'Идентификатор изображения для сравнения', samples: 'Число сэмплов модели', seed: 'Seed воспроизводимого расчёта',
  methods: 'Локальные модели', include_ocr: 'Включить локальное OCR', shadow: 'Параметры солнечной геометрии',
}

export function validateValue(value: unknown, schema: InputSchema, name: string, depth = 0): void {
  if (depth > 5) throw new Error(`${name}: слишком глубокая структура.`)
  const fail = (reason: string): never => { throw new Error(`${name}: ${reason}`) }
  if (schema.enum && !schema.enum.includes(value as string | number | boolean)) fail('выберите допустимое значение.')
  if (schema.type === 'string') {
    if (typeof value !== 'string') fail('нужен текст.')
    const text = value as string
    if (schema.minLength != null && text.length < schema.minLength) fail(`минимум ${schema.minLength} символов.`)
    if (schema.maxLength != null && text.length > schema.maxLength) fail(`максимум ${schema.maxLength} символов.`)
  } else if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value) || schema.type === 'integer' && !Number.isInteger(value)) fail(schema.type === 'integer' ? 'нужно целое число.' : 'нужно конечное число.')
    const number = value as number
    if (schema.minimum != null && number < schema.minimum || schema.exclusiveMinimum != null && number <= schema.exclusiveMinimum) fail('число меньше допустимого.')
    if (schema.maximum != null && number > schema.maximum || schema.exclusiveMaximum != null && number >= schema.exclusiveMaximum) fail('число больше допустимого.')
  } else if (schema.type === 'boolean') {
    if (typeof value !== 'boolean') fail('нужно true или false.')
  } else if (schema.type === 'array') {
    if (!Array.isArray(value)) fail('нужен JSON-массив в квадратных скобках.')
    const values = value as unknown[]
    if (schema.minItems != null && values.length < schema.minItems || schema.maxItems != null && values.length > schema.maxItems) fail('неверное число элементов.')
    if (values.length > 2000) fail('слишком много элементов.')
    if (schema.items) values.forEach((item, index) => validateValue(item, schema.items!, `${name}[${index}]`, depth + 1))
  } else if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail('нужен JSON-объект.')
    const object = value as Record<string, unknown>
    for (const key of schema.required || []) if (!(key in object)) fail(`нет обязательного поля ${key}.`)
    for (const [key, item] of Object.entries(object)) {
      if (['__proto__', 'prototype', 'constructor'].includes(key)) fail('недопустимое имя поля.')
      if (schema.properties?.[key]) validateValue(item, schema.properties[key], `${name}.${key}`, depth + 1)
      else if (schema.additionalProperties === false) fail(`неизвестное поле ${key}.`)
    }
  }
}

export function parseToolArguments(schema: InputSchema, draft: Record<string, string>): Record<string, unknown> {
  const result: Record<string, unknown> = Object.create(null)
  for (const [name, field] of Object.entries(schema.properties || {})) {
    const raw = draft[name]
    if (raw === undefined || !raw.trim()) {
      if (schema.required?.includes(name)) throw new Error(`${parameterLabels[name] || name}: заполните обязательное поле.`)
      continue
    }
    if (raw.length > 30000) throw new Error(`${parameterLabels[name] || name}: слишком большой ввод.`)
    let value: unknown = raw
    if (['array', 'object', 'boolean'].includes(field.type || '')) {
      try { value = JSON.parse(raw) } catch { throw new Error(`${parameterLabels[name] || name}: некорректный JSON.`) }
    } else if (field.type === 'number' || field.type === 'integer') value = Number(raw)
    validateValue(value, field, parameterLabels[name] || name)
    result[name] = value
  }
  validateValue(result, schema, 'Параметры')
  return result
}

export function StructuredToolFields({ schema, draft, onChange, disabled }: { schema: InputSchema; draft: Record<string, string>; onChange(name: string, value: string): void; disabled?: boolean }) {
  return <div className="structured-tool-fields" aria-label="Параметры выбранного инструмента">{Object.entries(schema.properties || {}).slice(0, 32).map(([name, field]) => {
    const label = parameterLabels[name] || name
    const required = !!schema.required?.includes(name)
    const complex = field.type === 'array' || field.type === 'object'
    const value = draft[name] || ''
    const id = `tool-parameter-${name}`
    return <label className={`structured-tool-field ${complex ? 'is-complex' : ''}`} key={name} htmlFor={id}><span>{label}{required && <span aria-hidden="true"> *</span>}</span>
      {field.enum || field.type === 'boolean' ? <select id={id} aria-label={label} value={value} required={required} disabled={disabled} onChange={event => onChange(name, event.target.value)}><option value="">{required ? 'Выберите значение' : 'Не задано'}</option>{(field.enum || [true, false]).map(option => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select>
        : complex ? <textarea id={id} aria-label={label} rows={3} value={value} required={required} disabled={disabled} spellCheck={false} placeholder={name === 'titles' ? '["Chief Executive Officer", "Senior Engineer"]' : name === 'bounds' ? '[-180, -60, 180, 85]' : field.type === 'array' ? '[]' : '{}'} onChange={event => onChange(name, event.target.value)}/>
        : <input id={id} aria-label={label} type={field.type === 'number' || field.type === 'integer' ? 'number' : 'text'} step={field.type === 'integer' ? 1 : 'any'} min={field.minimum} max={field.maximum} maxLength={field.maxLength} value={value} required={required} disabled={disabled} spellCheck={false} placeholder={name === 'datetime_utc' ? '2024-02-29T13:59:59Z' : undefined} onChange={event => onChange(name, event.target.value)}/>}
      {field.description && <small>{field.description}</small>}{complex && <small>JSON{field.minItems != null || field.maxItems != null ? ` · элементов ${field.minItems ?? 0}–${field.maxItems ?? '…'}` : ''}</small>}
    </label>
  })}<p className="field-hint">* Обязательные поля. Пустые необязательные поля не передаются. Параметры повторно проверяет приложение.</p></div>
}
