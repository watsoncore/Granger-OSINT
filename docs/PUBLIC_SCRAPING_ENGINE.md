# Публичное получение данных: HTTP, parsing и изолированный DOM

Обновляется существующий `agent_browser.PublicPageReader`: прежние discovery,
ограничения глубины/страниц, checkpoints и evidence сохранены. Модель не получает
произвольный HTTP-клиент, параметры интерпретатора или возможность запускать код.

## Движок

`web_http.fetch_public` использует HTTPX и прежний DNS-pinned транспорт httpcore.
Для прямого чтения отдельно проверяется robots.txt каждого origin (часовой кэш); запрет, ошибка получения политики и запрещённый redirect не обходятся.
Каждый URL и переход повторно проверяются; localhost, private/service IP,
опасные схемы и URL с credentials запрещены. TLS проверяется для исходного
hostname, соединение устанавливается с проверенным IP. Переменные proxy среды
не используются. Запрос не принимает произвольные заголовки или секреты.

Поддерживаются GET и явно разрешённый вызывающим адаптером POST поисковой формы.
Login/upload/секретные поля не разрешены. Редиректы ограничены; POST не переносится
на другой origin. Ответ ограничен 2 МБ, HTTP-тайм-аутом и внешним deadline;
размер проверяется после декомпрессии. GET 502/503 имеет максимум один повтор,
401/403/CAPTCHA не обходятся. Общие слоты — 4 HTTP, 1 на домен; дополнительная
федерация источников — 2. Cookie jars только в памяти одного reader/origin,
не берутся из браузера пользователя и не сохраняются в checkpoint.

`web_scraping` хранит `ScrapeResult`: requested/final URL, метод, HTTP status,
title, текст, structured_data, ссылки, время, extraction_status и warnings.
При нормализации запись получает настоящий evidence_id. HTMLParser извлекает
metadata/OG/canonical/JSON-LD, заголовки, таблицы, ссылки и доступные атрибуты.
JSON ограничен глубиной/объёмом; XML/RSS/Atom не допускает DTD/ENTITY.

Результаты различают snippet, parsed_page, record_extracted, javascript_required,
empty_content и ошибку. `content_observed` не означает установленную личность
или проверенную истинность текста. Локально сохраняется полная ограниченная
запись; в модель идут релевантные выдержки и компактные структурированные поля.

## JavaScript

HTTP выполняется первым. При распознанной JS-оболочке и отсутствии login/challenge
используется отдельный процесс `--public-render-worker` на уже поставляемом Qt.
Он не имеет WebChannel, пользовательского профиля, секретов, файловых загрузок
или прямого сетевого доступа. До запуска ограниченно получаются classic scripts
через тот же pinned HTTP; произвольные динамические запросы остаются запрещены.
Проверяется DOM-состояние, а не истечение произвольной паузы.

Контекст одноразовый, renderer-слот один. На Windows Job Object завершает всё
собственное дерево при отмене/timeout; бюджет дерева 1 ГиБ и V8 heap 128 МиБ.
Ограничения относятся только к дочернему процессу Granger, параметры ОС не меняются.

Это ограниченный renderer, не универсальная автоматизация любого сайта:
module imports, сложные fetch/XHR-приложения и сайты с несовместимым CSP могут
не дать полезный DOM. Тогда возвращается честный неподтверждённый результат.
CAPTCHA, login и 403 не передаются в браузер как способ обхода.

Настоящая разрешённая проверка: `https://quotes.toscrape.com/js/` — HTTP shell,
затем реальные цитаты/авторы из DOM. Отчёт `output/public-scraping-engine/quotes-live.json`,
`mock:false`. Это специальный учебный сайт для scraping, не данные реального человека.

## Источники без персональных ключей

`public_sources.py` задаёт отдельные endpoints и JSON mappings:

| Адаптер | Документированный endpoint | Данные |
| --- | --- | --- |
| github_profile | api.github.com/users/{username} | Публичные поля точного профиля |
| github_users | api.github.com/search/users | Публичные записи поиска профилей |
| github_repositories | api.github.com/search/repositories | Метаданные публичных репозиториев |
| hn_profile | hacker-news.firebaseio.com/v0/user/{id}.json | Публичный профиль HN |
| hn_search | hn.algolia.com/api/v1/search | Публикации/комментарии, автор и дата |
| openlibrary_search | openlibrary.org/search.json | Книги, авторы, даты, identifiers |
| wikipedia_search | en.wikipedia.org/w/api.php | Поиск и настоящий introductory extract |

Все семь выполнили живые запросы с созданием evidence через ToolRegistry.
Отчёт: `output/autonomous-qa/public-search-live.json`. Internet Archive search
реализован и проверен фикстурами, но два живых запроса завершились timeout;
он исключён из активного реестра и стандартной федерации до подтверждения.

Поиск без CSE объединяет ограниченный набор подходящих источников; это не
глобальная выдача Google. Google CSE остаётся дополнительным подключением.
При его отказе новые отдельные клиенты выполняют публичный поиск без передачи
ключа. Автоматические запросы DuckDuckGo /html и /lite исключены по robots.txt.

Кэш — 5 минут, максимум 32 записи. GitHub search ограничен интервалом 6.1 с,
локальной квотой 60 запросов/час на API host и серверными rate headers.
Остальные адаптеры имеют интервал 1.1 с/host, backoff и bounded concurrency.
Внешние приложения также используют общую квоту IP: их расход не исследуется.

Перед паузой при повторяющемся отказе AgentRunner может запустить до трёх
разных зарегистрированных публичных альтернатив для того же аргумента.
Повторный запрос, придуманный URL или обход отказа авторизации не создаётся.
Явное «только этот источник», бюджет и отмена сохраняются.

Первичные документы: [GitHub users](https://docs.github.com/en/rest/users/users#get-a-user),
[GitHub search](https://docs.github.com/en/rest/search/search),
[HN API](https://github.com/HackerNews/API), [Algolia HN](https://hn.algolia.com/api),
[Open Library search](https://openlibrary.org/dev/docs/api/search),
[MediaWiki extracts](https://www.mediawiki.org/wiki/Extension:TextExtracts#API),
[Archive automated access](https://archive.org/developers/bots.html),
[DuckDuckGo robots](https://duckduckgo.com/robots.txt).
