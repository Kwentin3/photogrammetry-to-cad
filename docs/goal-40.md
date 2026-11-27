# Goal #40: сетки, фотографические текстуры и Meshroom GUI

Текущая задача — [issue #40](https://github.com/Kwentin3/photogrammetry-to-cad/issues/40).
База реализации — `0f97f2e`, ветка `goal/40-mesh-textures`. Исследование #38
включено без изменений из `f7b3d70`; merge [PR #39](https://github.com/Kwentin3/photogrammetry-to-cad/pull/39)
не предполагается. Это единственная текущая запись задачи.

## Результат и границы

Агент выбирает подготовленное облако, сетку или фотографический внешний вид.
Первый реальный пример — сохранённая комната #27: неизменённый raw, отдельно
выбранная обработанная сетка и полный фотографический материал с происхождением.
После вычислений в Meshroom доступны выполненный граф, фото, камеры, параметры,
выходы и журналы. Независимый проверяющий открывает перемещённую выдачу по инструкции
после остановки compute. Unknown scale и PARTIAL для обмеров сохраняются.

Входят native продолжение, export/report, переносимая выдача, существующие
skill/docs, независимые проверки, опубликованный PR и безопасная уборка.
Не входят WSL, новый viewer/remote desktop, CAD, новая съёмка, смена compute pin
или патч ядра. Домашний Linux VPS разрешён для ограниченной временной работы
без изменений других сервисов. Новых численных пределов Vast нет; аренда не создавалась.

## Принятые решения

- Meshroom/AliceVision владеют graph/UID/status/вычислением; существующий runner
  ограничивает job. Export/report сохраняют файлы и provenance; GUI launcher
  отображает файловый root и выбирает штатные renderer/8-bit viewer.
- Вычисления: Meshroom `b12ea889` / AliceVision `d012d055`; Windows GUI
  `8df9560` квалифицируется отдельно для просмотра. Core не патчится.
- Original backup #27 не изменяется. Новые настройки — новый RUN с явным shared
  cache и доказанным upstream reuse; старые UID/SUCCESS вручную не переносятся.
- Выбраны native MeshFiltering без сглаживания и Texturing PNG/sRGB, Basic UV,
  working8192/downscale4, один частотный band, fillHoles=false, subdivision=0.
  Это настройки конкретной CPU-выдачи, не универсальные defaults.
- Windows: полный bundle, app-local Mesa26.3.1 x64, native 8-bit viewer,
  временный принадлежащий launcher DOS drive. Graph/cache/JPEG не переписываются.
  Windows compute/resume и перенос всего workflow в другую среду не заявлены.

## Проверенное состояние

27 ноября 2026, поставка пока локальна; PR будет доставлен после финальной
GUI-приёмки. Код и данные подготовлены для этой проверки.

1. Проверены runtime SHA, все494 исходных payload-файла и77 JPEG. Строгая
   Linux-загрузка сохранила18/18 UID, без compatibility nodes.
2. Восстановлен только ExportImages:77 EXR/2877637987B, actual QA PASS.
   Первый bounded job истёк после70файлов; после confirmed cleanup штатно
   повторена только вторая chunk. SfM/DepthMap/Meshing не пересчитывались.
3. MeshFiltering SUCCESS, UID `5aa45d0797fb9e3bacf50409b31a838bbb066b13`.
   Реальный derived export прошёл. Фактические настройки: smoothing0,
   keepLargest=false, iterations1, factor60, ratio0.
4. Raw584109 OBJстрокv/1163039треугольников → filtered584113/1163024.
   Удалены15ненулевых граней и одна XYZпозиция; bbox совпал. Сохранившиеся
   позиции NNmax7.3e-12 без fitting. Удалено1.89946% площади raw; boundary edges
   33→50, длина9.2843→18.6201 условных единиц. На проекциях виден веер крупных
   граней в разреженном конце комнаты. Полезность удаления проверяется в GUI
   рядом с фото; безвредность/замкнутость не заявлены.
5. Actual OBJ→cloud `diag(1,-1,-1)`, translation0, scale1 подтверждены по всем
   584106dense-точкам: NNmax8.51e-6; identity median0.491/max2.965.
   Raw/export/native SHA совпадает. Физических единиц это не устанавливает.
6. Texturing SUCCESS, UID `3bc587f0d9c4745839e6f57a32d0b261575ea21e`:
   OBJ/MTL и10PNG, native runtime954.212s, окончание17:10:53UTC.
   Оба реальных derived exports с полным material closure и provenance прошли.
7. Первый Basic2048/downscale1 дал161атлас и был адресно остановлен.
   Следующий8192/downscale4 упёрся в hard3GiB при downscale: native ERROR,
   oom_kill=1, cleanup confirmed; log/status сохранены. Повтор того же graph
   с3GiB RAM+2GiB существующего swap завершился без OOM. Native hardware flags
   подтвердили2048Mo/2cores; это подсказка, отдельный hard limit остаётся обязательным.
8. Native Windows GUI показал original JPEG,77камер и raw mesh. Mesa устраняет
   наблюдаемую несовместимость Intel OpenGL4.3 с GLSL460; native8-bit устраняет
   ошибку JPEG. CameraInit VersionConflict12.1→12.2 сохранён. В перемещённой
   пробе oldroot отсутствовал,452файла сохранили SHA, loading=false/error='',
   normal close0, drive очищен. Финальный фотографический комплект ещё не открыт.
9. Постоянный GUI software:9574файла/2216246790B сверены по SHA, relative-path
   Open-Meshroom.cmd и встроенный Python готовы. View/data добавлены: 523 файла,
   1360881066 байт, все SHA сверены; staging перемещён и отсутствует.
10. Код:74reconstruction+6CPU helper+3drive tests PASS; независимые scoped code
    reviews PASS. Native argv/status/UID проверены на реальном runtime.
    Skill/runbook/режимы/geometry review/карточка обновлены; независимый агент
    без истории разобрал четыре требуемых случая — PASS.

Backup: 870 файлов, 4810677259 байт, каждый SHA проверен. Manifest SHA
`7081422bfbf5580b2663fb159a43347d5e9e00c3e93310f3ddcf7aedc23da169`.
Контейнер с лимитами 2 CPU / 3 GiB RAM + 2 GiB swap / 128 PID удалён
17:19:27 UTC. Все 15 baseline контейнеров сохранили ID и состояния.
Private ID/SSH/paths — в карточке вне Git. Временные данные VPS удалены
17:33:15 UTC после проверки backup; прежний root отсутствует физически.

## Обязательные оставшиеся шаги

1. Textured→filtered сравнение завершено: все XYZ сохранены, bbox тот же,
   четыре ненулевые грани удалены, площадь 0.312713134214 условных единиц².
   Координаты сохранены в audit. Actual report завершён status=reported,
   два derived receipts приняты; физический масштаб unknown.
2. Открыть перемещённую финальную выдачу в Meshroom после удаления compute:
   материал/поворот/plain/raw/filter, фото, камеры, graph/settings/logs.
   Старый root недоступен; оригинал графа сохранён.
3. Завершить отчёт/инструкции, независимую приёмку всех требований, публикацию PR
   и безопасную уборку своих временных ресурсов. Логи и полезные данные сохранить.

Ближайший шаг — завершить локальное геометрическое сравнение и GUI-приёмку.
Вопрос о другой GUI-машине снят: локальный маршрут уже работает. Goal в работе.
