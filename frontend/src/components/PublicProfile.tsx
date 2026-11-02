import type { Source } from '../types'

const scalar=(value:unknown)=>typeof value==='string'||typeof value==='number'?String(value):typeof value==='boolean'?(value?'Да':'Нет'):'Не предоставлено'
export function PublicProfile({source}:{source:Source}) {
  const data=source.details||{}
  if(!['vk_public','tiktok_public_profile'].includes(String(data.capability||'')))return null
  const tiktok=data.capability==='tiktok_public_profile'
  const fields=tiktok?[
    ['Имя автора',data.nickname],['uniqueId',data.uniqueId],['userId',data.userId],['secUid',data.secUid],
    ['Тип входа',data.input_kind==='video'?'Видео':'Профиль'],['ID видео',data.video_id],
    ['Описание',data.signature],['Регион',data.region],['Язык',data.language],
    ['Верификация аккаунта',data.verified],['Дата создания аккаунта',data.accountCreationTimestamp]
  ]:[['Название',data.display_name],['ID из входного URL',data.profile_id||data.community_id],['Screen name из URL',data.screen_name],['Описание',data.description]]
  return <section className="geoint-observation" aria-label="Публичные поля профиля"><h3>{tiktok?'TikTok':'VK'} · полученные поля</h3>
    <dl className="details-list">{fields.map(([label,value])=><div key={String(label)}><dt>{String(label)}</dt><dd>{scalar(value)}</dd></div>)}</dl>
    {tiktok&&data.counters==null&&<p className="muted">Счётчики не предоставлены этим ответом. Это не нулевые значения.</p>}
    {tiktok&&<p className="muted">Время video ID не является датой создания аккаунта.</p>}
    <details className="technical-details"><summary>JSON полученных полей</summary><pre>{JSON.stringify(data,null,2)}</pre></details>
  </section>
}
