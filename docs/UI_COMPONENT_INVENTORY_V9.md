# V9 · Component inventory

Это перечень реализаций embedded UI. Количество исходных объявлений не равно
числу элементов на открытой странице. Нативные Windows file/vault dialogs
относятся к ОС и не заменены web-компонентами.

| Элемент | Общая реализация и места использования | Проверяемые состояния |
| --- | --- | --- |
| Checkbox | `components/ui.tsx` Checkbox, общие HTML checkbox в `controls.css`, ResultsTable и ResearchResults | checked, unchecked, mixed, disabled, read-only, keyboard focus, независимый контраст акцента |
| Radio | Radix RadioItem в SearchableSelect, резервный `input[type=radio]` в controls.css | selected, disabled, focus, клавиатура |
| Select | ui.tsx Select → SearchableSelect, формы узлов/связей, ConnectionSettings, ToolForm, AppearanceEditor, GeoIntView | поиск, Enter, Escape, Up/Down, disabled, длинный список, collision positioning |
| ComboBox | `components/ComboBox.tsx`, редактируемая модель Ollama в ConnectionSettings | свободный ввод, фильтр, popup, фокус, выбор, закрытие |
| Input | controls.css и семантические поля форм, поиска и настроек | placeholder, value, error, focus-visible, disabled, number, password |
| Textarea | controls.css, Chat, EntityComposer, Canvas и редакторы заметок | перенос, resize, focus, disabled, сохранение черновика при отказе |
| Switch | ui.tsx Toggle → Radix Switch, PreferenceRow в Settings | on/off, disabled, keyboard |
| Slider | Radix Slider в Settings/AppearanceEditor, общий range fallback в controls.css | current value, focus, keyboard, reduced motion |
| Button | ui.tsx Button/IconButton, общий .button, специальные graph toolbar buttons | default, secondary, ghost, danger, hover, focus, disabled, busy |
| Accordion | ui.tsx Disclosure → Radix Collapsible, настройки инструментов и бюджетов | open/closed, aria-expanded, SVG rotation, reduced motion |
| Disclosure | ui.tsx Details/Summary, технические сведения источников и инструментов | keyboard activation, скрытый native marker, SVG ChevronDown |
| Popover | существующие Radix dropdown portals, панели ResearchCanvas | collision bounds, z-index, themed surface, scroll |
| Tooltip | ui.tsx IconButton → Radix Tooltip, названия действий графа | focus, hover, portal, длинный текст |
| Dropdown | ui.tsx ActionsMenu/MenuItem, SearchableSelect | mouse, keyboard, disabled item, focus return |
| Table | `components/ResultsTable.tsx`, общие table rules, Markdown tables | stable columns, compact/comfortable rows, selection/mixed header, sorting, paging, empty state |
| List | ResearchResults gallery, History, ResearchBrowser, Chat activity | одинаковые интервалы, ellipsis, selected/empty, scroll |
| Tree | существующие вложенные разделы документов/проекций в ResearchCanvas и InvestigationWorkspace | скрытие/раскрытие, отступы, SVG control, выбранный объект |
| Menu | ActionsMenu, project menu, command palette в App | active/disabled, hover/focus, Escape |
| Context menu | существующее contextual toolbar выбранного объекта/связи в ResearchCanvas | выбранный target, доступность действий, отсутствие автоматического OSINT по double click |
| Scrollbar | глобальные scrollbar-color/width и WebKit fallback в controls.css | page, inspector, settings, history, chat, dropdown, viewer, results, dialog |
| Dialog | Radix Dialog в App/Sources/RelationComposer, существующие image import/viewer | themed overlay, focus, Escape/close, bounded viewport, inline error |
| Toast | App .toast role=alert, existing notices и insertion status | warning/error/success, dismiss, reduced motion |
| Results card | ResearchResults gallery и Canvas2D templates в InvestigationCanvas | profile/email/phone/company/wallet/NFT/image/document/note/group, single/multi selection, dimmed/related/drag |
| Evidence item | Sources/SourceInspector/SourceDialog и ResearchResults | provenance, status, limitations, preview, insertion, source URLs |
| Pagination | ResultsTable и ResearchResults footer | first/last disabled, stable footer, total/filter count |

## Общие решения

Темы используют одни переменные для текста, панели, границ, акцента и focus.
Checkbox вычисляет собственный foreground по accent и не зависит от цвета
основной кнопки. Свечение графа не заменяет focus. Существующие SVG Lucide
сохраняют единый набор значков. Стрелки направления аналитических связей
не переименованы и не удалены.

Нативные HTML select и details вне общих primitives устранены из активных
компонентов. Внешний вид controls распространяется и на менее частые формы,
а не только на показанные в задании примеры. Количественный снимок исходников
и результаты нативного обхода разделов входят в протокол V9.

## Границы проверки

Снимки пустого QA-профиля подтверждают композицию настроек и common controls.
Отдельные native сценарии проверяют реальные формы, медиа, findings, граф,
double click и GitHub. Контролируемые frontend tests проверяют mixed/read-only,
клавиатуру и rollback черновика. Это разные источники свидетельств. Нельзя
приравнивать статический поиск тегов к проверке всех возможных экранных состояний.
