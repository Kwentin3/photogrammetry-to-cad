# Goal #40: сетки, фотографические текстуры и Meshroom GUI

Задание — [issue #40](https://github.com/Kwentin3/photogrammetry-to-cad/issues/40).
Реализация ведётся в ветке `goal/40-mesh-textures` от базы `0f97f2e`.
Первый commit — `3f12b724`; финальная публикация PR готовится. Исследование #38 включено
из `f7b3d70` с тем же Git blob; merge PR #39 не предполагается.
Это единственная текущая запись задачи. **Goal не завершён.**

## Результат и границы

Пользователь выбирает подготовленное облако, сетку или фотографический вид.
Первый пример — сохранённая комната #27: исходный raw, отдельная обработанная
сетка, полный фотографический материал и проект выполненного продолжения.
После завершения compute независимый проверяющий открывает перемещённую выдачу
в Meshroom: фото, камеры, параметры, результаты и журналы доступны. Требуются
реальные пиксели материала, поворот и сравнение plain/raw/filter с исходными фото.

Native raw, provenance, оси, unknown scale и PARTIAL для обмеров сохраняются.
Входят существующие skill/docs, export/report, backup, PR и уборка.
Не входят CAD, новая съёмка, WSL, новый viewer/remote desktop, патч ядра,
смена compute pin или обещание точности изготовления. Домашний Linux VPS
использован с ограниченной нагрузкой; новых пределов Vast нет, аренда не создавалась.

## Принятые решения

- Meshroom/AliceVision владеют graph/UID/status/compute, существующий runner —
  job/пределами. Export/report сохраняют выбранный native output и provenance.
- Новые настройки — новый RUN с явным shared cache и доказанным upstream reuse.
  Original backup #27 не меняется; старые UID/SUCCESS вручную не переносятся.
- Compute pin: Meshroom `b12ea889` / AliceVision `d012d055`.
  Windows GUI `8df9560` квалифицируется отдельно для просмотра.
- Выбраны MeshFiltering без сглаживания и Texturing Basic/UDIM,
  working8192/downscale4, PNG/sRGB, correctEV=true, один частотный band,
  fillHoles=false, subdivision=0. Это выбор для данной сцены, не defaults для всех.
- Windows использует полный bundle, app-local Mesa26.3.1 и native 8-bit viewer.
  Launcher отображает filesystem root через свободный drive; graph/cache/JPEG/PNG
  не переписываются. Windows compute-resume не квалифицирован.

## Проверенное состояние

Расчёт 27 ноября, продолжение GUI-проверки 28 ноября 2026.
Подробности и hashes — [отчёт](reports/2026-11-27/room-mesh-textures.md).

1. Проверены runtime SHA, 494 исходных payload-файла и 77 JPEG. Строгая Linux
   загрузка сохранила 18/18 UID, без compatibility nodes. SfM/dense не повторялись.
2. Восстановлен только ExportImages: 77 EXR / 2877637987 байт, actual QA PASS.
   После timeout первой попытки подтверждено завершение дерева и повторена только
   вторая native chunk. Исторический SUCCESS не заменял наличие EXR.
3. MeshFiltering и Texturing — native SUCCESS. Выполнены оба derived exports:
   OBJ/MTL и 10 PNG 2048×2048 RGB8 с native sRGB tag/CRC; 126053240 байт карт.
   Texturing занял 954.212 s. Первый вариант со 161 атласом остановлен; OOM
   следующего при hard3GiB сохранён. Тот же graph завершён с 3 GiB RAM + максимум
   2 GiB существующего swap, 2 CPU / 128 PID / TTL1800 s, без нового OOM.
4. Raw 584109 OBJ v / 1163039 triangles → filtered 584113 / 1163024.
   Удалены 15 ненулевых граней и одна XYZ-позиция: 1.89946% raw площади,
   boundary edges 33→50. Bbox совпал; сохранившиеся позиции NN max7.3e-12 без fit.
   Проекции локализовали веер крупных граней в разреженном конце комнаты.
5. Textured содержит 845891 OBJ v, те же 572227 уникальных XYZ и bbox,
   1163020 triangles, 10 materials и допустимые UV. Рост v — дубликаты XYZ;
   дополнительно удалены четыре ненулевые грани общей площадью
   0.312713134214 условных единиц². Координаты сохранены в audit.
6. Actual OBJ→cloud diag(1,-1,-1), translation0, scale1 проверены без registration:
   все 584106 dense-точек → raw NN max8.51e-6. Raw/export/native SHA совпадает.
   Existing report на final RUN с raw и двумя receipts: status=reported,
   два verified derived mesh, scale=unknown. Физических миллиметров это не задаёт.
7. Backup: 870 файлов / 4810677259 байт, каждый SHA проверен до удаления compute.
   View: 523 файла / 1360881066 байт, graph bytes/UID сохранены; staging перемещён.
   EXR/jobs/невыбранные попытки исключены из view с полным списком. Restored EXR
   сохранены в backup; исторические DepthMap/DepthMapFilter EXR отсутствовали ранее.
8. Контейнер удалён 27 ноября 17:19:27 UTC; его remote root — 17:33:15 UTC.
   Все 15 baseline контейнеров сохранили ID/состояния. Retained runtime у владельца.
   Частные IDs/paths и доказательства — вне Git.
9. Software 9574 файла / 2216246790 байт сверены по SHA. Обычный Open-Meshroom.cmd
   открыл конечный проект: normal WM_CLOSE, cmd exit0, собственный drive снят.
   Loader подтвердил одну full Texturing mesh, valid/hasTextures, sparse SfM
   30012 points / 77 cameras. Это ещё не визуальная приёмка фотографического вида.
10. 77 reconstruction + 6 CPU-helper + 3 drive tests PASS; scoped code reviews PASS.
    Skill/runbook/режимы/geometry review/карточка обновлены. Независимый агент
    без истории разобрал четыре требуемых случая — PASS. Итоговый reviewer:
    NEEDS_EVIDENCE только по final GUI/visual, финальным docs и PR.

## Текущая GUI-проверка

Первые private probes выявили риск duplicate view-request; исправление QUrl/path
и один native request подтверждены чтением. Затем на одном mesh+sparse доказан
model-ready без error при PrivateBytes около 1.21–1.27 GB.

Проверка 28 ноября с обычным окном подтвердила isExposed=true и frameSwapped:
отключённая RDP-сессия не является установленной причиной. Полная сетка достигает
hard Job limit 2 GiB и при обычном render без capture: отдельно проверены Mesa
и native D3D11 на Intel HD4600, Material2 до входа в event loop, mesh-only после
выгрузки sparse. Реальные пиксели полного материала пока не приняты.
После каждой остановки подтверждены завершение дерева, снятие своего drive
и сохранность 523 файлов. Core, launcher и вычисленные файлы не менялись.

Выбран отдельный native MeshDecimate→Texturing RUN для ограниченного viewer.
Полный raw/filter/textured результат и его backup сохраняются. MeshDecimate
получает прежний filtered output; factor=0.5 означает долю вершин, прочие
vertex limits=0, flipNormals=false. Это quadric simplification без exposed
boundary lock/max-error: фактические потери и отклонения подлежат проверке,
а число граней само по себе не является приёмкой. Native template создаётся
Graph API и передаётся normal prepare --template; upstream UID проверяются.

Создана отдельная CPU-среда на прежнем домашнем Linux: 2 CPU, 3 GiB RAM,
до 2 GiB swap, 128 PID, срок один час; ID/начало/deadline записаны вне Git.
Runtime и 760 файлов восстановлены с полной SHA-проверкой. Native prepare:
19 узлов, 0 compatibility nodes, прежние upstream UID сохранены. MeshDecimate
завершился SUCCESS за 16 s: 292056 вершин / 578910 граней. Native boundary50→50,
components1392→1392; двусторонние sample→surface отклонения и worst ROI сохранены
в audit, без fit и физических единиц. Texturing SUCCESS за 867.056 s: 11 PNG
2048×2048 RGB8/sRGB, CRC/IEND проверены. Получены отдельные native exports.
Новый полный backup: 895 файлов / 5011378169 байт, все SHA и inventory совпали.
Контейнер удалён 28 ноября 08:09:01 UTC, его root — 08:09:59 UTC; все 15 baseline
контейнеров сохранили ID/состояния. Новых оплачиваемых ресурсов, изменения
Windows policy или патча ядра нет.

Сборка новой view-копии столкнулась с transient nonstrict Path.resolve при
параллельном создании родителей. Проверка после создания показала тот же путь
внутри delivery, без reparse. Частичные совпадающие файлы сохраняются; исправление
проверяет existing strict parents перед копированием и explicit resume по SHA.
Оригинальные view/models/backup остаются неизменными.

Новый view собран и проверен: 410 файлов / 1041336457 байт, exact graph,
77 JPEG; raw mesh/cloud/scene.json совпадают с прежними побайтно. Новая CPU-среда
и её root удалены после проверки 895 файлов backup; все 15 baseline контейнеров
не изменились. Первый GUI probe остановил дополнительный soft1750MiB guard.
Повтор без него, с прежним hard2GiB, завершился нормально: peak1884954624B,
stable около1637457920B, 161 frameSwapped. Это уже не memory failure.
Win32 foreground gate не разрешил OS capture. Затем native Qt readback
собственного уже отрендеренного окна дал реальные фотографические пиксели.
Подтверждены поворот, Material2→Shaded0→Material2 того же оконного участка,
native camera pose, исходный JPEG, raw/filter/MD comparison, 77 camera frusta,
параметры MD0.5/Texturing8192/downscale4/PNG и настоящий native0.log.
После каждого запуска все 410 SHA сохранены, свой drive снят, процессы завершены.

На plain видна грубая рваная поверхность, на материале — белые участки.
Причина белых участков UNKNOWN; все 11 MTL/UV bindings проверены, конкретной
ошибки не установлено. Независимый review точного договора не нашёл требования
исправить их до косметического порога; ограничение выдаётся явно вместе с PARTIAL.

Обычный launcher раньше оставлял native PBR3, а агент проверял Material2 до
first render; native Shading control disabled во время loading. Исправление
устанавливает Material2 один раз через native mesh Instantiator.objectAdded,
без poll/замены loader/core; пользовательские переключения сохраняются.
Полный обычный CMD→parentPython→gui-child с окончательным source/deployed
`89538d15` проверен: Material2 при loading=true от public hook, private shading
и renderer overrides отсутствовали. Полный цветной mesh реально виден;
exit0, cleanup confirmed, active0, свой P: снят. Peak всего Job2123735040B,
прежний hard2147483648B соблюдён. Post410 SHA PASS. Source-scoped review PASS;
независимый итоговый review feature/data/GUI PASS, без нового порога красоты.
Source и deployed script `424f11ac…` совпадают, AST/drive tests PASS.
Ещё требуется actual полный CMD→parentPython→gui-child маршрут с этим профилем.
Ранние direct observer снимки сами по себе не доказывают его memory capacity.

## Обязательное оставшееся

1. Завершить операторскую навигацию и честный статус в README/карточке/отчёте,
   контексте и точках входа. Отделить агентскую приёмку от личной приёмки владельца.
2. Подтвердить final docs commit/push, PR
   и безопасная уборка своей рабочей копии; результаты и evidence сохранить.

Ближайший шаг — финальные документы, публикация PR и безопасная уборка своей копии.
Полный объём Goal сохранён; успешный loader или startup не заменяет final GUI.
