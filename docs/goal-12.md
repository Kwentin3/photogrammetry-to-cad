# Goal #12 — автоматические маски → Standard cloud/mesh

Источник: [issue #12](https://github.com/Kwentin3/photogrammetry-to-cad/issues/12).
Начато 22 ноября 2026. Статус: **реальный прогон и cleanup завершены; независимая приёмка и публикация выполняются**.
Это единственная текущая запись задачи.

## Результат и границы

Проверенные фото + текст объекта → SAM2.1-small/HF GroundingDINO-tiny → полный
набор PNG/диагностика/overlays → существующий вход масок → Standard cloud и mesh.
Новый объект/съёмка задаются файлами/JSON/CLI, не исправлением исходников.
Отдельное ML-окружение не меняет Meshroom Python и базовый bootstrap.
Код, настоящий inference и реальная реконструкция обязательны; одна установка,
локальные doubles или подготовленный план не закрывают Goal.

Выбор B принят владельцем. mrSegmentation, SAM3, RoMa/LightGlue, CAD и
квалификация Legacy/Turntable/TwoSides вне объёма. Optional CUDA extension SAM2
отключаем штатно; автоматическую обработку мелких дыр/пятен не заявляем.

## Принятая база и решения

- Локальная ветка `goal/12-auto-masks`: принятый PR #10
  `f5b7984c09165b34ed986492938f3cc9a169636b` и исследование PR #11 с решением B
  `239fafb512989aba1d6079751dceb433f4ece758`, сведены локальным merge `09895d7`.
  Оба PR пока открыты; предварительное слияние в main не было условием задачи.
- Meshroom/AliceVision pins и сохранённый полный runtime archive неизменны.
  Baseline #6, raw frames/manifest, Standard cloud/mesh/cache сохранены вне Git.
- Выбранный опыт — **все 37 прежних кадров**: сверены SHA, размеры, 37 views/poses,
  настройки и 15 native UID сохранённого Standard. Старые EXR совпали с backup
  и имеют alpha=1 везде. Новый subset потребовал бы нового baseline на нём.
  На Linux выполнены strict native загрузка и свежий baseline EXR checker:
  старый QA ссылался на metadata до окончательного export, сами EXR совпали.
- **Маски только dense**, `features=false`: неподвижная коробка, движущаяся
  камера; фон полезен оценке камер. Это одна интервенция, не квалификация стола.
  Новые masks/RUN, native UID и actual outputs исключают подмену старым кэшем.
- Физическая шкала остаётся unknown. Сопоставимый обзор оценивает коробку,
  пол/фон, края и пропуски; число точек само по себе не мера улучшения.

## Владельцы и контракты

| Значение | Владелец → контракт → потребитель |
|---|---|
| Снимки/происхождение | capture manifest + existing verify_images → exact bytes/SHA → generator/native CameraInit |
| Bbox/сегментация | штатные HF/SAM2 API → original-raster masks → тонкий PNG adapter |
| Цель/неоднозначность | JSON prompt/thresholds/selection → explicit single либо union → generator diagnostic |
| PNG/связь с фото | source/model/settings SHA, имя, W/H, 0/255, raw orientation → существующий mask preflight |
| Фотограмметрия | native graph/UID/cache/ExportImages/Meshing → EXR, scene/cloud/mesh → QA/report/view |
| Ресурсы | existing remote_job/deadline + Vast CLI/API/private run card → logs/status/backup/destroy |

Нового registry, manager моделей, job DSL или planner нет. ML imports lazy и
только у включённой насадки. Ошибка 0/нескольких объектов не заменяется первой
находкой/белой маской; правило выбора явно задано. Спорные кадры видны в preview.

## План и приёмка

1. Проверить исходники/совместимые API, подготовить закреплённое ML-окружение,
   локальные модели/metadata и конфиги; проверить генератор/контракт реальными
   файлами и границы отсутствующей ML-зависимости. Без выдачи doubles за inference.
2. Сверить baseline, подготовить transfer/backup/облачную карточку и адресную
   остановку. Перед арендой — применимый денежный допуск и достаточная готовность.
3. На разрешённой GPU: один кадр, затем весь набор; фактическое окружение,
   setup/inference time, RAM/VRAM, полный mask diagnostic и 4–8 overlays.
4. После содержательной проверки — настоящий Standard с этими PNG, native EXR QA,
   новые cloud/mesh. Сравнить с совпадающим baseline/камерами по нескольким видам
   и исходным кадрам. Учитывать ручные исправления/исключения и отрицательный эффект.
5. Проверить backup, выгрузить параллельно с SHA, удалить аренду, проверить её
   отсутствие/charges. Обновить навигацию/команды/ограничения, независимая приёмка,
   опубликовать проверенную поставку и сверить remote.

## Допуски и состояние

Владелец отдельно подтвердил для #12: ≤$0.60/h, ≤2h от первой ноды и ≤$5 всего
с диском/трафиком. Одна RTX3090 создана 22.11.2026 11:01:48 UTC; ставка с диском
около $0.219/h. ID, точная ставка и lifecycle evidence — в частной карточке вне Git.
Автоматический stop назначен на 12:31:48 UTC; крайнее удаление — 13:01:48 UTC.
Повторная попытка не обнуляет сроки/расходы. SSH/watchdog, отдельный ML bootstrap
и закреплённый AV runtime проверены; на этой единственной ноде выполнен реальный
inference и native masked Standard. Ключи повторно не запрашиваются.

Локальные команды — общий Windows-исполнитель, owner/TTL, один heavy,
2GiB/32 процесса. Удалённый запуск получит собственные наблюдение/лимиты/stop;
модели и MVS последовательно на одной GPU. Локальный диск D имеет >200GB свободно.
Private evidence/state: `photogrammetry-to-cad-work/issue-12/`, вне GPU и Git.

Подготовлены `generate_masks.py` / `mask_models.py`, отдельный offline bootstrap,
47 зависимостей с hash lock и manifest весов/исходников. 18 локальных файловых
тестов PASS; lazy imports, single/union/errors, raw EXIF и lossless PNG проверены.
Проверка actual API по pinned HF wheel/SAM archive не выявила блокеров;
это не выполнение нейросетей. Передаются все 37 кадров и нужный upstream cache;
baseline исходника не меняется. Большие файлы загружаются aria2 в 8 потоков
с resume/SHA; источник SAM — официальное HF-зеркало с тем же закреплённым SHA.

Все 56 файлов (3933764553 байта) проверены по SHA. Baseline archive:
246 regular payload files, 609334354 bytes до упаковки, SHA всех членов сверены;
полный retained runtime SHA совпал с pin. 70 общих локальных тестов PASS,
`--validate-only` реальных 37 кадров и весов PASS. Подготовленный код сохранён
локальным commit `1f768b4`; архив доставки связан отдельным SHA в частной карточке.

## Проверенное GPU-состояние

- Первый кадр: actual adapter, 7.75 s; затем полный CLI — 37/37 PNG, по одному
  кандидату, 0 failed/ambiguous. Total 21.90 s, обработка кадров 13.75 s,
  model load 4.72 s; peak RSS 1858478080 B, CUDA allocated 2190115840 B,
  reserved 2361393152 B. Это измерения запуска, не размер весов.
- Просмотрены 8 overlays, дополнительно спорные originals. Нужная коробка и
  отделение от пола подтверждены выборочно. В 00000/00006/00012 частично потеряна
  узкая тёмная нижняя грань; 00084/00090 уже обрезаны верхом исходной съёмки.
  Ручных правок масок и исключённых кадров нет; pixel-perfect полнота не заявлена.
- При восстановлении упаковщик нормализовал JPEG mtime=0. AV native view UID
  использует mtime fallback даже при ImageUniqueID, поэтому повторная CameraInit
  получила другие IDs. Первый prepare отклонён **до MVS**. В новом полном графе
  сохранены принятые native CameraInit inputs, SDK пересчитал UID, заново выполнен
  binding масок. Все 11 upstream UID совпали; 4 dense UID изменились. Ядро не менялось.
- Native reader связал 37 PNG с actual views. Обычный и новый EXR checker PASS
  37/37; baseline alpha=1, новый alpha исключает 54.16–70.42% пикселей, RGB на
  полностью opaque пикселях совпал точно. Native plan после ExportImages —
  только DepthMap, DepthMapFilter, Meshing; сфера камер переиспользована.
- Новый Standard до Meshing завершён за 75 s, owned tree cleanup confirmed.
  Export прошёл после штатного `scale` с mode=unknown; первичная попытка без
  scale-plan остановилась до выдачи файлов, ошибка и повтор сохранены.
  Cloud/mesh созданы, свежий EXR QA и полное сравнение 37 камер PASS.
- Remote backup: 725 payload-файлов / 1151931387 B; архив 1023161968 B,
  SHA256 `1fe1bcde355bbbb0bdcf858d797bfe022e27ea8c30fd921534d96bc962662752`.
  На GPU и локально проверены все члены; выгрузка завершена 8 файлов × 4 потока,
  части 64 MiB, средняя 2.44 MiB/s с проверкой/сборкой.
  Архив не включает повторно уже сохранённые у владельца модели/пакеты/runtime.
- Open3D фактически прочитал оба cloud/mesh; исходные SHA, finite coordinates,
  topology/indices и сохранение всех native faces проверены. Новый результат:
  46130 точек/46130 raw OBJ vertices/91409 triangles против 121291/121293/241137.
  Два общих вида показали исчезновение окружающего пола и сохранение широкой
  лицевой панели. Боковины/нижние края неполны и неровны; скрытая сторона неизвестна.
- GPU удалена 12:03:17 UTC; native all-pages absence подтверждён. От первого
  запроса создания — 61 min 29 s. Native ledger: $0.243 (GPU .127, disk .074,
  bwd .038, bwu .004), в пределах всех трёх разрешённых лимитов.

Итоговые данные, сопоставимые виды, ошибки и ресурсы — в
[отчёте](reports/2026-11-22/auto-masks.md); повторение — в [инструкции](auto-masks.md).
Следующий шаг: независимая приёмка по issue и публикация проверенного head.
Эти обязательные пункты пока открыты; завершение GPU-этапа не закрывает весь Goal.
