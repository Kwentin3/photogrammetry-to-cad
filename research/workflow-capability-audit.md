# Аудит #33: умеет ли агент использовать возможности текущего фотограмметрического стека

**Основание:** [Issue #33](https://github.com/Kwentin3/photogrammetry-to-cad/issues/33).  
**Характер документа:** исторический read-only аудит инструкций, скриптов и закреплённых контрактов на ревизиях ниже. Исправления в рабочий код, живой `SKILL.md` и `docs/` в рамках #33 не вносились; платные GPU-ресурсы не запускались (`$0`). В Goal #35 внесены точечные уточнения интерпретации; это не повторный полный аудит и не свидетельство исправления всех находок. Практический маршрут настройки и диагностики вынесен в [памятку](../docs/camera-sfm.md).

### Сверенные ревизии и границы базы

| Источник | Ревизия (проверена) | Статус на момент аудита |
|---|---|---|
| `main` | `9d4ad78483187d924bc50d39ca195fecfd28b7e8` | Активная база репозитория; по ней проводился слепой тест агента и локальные воспроизведения |
| [PR #28](https://github.com/Kwentin3/photogrammetry-to-cad/pull/28) (`goal/27-room-photos`) | `138a70f95b64699067107a736176a34596df7d37` | Открыт; добавляет разбор реальной съёмки комнаты и раннюю проверку оригиналов / `CameraInit` / sparse |
| [PR #30](https://github.com/Kwentin3/photogrammetry-to-cad/pull/30) (`goal/29-cctag-distances`) | `cff70a493bf2e56413d5f9a67f3ddb42053a4fc8` | Открыт (на базе PR #28); добавляет `capture_measurements.py`, разделение `scale`/`check`, `pair_report` и `configs/reconstruction-cctag.example.json` |
| [PR #32](https://github.com/Kwentin3/photogrammetry-to-cad/pull/32) (`research/31-micmac-agent-workflow`) | `d16bceed6a272632d7f09ec47d2774ca4fbfc5f3` | Открыт; только исследование MicMac/MMVII и проект структуры знаний, не внедрённый режим |
| Pinned Meshroom / AliceVision | `b12ea8896e7e95cc9911b4ec39c272914e4da726` / `d012d05589b528dcf57a2a0c805c0a5709df8613` | `configs/runtime-2026.json` (`Meshroom-2026.11.21-b12ea88-linux-full.tar.gz`) |

---

## 1. Короткий вердикт

**Текущий стек и обвязка надёжно ведут один отработанный базовый маршрут** (*обычные фото/видео неподвижной сцены → Standard или Legacy без кастомной калибровки → `Meshing` → облако + сырой OBJ с жёсткой защитой от подмены входов и осей*). В этой зоне репозиторий сильнее типичных фотограмметрических инструкций: честно разделяет выполненные запуски и непроверенные рецепты, не позволяет выдавать счётчики за точность, хранит SHA-связки входов/масок/масштаба и осевой контракт `diag(1,-1,-1)`.

**Но как только задача выходит за рамки базового запуска с настройками по умолчанию, цепочка рвётся сразу в двух местах — в обвязке и в рабочих знаниях:**
1. **Молчаливая потеря или искажение настроек в `scripts/reconstruction.py` (P0):**
   - `prepare()` применяет `config["nodes"]` **до** `CameraInit.initialize()`, который сбрасывает `intrinsics` и `viewpoints` (`F1`). Попытка задать модель дисторсии (`brown`/`fisheye4`), `locked=true` или предкалиброванные `intrinsics` молча стирается с `exit 0`, причём в `effective-settings.json` остаются и запрос пользователя, и пересозданный узел без сверки.
   - `configure_standard_transform()` оставляет `applyScale=True` при смене метода (`F2`). Для `auto_from_cameras` это допускает нормирование масштаба; пример `align_ground` при `applyTranslation=False` не доказывает перемасштабирование или поворот (см. уточнение F2).
2. **Слом сценария продолжения и диагностики (P1):**
   - Продолжение до `MeshFiltering` натыкается на противоречие инструкций и отсутствие общего экспорта/сравнения filtered-выдачи (`F3`). Отклонение иного mesh по raw SHA в отчёте защищает действующий raw-контракт и само по себе не является дефектом.
   - `settings()` падает от порядка ключей JSON на связанных атрибутах (`FeatureMatching_1` перед `FeatureExtraction_1`), а последующие вызовы молча перезаписывают пересекающиеся ключи `nodes.*` (`F4`).
   - Вход в геометрию/CAD (`extract_plane.py`) не привязан к `reconstruction-report.json`/`scale-evidence.json`: единицы и `scale_status` вводятся руками. `ConvexHull` реализует объявленный контракт выпуклого участка; автоматическая обработка проёмов этим контрактом не обещана (`F5`).
   - Есть каталог шаблонов и ранний native sparse-маршрут, усиленный PR #28/#30. Не хватает компактной диагностической таблицы «симптом → источник наблюдений → штатный рычаг → проверка эффекта» (`F6`); новый sparse-only CLI не является необходимым исправлением.

**Что уже улучшено в открытых PR (не дублируем как новые дефекты):**
- PR #28 усилил дисциплину проверки оригиналов, `CameraInit` и раннего sparse до MVS.
- PR #30 закрыл критический пробел в учёте замеров CCTag3 (`capture_measurements.py`, строгое разделение `scale` и `check`, учёт `uncertainty_mm`/`tolerance_mm`, `configs/reconstruction-cctag.example.json`, `verified_export_bindings`).
- **Поверх PR #30 остаются находки F1/F4 и отдельные ограничения F2–F7.** Их нельзя считать одинаково доказанными дефектами: F2 требует различения native-методов; F3 содержит защиту raw-контракта; F5 — объявленную границу выпуклой геометрии; ранний sparse-маршрут F6 уже есть.

---

## 2. Компактная карта покрытия по 8 областям

Условные статусы: **работает (проверено запуском)** · **частично / пробел** · **сломано в обвязке** · **рецепт без реального запуска** · **сознательно отложено**.

| Область | Нужная возможность | Путь через инструкции и native-инструмент | Способ проверки | Состояние / ограничение (`main` vs открытые PR) |
|---|---|---|---|---|
| **1. Исходники и съёмка** | Оригиналы фото/видео, EXIF, Regular/Smart, смаз/параллакс/перекрытие | `docs/capture.md`, `docs/operator.md`, `docs/runbook.md`, `KeyframeSelection` | Manifest и просмотр actual кадров | Regular выполнен в #6; Smart уже применялся на видео комнаты (см. [отчёт #27](../docs/reports/2026-11-26/room-photos.md)). Успешный отбор не равен успешной геометрии. EXIF-less кадры требуют сохранения входной идентичности/mtime. |
| **2. Камера и калибровка** | Группы `intrinsics`, смена модели дисторсии (`brown`/`fisheye4`), `locked`, отдельная калибровка (`distortionCalibration.mgt`) и перенос `.sfm` | `docs/meshroom-modes.md:439` (только строка в таблице), `scripts/reconstruction.py:319–328`, `CameraInit.py`, `ApplyCalibration` | Вручную сравнивать `effective-settings.json` и `sparse-before.json`/`scene.json` (`reconstruction_report.py` пишет только `intrinsic_count`) | **Сломано в обвязке (`F1`) + пробел знаний (`F6`):** `prepare()` сбрасывает `CameraInit.intrinsics` после `nodes`; `manifest()`/`verify_images()` блокируют вход `.sfm`; нет рецепта `distortionCalibration.mgt → ApplyCalibration` и нет проверки фактической модели/lock после `prepare` и SfM. |
| **3. Признаки, сопоставление и SfM** | Standard/Legacy, фактические пары/совпадения, выпавшие камеры | Native sparse до MVS, логи, features/matches; [памятка](../docs/camera-sfm.md) | Реальные точки/камеры и исходные изображения, actual `describerTypes` | Ранний маршрут существует в PR #28/#30. Пробел F6 — последовательность диагностики; `sparse-before.json.structure` CCTag-only нельзя использовать как общие tracks. Порядок linked-настроек — отдельный F4. |
| **4. Маски, dense и mesh** | Маски, dense, MeshFiltering, Texturing | `docs/auto-masks.md`, `docs/meshroom-modes.md`, native граф | Маски/EXR QA и осмотр геометрии | Маски Standard выполнены в #12. Filtered/Texturing имеют отдельный native-путь, но не полный общий маршрут экспорта/отчёта/сравнения; raw SHA gate нужно сохранить (F3). Комбинации Legacy + masks + CCTag и Object/TwoSides здесь не квалифицированы. |
| **5. Мишени, масштаб и контроль** | CCTag3, отдельные scale/check, неопределённость, ориентация | `capture_measurements.py`, native SfMTransform, `check_marker_scale.py` | PDF CPU-проверка, scale evidence, независимые check-пары | PR #30 разделяет scale/check. F2: `auto_from_cameras` может нормировать масштаб; `align_ground` при выключенном переносе не служит таким примером. Поворот нужно проверять численно по той же геометрии; физическая точность отдельно. |
| **6. Запуск, продолжение и смена параметров** | Повторное использование native `cache`, `remote_job.sh` / `owned_process.py`, фактические лимиты CPU/RAM/GPU, защита от подмены входов | `docs/runbook.md:568–658`, `scripts/remote_job.sh`, `scripts/owned_process.py`, `reconstruction.py:prepare --cache / verify` | `verify_run_inputs` (SHA фото/manifest/settings/масок), `owned-process` receipt (`cleanup=confirmed`), `cgroup` проверка вручную | **Частично (`F3`, `F4`):** защита от подмены входов и убийства дерева процессов сильные. **Разрывы:** противоречие инструкций по продолжению графа (`F3`); `prepare --cache` в Legacy+CCTag не восстанавливает `SfMTransform` до `scale`; `prepare_dense_images.py` не пишет native `status` (при повторном `meshroom_compute` риск пересчёта `PrepareDenseScene_1`); в `prepare()` нет проверки, что заданные в `settings` параметры не стёрлись и не перезаписались (`F1`, `F4`); в pinned Meshroom `cgroup.py` читает только cgroup v1 (задокументировано честно в `meshroom-modes.md:381`). |
| **7. Просмотр, диагностика и вход в CAD** | Фото ↔ cloud ↔ mesh; оси/масштаб в CAD | `docs/geometry-review.md`, `inspect_geometry.py`, `extract_plane.py`, `build_cad.py` | Геометрия, evidence, `thickness=unresolved` | Raw-осмотр работает. Стык единиц/SHA на входе CAD остаётся ограничением F5. ConvexHull предназначен для выпуклого участка и не восстанавливает отверстия; это граница задачи, а не нарушение контракта. |
| **8. Знания и навигация агента** | Короткий вход, непротиворечивые инструкции | `AGENTS.md`, `README.md`, context, skill, runbook | Новый сценарий без истории чата с сохранённым точным запросом | Исторический замер объёма логистики — 55.9% строк runbook, не оценка интеллекта агента или причин его выбора. Старое описание слепой проверки не содержит сохранённых точных prompts (раздел 5). |

---

## 3. Приоритетные находки с доказательствами

Ниже сохранены находки исторического аудита: подтверждённые ограничения кода, пробелы инструкций и интерпретации. Уточнения Goal #35 отделяют их от штатной защиты контрактов, объявленных границ и неподтверждённых гипотез. Приоритеты относятся к исходной базе, а не автоматически к новому кандидату.

### F1 (P0 · ограничение обвязки + пробел знаний): `prepare()` молча стирает `CameraInit.intrinsics` и блокирует предкалиброванный `.sfm`

- **Сценарий:** пользователь даёт фото на сверхширокоугольную камеру (например, 13 мм экв.) и просит применить модель дисторсии `brown` / `fisheye4`, зафиксировать калибровку (`locked` / `distortionLocked`) или подать предкалиброванный `.sfm` (например, из `distortionCalibration.mgt`).
- **Конкретный разрыв:**
  1. В [`scripts/reconstruction.py:319–328`](../scripts/reconstruction.py#L319-L328) (и в PR #30 [`cff70a49` L344–353](https://github.com/Kwentin3/photogrammetry-to-cad/blob/cff70a493bf2e56413d5f9a67f3ddb42053a4fc8/scripts/reconstruction.py#L344-L353)) цикл `config['nodes']` выполняется **до** `camera.nodeDesc.initialize(camera, ...)`. В pinned AliceVision [`CameraInit.py:505,527`](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L503-L527) метод `initialize()` вызывает `self.resetAttributes(node, ["viewpoints", "intrinsics"])` и заново заполняет их из фото.
  2. Верхние параметры `CameraInit` (`defaultFieldOfView`, `groupCameraFallback`, `sensorDatabase`, `viewIdMethod`, `isSequence`) сохраняются, **но у `CameraInit` вообще нет верхнего атрибута `defaultCameraModel` / `distortionType`**: выбор модели (`brown`, `fisheye4`, `radialk3pt` и т.д.) и флаги `locked`/`scaleLocked`/`offsetLocked`/`distortionLocked` живут **только внутри `intrinsics[*]`** — ровно там, где `initialize()` всё очищает.
  3. `effective-settings.json` записывает одновременно исходный `settings` (где остаётся запрос пользователя) и дамп `nodes.CameraInit_1` (где уже сброшенный `radialk3`/`locked=False`), **не сверяя их**.
  4. Нативно `CameraInit.initialize()` ([`CameraInit.py:515`](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L515)) умеет принимать предкалиброванный `.sfm`/`.json`, но `reconstruction.py:manifest()` (`L69`) и `verify_images()` (`L49–61`) принимают только растровые расширения и отвергают `.sfm`.
- **Источник / воспроизведение:**
  - Контракт сверен по pinned `CameraInit.py` и [`bin/meshroom_batch:254`](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/bin/meshroom_batch#L254) (в штатном `meshroom_batch` переопределения применяются *после* `initialize`).
  - Локальная проба (`REPRO_3_CAMERAINIT` и `REPRO_4_SFM_MANIFEST_REJECT` на `scripts/reconstruction.py`): `defaultFieldOfView=80.0` переживает сброс `initialize()`, а `intrinsics[0].distortionType='brown', locked=True` откатывается к `radialk3, locked=False` без ошибки; папка с `calibrated.sfm` в `manifest()` даёт пустой `files: []`, который затем падает в `verify_images()` (`Reconstruction requires at least two images`).
  - Подтверждено слепым агентом (Задача 1): не зная устройства `CameraInit.py`, агент предположил передачу модели `brown` через верхний атрибут `nodes.CameraInit_1`.
- **Последствие для пользователя:** агент запускает платный GPU-расчёт в уверенности, что применил `brown` или заблокировал калибровку, хотя фактически отработал дефолтный `radialk3` со свободной оптимизацией; искажения сверхширика остаются, а `reconstruction_report.py` (`intrinsic_count` без типа и коэффициентов) этого не замечает.
- **Минимальное исправление:**
  1. В `scripts/reconstruction.py:prepare()` разделить настройки до `CameraInit.initialize()` (верхние атрибуты `CameraInit` вроде `defaultFieldOfView`, `groupCameraFallback`, `sensorDatabase`) и **пост-инициализационные** (изменение `CameraInit.intrinsics` — либо явное `camera_intrinsics` с `type`/`distortionType`/`locked`, либо применение не-init ключей после `initialize()`), с **обязательной read-back проверкой**, что все запрошенные значения реально присутствуют в `graph.node(name)` после сборки графа (иначе `ValueError` до сохранения `project.mg`).
  2. Для предкалиброванного `.sfm` и `distortionCalibration.mgt` не расширять `manifest()` ради редкого сценария, а дать в `docs/meshroom-modes.md` короткий штатный рецепт (`ApplyCalibration` / `meshroom_batch`) и включить вывод `type`/`distortionType`/`locked`/`focalLength`/`distortionParams` в `reconstruction_report.py:scene_summary()`.
- **Достаточная проверка исправления:** unit-тест с двойником `CameraInit`, реально очищающим `intrinsics`/`viewpoints` внутри `initialize()`, проверяющий: (a) заданный `distortionType='brown'` и `locked=True` сохраняются в `effective-settings.json` после `prepare()`; (b) при попытке задать параметр, который сбрасывается или перезаписывается, `prepare()` падает с явной ошибкой; (c) на одном реальном/тестовом Linux-прогоне `CameraInit` + sparse сравнение `intrinsics` в `effective-settings.json` и `sparse-before.json` подтверждает модель и неизменность заблокированных параметров.

---

### F2 (P0 · интерпретация преобразования): Методы SfMTransform имеют разное назначение; ориентацию надо проверять на геометрии

- **Исторический REPRO_1:** `configure_standard_transform(..., method='align_ground', applyRotation=True)` оставлял `applyScale=True`, `applyTranslation=False`. Это воспроизведение словаря, не доказательство изменения масштаба.
- **Уточнение по pinned native source:** `align_ground` вызывает только `computeNewCoordinateSystemGroundAuto(sfmData, t)`; S остаётся 1, R — identity. При wrapper `applyTranslation=False` его перенос затем обнуляется. Такой пример не меняет масштаб и не выравнивает наклон сцены. Напротив, `auto_from_cameras` вычисляет `S=1/sqrt(stddev)` и может нормировать масштаб при `applyScale=True`. [main_sfmTransform.cpp](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_sfmTransform.cpp#L619-L814), [alignment.cpp](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/sfm/utils/alignment.cpp#L1063-L1114).
- **Действительный риск:** запрос «только ориентация» не задаёт метод/проверку достаточно точно, а identity в плане не доказывает actual transform. Нельзя переносить вывод о scale с одного метода на все остальные.
- **Безопасный маршрут без нового адаптера:** native `method=manual`, явные Euler-углы, `applyScale=false`, контроль координат и расстояний тех же точек/камер до/после. Параметры и ограничения — в [памятке](../docs/camera-sfm.md). Намеренное масштабирование остаётся отдельной штатной операцией.
- **Legacy на исходной базе:** `SfMTransform_1` отсутствует в prepare до scale; ориентацию нельзя обещать через тот же override. Допустим отдельный native-граф/шаг с собственной идентичностью входа и выхода.
- **Приёмка исправления:** реально изменённая ориентация при сохранённых евклидовых расстояниях; actual Scale/Rotation/Translate и SHA сцен. Сохранённый флаг или два unit-теста словаря этого не доказывают.

---

### F3 (P1 · пробел маршрута): Продолжение до MeshFiltering/Texturing не сведено в общий экспорт и сравнение; raw-отчёт защищает свой контракт

- **Сценарий:** реконструкция дошла до `Meshing_1`; на сырой сетке видны крупные треугольные перемычки через проём. Пользователь просит очистить их штатным `MeshFiltering` с `smoothingIterations=0` и получить обновлённый отчёт и сравнение до/после.
- **Конкретный разрыв:**
  1. **Прямое противоречие инструкций:** [`docs/meshroom-modes.md:267`](../docs/meshroom-modes.md#L267) говорит *«в том же проекте настроить MeshFiltering, сохранить граф и выполнить compute до его имени»*, тогда как [`docs/runbook.md:588–598`](../docs/runbook.md#L588-L598) запрещает менять завершённый RUN и требует `prepare "$NEW_SETTINGS" "$NEW_RUN" "$MESHROOM_ROOT" --cache "$CACHE"`.
  2. **Экспорт не поддерживает `MeshFiltering`/`Texturing`:** [`scripts/reconstruction.py:431–435`](../scripts/reconstruction.py#L431-L435) жёстко экспортирует `node(graph, 'Meshing').outputMesh.value`.
   3. **Отчёт принимает именно raw mesh:** ошибка `--mesh does not match verified export: mesh_export.sha256` при подстановке filtered-файла — правильная защита происхождения. Подпись `raw native Meshing output` корректна для принятого входа. Отдельный filtered-результат требует явного происхождения, параметров и собственной SHA-связки; ослаблять raw-проверку нельзя.
  4. **Визуальный просмотр не сравнивает две сетки:** [`scripts/inspect_geometry.py:87–90, 170`](../scripts/inspect_geometry.py#L87-L90) поддерживает `--compare-cloud`, но не `--compare-mesh`, и жёстко подписывает панель `"Original raw mesh"`.
  5. **Скрытый срыв кэша при `prepare --cache`:** (a) в `Legacy + CCTag3` новый `prepare --cache` не содержит пост-sparse `SfMTransform`, пока не повторить `scale` (а `prepare_dense_images.py` не пишет native `status`, поэтому `meshroom_compute` снова планирует `PrepareDenseScene_1` — подтверждено `dfsToProcess` в `docs/meshroom-modes.md:332`); (b) на кадрах без EXIF (`video_frames.py`) `CameraInit` UID зависит от `mtime` (`docs/auto-masks.md:140–145`), поэтому `prepare --cache` после переноса кэша может пересчитать весь граф с нуля.
- **Источник / воспроизведение:** чтение `reconstruction.py`, `reconstruction_report.py`, `inspect_geometry.py` и инструкций; раздел 5 сохраняет исторический пересказ дополнительной проверки. Точный prompt и полный trace той проверки не сохранены, поэтому её независимость нельзя повторно установить по этому документу.
- **Последствие для пользователя:** отдельный native filtered-выход требует явной ручной выдачи и сравнения с raw baseline. Это неудобство маршрута, а не разрешение подменить raw-вход в отчёте. Повторное использование кэша нужно сверять по upstream UID до дорогого расчёта.
- **Минимальное исправление:**
  1. Устранить противоречие в доках: один согласованный путь (новый RUN через `prepare --cache` + обязательная сверка совпадения upstream UID `Meshing_1` до запуска `meshroom_compute`).
   2. Если появится отдельная задача на filtered-выдачу, добавить её собственные source-node/processing/SHA evidence, сохранив raw `mesh.obj` и raw SHA gate. Не принимать filtered mesh как raw ради прохождения отчёта.
  3. Добавить `--compare-mesh` в `inspect_geometry.py` (небольшая правка на ~15 строк) — вместо того чтобы заставлять агента импровизировать рендер каждый раз.
- **Достаточная проверка исправления:** локальные unit-тесты на `export`/`reconstruction_report.py`/`inspect_geometry.py` с двумя разными OBJ (raw + filtered) и проверка, что `reconstruction_report.py` фиксирует параметры `MeshFiltering_1` (`smoothingIterations=0`), не путая raw и filtered SHA; один реальный Linux-прогон `meshroom_compute --toNode MeshFiltering_1` поверх готового кэша при следующем GPU-сеансе (подтвердить переиспользование `Meshing_1` и оси выходного OBJ).

---

### F4 (P1 · ограничение обвязки): `settings()` падает от порядка ключей JSON на связанных атрибутах, а пост-шаги `prepare()` молча перезаписывают `nodes.*`

- **Сценарий:** агент включает `cctag3` (в `FeatureExtraction_1`, `FeatureMatching_1`, `StructureFromMotion_1`) или задаёт `FeatureExtraction_1.maxThreads` / параметры масок через `settings.json`.
- **Конкретный разрыв:**
  1. В обоих шаблонах `photogrammetry.mgt` и `photogrammetryLegacy.mgt` атрибут `FeatureMatching_1.describerTypes` связан ссылкой `{FeatureExtraction_1.describerTypes}`, а `StructureFromMotion_1` / `TracksBuilding_1` ссылаются на `{FeatureMatching_1.describerTypes}`.
  2. [`scripts/reconstruction.py:99–106`](../scripts/reconstruction.py#L99-L106) в цикле по `config['nodes']` при встрече `attr.isLink` сравнивает `attr.value != value` и кидает `ValueError('Conflicting linked setting')`. Если в JSON `FeatureMatching_1` стоит *раньше* `FeatureExtraction_1`, **`prepare()` падает даже при полностью согласованных значениях**. Пример в PR #30 (`configs/reconstruction-cctag.example.json`) работает лишь из-за случайного порядка ключей.
  3. Сразу после цикла `config['nodes']` строки [`L321`](../scripts/reconstruction.py#L321) (`FeatureExtraction.maxThreads = threads`) и [`L325`](../scripts/reconstruction.py#L325) (`configure_masks`, задающий `masksFolder`/`masksFolders`/`maskExtension`/`maskInvert`/`outputFileType`/`saveMetadata`) **молча перезаписывают** любые значения этих полей, заданные агентом в `nodes.*`, не поднимая ошибку конфликта.
- **Источник / воспроизведение:**
  - Локально воспроизведено (`REPRO_2_ORDER_CRASH`): `ValueError: Conflicting linked setting: FeatureMatching_1.describerTypes` при подаче `[FeatureMatching_1, FeatureExtraction_1]` с одинаковым `['dspsift', 'cctag3']`.
  - Причина пропуска в CI: [`tests/test_reconstruction_preflight.py:32`](../tests/test_reconstruction_preflight.py#L32) использует `AttributeNode`, где у всех атрибутов жёстко стоит `isLink=False`.
- **Последствие для пользователя:** хрупкое падение `prepare()` от перестановки ключей в JSON (например, после сериализации `json.dumps(..., sort_keys=True)`) и тихая перезапись пользовательских настроек `nodes.*` параметрами `resources`/`masks`.
- **Минимальное исправление:** в `prepare()` сначала применить все не-связанные атрибуты (плюс `resources`/`masks` с явной ошибкой при конфликте с `nodes.*`), и только **вторым проходом** проверять все `attr.isLink` (плюс итоговая сверка эффективных значений после `CameraInit.initialize()`).
- **Достаточная проверка исправления:** unit-тест с реальным `isLink=True` двойником: (a) обратный порядок `FeatureMatching_1` → `FeatureExtraction_1` с одинаковым списком проходит; (b) реальное расхождение списков по-прежнему падает; (c) конфликт `nodes.FeatureExtraction_1.maxThreads` с `resources.threads` даёт явный `ValueError`, а не тихую перезапись.

---

### F5 (P1 · стык единиц): Незащищённый ввод масштаба в CAD и объявленная граница выпуклого участка

- **Сценарий:** после получения масштабированного `dense.ply` (в мм или м) агент извлекает плоскость и передаёт параметры в `build_cad.py` → STEP.
- **Конкретный разрыв:**
  1. [`scripts/extract_plane.py:145–148`](../scripts/extract_plane.py#L145-L148) принимает `--meters-per-unit` и `--scale-status` как свободные CLI-аргументы **без привязки к `reconstruction-report.json` или `scale-evidence.json`**. Агент может передать `--meters-per-unit 1.0` для облака в миллиметрах (ошибка в 1000×) или `--scale-status measured` для облака с `scale.mode="unknown"`, и ошибка беззвучно пройдёт в JSON параметров и в STEP.
   2. `extract_plane.py` строит `ConvexHull` и явно объявляет выпуклый контур без отверстий. Он не обещает восстановление проёмов; заполнение отверстия при попытке применить его ко всей стене — выход за этот контракт. Общий маршрут «облако → границы проёма → CAD» остаётся отдельной будущей задачей.
  3. [`scripts/inspect_geometry.py:164`](../scripts/inspect_geometry.py#L164) требует обязательный `--mesh` (нельзя визуально проинспектировать одно облако/разреженный SfM) и хардкодит путь к шрифту `C:/Windows/Fonts/arial.ttf` (`L71`, с fallback на крошечный bitmap-шрифт на Linux).
- **Источник / воспроизведение:** чтение `scripts/extract_plane.py`, `scripts/build_cad.py`, `scripts/inspect_geometry.py`.
- **Последствие для пользователя:** риск получить STEP с неверным масштабом в 10×/1000× или ложным статусом `measured`, не имея автоматической сверки с `scale-evidence.json`, несмотря на всю строгость SHA-проверок на предыдущем этапе.
- **Минимальное исправление:**
  - В `extract_plane.py` добавить опциональный `--report` (`reconstruction-report.json`): если передан, автоматически сверять `source_sha256 == report.inputs.cloud.sha256`, выводить `meters_per_unit` из `report.scale.units` (`mm→0.001, cm→0.01, m→1.0`) и запрещать `--scale-status measured` при `report.scale.applied != True`.
  - В `inspect_geometry.py` сделать `--mesh` опциональным (для осмотра sparse/cloud-only).
  - *Вопрос проёмов (невыпуклый контур / пересечение 4 плоскостей откосов)* сознательно не решать костылём в `extract_plane.py` до первого реального масштабированного прогона на проёме, но явно зафиксировать границу текущего скрипта.
- **Достаточная проверка исправления:** unit-тест в `tests/test_geometry.py`: несовпадение SHA облака, попытка передать `measured` при `scale.applied=false` или неверные единицы (`mm` vs `1.0`) отклоняются с `ValueError`.

---

### F6 (P1 · пробел знаний): Нужен рабочий порядок диагностики, ранний sparse-маршрут уже существует

- **Сценарий:** зарегистрирована часть кадров или геометрия двоится/изгибается. Числа 20/150 из исторического примера не являются универсальным порогом.
- **Что уже есть:** PR #28/#30 описывают actual native sparse, экспорт точек/камер и решение до MVS. Требование `--cloud` у финального raw-отчёта не отменяет этот маршрут; новый `--sparse-only` не нужен для его использования.
- **Граница источника:** проектный `sparse-before.json` сохраняет views/poses/intrinsics, но `structure` CCTag-only. Для обычных tracks, длины наблюдений и residuals нужен полный native scene/соответствующий экспорт и логи/features/matches. Не вычислять отсутствующие метрики из marker-only structure.
- **Пробел инструкции:** связать симптом с исходными кадрами и фактическими CameraInit groups/models/locks, списком пар ImageMatching, проверенными соответствиями FeatureMatching, sparse-покрытием и исходом SfM. Модель камеры и distortionType — разные поля; ultra-wide не означает обязательный brown.
- **Штатные рычаги:** ImageMatching выбирает пары (Sequential/SequentialAndVocabularyTree/Exhaustive и настроенный minNbImages), FeatureMatching проверяет их геометрию. Менять один параметр при наблюдаемой причине; не обещать спасение по числу кадров. [Pinned ImageMatching](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ImageMatching.py#L56-L124), [CameraInit](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L72-L151).
- **Минимальное улучшение:** [короткая памятка](../docs/camera-sfm.md) «симптом → native evidence → оправданное действие → остановка», включая ApplyCalibration и свободные/заблокированные intrinsics. Готовая калибровка допустима через native CLI/граф без расширения общего manifest.
- **Проверка:** новый агент решает ограниченную пользовательскую проблему без истории чата; точный prompt, существенные команды/наблюдения и вывод сохраняются. Старый пересказ не позволяет восстановить исходные prompts.
- **Вне этого среза:** HSV ImageMasking, мелкие мишени на столе и общий filtered/Texturing delivery остаются отдельными сценариями; наличие этих рецептов не является новой GPU-квалификацией.

---

### F7 (P2 · навигация): Большой объём логистики и повторяющаяся хроника; влияние на решения требует отдельной проверки

- **Сценарий:** новый агент заходит в репозиторий решать пользовательскую фотограмметрическую задачу.
- **Конкретный разрыв:**
   - Исторический замер на `main`: 501/897 строк runbook (55.9%) отнесены к облачной логистике, 91 (10.1%) — к отчёту/просмотру, 256 (28.5%) — к фотограмметрии. Это классификация объёма текста, не метрика интеллекта, самостоятельности или качества выбора. По ней нельзя причинно объяснить ошибки агента.
  - Хронологические отчёты по Goals #2–#21 дублируются в начале [`README.md:9–49`](../README.md#L9-L49), [`AGENTS.md:9–30` и `92–105`](../AGENTS.md#L9-L30) (где на `L14` висит устаревшее *«PR #20 ещё не влит»*, хотя в `README.md:14` он уже указан влитым) и [`docs/project-context.md:3–54`](../docs/project-context.md#L3-L54).
- **Предполагаемое последствие:** длинная навигация может затруднять поиск нужной команды. Это проверяется сценарием по репозиторию, а не процентом инфраструктурных строк.
- **Минимальное исправление:** вынести/сослать облачный транспорт из `docs/runbook.md` в уже существующий `docs/infrastructure.md`, а в `AGENTS.md` и `README.md` оставить короткий блок «Текущий статус» на 5–7 строк со ссылкой на один источник (`docs/project-context.md`).
- **Достаточная проверка улучшения:** нужный маршрут находится по текущей точке входа; новый агент проходит ограниченный сценарий, сохраняя правила безопасности. Сокращение вдвое не является критерием приёмки.

---

### Что проверено и признано обоснованным исключением (НЕ дефекты)

1. **Запрет `CCTag3` в `Standard` (`reconstruction.py:302–304`):** обоснованно — кодирование ID CCTag в новом модульном DAG (`TracksBuilding → SfMBootStrapping → SfMExpanding`) реально не квалифицировано запуском; обход через `Legacy` документирован явно.
2. **Запрет `masks.invert=True` (`reconstruction.py:165–166`):** обоснованно — у `ExportImages` и `PrepareDenseScene` в pinned AliceVision действительно нет атрибута `maskInvert`, в отличие от `FeatureExtraction`.
3. **Отклонение `scale.mode="marker_coords"` в общем адаптере (`reconstruction.py:298–299`):** обоснованно — полные 3D-координаты мишеней (`from_markers`) требуют тахеометра/поверенной рамки и иного контракта, чем рулетка между двумя центрами.
4. **Отказ от немедленного внедрения `mrSegmentation` / `mrRomatch` (RoMa) / `LightGlue`:** обоснованно — требуют 6+ ГБ весов, внешних плагинов (с подтверждённым расхождением API и лицензионным вопросом DINOv3 #52 для RoMa) и не заменяют базовую диагностику съёмки.
5. **Синхронизация `prepare()` с `verify_run_inputs()` и неизменяемость завершённого RUN:** сильное и правильное решение — его не нужно ослаблять, нужно лишь сделать продолжение в новый RUN через `--cache` действительно рабочим (`F3`).

---

## 4. Неподтверждённые подозрения и границы выполненных проб

Чтобы не смешивать доказанные дефекты с предположениями, границы наших локальных проверок фиксируются явно:

1. **Linux AliceVision / GPU не запускались** (аудит проводился на Windows без аренды GPU и без запуска `meshroom_compute`):
   - **Не проверено в реальном прогоне:** поведение `IntrinsicsTransforming` + `ExportImages` на сверхширокоугольной камере (13 мм экв.) с моделью `brown` (возможная сильная обрезка поля зрения / нулевые углы alpha при undistortion).
   - **Не проверено в реальном прогоне:** осевая конвенция `MeshFiltering.outputMesh` (ожидается `(x, -y, -z)` от `Mesh::save`, как у `Meshing`, но фактический Linux-выход в проекте ни разу не проверялся).
   - **Не проверено в реальном прогоне:** сохранение красного канала CCTag3 ID в новом `Standard` DAG (`TracksBuilding → SfMBootStrapping → SfMExpanding`). По `photogrammetry.mgt` видно, что `SfMTransform_1` стоит *до* `SfMColorizing_2`, поэтому гипотеза, что проблема именно в порядке `SfMColorizing`, не подтверждается — проверять нужно именно перенос `describerTypes=['cctag3']` и ID через `TracksBuilding`/`SfMExpanding` в живом Linux runtime.
   - **Не проверено этим аудитом:** совместный прогон `Legacy + masks.features=true + CCTag3 + measured_baseline` на поворотном столе. Smart на видео комнаты уже выполнялся; не считать его отсутствующим опытом только потому, что данный аудит не запускал его заново.
2. **Локальные Python-пробы на Windows:**
   - Выполнены прямые воспроизведения контрактов `scripts/reconstruction.py` (`REPRO_1`–`REPRO_4`) на `origin/main` (`9d4ad784`) — все 4 воспроизведения сработали детерминированно (`exit 0`).
   - Прогон `python -m unittest discover -s tests` в системном Python 3.11 прошёл 68/74 тестов; 6 падений связаны исключительно с отсутствием `open3d` в глобальном Python (Open3D установлен в отдельном приватном окружении владельца, `docs/runbook.md:67`).
3. **Входные артефакты реальной съёмки комнаты (PR #28):** анализировались по отчёту и коду в PR #28/#30 без доступа к приватным фото/облакам вне Git.

---

## 5. Историческое описание независимой проверки другим агентом

Исходный аудит сообщает о read-only агенте без истории переписки на `9d4ad784` и четырёх коротких задачах. Сохранён пересказ результатов ниже, но точные prompts, существенные команды и полный trace не приложены. Поэтому это историческое свидетельство, а не воспроизводимый слепой тест; восстанавливать формулировки задним числом нельзя. Goal #35 требует нового ограниченного сценария с сохранением точного запроса и наблюдений.

| Задача | Что сработало отлично (агент справился по репо) | Где агент упёрся в реальный разрыв или ошибся из-за репо |
|---|---|---|
| **1. Камера 13 мм, `brown` или предкалиброванные заблокированные `intrinsics`** | Верно выбрал `Standard`, верно запросил оригиналы с EXIF, контрольные диагонали и формат калибровки; **сам заметил** по коду `reconstruction.py:319–328`, что `prepare()` не позволяет задать предкалиброванные `intrinsics`, и что `reconstruction_report.py` пишет только `intrinsic_count`. | **Попался в ловушку отсутствия знаний о `CameraInit.py`:** предположил, что модель `brown` можно передать «верхним атрибутом `nodes.CameraInit_1`» (которого не существует в pinned `CameraInit.py`), и вынужден был отложить выбор точных имён до чтения runtime. Не нашёл рецепта стыковки `distortionCalibration.mgt`. |
| **2. MeshFiltering без сглаживания + отчёт** | В историческом пересказе найдены `smoothingIterations=0`, raw baseline и необходимость сравнения вершин | Перечислены пробелы инструкции/экспорта/сравнения. Отклонение filtered mesh по raw SHA и raw-подпись — защита контракта, а не ложное происхождение принятого файла. |
| **3. Поворотный стол с метками `CCTag3` в мм** | Безупречно выбрал `Legacy + masks.features=true + CCTag3 + measured_baseline`, жёстко отделил проверенные куски (#4/#6/#12/#15) от непроверенной целевой связки, верно потребовал ≥ 60 px и Linux CPU-пробу. | Выявил практические пробелы: (1) `make_capture_kit.py` запрещает диаметр < 20 мм и кладёт 1 метку/лист; (2) `mask-turntable-white.json` вырежет белые поля самих меток, `generate_masks.py single` отрежет метки от детали, а `ImageMasking` описан только через GUI; (3) расхождение доков и `configs/cctag.json` по `StructureFromMotion_1.describerTypes`. |
| **4. Видео помещения: частичная регистрация** | В пересказе агент остановился до MVS и рассмотрел кадры/параллакс/сопоставление | Нужна понятная последовательность диагностики. Ранний native sparse-маршрут уже описан в PR #28/#30; CCTag-only JSON не является источником ordinary tracks/residuals. |

**Граница вывода:** пересказ указывает на полезную дисциплину и возможные навигационные пробелы. Он не доказывает по отсутствующим prompts ни полноту отсутствия подсказок, ни причинную связь всех ошибок с репозиторием. Кодовые ограничения F1/F4 обоснованы отдельно чтением и локальными пробами; уточнения F2/F3/F6 выше обязательны.

---

## 6. Ответы на неудобные вопросы

1. **После #8/#15 появилось рабочее знание или преимущественно каталог возможностей? Почему случай с калибровкой прошёл мимо, и где ещё тот же слепой участок?**  
   Исторические тесты охватывали инженерные контракты, но не проверяли применение настроек реальным CameraInit после initialize. Двойник со сбросом атрибутов обнаруживает регрессию F1; реальные linked-зависимости нужны для F4. Для F2 необходима проверка геометрии, а не одного словаря флагов. Native-проверки Goal #35 и их ограничения фиксируются в отдельном [отчёте](../docs/reports/2026-11-26/camera-sfm.md).

2. **Может ли новый агент выполнить другую съёмку только по репозиторию, без памяти автора и копирования параметров старого запуска?**  
    Для исторической базы базовый маршрут до Meshing проверен, а нестандартные режимы требуют чтения native-параметров и иногда отдельного native-графа. Нельзя делать общий вывод о неспособности нового агента только из старого пересказа. Новая памятка и ограниченный сценарий #35 проверяют конкретно настройку камеры и решение до dense.

3. **Может ли агент уверенно сообщить, что изменил настройку, хотя подготовка её стёрла, другой узел переопределил или downstream её не использует? Обнаружат ли это текущие проверки?**  
    Да: исходный запрос может отличаться от фактического графа. F1/F4 описывают потерю настроек; F2 требует проверки реально выполненного преобразования. Значение `applyScale=True` доказывает возможность масштабирования только вместе с выбранным методом/геометрией, а не само изменение расстояний. Проверки исходного JSON недостаточно.

4. **Не закрыли ли мы собственной обвязкой штатную возможность? Может ли агент воспользоваться нужным native-режимом без переписывания Python под очередной объект?**  
    На исходной базе общий адаптер мешает части overrides F1/F4 и некоторым ориентационным сценариям F2. Готовая калибровка доступна через native ApplyCalibration/граф без расширения manifest; отдельная filtered-выдача — иной контракт. Ранний sparse-путь уже есть; новый sparse-only report CLI не требуется, а CCTag-only JSON не заменяет полную сцену.

5. **Умеет ли агент различить ошибку калибровки, плохие соответствия, недостаток ракурсов, проблему dense и дефект экспорта?**  
    Такие причины нельзя однозначно определить по одному виду сетки или доле камер. Следует сопоставить исходные кадры, пары, проверенные соответствия, actual intrinsics, полную sparse-сцену и логи; затем испытать один обоснованный рычаг. Конкретная последовательность дана в [памятке](../docs/camera-sfm.md).

6. **Почему мы обсуждаем дополнительный инструмент (например MicMac/MMVII в #31 или RoMa): он закрывает подтверждённый недостаток или мы ещё не научили агента использовать основной стек?**  
    Наличие сложного набора или сверхширокоугольного объектива само по себе не доказывает предел AliceVision. Сначала нужны сохранённые настройки, фактические native-результаты и диагноз. Не считать `brown` обязательной правильной моделью или locks улучшением точности; новый стек рассматривают при подтверждённом недостатке основного маршрута, а не вместо этих проверок.

7. **Может ли повторный расчёт выглядеть успешным, но использовать старые камеры, маски, масштаб или геометрию? Как связываются входы, параметры и выданный результат?**  
   - **На этапе `reconstruction.py` + `reconstruction_report.py` — защита сильная:** `verify_run_inputs()` проверяет SHA всех фото, `manifest.json`, `settings.json` и каждой маски; `scale-evidence.json` привязан к `scene.json` SHA; в PR #30 `verified_export_bindings` дополнительно проверяет SHA `scene`/`cloud`/`mesh`.
    - Остаточные ограничения: ручная filtered-выдача нуждается в отдельной привязке; ориентационный override должен отражать фактическое преобразование; ввод единиц/статуса в extract_plane остаётся отдельным стыком F5. Raw SHA rejection — работающая защита, её нельзя называть дырой.

8. **Не используем ли контрольные данные для подгонки? Что на самом деле подтверждают малая репроекция, все зарегистрированные камеры, густое облако, гладкая стена и одна совпавшая контрольная длина?**  
   - В PR #30 (`capture_measurements.py`) дисциплина разделения `scale` и `check` выстроена образцово — контрольные пары физически не подаются в `SfMTransform`.
   - **Что НЕ доказывают отдельные зелёные метрики:**
     - *Малая репроекция* подтверждает лишь внутреннюю согласованность 2D-наблюдений и может скрывать глобальный перекос/«чашу» (bowl effect) от неверной дисторсии.
      - *100% зарегистрированных камер* означает определённые позы для всех соответствующих views; само по себе не доказывает единую правильную связность, глубину, физическую точность или отсутствие дрейфа.
     - *Густое облако / гладкая стена* могут быть результатом интерполяции/сглаживания (`smoothingIterations=5`) поверх смещённой поверхности.
      - *Одна совпавшая контрольная длина* проверяет только этот участок и направление. Дополнительные независимые размеры выбирают под задачу и неопределённость; универсальный обязательный минимум диагоналей здесь не установлен.

9. **Не просим ли человека сделать то, что агент может выяснить из файлов или выполнить штатной командой? И наоборот: не обещаем ли восстановить скрытую поверхность или неизвестный размер без новых наблюдений?**  
   - *Скрытые поверхности и неизвестные размеры* проект честно не обещает (`thickness=unresolved`, `scale.mode=unknown`, запрет выдавать `MeshFiltering` за новые наблюдения).
   - *Лишние просьбы к человеку* пока возможны в двух местах: (а) модель камеры, фокусное расстояние, ориентацию, разрешение и наличие зума агент должен сам вычитать из EXIF/`ffprobe`/`CameraInit` *до* вопросов человеку (в PR #28 это уже начали исправлять); (б) при провале SfM из-за отсутствия локальной sparse-диагностики агент рискует попросить человека «переснять», прежде чем сам проверил, не сломал ли сшивку `ImageMatching` или неверная модель камеры.

10. **Если все текущие проверки зелёные, может ли пользователь всё ещё не получить нужный проём, кромку или достоверный размер? Какая короткая проверка обнаружит именно этот разрыв?**  
     Да. Техническая целостность не проверяет границы нужного проёма или его истинные размеры. ConvexHull не следует применять как средство восстановления отверстий: он объявлен для выпуклого участка. Следующий CAD-этап требует отдельного контракта и проверок.
     Адресная проверка: сопоставить исходные фото с raw cloud/mesh и сечениями в нужном проёме, проверить существенные границы и независимые доступные check-отрезки с их uncertainty. Состав размеров и допуск согласуется для задачи; запретить автоматическую готовность к изготовлению по одному отчёту.

11. **Какие правила можно удалить или упростить без потери результата? Не занимают ли инфраструктура, доказательства и общие запреты больше внимания, чем выбор и оценка самой фотограмметрической обработки?**  
     Исторический замер объёма текста показывает возможность улучшить навигацию, но не доказывает, что инфраструктура мешает выбору модели. Проверка — пользовательский сценарий по инструкции; реорганизация всего архива не входит в Goal #35. Полезные кандидаты на будущее:
    - убрать дублирующуюся хронику Goals #2–#21 из `README.md` и `AGENTS.md` (оставив один короткий статус со ссылкой на `docs/project-context.md`);
    - вынести блоки аренды/SSH/rclone/split-parts из `docs/runbook.md` в `docs/infrastructure.md`, чтобы `runbook.md` стал коротким рабочим руководством по запуску пайплайна;
    - не ослаблять правила SHA-проверок, `cleanup=confirmed` и запрета выдуманного масштаба — они компактны в коде и реально защищают от дорогих ошибок.

---

## 7. Минимальный план исправления и ОДИН наиболее полезный следующий шаг

Распределение минимальных действий по слоям (без нового оркестратора, без раздувания `SKILL.md` и без россыпи issue):

| Слой | Что сделать | Что сознательно отложить |
|---|---|---|
| **Минимальная правка адаптера** | Сохранить intrinsics после initialize, проверить linked-параметры независимо от порядка и явно отклонять настоящие конфликты; назначение ориентации сверять по реальному transform/геометрии | Не вводить правило «любой нестандартный method → запрет scale»; намеренное масштабирование остаётся допустимым. Не превращать manifest фото в загрузчик .sfm. |
| **Отчёт и CAD, вне Goal #35** | Сохранить находки F3/F5 как будущие отдельные стыки; raw SHA protection не ослаблять | Новый sparse-only/compare-mesh CLI, filtered/Texturing delivery и CAD-единицы не являются обязательной поставкой #35. |
| **Штатный вызов (без кода)** | Предкалибровка (`distortionCalibration.mgt` + `ApplyCalibration`), нестандартные графы (`ObjectTurntable`/`TwoSides`, `ImageMasking` при надобности) и `Texturing` — через штатные `meshroom_batch`/`meshroom_compute`. | Не устанавливать `mrSegmentation` / `mrRomatch` / MicMac в базовый стек без подтверждённого провала настроенного AliceVision. |
| **Инструкции** | Короткая [памятка камеры/SfM](../docs/camera-sfm.md), ссылки из текущего входа и адресный новый сценарий без чата | Не вводить универсальные пороги камер/кадров, preset для ultrawide или квоту сокращения runbook. |

### Один наиболее полезный следующий шаг

> **Приоритет Goal #35:** устранить потерю/неоднозначность настроек F1/F4, показать фактическое применение camera settings и безопасный native-поворот на геометрии; пройти раннее sparse-решение и один новый сценарий без истории чата. Использовать существующие native-выходы, не требуя нового отчётного режима.

**Граница плана:** это цель отдельного #35, а не свидетельство её выполнения этим историческим аудитом. Native-проверка должна показать потребление настройки и геометрию, а не только флаги. Улучшение физической точности, калибровка комнаты, новый dense-прогон и CAD требуют своих наблюдений/измерений.

---

## 8. Проект минимальных правок рабочих инструкций (черновик, не применён)

*Ниже — компактный проект изменений; живые файлы `SKILL.md`, `docs/meshroom-modes.md` и `docs/runbook.md` в этом PR не изменялись.*

1. **`.agents/skills/photogrammetry-workflow/SKILL.md` (не раздувать — +2 строки):**
   - В п. 3 уточнить: *«После `prepare` сверь фактические `nodes` в `effective-settings.json` (особенно `CameraInit.intrinsics`, `SfMTransform`, `MeshFiltering`), а не исходный JSON запроса.»*
   - В п. 5 уточнить: *«При неполном SfM остановись до MVS, сопоставь кадры с native sparse/логами и полными observations; CCTag-only structure не использовать как обычные tracks.»*
2. **`docs/meshroom-modes.md`:**
   - На стр. 267 заменить *«в том же проекте настроить MeshFiltering»* на единое правило из `runbook.md`: *«создать новый RUN через `prepare --cache` и сверить совпадение upstream UID до `Meshing_1` перед `meshroom_compute`»*.
   - Для ориентации дать проверяемый native manual-поворот с `applyScale=false` и сравнением расстояний; объяснить отличие `align_ground` от `auto_from_cameras`. Намеренный scale разрешать явно; Legacy вести отдельным native-шагом.
   - Дать ссылку на компактную таблицу «симптом → native evidence → обоснованный рычаг → остановка» в отдельной памятке; не выдавать CCTag-only JSON за полную sparse-диагностику.
3. **`docs/runbook.md` / `AGENTS.md` / `README.md`:**
   - Перенести детали выбора ноды / rclone / split-parts из `docs/runbook.md` в `docs/infrastructure.md` со ссылкой в одну строку.
   - Убрать дублирование хроники Goals #2–#21 из `AGENTS.md` и `README.md`, оставив актуальную ссылку на `docs/project-context.md`.
