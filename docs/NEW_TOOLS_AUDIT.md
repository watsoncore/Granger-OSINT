# Master Fix V2 — обнаружение сторонних проектов

Root: существующий Hermi_osint; исходный commit c92b116, ветка
granger/chibi-reconstruction, origin watsoncore/Granger-OSINT. Начальный working
tree чист. Рекурсивное обнаружение до3 уровней исключает приложения, runtimes,
build/dist, node_modules и QA blobs; vendor entry points не выполнялись.

Найдены29 manifests/archive entries:12 архивов,13 самостоятельных распакованных
проектов,4 вложенных build/docs/test-компонента. Вложенные manifests не считаются
новыми инструментами. Все12 архивов совпали по SHA-256 с предыдущим аудитом;
новых самостоятельных проектов не обнаружено. [Машинная инвентаризация](validation/master-fix-v2/project-discovery.json).

Предыдущая [матрица13 добавленных проектов](validation/intelligence-v1/tool-matrix.json)
сохраняет лицензии, entry points и причины исключений. Это не утверждение об их
полной интеграции. В этой работе публичные VK/TikTok/Steam collectors будут
проверяться отдельно; чужие token/cookie/bypass paths не будут активированы.

До правок сняты SHA всех92 assets,202 resources,16 Pet runtime modules,
69 существующих файлов профиля,509 файлов оригинального Gansar и файлов двух
модельных runtimes:23387 visual-cpu и25 scene-vision. Секреты не расшифровывались.
Полный снимок с приватными относительными именами остаётся только в ignored QA
output. [Публичные агрегаты baseline](validation/master-fix-v2/baseline.json).

Реестр содержит70 операций; локальная готовность и сетевой live-status не
отождествляются. Последующие результаты будут публиковаться с разделением
source fixtures, настоящих сетевых ответов и конечного Windows EXE.
