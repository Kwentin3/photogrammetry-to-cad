# Аудит #33: умеет ли агент использовать возможности текущего фотограмметрического стека

**Основание:** [Issue #33](https://github.com/Kwentin3/photogrammetry-to-cad/issues/33).  
**Характер документа:** read-only аудит инструкций, скриптов и закреплённых контрактов. Исправления в рабочий код, живой `SKILL.md` и `docs/` в рамках этого аудита не вносились; платные GPU-ресурсы не запускались (`$0`).

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
   - `configure_standard_transform()` при включении ориентации (`method: "align_ground"` / `"auto_from_cameras"`, `applyRotation: true`) молча оставляет **`applyScale=True`** (`F2`), меняя масштаб сцены вопреки `scale-plan.json` (`mode="unknown", scale=1.0`).
2. **Слом сценария продолжения и диагностики (P1):**
   - Продолжение до `MeshFiltering` (например, убрать перемычки без сглаживания) натыкается на прямое противоречие между `docs/meshroom-modes.md` и `docs/runbook.md`, не экспортируется `reconstruction.py export`, **отклоняется** `reconstruction_report.py` по `mesh_export.sha256` и не сравнивается в `inspect_geometry.py` (`F3`).
   - `settings()` падает от порядка ключей JSON на связанных атрибутах (`FeatureMatching_1` перед `FeatureExtraction_1`), а последующие вызовы молча перезаписывают пересекающиеся ключи `nodes.*` (`F4`).
   - Вход в геометрию/CAD (`extract_plane.py`) никак не привязан к `reconstruction-report.json`/`scale-evidence.json` (единицы и `scale_status` вводятся руками без проверки SHA), а контур строится единственным `ConvexHull`, перекрывающим проёмы (`F5`).
   - В документации есть **каталог шаблонов** (27 `.mgt`), но почти нет **диагностической таблицы «симптом SfM/камеры → конкретный штатный рычаг AliceVision → как проверить эффект»** и нет штатного sparse-only отчёта до MVS (`F6`).

**Что уже улучшено в открытых PR (не дублируем как новые дефекты):**
- PR #28 усилил дисциплину проверки оригиналов, `CameraInit` и раннего sparse до MVS.
- PR #30 закрыл критический пробел в учёте замеров CCTag3 (`capture_measurements.py`, строгое разделение `scale` и `check`, учёт `uncertainty_mm`/`tolerance_mm`, `configs/reconstruction-cctag.example.json`, `verified_export_bindings`).
- **При этом все ключевые разрывы `F1`–`F7` сохраняются и поверх PR #30 (`cff70a49`).**

---

## 2. Компактная карта покрытия по 8 областям

Условные статусы: **работает (проверено запуском)** · **частично / пробел** · **сломано в обвязке** · **рецепт без реального запуска** · **сознательно отложено**.

| Область | Нужная возможность | Путь через инструкции и native-инструмент | Способ проверки | Состояние / ограничение (`main` vs открытые PR) |
|---|---|---|---|---|
| **1. Исходники и съёмка** | Оригиналы фото/видео, EXIF, отбор кадров Regular/Smart, диагностика смаза/параллакса/перекрытия | `SKILL.md`, `docs/capture.md`, `docs/operator.md`, `docs/runbook.md`, `scripts/video_frames.py`, `KeyframeSelection` | `manifest.json` (SHA/размеры), визуальный просмотр кадров, `scores.csv` в `seal` | **Частично:** Regular отбор на 37 кадрах выполнен (#6); в PR #28 усилена проверка оригиналов/EXIF. **Smart** остаётся непроверенным рецептом; нет руководства по видеосъёмке интерьеров/шириков; `CameraInit` UID на EXIF-less кадрах зависит от `mtime` (`docs/auto-masks.md:140`). |
| **2. Камера и калибровка** | Группы `intrinsics`, смена модели дисторсии (`brown`/`fisheye4`), `locked`, отдельная калибровка (`distortionCalibration.mgt`) и перенос `.sfm` | `docs/meshroom-modes.md:439` (только строка в таблице), `scripts/reconstruction.py:319–328`, `CameraInit.py`, `ApplyCalibration` | Вручную сравнивать `effective-settings.json` и `sparse-before.json`/`scene.json` (`reconstruction_report.py` пишет только `intrinsic_count`) | **Сломано в обвязке (`F1`) + пробел знаний (`F6`):** `prepare()` сбрасывает `CameraInit.intrinsics` после `nodes`; `manifest()`/`verify_images()` блокируют вход `.sfm`; нет рецепта `distortionCalibration.mgt → ApplyCalibration` и нет проверки фактической модели/lock после `prepare` и SfM. |
| **3. Признаки, сопоставление и SfM** | Выбор Standard/Legacy, тюнинг `FeatureExtraction` / `ImageMatching` / `FeatureMatching` / `SfMExpanding` / `StructureFromMotion`, диагностика выпавших камер | `docs/meshroom-modes.md:70–88`, `docs/runbook.md:468–520`, `reconstruction.py`, `configs/*.json` | `sparse-before.json` (вручную) + логи в `cache/`; `reconstruction_report.py` требует `--cloud` (не работает на sparse-only) | **Частично (`F4`, `F6`):** базовые Standard и Legacy выполнены на 37 кадрах (#6), отказ от преждевременного RoMa работает хорошо. Нет диагностического маршрута «выпало >50% камер → какие узлы и параметры смотреть» (`ImageMatching` Sequential/VocabTree на 100+ кадрах, `akaze`, `guidedMatching`, `fundamental_with_distortion`, `minAngleForTriangulation`), нет sparse-only отчёта; порядок ключей JSON в `settings()` вызывает краш на linked-атрибутах (`F4`). |
| **4. Маски, dense и mesh** | Маски фона (`features=false/true`), `ImageMasking` (HSV), `ExportImages`/`PrepareDenseScene`, `DepthMap`/`Meshing`, `MeshFiltering` без сглаживания, `Texturing` | `docs/auto-masks.md`, `docs/meshroom-modes.md:113–185, 220–306`, `scripts/generate_masks.py`, `scripts/prepare_dense_images.py`, `scripts/check_dense_images.py` | `validate_masks` (SHA + `pyalicevision` W×H), `check_dense_images.py` (EXR/alpha/metadata), `inspect_geometry.py` | **Разнородно (`F3`):** Standard dense-only авто-маски выполнены (#12); `check_dense_images.py` и `prepare_dense_images.py` (для Legacy `PrepareDenseScene_1`) работают. **Но:** `MeshFiltering` без сглаживания и `Texturing` сломаны на стыке `export`/`report`/`inspect` (`F3`); `ImageMasking` описан только через GUI; `masks.features=true` + Legacy + CCTag3, `ObjectTurntable`/`TwoSides` (`mrSegmentation`, `PrepareDenseScene_3`) — рецепты без запуска. |
| **5. Мишени, масштаб и контроль** | Печатные `CCTag3`, масштабная база, независимые `check`-пары, неопределённость, ориентация `SfMTransform`, оси OBJ/PLY | `docs/capture.md`, `scripts/make_capture_kit.py`, `scripts/check_capture_kit.py`, `scripts/check_marker_scale.py`, `reconstruction.py:scale/export`; в PR #30 — `scripts/capture_measurements.py` | `check_capture_kit.py` (Linux CPU), `scale-evidence.json` (SHA к `scene.json`), `reconstruction_report.py` (в PR #30 — `pair_report`), `diag(1,-1,-1)` | **Сильная часть на стороне PR #30, но есть P0 (`F2`):** цифровой PDF A4/100 мм проверен (#15), численный scalar-перенос проверен на синтетике (#6), PR #30 ввёл честное разделение `scale`/`check` и допусков. **Пробелы:** `configure_standard_transform` молча сохраняет `applyScale=True` при ориентации (`F2`); в Legacy ориентация+масштаб через `settings.json` недоступны; физическая печать и реальная точность на фото ещё не квалифицированы; `make_capture_kit.py` ограничивает диаметр ≥ 20 мм и 1 метка/лист. |
| **6. Запуск, продолжение и смена параметров** | Повторное использование native `cache`, `remote_job.sh` / `owned_process.py`, фактические лимиты CPU/RAM/GPU, защита от подмены входов | `docs/runbook.md:568–658`, `scripts/remote_job.sh`, `scripts/owned_process.py`, `reconstruction.py:prepare --cache / verify` | `verify_run_inputs` (SHA фото/manifest/settings/масок), `owned-process` receipt (`cleanup=confirmed`), `cgroup` проверка вручную | **Частично (`F3`, `F4`):** защита от подмены входов и убийства дерева процессов сильные. **Разрывы:** противоречие инструкций по продолжению графа (`F3`); `prepare --cache` в Legacy+CCTag не восстанавливает `SfMTransform` до `scale`; `prepare_dense_images.py` не пишет native `status` (при повторном `meshroom_compute` риск пересчёта `PrepareDenseScene_1`); в `prepare()` нет проверки, что заданные в `settings` параметры не стёрлись и не перезаписались (`F1`, `F4`); в pinned Meshroom `cgroup.py` читает только cgroup v1 (задокументировано честно в `meshroom-modes.md:381`). |
| **7. Просмотр, диагностика и вход в CAD** | Визуальная связь фото ↔ облако ↔ mesh, сравнение итераций до/после, передача масштаба/осей в Open3D/CloudCompare/`extract_plane.py`/`build_cad.py` | `docs/geometry-review.md`, `scripts/inspect_geometry.py`, `scripts/extract_plane.py`, `scripts/build_cad.py` | `geometry-evidence.json`, `reconstruction-report.json`, `thickness=unresolved` gate в `build_cad.py` | **Частично (`F3`, `F5`):** визуальный осмотр cloud + raw OBJ работает, `thickness=unresolved` защищает от выдуманных толщин. **Разрывы:** `inspect_geometry.py` требует `--mesh`, не умеет `--compare-mesh` и захардкодил Windows-шрифт (`arial.ttf`); `extract_plane.py` принимает `--meters-per-unit` и `--scale-status` вручную без SHA-привязки к отчёту и строит только выпуклую оболочку `ConvexHull`, перекрывая проёмы (`F5`). |
| **8. Знания и навигация агента** | Короткий `SKILL.md`, непротиворечивые `docs/`, приоритет актуального над архивом, отсутствие зависимости от переписки | `AGENTS.md`, `README.md`, `docs/project-context.md`, `.agents/skills/photogrammetry-workflow/SKILL.md`, `docs/meshroom-modes.md`, `docs/runbook.md` | Независимый слепой тест (раздел 5 ниже) | **Частично (`F7`):** `SKILL.md` (64 строки) и дисциплина статусов работают отлично. **Но:** `docs/runbook.md` на 55.9% состоит из облачной/SSH/rclone-обвязки (501 из 897 строк на `main`), в `README.md`/`AGENTS.md`/`project-context.md` дублируется хроника Goals #2–#21 (в `AGENTS.md:14` устаревшая заметка «PR #20 ещё не влит»), есть прямое противоречие по продолжению графа (`meshroom-modes.md:267` vs `runbook.md:590`). |

---

## 3. Приоритетные находки с доказательствами

Ниже приведены только подтверждённые по исходникам и локальным воспроизведениям разрывы. Для каждой находки указан тип: **ограничение обвязки**, **пробел знаний**, **дефект интерпретации** или **отсутствие данных/зависимостей**.

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

### F2 (P0 · ограничение обвязки + дефект интерпретации): `configure_standard_transform()` молча включает `applyScale=True` при ориентации сцены; в Legacy ориентация заблокирована

- **Сценарий:** пользователь просит выровнять модель по вертикали/полу (`method: "align_ground"` или `"auto_from_cameras"`, `applyRotation: true`), сохранив исходный масштаб (или контролируя его отдельно).
- **Конкретный разрыв:**
  1. [`docs/meshroom-modes.md:205–207`](../docs/meshroom-modes.md#L205-L207) прямо инструктирует: *«для ориентации явно выбрать method и applyRotation=true, а остальные флаги — по задаче»*.
  2. В [`scripts/reconstruction.py:122–128`](../scripts/reconstruction.py#L122-L128) `configure_standard_transform()` стартует с `{'method': 'transformation', 'transformation': '', 'scale': 1., 'applyScale': True, 'applyRotation': False, 'applyTranslation': False}` и накладывает `overrides`. Если пользователь/агент передаёт `{'SfMTransform_1': {'method': 'align_ground', 'applyRotation': True}}` (точно так же, как в тесте [`tests/test_reconstruction_preflight.py:142–146`](../tests/test_reconstruction_preflight.py#L142-L146)!), **`applyScale` молча остаётся `True`**.
  3. При методах `auto`, `auto_from_cameras`, `align_ground` флаг `applyScale=True` позволяет `SfMTransform` **перемасштабировать сцену**, тогда как `scale-plan.json` (`scripts/reconstruction.py:389`) и `reconstruction_report.py` (`L75–77`) запишут `scale=1.0, rotation=IDENTITY`.
  4. В `Legacy` (`photogrammetryLegacy.mgt`) узла `SfMTransform_1` на этапе `prepare()` вообще нет (`scale()` добавляет его через `addNewNode` только при `scale.mode != 'unknown'` и жёстко задаёт `applyRotation=False, applyTranslation=False`, `L406–407`). Следование совету из `meshroom-modes.md:205` на Legacy роняет `prepare()`, а совместить `CCTag3`-масштаб и поворот сцены через `settings.json` невозможно.
- **Источник / воспроизведение:**
  - Локально воспроизведено на `scripts/reconstruction.py` (`REPRO_1_SFMTRANSFORM`): вызов `configure_standard_transform(graph, {'SfMTransform_1': {'method': 'align_ground', 'applyRotation': True}})` даёт `{'method': 'align_ground', 'transformation': '', 'scale': 1.0, 'applyScale': True, 'applyRotation': True, 'applyTranslation': False}` без предупреждения.
  - Факт топологии `photogrammetry.mgt`: `SfMExpanding_1 → SfMTransform_1 → SfMColorizing_2 → IntrinsicsTransforming_1 → ExportImages_1` (`SfMTransform_1` стоит *до* `SfMColorizing_2`).
- **Последствие для пользователя:** скрытое изменение масштаба сцены и ложная запись `transform: {scale: 1.0, rotation: IDENTITY}` в `scale-plan.json` / `reconstruction-report.json`; падение `prepare()` при попытке ориентировать Legacy-сцену.
- **Минимальное исправление:**
  1. В `configure_standard_transform()` при `method != 'transformation'` ставить безопасный дефолт `applyScale=False` (если пользователь не указал `applyScale` явно) — либо требовать явного указания `applyScale` при смене `method`.
  2. В `scale-plan.json` / `reconstruction_report.py` явно отражать, если `SfMTransform_1` отличается от identity (`orientation_override` / фактические параметры `SfMTransform_1`), а не записывать фиктивный `IDENTITY`.
  3. В `docs/meshroom-modes.md:205` явно указать ограничение Legacy (ориентация через отдельный шаг графа, не через `nodes.SfMTransform_1` в `prepare()`).
- **Достаточная проверка исправления:** unit-тест на `configure_standard_transform` с `method='align_ground', applyRotation=True` (и `auto_from_cameras`) проверяет `applyScale is False`; тест на `method='transformation'` без overrides сохраняет прежний identity-контракт.

---

### F3 (P1 · ограничение обвязки + противоречие инструкций): Продолжение до `MeshFiltering` / `Texturing` ломается на экспорте, отчёте и визуальном сравнении

- **Сценарий:** реконструкция дошла до `Meshing_1`; на сырой сетке видны крупные треугольные перемычки через проём. Пользователь просит очистить их штатным `MeshFiltering` с `smoothingIterations=0` и получить обновлённый отчёт и сравнение до/после.
- **Конкретный разрыв:**
  1. **Прямое противоречие инструкций:** [`docs/meshroom-modes.md:267`](../docs/meshroom-modes.md#L267) говорит *«в том же проекте настроить MeshFiltering, сохранить граф и выполнить compute до его имени»*, тогда как [`docs/runbook.md:588–598`](../docs/runbook.md#L588-L598) запрещает менять завершённый RUN и требует `prepare "$NEW_SETTINGS" "$NEW_RUN" "$MESHROOM_ROOT" --cache "$CACHE"`.
  2. **Экспорт не поддерживает `MeshFiltering`/`Texturing`:** [`scripts/reconstruction.py:431–435`](../scripts/reconstruction.py#L431-L435) жёстко экспортирует `node(graph, 'Meshing').outputMesh.value`.
  3. **Отчёт отвергает отфильтрованную сетку и врёт о её происхождении:** [`scripts/reconstruction_report.py:222–224`](../scripts/reconstruction_report.py#L222-L224) (и `verified_export_bindings` в PR #30) падает с `ValueError('Mesh differs from saved native export SHA-256')`, если в `--mesh` передать файл `MeshFiltering.outputMesh`; а в `mesh_summary()` (`L182`) жёстко зашита строка `'processing': 'raw native Meshing output; no filtering/smoothing'`.
  4. **Визуальный просмотр не сравнивает две сетки:** [`scripts/inspect_geometry.py:87–90, 170`](../scripts/inspect_geometry.py#L87-L90) поддерживает `--compare-cloud`, но не `--compare-mesh`, и жёстко подписывает панель `"Original raw mesh"`.
  5. **Скрытый срыв кэша при `prepare --cache`:** (a) в `Legacy + CCTag3` новый `prepare --cache` не содержит пост-sparse `SfMTransform`, пока не повторить `scale` (а `prepare_dense_images.py` не пишет native `status`, поэтому `meshroom_compute` снова планирует `PrepareDenseScene_1` — подтверждено `dfsToProcess` в `docs/meshroom-modes.md:332`); (b) на кадрах без EXIF (`video_frames.py`) `CameraInit` UID зависит от `mtime` (`docs/auto-masks.md:140–145`), поэтому `prepare --cache` после переноса кэша может пересчитать весь граф с нуля.
- **Источник / воспроизведение:** подтверждено чтением `scripts/reconstruction.py`, `scripts/reconstruction_report.py`, `scripts/inspect_geometry.py`, `docs/meshroom-modes.md`, `docs/runbook.md`, и **полностью независимо воспроизведено слепым агентом в Задаче 2** (агент упёрся во все 4 пункта без подсказок).
- **Последствие для пользователя:** простейшая штатная операция очистки перемычек требует ручной выемки файлов из кэша, обхода `reconstruction_report.py` и написания одноразового скрипта сравнения; высок риск случайно пересчитать весь дорогой MVS из-за сброса UID.
- **Минимальное исправление:**
  1. Устранить противоречие в доках: один согласованный путь (новый RUN через `prepare --cache` + обязательная сверка совпадения upstream UID `Meshing_1` до запуска `meshroom_compute`).
  2. Добавить опциональный `--mesh-node` / экспорт `filtered_mesh` (сохраняя raw `mesh.obj` нетронутым) и честное поле `processing` / `mesh_source_node` в `reconstruction.py export` и `reconstruction_report.py` (либо не блокировать `--filtered-mesh` хэшем сырого `Meshing`).
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

### F5 (P1 · ограничение обвязки + дефект интерпретации): Незащищённый стык масштаба/единиц на входе в CAD (`extract_plane.py`) и выпуклый контур на проёмах

- **Сценарий:** после получения масштабированного `dense.ply` (в мм или м) агент извлекает плоскость и передаёт параметры в `build_cad.py` → STEP.
- **Конкретный разрыв:**
  1. [`scripts/extract_plane.py:145–148`](../scripts/extract_plane.py#L145-L148) принимает `--meters-per-unit` и `--scale-status` как свободные CLI-аргументы **без привязки к `reconstruction-report.json` или `scale-evidence.json`**. Агент может передать `--meters-per-unit 1.0` для облака в миллиметрах (ошибка в 1000×) или `--scale-status measured` для облака с `scale.mode="unknown"`, и ошибка беззвучно пройдёт в JSON параметров и в STEP.
  2. [`extract_plane.py:20, 73, 102–103`](../scripts/extract_plane.py#L14-L23) строит контур через `scipy.spatial.ConvexHull`, который **затягивает внутренние проёмы** (окна, дверные проёмы, вырезы в раме). Ограничение честно прописано в `limitations`, но для нашей целевой задачи (проёмы, откосы, диагонали) рабочего стыка «от облака/плоскостей откосов → к размерам проёма» пока нет.
  3. [`scripts/inspect_geometry.py:164`](../scripts/inspect_geometry.py#L164) требует обязательный `--mesh` (нельзя визуально проинспектировать одно облако/разреженный SfM) и хардкодит путь к шрифту `C:/Windows/Fonts/arial.ttf` (`L71`, с fallback на крошечный bitmap-шрифт на Linux).
- **Источник / воспроизведение:** чтение `scripts/extract_plane.py`, `scripts/build_cad.py`, `scripts/inspect_geometry.py`.
- **Последствие для пользователя:** риск получить STEP с неверным масштабом в 10×/1000× или ложным статусом `measured`, не имея автоматической сверки с `scale-evidence.json`, несмотря на всю строгость SHA-проверок на предыдущем этапе.
- **Минимальное исправление:**
  - В `extract_plane.py` добавить опциональный `--report` (`reconstruction-report.json`): если передан, автоматически сверять `source_sha256 == report.inputs.cloud.sha256`, выводить `meters_per_unit` из `report.scale.units` (`mm→0.001, cm→0.01, m→1.0`) и запрещать `--scale-status measured` при `report.scale.applied != True`.
  - В `inspect_geometry.py` сделать `--mesh` опциональным (для осмотра sparse/cloud-only).
  - *Вопрос проёмов (невыпуклый контур / пересечение 4 плоскостей откосов)* сознательно не решать костылём в `extract_plane.py` до первого реального масштабированного прогона на проёме, но явно зафиксировать границу текущего скрипта.
- **Достаточная проверка исправления:** unit-тест в `tests/test_geometry.py`: несовпадение SHA облака, попытка передать `measured` при `scale.applied=false` или неверные единицы (`mm` vs `1.0`) отклоняются с `ValueError`.

---

### F6 (P1 · пробел знаний + отсутствие диагностики): Каталог шаблонов без рабочей диагностики SfM / калибровки / сопоставления

- **Сценарий:** после отбора кадров видео или сложной съёмки в помещении в SfM регистрируется только 20 из 150 кадров (или стены выгибаются «бочкой» / двоятся).
- **Конкретный разрыв:**
  1. `docs/meshroom-modes.md` отлично описывает *выбор шаблона* (Standard/Legacy/Object/TwoSides и 22 остальных `.mgt`), но **не содержит рабочего руководства по настройке и диагностике узлов SfM**:
     - какие модели камеры/дисторсии есть в `CameraInit` (`radialk3`, `brown`, `fisheye4`, `equidistant_r3`), когда выбирать `brown` и как проверить, что `groupCameraFallback` не слил разные объективы/зумы в один `intrinsicId`;
     - как `ImageMatching` переключается между `Exhaustive` и `VocabularyTree`/`Sequential` при >100 кадрах и какие параметры (`method`, `nbMatches`, `minNbImages`) спасают длинную видеопоследовательность;
     - когда в `FeatureExtraction`/`FeatureMatching` имеет смысл `describerPreset=high`, `akaze`, `guidedMatching=true`, `geometricFilterType=fundamental_with_distortion`, `distanceRatio`, а в `SfMExpanding`/`StructureFromMotion` — `lockAllIntrinsics`, `minAngleForTriangulation`, `maxReprojectionError`;
     - чем отличаются ошибки калибровки (систематический изгиб/«бочка», дрейф фокусного), плохих соответствий (разрыв графа на компоненты), отсутствия параллакса (панорама с места) и проблем dense (`DepthMap`/маски).
  2. `scripts/reconstruction_report.py:233` требует `--cloud` (`required=True`) — его **нельзя запустить после провала SfM до MVS**, чтобы получить структурированный отчёт по `sparse-before.json` (зарегистрированные кадры, число групп intrinsics, модель/коэффициенты дисторсии, длины tracks, reprojection error). Хотя `docs/reports/2026-11-22/meshroom-neural-addons.md:176–179` прямо требует оценивать именно эти метрики!
  3. **Вторичные пробелы из слепого теста (Задача 3):**
     - `docs/meshroom-modes.md:128` предлагает добавлять `ImageMasking` (HSV) только через GUI (неприменимо на headless GPU-ноде).
     - `configs/mask-turntable-white.json` вырезает белый фон — при печати CCTag3 на белой бумаге это вырежет белые поля/кольца меток; требование контрастного небелого фона не проговорено.
     - `scripts/make_capture_kit.py:58` жёстко запрещает `diameter_mm < 20` и кладёт строго 1 метку на лист A4/A3 (неудобно для мелких деталей на поворотном столе).
- **Источник / воспроизведение:** подтверждено анализом всех файлов `docs/` и независимо подтверждено слепым агентом в Задачах 1, 3 и 4.
- **Последствие для пользователя:** при первом же неидеальном наборе фото агент либо гадает вслепую / переписывает одноразовые парсеры кэша, либо тратит GPU-время на слепое переключение Standard → Legacy, либо преждевременно просит переснять всё или поднять тяжёлый `mrRomatch` / MicMac.
- **Минимальное исправление:**
  1. Добавить в `docs/meshroom-modes.md` (или связанную короткую памятку, не раздувая `SKILL.md`) компактную **таблицу «симптом → проверка по `sparse-before.json` / логам → один штатный рычаг AliceVision → когда остановиться и доснять»** (~40–50 строк, без энциклопедии всех флагов).
  2. Сделать `--cloud` опциональным в `reconstruction_report.py` (режим `--sparse-only` по `sparse-before.json`) и вывести в `scene_summary` фактические `intrinsics` (`type`, `distortionType`, `locked`, `pxFocalLength`, `distortionParams`) + распределение длины tracks / число камер по группам intrinsics.
- **Достаточная проверка исправления:** повторная слепая проверка на задачах 1 и 4: новый агент по репозиторию без подсказок называет точный способ выбора/проверки дисторсии и конкретную последовательность диагностики 20/150 кадров; `reconstruction_report.py --scene sparse-before.json --settings ...` отрабатывает с `exit 0` без `dense.ply`.

---

### F7 (P2 · навигация и вес инструкций): `docs/runbook.md` перегружен облачной инфраструктурой (56%), а хроника Goals дублируется в 3 входных файлах

- **Сценарий:** новый агент заходит в репозиторий решать пользовательскую фотограмметрическую задачу.
- **Конкретный разрыв:**
  - По фактическому замеру `docs/runbook.md` на `main` (897 строк; в PR #30 ~980 строк): **501 строка (55.9%)** — облачная логистика (Vast.ai, SSH, rclone, aria2, split-parts, дедлайны, local Python env), **91 строка (10.1%)** — локальный отчёт/просмотр, и только **256 строк (28.5%)** — сама фотограмметрия (отбор кадров, `prepare`, `scale`, `dense`, `filtering`, маски, масштаб).
  - Хронологические отчёты по Goals #2–#21 дублируются в начале [`README.md:9–49`](../README.md#L9-L49), [`AGENTS.md:9–30` и `92–105`](../AGENTS.md#L9-L30) (где на `L14` висит устаревшее *«PR #20 ещё не влит»*, хотя в `README.md:14` он уже указан влитым) и [`docs/project-context.md:3–54`](../docs/project-context.md#L3-L54).
- **Последствие для пользователя:** агент сжигает заметную часть контекста на чтение облачного транспорта и истории прошлых Goal'ов, прежде чем добирается до выбора режимов и параметров реконструкции.
- **Минимальное исправление:** вынести/сослать облачный транспорт из `docs/runbook.md` в уже существующий `docs/infrastructure.md`, а в `AGENTS.md` и `README.md` оставить короткий блок «Текущий статус» на 5–7 строк со ссылкой на один источник (`docs/project-context.md`).
- **Достаточная проверка исправления:** размер `docs/runbook.md` сокращается примерно вдвое без потери команд; противоречивые упоминания статуса PR удалены.

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
   - **Не проверено в реальном прогоне:** совместный прогон `Legacy + masks.features=true + CCTag3 + measured_baseline` на поворотном столе, а также `KeyframeSelection` в режиме `Smart`.
2. **Локальные Python-пробы на Windows:**
   - Выполнены прямые воспроизведения контрактов `scripts/reconstruction.py` (`REPRO_1`–`REPRO_4`) на `origin/main` (`9d4ad784`) — все 4 воспроизведения сработали детерминированно (`exit 0`).
   - Прогон `python -m unittest discover -s tests` в системном Python 3.11 прошёл 68/74 тестов; 6 падений связаны исключительно с отсутствием `open3d` в глобальном Python (Open3D установлен в отдельном приватном окружении владельца, `docs/runbook.md:67`).
3. **Входные артефакты реальной съёмки комнаты (PR #28):** анализировались по отчёту и коду в PR #28/#30 без доступа к приватным фото/облакам вне Git.

---

## 5. Результаты независимой проверки другим агентом (слепой тест)

Запущен независимый агент (`research`, read-only, без истории переписки и без подсказок по конкретным багам) на чистой копии `origin/main` (`9d4ad784`). Ему даны 4 короткие пользовательские задачи.

| Задача | Что сработало отлично (агент справился по репо) | Где агент упёрся в реальный разрыв или ошибся из-за репо |
|---|---|---|
| **1. Камера 13 мм, `brown` или предкалиброванные заблокированные `intrinsics`** | Верно выбрал `Standard`, верно запросил оригиналы с EXIF, контрольные диагонали и формат калибровки; **сам заметил** по коду `reconstruction.py:319–328`, что `prepare()` не позволяет задать предкалиброванные `intrinsics`, и что `reconstruction_report.py` пишет только `intrinsic_count`. | **Попался в ловушку отсутствия знаний о `CameraInit.py`:** предположил, что модель `brown` можно передать «верхним атрибутом `nodes.CameraInit_1`» (которого не существует в pinned `CameraInit.py`), и вынужден был отложить выбор точных имён до чтения runtime. Не нашёл рецепта стыковки `distortionCalibration.mgt`. |
| **2. `MeshFiltering` без сглаживания + обновлённый отчёт** | Мгновенно и точно нашёл `smoothingIterations=0` и `filterLargeTrianglesFactor` в `meshroom-modes.md:253–260`, сохранил raw baseline, предложил количественную проверку отсутствия смещения вершин. | **Самостоятельно упёрся во все 4 разрыва `F3`:** (1) прямое противоречие `meshroom-modes.md:267` vs `runbook.md:590`; (2) `export` хардкодит `Meshing.outputMesh`; (3) `reconstruction_report.py` падает на `mesh_export.sha256` и хардкодит ложное `'raw native Meshing output'`; (4) `inspect_geometry.py` не имеет `--compare-mesh`. |
| **3. Поворотный стол с метками `CCTag3` в мм** | Безупречно выбрал `Legacy + masks.features=true + CCTag3 + measured_baseline`, жёстко отделил проверенные куски (#4/#6/#12/#15) от непроверенной целевой связки, верно потребовал ≥ 60 px и Linux CPU-пробу. | Выявил практические пробелы: (1) `make_capture_kit.py` запрещает диаметр < 20 мм и кладёт 1 метку/лист; (2) `mask-turntable-white.json` вырежет белые поля самих меток, `generate_masks.py single` отрежет метки от детали, а `ImageMasking` описан только через GUI; (3) расхождение доков и `configs/cctag.json` по `StructureFromMotion_1.describerTypes`. |
| **4. Видео помещения: в SfM сшились 20/150 кадров** | Строго соблюдал дисциплину: остановил цепочку до MVS, не прыгнул в `RoMa` и не стал вслепую крутить параметры, запросил оригинал видео и сравнение 20 vs 130 кадров, корректно разделил причины (параллакс/смаз vs сопоставление → Smart / Legacy / адресная досъёмка). | Упёрся в отсутствие диагностического инструментария: `reconstruction_report.py` требует `--cloud` (нельзя отчитаться по `sparse-before.json`), нет скрипта для извлечения inliers/tracks/residuals, не описано поведение `ImageMatching` (`Exhaustive` vs `VocabTree`/`Sequential`) на 150 кадрах видео и специфика интерьеров. |

**Главный вывод слепого теста:** дисциплина безопасности, честность статусов и базовый выбор режимов (`SKILL.md` + таблицы в `meshroom-modes.md`) **работают на отлично** — новый агент не выдумывает точность, не прыгает в лишние нейросети и не портит baseline. Реальные сбои происходят ровно там, где подтверждены `F1`, `F3` и `F6`.

---

## 6. Ответы на неудобные вопросы

1. **После #8/#15 появилось рабочее знание или преимущественно каталог возможностей? Почему случай с калибровкой прошёл мимо, и где ещё тот же слепой участок?**  
   Появилась отличная *инженерная дисциплина и каталог шаблонов*, но в части параметров самого движка AliceVision — преимущественно **каталог**. Случай с калибровкой прошёл мимо, потому что приёмка #8/#15 и `test_reconstruction_preflight.py` проверяли чтение готовых backup'ов, `dfsToProcess` с CompatibilityNodes, Open3D SOR и стабы `AttributeNode(isLink=False)` — ни одна проверка не запускала реальный `CameraInit.initialize()` после `config["nodes"]` и не проверяла, сохранились ли изменённые настройки узлов. Тот же слепой участок действует в `F2` (`SfMTransform.applyScale=True` в тесте `auto_from_cameras`), `F3` (`MeshFiltering` проверялся только планировщиком без `export`/`report`), и `F4` (связанные атрибуты `isLink=True` и пост-перезапись `maxThreads`/масок).

2. **Может ли новый агент выполнить другую съёмку только по репозиторию, без памяти автора и копирования параметров старого запуска?**  
   **Обычную неподвижную съёмку на стандартную камеру до `Meshing` — да.** Съёмку на сверхширик с ручной моделью дисторсии, очистку сетки `MeshFiltering` с обновлением отчёта, поворотный стол с метками + масками или диагностику провала SfM на длинном видео — **нет без импровизации и обхода собственных скриптов**.

3. **Может ли агент уверенно сообщить, что изменил настройку, хотя подготовка её стёрла, другой узел переопределил или downstream её не использует? Обнаружат ли это текущие проверки?**  
   **Да, может — и текущие проверки это НЕ обнаружат.** Подтверждены три механизма: (a) `CameraInit.initialize()` стирает `intrinsics` (`F1`), а `effective-settings.json` хранит исходный `settings` без сверки с итоговыми `nodes`; (b) `prepare()` молча перезаписывает `nodes.FeatureExtraction_1.maxThreads` и параметры масок после цикла `nodes` (`F4`); (c) `configure_standard_transform()` молча оставляет `applyScale=True` при ориентации (`F2`). На этапе отчёта `reconstruction_report.py` не проверяет ни модель дисторсии/lock, ни `SfMTransform` override, ни `MeshFiltering`.

4. **Не закрыли ли мы собственной обвязкой штатную возможность? Может ли агент воспользоваться нужным native-режимом без переписывания Python под очередной объект?**  
   **Да, в четырёх конкретных местах обвязка закрыла штатные возможности AliceVision:** (1) настройка `CameraInit.intrinsics` и подача предкалиброванного `.sfm` (`F1`); (2) совмещение ориентации и контроля масштаба в `SfMTransform` (`F2`); (3) экспорт, отчёт и сравнение `MeshFiltering.outputMesh` / `Texturing` (`F3`); (4) отчёт по `sparse-before.json` до MVS (`F6`) и headless `ImageMasking` (описан только через GUI). При этом саму идею тонкого адаптера менять не нужно — достаточно снять эти конкретные ограничения и оставить нестандартные графы штатному `meshroom_batch`/`meshroom_compute`.

5. **Умеет ли агент различить ошибку калибровки, плохие соответствия, недостаток ракурсов, проблему dense и дефект экспорта?**  
   Недостаток ракурсов / смаз и дефект экспорта (оси `diag(1,-1,-1)`, EXR QA) — **да**. Различить **ошибку калибровки/дисторсии**, **сбой `ImageMatching` (VocabTree vs Sequential)**, **нехватку признаков на слабой текстуре** и **дрейф self-calibration** по текущим инструкциям агент **не умеет**: в репозитории нет ни описания диагностических признаков по `sparse-before.json`/логам, ни скрипта для их быстрого чтения (`F6`). Риск преждевременного «переключить Standard → Legacy» или «переснять всё» реален, хотя на провале видео (Задача 4) слепой агент уже неплохо удерживается от слепого тюнинга и RoMa.

6. **Почему мы обсуждаем дополнительный инструмент (например MicMac/MMVII в #31 или RoMa): он закрывает подтверждённый недостаток или мы ещё не научили агента использовать основной стек?**  
   **Сейчас — в первую очередь второе.** Мы ещё ни разу не провели на живой сложной съёмке управляемый прогон основного стека с правильной моделью дисторсии (`brown`), заблокированными/проверенными `intrinsics`, диагностикой `ImageMatching`/`FeatureMatching` и контрольными `check`-парами из PR #30. MicMac/MMVII полезно держать в резерве (`research/`) именно для задач, где AliceVision *доказанно* упрётся (например, строгая фотограмметрическая метрология со свободной калибровкой камер на CPU без GPU), но не вместо исправления `F1`–`F6` в основном стеке.

7. **Может ли повторный расчёт выглядеть успешным, но использовать старые камеры, маски, масштаб или геометрию? Как связываются входы, параметры и выданный результат?**  
   - **На этапе `reconstruction.py` + `reconstruction_report.py` — защита сильная:** `verify_run_inputs()` проверяет SHA всех фото, `manifest.json`, `settings.json` и каждой маски; `scale-evidence.json` привязан к `scene.json` SHA; в PR #30 `verified_export_bindings` дополнительно проверяет SHA `scene`/`cloud`/`mesh`.
   - **Но остались три дыры:** (1) при `prepare --cache` на `Legacy`, где `prepare_dense_images.py` не пишет native `status`, или при ручном копировании `MeshFiltering.outputMesh` в обход `export` связка нарушается (`F3`); (2) при `SfMTransform` override в `Standard` отчёт всё равно пишет `scale=1.0, IDENTITY` (`F2`); (3) **на входе в `extract_plane.py` связка обрывается полностью** — `--meters-per-unit` и `--scale-status` не сверяются с `reconstruction-report.json` (`F5`).

8. **Не используем ли контрольные данные для подгонки? Что на самом деле подтверждают малая репроекция, все зарегистрированные камеры, густое облако, гладкая стена и одна совпавшая контрольная длина?**  
   - В PR #30 (`capture_measurements.py`) дисциплина разделения `scale` и `check` выстроена образцово — контрольные пары физически не подаются в `SfMTransform`.
   - **Что НЕ доказывают отдельные зелёные метрики:**
     - *Малая репроекция* подтверждает лишь внутреннюю согласованность 2D-наблюдений и может скрывать глобальный перекос/«чашу» (bowl effect) от неверной дисторсии.
     - *100% зарегистрированных камер* подтверждает связность траектории, но не точность глубины или отсутствие дрейфа масштаба.
     - *Густое облако / гладкая стена* могут быть результатом интерполяции/сглаживания (`smoothingIterations=5`) поверх смещённой поверхности.
     - *Одна совпавшая контрольная длина* (особенно параллельная масштабной базе) проверяет только один масштабный фактор в одном направлении, но **не ловит перекос осей, неортогональность и радиальный изгиб** — для этого нужны минимум обе диагонали проёма и размер поперёк базы.

9. **Не просим ли человека сделать то, что агент может выяснить из файлов или выполнить штатной командой? И наоборот: не обещаем ли восстановить скрытую поверхность или неизвестный размер без новых наблюдений?**  
   - *Скрытые поверхности и неизвестные размеры* проект честно не обещает (`thickness=unresolved`, `scale.mode=unknown`, запрет выдавать `MeshFiltering` за новые наблюдения).
   - *Лишние просьбы к человеку* пока возможны в двух местах: (а) модель камеры, фокусное расстояние, ориентацию, разрешение и наличие зума агент должен сам вычитать из EXIF/`ffprobe`/`CameraInit` *до* вопросов человеку (в PR #28 это уже начали исправлять); (б) при провале SfM из-за отсутствия локальной sparse-диагностики агент рискует попросить человека «переснять», прежде чем сам проверил, не сломал ли сшивку `ImageMatching` или неверная модель камеры.

10. **Если все текущие проверки зелёные, может ли пользователь всё ещё не получить нужный проём, кромку или достоверный размер? Какая короткая проверка обнаружит именно этот разрыв?**  
    **Да, легко.** Зелёные `dense-images-check.json`, `scale-evidence.json`, `reconstruction-report.json` и даже `geometry-review` проверяют техническую целостность файлов и числовой перенос базы, но **не проверяют** ни попадание нужных откосов проёма в качественную плотную геометрию без перемычек, ни истинный размер самого проёма (и на входе в CAD `ConvexHull` закроет проём, а `--meters-per-unit` можно перепутать руками).  
    **Короткая проверка, ловящая этот разрыв:** после `reconstruction_report.py` измерить на реальном `dense.ply` (не на сглаженном mesh) **4 независимых отрезка целевого проёма — ширину, высоту и обе диагонали** — и сопоставить их с `purpose=check` из `measurements.csv` с учётом `uncertainty_mm` и допуска + визуально открыть 2 ортогональных разреза откосов без сглаживания (проверить толщину шума кромки и отсутствие двойной стенки).

11. **Какие правила можно удалить или упростить без потери результата? Не занимают ли инфраструктура, доказательства и общие запреты больше внимания, чем выбор и оценка самой фотограмметрической обработки?**  
    **Да, занимают — и существенно.** В `docs/runbook.md` 55.9% объёма (501/897 строк) — это облачная инфраструктура и передача архивов, тогда как фотограмметрия занимает 28.5%. Без потери безопасности можно:
    - убрать дублирующуюся хронику Goals #2–#21 из `README.md` и `AGENTS.md` (оставив один короткий статус со ссылкой на `docs/project-context.md`);
    - вынести блоки аренды/SSH/rclone/split-parts из `docs/runbook.md` в `docs/infrastructure.md`, чтобы `runbook.md` стал коротким рабочим руководством по запуску пайплайна;
    - не ослаблять правила SHA-проверок, `cleanup=confirmed` и запрета выдуманного масштаба — они компактны в коде и реально защищают от дорогих ошибок.

---

## 7. Минимальный план исправления и ОДИН наиболее полезный следующий шаг

Распределение минимальных действий по слоям (без нового оркестратора, без раздувания `SKILL.md` и без россыпи issue):

| Слой | Что сделать | Что сознательно отложить |
|---|---|---|
| **Минимальная правка адаптера (`scripts/reconstruction.py` + тесты)** | **Шаг 1 (главный):** починить порядок `CameraInit.initialize()` + пост-инициализационное применение `intrinsics` с обязательной read-back сверкой применённых настроек (`F1`); выставить безопасный `applyScale=False` при нестандартном `SfMTransform.method` (`F2`); сделать `settings()` независимым от порядка ключей JSON и ловить конфликты `nodes.*` с `resources`/`masks` (`F4`); добавить честные unit-тесты с `initialize()`-сбросом и `isLink=True`. | Не добавлять новый универсальный конфиг-слой, не переписывать `manifest()` под `.sfm`, не встраивать `ImageMasking` в адаптер до реальной задачи на столе. |
| **Небольшое усиление отчёта и стыка с CAD (`reconstruction_report.py`, `inspect_geometry.py`, `extract_plane.py`)** | Сделать `--cloud` опциональным (sparse-only отчёт с выводом фактических `intrinsics`: `type`, `distortionType`, `locked`, `distortionParams`); поддержать экспорт/отчёт/сравнение `MeshFiltering` без порчи raw baseline (`F3`); добавить `--report` в `extract_plane.py` для автопроверки SHA/единиц/статуса масштаба (`F5`). | Не строить автоматическое распознавание проёмов/деталей в `extract_plane.py` до первого масштабированного облака с реальным проёмом. |
| **Штатный вызов (без кода)** | Предкалибровка (`distortionCalibration.mgt` + `ApplyCalibration`), нестандартные графы (`ObjectTurntable`/`TwoSides`, `ImageMasking` при надобности) и `Texturing` — через штатные `meshroom_batch`/`meshroom_compute`. | Не устанавливать `mrSegmentation` / `mrRomatch` / MicMac в базовый стек без подтверждённого провала настроенного AliceVision. |
| **Обновление `docs/` (без раздувания `SKILL.md`)** | Устранить противоречие `meshroom-modes.md:267` vs `runbook.md:590` (`F3`); добавить короткую диагностическую таблицу SfM/камеры в `docs/meshroom-modes.md` (`F6`); разгрузить `docs/runbook.md` от облачной рутины в `docs/infrastructure.md` и убрать дубли хроники Goals (`F7`). | Не писать энциклопедию всех флагов 112 узлов AliceVision. |

### Один наиболее полезный следующий шаг

> **Одной небольшой правкой закрыть тихую потерю и искажение настроек в `scripts/reconstruction.py` (`F1` + `F2` + `F4`) + добавить вывод фактических `intrinsics` и режим `--sparse-only` в `scripts/reconstruction_report.py` (`F6`), закрепив всё честными unit-тестами (с реальным сбросом `CameraInit.initialize()` и `isLink=True`).**

**Почему именно это первым:** этот шаг не требует платной GPU-аренды, не ломает базовый маршрут, не конфликтует с открытыми PR #28/#30 (легко ложится поверх #30 после его merge) и **мгновенно убирает самый опасный класс ошибок — ситуацию, когда агент уверенно отчитывается о применённой калибровке/ориентации, которой на деле не было.** После него первая же реальная съёмка (например, комната с `CCTag3` из #28/#30) сможет честно проверить `brown`/калибровку и независимые контрольные диагонали.

---

## 8. Проект минимальных правок рабочих инструкций (черновик, не применён)

*Ниже — компактный проект изменений; живые файлы `SKILL.md`, `docs/meshroom-modes.md` и `docs/runbook.md` в этом PR не изменялись.*

1. **`.agents/skills/photogrammetry-workflow/SKILL.md` (не раздувать — +2 строки):**
   - В п. 3 уточнить: *«После `prepare` сверь фактические `nodes` в `effective-settings.json` (особенно `CameraInit.intrinsics`, `SfMTransform`, `MeshFiltering`), а не исходный JSON запроса.»*
   - В п. 5 уточнить: *«При провале SfM остановись до MVS и сначала проверь диагностику `sparse-before.json` и кадры по таблице в `docs/meshroom-modes.md`.»*
2. **`docs/meshroom-modes.md`:**
   - На стр. 267 заменить *«в том же проекте настроить MeshFiltering»* на единое правило из `runbook.md`: *«создать новый RUN через `prepare --cache` и сверить совпадение upstream UID до `Meshing_1` перед `meshroom_compute`»*.
   - На стр. 205–207 добавить оговорку: при ориентации в `Standard` явно задавать `applyScale=false`, если масштаб не должен меняться; в `Legacy` `SfMTransform_1` создаётся только после sparse.
   - Добавить компактную таблицу «Диагностика SfM и калибровки до MVS» (5–6 строк: *симптом → что проверить в `sparse-before.json` / логах → один штатный рычаг `CameraInit` / `ImageMatching` / `FeatureExtraction` / `FeatureMatching` / `SfM` → критерий остановки и досъёмки*).
3. **`docs/runbook.md` / `AGENTS.md` / `README.md`:**
   - Перенести детали выбора ноды / rclone / split-parts из `docs/runbook.md` в `docs/infrastructure.md` со ссылкой в одну строку.
   - Убрать дублирование хроники Goals #2–#21 из `AGENTS.md` и `README.md`, оставив актуальную ссылку на `docs/project-context.md`.
