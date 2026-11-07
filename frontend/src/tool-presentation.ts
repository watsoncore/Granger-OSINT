import type { Tool } from './types'

const names: Record<string, string> = {
  saved_investigation:'Сохранённое расследование',
  email_research:'Исследовать email',company_research:'Исследовать компанию',company_gleif:'GLEIF · LEI',company_sec:'SEC EDGAR',company_companies_house:'Companies House',company_opencorporates:'OpenCorporates',company_opensanctions:'OpenSanctions · кандидаты',publication_crossref:'Crossref · публикации',software_osv:'OSV · запись об уязвимости',
  map_panoramax:'Panoramax · эталонные фотографии', x_profile:'Публичный профиль X', nuclei_check:'Nuclei · разрешённое наблюдение заголовков',
  visual_geoint:'GEOINT · последовательный анализ изображения', geoclip_predict:'GeoCLIP · географические гипотезы', waypoint_predict:'Waypoint · географические гипотезы', waypoint_match:'Waypoint · сопоставление изображений',
  tiktok_timestamp:'TikTok · время из ID', shadow_regions:'ShadowFinder · солнечная геометрия', role_classify:'Классификация должностей', evidence_graph:'Сущности и связи', mail_dns:'MailAccess · DNS домена', historical_contacts:'Исторические контакты', x_post:'Публичный пост X', arctic_posts:'Arctic Shift · публикации', arctic_comments:'Arctic Shift · комментарии',
  image_metadata:'EXIF и признаки изображения', image_ocr:'Распознавание текста', image_compare:'Локальные дубликаты', map_geocode:'Nominatim', map_overpass:'OpenStreetMap · Overpass', map_wikimedia:'Wikimedia Commons', github_repository:'GitHub · репозиторий', threat_feodo:'Feodo Tracker', hash_virustotal:'VirusTotal · SHA-256',
  web_search: 'Веб-поиск', web_read: 'Чтение страницы', browser_read: 'Чтение в браузере',
  username_maigret: 'Maigret', username_blackbird: 'Blackbird', username_social_analyzer: 'Social Analyzer', username_snoop: 'Snoop', email_holehe: 'Holehe', phone_metadata: 'PhoneInfoga', blockchain_gansar: 'Gansar', web_archive: 'Wayback Machine', telegram_public: 'Telegram', vk_public: 'VK', instagram_public: 'Instagram', domain_lookup: 'Домен · DNS и RDAP', ip_lookup: 'IP · ASN и префикс',
  evidence_get: 'Сохранённые доказательства', tools_list: 'Доступность инструментов',
  maigret: 'Maigret', blackbird: 'Blackbird', social_analyzer: 'Social Analyzer', snoop: 'Snoop',
  holehe: 'Holehe', phoneinfoga: 'PhoneInfoga', gansar: 'Gansar',
  telegram: 'Telegram', telegram_lookup: 'Telegram', vk: 'VK', vk_lookup: 'VK', instagram: 'Instagram', instagram_lookup: 'Instagram',
  google: 'Google', google_dork: 'Операторы Google', blockchain: 'Блокчейн', ton: 'TON',
}
const states: Record<string, string> = {
  source_reported:'Сообщено источником',
  ready_local:'Локально готов',live_verified:'Проверен запросом',configuration_required:'Нужна настройка',authentication_required:'Нужна авторизация',catalog_only:'Кандидат каталога',temporarily_unavailable:'Временно недоступен',
  ready: 'Готов', available: 'Готов', installed: 'Готов', checking: 'Проверяется', unverified: 'Ещё не проверен', configured_unverified: 'Настроен, доступ не проверен',
  auth_required: 'Нужна авторизация', needs_auth: 'Нужна авторизация', missing_credentials: 'Нужна авторизация',
  missing: 'Нет зависимости', missing_dependency: 'Нет зависимости', dependency_missing: 'Нет зависимости', not_installed: 'Не установлен',
  configuration_error: 'Ошибка настройки', config_error: 'Ошибка настройки', invalid_config: 'Ошибка настройки',
  unavailable: 'Сервис недоступен', service_unavailable: 'Сервис недоступен', rate_limited: 'Ограничение сервиса', restricted: 'Ограничение сервиса',
  unsupported: 'Не поддерживается', unsupported_environment: 'Не поддерживается', disabled: 'Отключён', error: 'Ошибка проверки',
  running: 'Выполняется', started: 'Выполняется', success: 'Завершено', completed: 'Завершено', done: 'Завершено',
  failed: 'Ошибка', cancelled: 'Остановлено', stopped: 'Остановлено', pending: 'Ожидание', waiting: 'Ожидание',
  partial: 'Частичный результат', not_found: 'Совпадений нет', found: 'Есть находки', detected: 'Есть находки', complete: 'Завершено', empty: 'Совпадений нет', timeout: 'Превышено время ожидания',
}
const inputTypes: Record<string, string> = { chronology:'TikTok video ID или URL', geoint_geometry:'Известные время и геометрия тени', social_analytics:'Тексты должностей', graph:'Сохранённые свидетельства', x_post:'URL поста X', reddit:'Автор или subreddit', visual_geoint:'Выбранное изображение', image:'Идентификатор вложения',coordinates:'Координаты или топоним',repository:'owner/repository',hash:'SHA-256', ip: 'IP-адрес', dork: 'Поисковый запрос', username: 'Никнейм', email: 'Email', phone: 'Телефон', url: 'Веб-адрес', domain: 'Домен', web: 'Поисковый запрос', query: 'Поисковый запрос', telegram: 'Telegram ID', vk: 'VK ID', instagram: 'Instagram', blockchain: 'Адрес кошелька', evidence: 'Доказательство', any: 'Открытые данные', none: 'Без параметров' }
export function toolName(id: string, displayName?: string) { return displayName || names[id] || id.replace(/_/g, ' ') }
export function stateLabel(state: string, available?: boolean) { return state === 'unverified' && available ? 'Локально готов' : states[state] || (available ? 'Локально готов' : 'Нужно проверить') }
export function executionLabel(status: string) { return status === 'error' ? 'Ошибка выполнения' : states[status] || 'Состояние выполнения не уточнено' }
export function inputLabel(type: string) { return inputTypes[type] || type.replace(/_/g, ' ') }
export function toolRemedy(tool: Tool) {
  if (tool.remedy || tool.diagnostic?.remedy) return tool.remedy || tool.diagnostic!.remedy!
  if (tool.available) return 'Выберите инструмент и укажите запрос подходящего типа.'
  if (['checking', 'unverified'].includes(tool.state)) return 'Дождитесь автоматической проверки или обновите доступность.'
  if (/auth|credential/.test(tool.state)) return 'Добавьте ключ или существующую сессию в настройках инструментов.'
  if (/missing|dependency|installed/.test(tool.state)) return 'Проверьте папку инструментов и Python для внешних зависимостей в настройках.'
  if (/disabled/.test(tool.state)) return 'Включите этот источник в настройках, если вы хотите его использовать.'
  if (/unsupported/.test(tool.state)) return 'Проверьте поддержку инструмента в текущем окружении. Другие источники остаются доступны.'
  if (/rate|restricted/.test(tool.state)) return 'Дождитесь снятия ограничений сервиса. Не повторяйте запросы непрерывно.'
  return 'Откройте причину ниже и проверьте настройки источника. Затем повторите проверку готовности.'
}
