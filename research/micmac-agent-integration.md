# Исследование #31: MicMac / MMVII — выбор, запуск и оценка результата агентом

> **Статус:** исследовательский отчёт по [Issue #31](https://github.com/Kwentin3/photogrammetry-to-cad/issues/31) на базе `main` (`9d4ad78483187d924bc50d39ca195fecfd28b7e8`, с учётом открытых PR #28 и PR #30 как невмерженных ориентиров). **MicMac/MMVII не установлены как штатный режим проекта**; проект дополнений к рабочим инструкциям вынесен отдельно в [проект знаний для агента](micmac-agent-knowledge-draft.md).

## 1. Короткое решение

**Основной маршрут (`Meshroom/AliceVision 2026 + CCTag3` из #29/#30) остаётся главным.** Менять базовый движок, устанавливать плагин `mrMicMac` или переходить на `MMVII` сейчас **не обосновано**.

**Единственный полезный первый сценарий для опционального подключения:** **прямой headless-вызов классического MicMac V1 (`v1.2.0`, `mm3d`) на CPU в изолированном каталоге запуска** (`Tapioca → Tapas → AperiCloud → опционально C3DC QuickMac/MicMac → .ply`).

Когда этот узкий сценарий реально оправдан сверх AliceVision:
1. **CPU-диагностика калибровки и кросс-проверка SfM за `$0` GPU** на небольшом наборе (`10–45` резких фото), когда на реальных данных подозревается систематический изгиб/недокомпенсация оптики и хочется сравнить физическую модель (`FraserBasic` / `RadialStd` / `FishEyeEqui`) с AliceVision до платного GPU-прогона.
2. **Резервное CPU-облако (`C3DC QuickMac`/`MicMac`)** на локальном участке (`10–40` фото, например один проём или секция конструкции), когда CUDA-нода недоступна или не разрешена, с выходом в стандартный `.ply` (XYZ + нормали + RGB) для `Open3D` / `CloudCompare`.

Что **осознанно не подключаем** на этом этапе:
- **`mrMicMac`** (`meshroomHub/mrMicMac`): не даёт моста «калибровка/позы MicMac → MVS AliceVision», имеет незавершённую инвалидацию кэша Meshroom при общем мутабельном каталоге `project/`, содержит GUI-узлы `Saisie*QT`.
- **`MMVII`** (`micmac-V2/MMVII`): несовместим с `CCTag3` (поддерживает только `IGN*` и `CERN`), не содержит самостоятельного многовидового MVS уровня `C3DC`, требует отдельной обвязки `SysCo`/`RTL`/начальных 3D-координат.
- **Смешанный конвейер `MicMac Ori-* → AliceVision MVS`**: штатного конвертера в `mrMicMac` и AliceVision нет, а модели дисторсии математически не идентичны (`ModPhgrStd` / `FishEyeEqui` ≠ `radialk3` / `brown` / `fisheye4`). Самописный конвертер до доказанной потребности не нужен.

---

## 2. Разделение компонентов: AliceVision vs MicMac V1 vs MMVII vs `mrMicMac`

Все факты ниже сверены по первичным исходникам и релизам на **26 ноября 2026 года**:

| Компонент и проверенная ревизия | Готовность и бинарники | Калибровка и SfM | Плотная геометрия (MVS) | Мишени и масштаб | Совместимость с нашим workflow |
|---|---|---|---|---|---|
| **Закреплённый AliceVision** `d012d055` / Meshroom `b12ea889` (`2026-11-21`) | Готовый Linux CUDA 12.8 bundle (`600 МБ`), уже встроен и проверен | `CameraInit` (`pinhole`: `radialk1`, `radialk3`, `brown`; `equidistant`: `radialk3pt`, `fisheye1`, `fisheye4`); внешняя калибровка `CheckerboardDetection` → `CheckerboardCalibration` / `DistortionCalibration` → `ApplyCalibration` | CUDA GPU (`DepthMap` → `Meshing` → `dense.ply` + `mesh.obj`). Нет CPU MVS | **Нативный `CCTag3`** (`Legacy` квалифицирован), скалярный `SfMTransform` по базе; `SfMDistances` для диагностики; `SfMSurveyInjecting` требует полные `survey_3d` XYZ | **Основной конвейер.** Полная связка с #29/#30 (`capture/measurements.csv`, `reconstruction_report.py`) |
| **MicMac V1** `micmacIGN/micmac` `v1.2.0` (`2026-06-10`, HEAD `f8fe4321`, бинарник `f357685`) | Официальные архивы: `micmac_linux.tgz` (`52.2 МБ`), `micmac_windows.zip` (`42.5 МБ`, включает `make/exiftool/exiv2/convert/proj/cs2cs`) | `Tapioca` + `Tapas` (`RadialBasic`, `RadialStd`, `RadialExtended`, `FraserBasic`, `Fraser`, `FishEyeBasic`, `FishEyeEqui`, `HemiEqui`, `Figee`, `AutoCal`); прозрачные XML `AutoCal_*.xml` и `Residus.xml` | **CPU-only `C3DC`** (`QuickMac`, `MicMac`, `BigMac`, `Statue`) → бинарный `.ply` с нормалями | **Нет детектора мишеней** (ни CCTag3, ни CERN). Масштаб через `SBGlobBascule DistFS=...` по 2 вручную отмеченным 2D-точкам (`Mesure-S2D.xml`) или `Campari` с GCP XYZ | **Рекомендуемый опциональный CPU-резерв** через прямой вызов `mm3d` в отдельном каталоге; в `Open3D`/`CloudCompare` отдаёт `.ply` |
| **MMVII (MicMac V2)** `micmac-V2/MMVII` HEAD `a311b8e2` (`2026-11-26`) | `mmvii_windows.zip` (`72.5 МБ`), Docker `ghcr.io/micmac-v2/mmvii:latest`, активная разработка | `OriCreateCalib`, `OriPoseEstimSpaceResection`, `OriBundleAdj` (BA + `Topo` + жёсткие блоки + клинометры) | **Нет самостоятельного multi-view MVS**: `DenseMatchEpipGen` делает парный эпиполярный матчинг через `MMV1` SGM или `PSMNet` и требует пофайловые маски | `CodedTargetCircExtract` / `CodedTargetExtract` — **только `eIGNIndoor`, `eIGNDroneSym`, `eIGNDroneTop`, `eCERN`** (`MMVII_enums.h`). `Topo` OBS code `3` поддерживает 3D-расстояния в BA, но требует `RTL` SysCo и начальные 3D-координаты | **Отложить.** Несовместим с `CCTag3`, не заменяет плотный MVS, заметно сложнее в эксплуатации для агента |
| **`mrMicMac`** `meshroomHub/mrMicMac` HEAD `9e8f7483` (`2026-10-27`) | Плагин Meshroom 2026+ (`MESHROOM_PLUGINS_PATH`), 33 узла `mm3d` + 3 утилиты MMVII (`OriConvV1V2`, `MeshCheck`, `MeshCloudClip`) | Обёртка над `mm3d` (`Tapioca*`, `Tapas`, `Campari`, `SBGlobBascule`) | Обёртка над `mm3d C3DC`, `TiPunch`, `Tequila` | Через GUI-узлы `SaisieBascQT` / `SaisieAppuis*QT` (непригодны headless) | **Отклонить.** Не связывает MicMac с MVS AliceVision, ломает инвалидацию кэша Meshroom (`Meshroom README.md:L106`) |

### Проверка `CameraCalibration` в закреплённом AliceVision (`d012d055`)

В старой документации `meshroom-manual` описан монолитный узел `CameraCalibration`. Проверка дерева [meshroom/aliceVision на коммите d012d055](https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision) показала, что **узла `CameraCalibration.py` в нашей версии нет**. Вместо него в комплекте уже присутствуют модульные штатные узлы:
- `CheckerboardDetection.py` и `CheckerboardCalibration.py` (калибровка по шахматной доске);
- `DistortionCalibration.py` (калибровка дисторсии по полноэкранной сетке, модели `3deanamorphic4`, `3declassicld`, `3deradial4`);
- `ApplyCalibration.py` (принудительная подстановка заранее откалиброванного `sfmData` в новую сцену);
- в `CameraInit.py` уже доступны `pinhole` + `brown` (3 радиальных + 2 тангенциальных коэффициента) и `equidistant` + `fisheye4` / `radialk3pt`.

**Практический вывод:** прежде чем тащить MicMac ради «более сложной калибровки», нужно проверить, использованы ли штатные настройки самого AliceVision (`brown` вместо `radialk3` при признаках децентрирования, либо предварительная `CheckerboardCalibration` + `ApplyCalibration` для конкретного фиксированного режима телефона).

---

## 3. Калибровка широкоугольного телефона (Huawei Mate 50): модели, перенос и диагностика

### Выбор модели без ложного предположения «широкий угол = fisheye»

- **Широкий угол на смартфоне не равен fisheye.** Смартфоны (включая Huawei Mate 50 на `0.5x` / `13 мм` экв.) обычно применяют встроенную ректилинейную (центрально-проективную) коррекцию в ISP до сохранения JPEG. Факт из [PR #28](https://github.com/Kwentin3/photogrammetry-to-cad/pull/28): на 77 оригинальных JPEG `4160×3120` сверхширика `1.95 мм` модель `pinhole/radialk3` сошлась на 77/77 камер с медианой репроекции `0.910 px` и умеренными коэффициентами дисторсии `(-0.021, 0.009, -0.003)` — это ректилинейная проекция, а не fisheye.
- **Как выбирать модель в MicMac `Tapas`:**
  1. Основная камера `1x` (~24–26 мм экв.) и ректилинейный сверхширик `0.5x` (прямые дверные косяки на фото остаются почти прямыми): начинать с **`FraserBasic`** (10 параметров: `F`, `PP`, `k1..k3`, `P1/P2`, `b1/b2`, с `PPa == PPs`). При малом числе фото (< 15) или плоской сцене сначала стабилизировать более простой **`RadialStd`** / **`RadialBasic`**, чтобы не переобучить параметры.
  2. Настоящий fisheye (сильно изогнутые прямые у краёв, FOV > 120–140° без ректификации в ISP, либо `RAW`/`DNG` без автокоррекции): **`FishEyeBasic`** / **`FishEyeEqui`**. Если `FraserBasic` даёт систематический рост ошибки на краях кадра (`> 1.5–2 px` при резких кадрах и хорошем параллаксе), только тогда проверять `FishEyeBasic`.

### Когда калибровку нельзя переносить между съёмками

Внутреннюю калибровку (`AutoCal_*.xml` в MicMac или откалиброванный `sfmData` в AliceVision) **запрещено переносить** при любом из следующих изменений:
- **Смена физического модуля** (`0.5x` ↔ `1x` ↔ `3.5x`) или любой цифровой/гибридный зум.
- **Смена разрешения или соотношения сторон** (`4:3` `4160×3120` ↔ `16:9` ↔ видео `1920×1080` / `3840×2160`): кроп меняет эффективную ширину матрицы и главную точку.
- **Фото ↔ видео:** видеорежим смартфона включает электронную стабилизацию (EIS), динамический кроп и rolling shutter — параметры внутренней калибровки меняются даже между соседними кадрами видео.
- **Автофокус на ближней дистанции (макро / < 0.8 м):** изменение дистанции фокусировки сдвигает фокусное расстояние `F` (focus breathing). Для обмеров проёмов (1.5–3 м) фокус практически на гиперфокале, но при съёмке мелких деталей вплотную `F` фиксировать нельзя.
- **Переключение ISP-коррекции / стороннего приложения камеры / RAW ↔ JPEG.**

### Самокалибровка по рабочим фото vs отдельная калибровочная съёмка

- **По текущим рабочим фото** (`Tapas FraserBasic` / BA AliceVision) самокалибровка хорошо работает, когда в сцене есть глубина (не одна плоская стена), перекрывающиеся ракурсы с параллаксом и **разнообразие углов наклона/крена** (в идеале — кадры с поворотом камеры вокруг оптической оси).
- **Отдельная калибровочная съёмка** оправдана только если рабочая сцена почти плоская (например, одна ровная стена/фасад, где `F` и глубина вырождены) или при длинной вытянутой траектории без перекрёстных взглядов («эффект банана»).
- **Минимальная инструкция человеку для калибровки режима (если реально понадобится):**
  1. Зафиксировать **ровно один** фото-режим (например, основная камера `1x`, 4:3, без зума, без HDR-склейки со смещением).
  2. Сделать `15–25` резких фото объёмной контрастной сцены (угол комнаты с полками/рельефом либо плоская печатная шахматная доска на жёсткой подложке) с дистанции, близкой к рабочей (`1.5–2.5 м`).
  3. Заполнять деталями не только центр, но и **углы кадра** (иначе дисторсия по краям не определена).
  4. Сделать часть кадров в обычной горизонтальной ориентации и **4–6 кадров с поворотом телефона на ±90° вокруг оптической оси** (roll diversity развязывает главную точку и дисторсию от положения камеры).
  5. Передать оригиналы без пересжатия; в MicMac калибровку сохраняют в `Ori-Calib/` и затем подают в рабочую съёмку через `Tapas Figee ... InCal=Calib` (замороженная) или `Tapas AutoCal ... InCal=Calib` (слабое уточнение).

### Диагностика: калибровка vs параллакс / смаз / текстура / ракурсы

| Наблюдаемый симптом | Что проверить в первую очередь | Вероятнее ошибка калибровки | Вероятнее дефект съёмки / данных | Что остаётся гипотезой |
|---|---|---|---|---|
| Камеры не связываются (как 17/160 на видео #25) | Оригиналы 1:1 (смаз, rolling shutter), число пар и общих деталей, шаг между кадрами | Только если кадры резкие, перекрытие высокое, а линии у краёв сильно выгнуты (fisheye) | Смаз, поворот на месте без смещения (нулевой параллакс), однотонные стены, пересветы | Доля вклада каждого фактора без контрольного теста на тех же кадрах |
| Все камеры сошлись, репроекция `< 1 px`, но на контрольной паре в другом конце комнаты ошибка `> 0.5–1%` или ровная стена «выгнута дугой» | Ошибка на независимых `check`-отрезках в разных зонах, плоский срез стены в `CloudCompare`/`Open3D` | **Да — главный признак недокомпенсированной радиальной дисторсии / дрейфа `F`** | Также может быть слабая связка между зонами (узкий дверной проём, проход без перекрёстных кадров) | Исправит ли это `FraserBasic` vs `1x` оптика — покажет только сравнительный прогон |
| Края одного проёма рваные/бугристые при нормальных контрольных парах | Исходники проёма в 100% масштабе, экспозиция окна, число ракурсов с параллаксом | Маловероятно | Однотонная белая поверхность, контровой пересвет, мало ракурсов по высоте | Поможет ли `downscale=1` / `C3DC MicMac` — проверять на том же участке |

### Границы практичности CPU-маршрута MicMac

- **Практично на CPU:** `8–40` фото (или локальный участок на `1000–2500 px` в `Tapioca` и `ZoomF=4` / `QuickMac` в `C3DC`). В нашей реальной пробе (см. раздел 6) 8 фото `1296×972` прошли полный цикл `Tapioca → Tapas → AperiCloud → C3DC QuickMac` за **2 мин 36 с** на 2 процессах в пределах `2 GiB` RAM.
- **Непрактично на CPU:** `70–150+` полноразмерных фото `4160×3120` в `C3DC BigMac` (`ZoomF=1`) или `Tapioca All -1` (полное разрешение): время уходит в часы, а память — в десятки ГБ, где наш уже работающий Vast.ai GPU-маршрут (`$0.25` за 77 фото в PR #28) быстрее и дешевле по человеческому времени.

---

## 4. Способ подключения: прямой `mm3d` vs `mrMicMac` vs адаптер

### Почему `mrMicMac` не подходит для агентного workflow

Анализ исходников `meshroomHub/mrMicMac` (`9e8f7483`):
1. **Нет моста в AliceVision MVS:** [MicMacProject.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/project/MicMacProject.py) читает `CameraInit.output` лишь для того, чтобы **скопировать JPEG-файлы** в `{nodeCacheFolder}/project`. В [MicmacBasic.mgt](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/MicmacBasic.mgt) вся цепочка `TapiocaMulScale → Tapas → AperiCloud / C3DC` выполняется внутри MicMac. Узлов экспорта `Ori-* → AliceVision sfmData` в `mrMicMac` нет.
2. **Риск чтения устаревших результатов:** [Meshroom README.md:L106](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/README.md#L106) прямо предупреждает: *"While the plugin does not yet support Meshroom's full invalidation system"*. Причина видна в [node.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/common/node.py): все узлы работают с одним общим каталогом `projectDir` и мутируют в нём `Homol/`, `Ori-*`, `PIMs-*`.
3. **Интерактивные GUI-узлы:** `SaisieBascQT`, `SaisieMasqQT`, `SaisieAppuisInitQT` требуют окна Qt и непригодны для автономного headless-агента.

### Штатный способ: прямой вызов `mm3d` в изолированном каталоге запуска

- **Установка:** официальный бинарный архив `v1.2.0` (`micmac_linux.tgz` / `micmac_windows.zip`, вне Git, с проверкой SHA256). Все вспомогательные бинарники (`make`, `exiftool`, `exiv2`, `convert`, `proj`, `cs2cs`) в Windows-архиве уже внутри (`mm3d CheckDependencies`).
- **Обязательные флаги headless-запуска:** всегда добавлять `@ExitOnBrkp @ExitOnWarn @ExitOnNan` (иначе `mm3d` может повиснуть в ожидании нажатия Enter при предупреждении!).
- **Ограничение числа процессов:** MicMac порождает дочерние процессы через `make`. В среде с лимитом процессов/памяти (включая локальную Windows-политику `max_processes=32`, `2 GiB`) обязательно задать `<NbMaxProc> 2 </NbMaxProc>` в `include/XML_MicMac/MM-Environment.xml` и `ByP=2` для `Tapioca`.
- **Чистота путей и regex:** каталог бинарников и каталог запуска должны быть в **чистом ASCII без пробелов** (на Windows при кириллице в профиле пользователя работает Windows 8.3 short path или ASCII-каталог рабочей зоны). В шаблоне имён файлов на Windows **не писать обратный слэш `\.`** (`P10561.*jpg`, а не `P10561.*\.jpg` — иначе `mm3d.cpp:73` трактует `\` как разделитель каталога и падает с `FileLogMM3d: cannot open file for writing`).
- **Защита от устаревших файлов при повторе:** **каждый запуск с новыми входами или настройками — в новом пустом каталоге** `$WORK/micmac-run-<id>/` (копируются/линкуются только нужные оригиналы). При сравнении двух моделей калибровки на тех же `Homol/` задавать разные имена `Out=Rel_RadialStd` и `Out=Rel_FraserBasic` и отдельные имена PLY (`Out=C3DC_QuickMac.ply`).
- **Выходные файлы и соглашения:**
  - `Ori-<Out>/AutoCal_*.xml` — внутренняя калибровка (`F` в пикселях, `PP` в пикселях, `SzIm`, `ModPhgrStd` / `ModRad` / `ModFishEye`, конвенция `eConvApero_DistM2C`).
  - `Ori-<Out>/Orientation-<image>.xml` — внешние позы (`Centre`, `ParamRotation/CodageMatr` L1..L3, контрольные проекции `<Verif><Appuis>`).
  - `Ori-<Out>/Residus.xml` — история всех итераций BA (`AverageResidual`, по каждому кадру `Residual`, `PercOk`, `NbPts`, `NbPtsMul`).
  - `AperiCloud_<Out>.ply` — разреженное облако + пирамиды камер (binary little-endian PLY, XYZ + RGB).
  - `C3DC_<Mode>.ply` — плотное облако (binary little-endian PLY, `x y z nx ny nz red green blue`), готовое к прямому открытию в `Open3D` / `CloudCompare`.
  - **Единицы координат:** после `Tapas` — **произвольные относительные единицы (`scale = unknown`)**, оси произвольные. Единицы появляются только после явного масштабирования (`SBGlobBascule DistFS=...` или внешнего масштабирования по подтверждённой базе с обязательной записью происхождения).

---

## 5. Связь с мишенями (`CCTag3` / #29) и масштабом

### Проверка совместимости семейств мишеней

1. **MicMac V1 (`mm3d`):** не имеет встроенного детектора кодированных мишеней (ни `CCTag3`, ни `ArUco`, ни круговых `CERN`).
2. **MMVII (`a311b8e2`):** в [include/MMVII_enums.h](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/include/MMVII_enums.h) перечислены **все** поддерживаемые семейства (`eTyCodeTarget`):
   - `eIGNIndoor` (шахматная мишень),
   - `eIGNDroneSym` / `eIGNDroneTop` (шахматные с кодом),
   - `eCERN` (центральный круг + внешнее битовое кольцо в стиле AICON/Metashape).
   - **`CCTag3` (концентрические кольца AliceVision) в MMVII не поддерживается.** Похожий «круглый» вид `eCERN` не означает совместимости.

### Разделение трёх задач для мишеней и масштаба

| Задача | AliceVision + #29/#30 (наш основной путь) | MicMac V1 (`mm3d`) | MMVII |
|---|---|---|---|
| **1. Найти ID и 2D-центр на фото** | Автоматически (`aliceVision_featureExtraction` + `cctag3`) | Только вручную (`SaisieBascQT` / `SaisieAppuisInitQT` → `Mesure-S2D.xml`) | Автоматически (`CodedTargetCircExtract` / `CodedTargetExtract`), но **только `CERN`/`IGN`** |
| **2. Получить 3D-центр мишени** | Автоматически из `sparse-before.json` / `scene.json` (`check_marker_scale.py`) | Из триангуляции ручных 2D-измерений в `SBGlobBascule` / `Apero` | Из `OriBundleAdj` / `ReportGCP` (`PointsMeasure`) |
| **3. Задать масштаб / уточнить геометрию** | Скалярный `SfMTransform` по одной подтверждённой базе; остальные `check`-пары — независимый контроль (`reconstruction_report.py`) | `SBGlobBascule DistFS=<L>` (1 отрезок `Ech1`–`Ech2`, скалярный масштаб + плоскость); `Campari` требует GCP XYZ | `OriBundleAdj TopoDirIn=...` поддерживает **3D-расстояния** (`OBS code 3`, `cFormulaTopoDist`) прямо в BA — **но** требует `RTL` SysCo и начальные 3D-координаты; официальный пример `Circular-Coded-Targets` опирается на готовые 3D XYZ (`Panel_3D_coordinates.txt`) |

### Вывод по интеграции с #29/#30

- Пользовательский сценарий #29/#30 (отдельные печатные `CCTag3`, рабочая `capture/measurements.csv`, подтверждение заданной или фактической длины, 1 база масштаба + независимые контрольные пары) **полностью остаётся на основном маршруте AliceVision**.
- Менять `CCTag3` на `CERN`-мишени ради MMVII **сейчас нецелесообразно**: цена перехода — перестройка генератора комплекта, отказ от совместимости с `Legacy` Meshroom и потеря самостоятельного MVS (у MMVII нет своего многовидового `C3DC`). Возвращаться к MMVII + `CERN` + `OBS code 3` имеет смысл только если реальные промеры на `1x` + `CCTag3` докажут, что скалярного масштаба недостаточно и требуется совместное уравнивание сети расстояний внутри BA.
- Если MicMac V1 используется как CPU-диагностика на тех же фото с `CCTag3`, его выход честно остаётся в **`scale = unknown`** (сравниваем внутреннюю калибровку, репроекции, форму плоскостей/углы и безразмерные отношения длин `L_check / L_scale`), не тратя время оператора на ручное перещёлкивание центров в `SaisieBascQT`.

---

## 6. Выполненная минимальная CPU-проба (реальные входы → команды → выходы)

Чтобы не ограничиваться `--help` и документацией, выполнен реальный локальный прогон **MicMac V1 `v1.2.0`** на CPU Windows (внутри обязательного исполнителя `agent-exec.v3.exe`, лимит `2 GiB` RAM, `32` процесса, `$0` GPU).

### Входы и среда
- **Бинарник:** официальный [micmac_windows.zip (v1.2.0)](https://github.com/micmacIGN/micmac/releases/download/v1.2.0/micmac_windows.zip), `42 521 668` байт, SHA256 `7f2fcfb59c6dcc0b5db93fed9de01b413b279e589a7cdd423ab29af085af3c35`. `mm3d CheckDependencies` подтвердил `git revision : f357685` и встроенные `make/exiftool/exiv2/convert/proj/cs2cs`.
- **Публичные данные:** 8 оригинальных JPEG (`P1056139.jpg`–`P1056146.jpg`, `1296×972`, Panasonic `DC-GX9`, фокус `14 мм`, + `MicMac-LocalChantierDescripteur.xml`) из официального репозитория [MMVII-UseCaseDataSet/DevlopImage](https://github.com/micmac-V2/MMVII-UseCaseDataSet/tree/main/DevlopImage).
- **Изоляция:** свежий ASCII-каталог (Windows 8.3 short path) вне Git; в `include/XML_MicMac/MM-Environment.xml` добавлено `<NbMaxProc> 2 </NbMaxProc>`.

### Реально пойманные эксплуатационные проблемы (зафиксированы в рецепте)
1. **Regex с `\.` на Windows:** первый запуск `Tapioca All P10561.*\.jpg` упал (`rc=3221226505`, `mm3d.cpp:73: FileLogMM3d: cannot open file for writing in [P10561.*/]`) — MicMac на Windows трактует `\` как разделитель пути. Замена на `P10561.*jpg` полностью устранила сбой.
2. **Лимит процессов без `<NbMaxProc>`:** первый запуск `AperiCloud` без ограничения числа процессов был штатно остановлен политикой Windows Job (`exit=125 reason=active_process_limit`, лимит 32 процесса). Добавление `<NbMaxProc> 2 </NbMaxProc>` в `MM-Environment.xml` устранило сбой для `AperiCloud` и `C3DC`.

### Фактический проход (все 4 стадии `rc=0`, суммарно `156.2 с` на CPU)

| Стадия | Выполненная команда (внутри рабочего каталога) | Выход / статус | Время |
|---|---|---|---|
| 1. Признаки и сопоставление | `mm3d Tapioca All P10561.*jpg 800 ByP=2 @ExitOnBrkp @ExitOnWarn @ExitOnNan` | `rc=0`, `Homol/` создан | `40.96 с` |
| 2. Самокалибровка и SfM | `mm3d Tapas FraserBasic P10561.*jpg Out=Rel @ExitOnBrkp @ExitOnWarn @ExitOnNan` | `rc=0`, **8/8** камер в `Ori-Rel/`, 32 итерации, средний остаток **`0.2908 px`** (по кадрам `0.2759–0.2997 px`, `99.49–99.98%` inliers, `1772–5955` точек/кадр) | `45.66 с` |
| 3. Разреженное облако + камеры | `mm3d AperiCloud P10561.*jpg Rel Out=AperiCloud_Rel.ply @ExitOnBrkp @ExitOnWarn @ExitOnNan` | `rc=0`, `AperiCloud_Rel.ply` (`671 078` байт, **`44 723`** вершины XYZ+RGB) | `4.20 с` |
| 4. Плотное CPU-облако | `mm3d C3DC QuickMac P10561.*jpg Rel ZoomF=4 Out=C3DC_QuickMac.ply @ExitOnBrkp @ExitOnWarn @ExitOnNan` | `rc=0`, `C3DC_QuickMac.ply` (`3 669 345` байт, **`135 890`** вершин XYZ + нормали `nx,ny,nz` + RGB, `0` NaN/Inf, bounds `33.24 × 12.61 × 11.62` усл. ед.) | `65.40 с` |

Извлечённая внутренняя калибровка (`Ori-Rel/AutoCal_Foc-14000_Cam-DCGX9.xml`): `F = 1095.48 px`, `PP = (643.15, 478.81)`, `SzIm = 1296 × 972`, `ModPhgrStd` (`k1 = -5.66e-8`, `k2 = 3.82e-14`, `k3 = -1.70e-20`, `P1 = -1.80e-6`, `P2 = -2.45e-6`, `b1 = 1.54e-3`, `b2 = 6.36e-4`).

### Граница непроверенного (честное ограничение пробы)
- Проба подтверждает работоспособность цепочки `вход → mm3d CPU → AutoCal/Residus/PLY` и читаемость бинарного PLY.
- Проба **НЕ** подтверждает: физическую точность в миллиметрах (масштаб `unknown`, контрольных промеров нет), работу на фото Huawei Mate 50 (`4160×3120`, сверхширик `0.5x` или основной `1x`), визуальное качество кромок проёма и преимущество над AliceVision.

---

## 7. План честного сравнительного опыта (следующий шаг для доказательства пользы)

Не проводить большой бенчмарк всех режимов. Достаточно **одного небольшого сравнения на одинаковых исходниках**, когда появится первая реальная обмерная съёмка с метками по #29/#30:

- **Исходники:** один доступный проём/стена (комната или секция беседки), `25–45` резких оригиналов `4:3` с **одного фиксированного режима** Huawei Mate 50 (`1x` без зума, 2 яруса по высоте + крупные планы откосов), `4` печатных `CCTag3` (`0–1` `scale` ~1.5–2 м, `2–3` независимый `check`) + `2–3` реальных промера самого проёма (ширина, высота, диагональ) рулеткой/лазером.
- **Ветка A (основная):** `Meshroom/AliceVision 2026 Legacy + CCTag3` → `scale` по `0–1` → `DepthMap downscale=2` (и при необходимости `1` на ROI) → `dense.ply`, `mesh.obj`, `reconstruction_report.py`.
- **Ветка B (CPU-контроль MicMac V1):** те же самые оригиналы → `Tapioca MulScale` → `Tapas FraserBasic` → `AperiCloud` → `C3DC MicMac` (`ZoomF=2`) → `.ply`. Масштабирование для честного сравнения выполнять строго по **той же** базе `0–1` (не используя `2–3` и размеры проёма для подгонки!).
- **Что сравниваем в одной таблице:**
  1. Доля зарегистрированных камер и внутренняя репроекция (`px`).
  2. Ошибка на независимой контрольной паре `2–3` (`мм` и `%`) — проверка глобального масштаба/изгиба.
  3. Ошибка на реальных кромках проёма в `Open3D`/`CloudCompare` (ширина, высота, диагональ, `мм`).
  4. Время, RAM/стоимость GPU и объём ручной работы.
- **Критерий внедрения MicMac:** включать его в постоянный набор только если ветка B покажет воспроизводимый практический выигрыш (либо по геометрической точности/отсутствию изгиба, либо как реально востребованный бесплатный CPU-маршрут для малых участков), оправдывающий поддержку второго бинарника.

---

## 8. Ответы на 4 обязательных вопроса из Issue #31

1. **Какую конкретную проблему это решает сверх возможностей текущего AliceVision?**
   Две узкие, реальные задачи: (а) **бесплатный CPU-only плотный прогон (`C3DC`)** на малом объекте/участке (`10–40` фото) без CUDA-аренды; (б) **независимая вторая оценка внутренней калибровки и формы (`FraserBasic` / `FishEyeEqui`, прозрачные `AutoCal_*.xml` и `Residus.xml`)** для проверки гипотезы об изгибе/дисторсии оптики телефона. При этом задачи «метки + масштаб + контроль» (#29/#30) и «большие плотные сцены на GPU» (#27/#28) уже лучше закрыты нашим AliceVision-конвейером.
2. **Не пытаемся ли мы исправить отсутствующие наблюдения более сложной калибровкой?**
   **Да, этот риск реален — и его нужно жёстко пресекать.** Ни `FraserBasic` в MicMac, ни `OriBundleAdj` в MMVII не восстановят смазанное видео, отсутствие параллакса, пересвеченные стёкла или невидимые стороны мебели. Для наших задач переход со сверхширика `13 мм` на основную камеру `1x`, 2 яруса камер по высоте, крупные планы откосов и 4 метки `CCTag3` дадут точности на порядок больше, чем смена модели дисторсии на плохих фото.
3. **Сможет ли следующий агент отличить хороший внутренний расчёт от точного физического результата?**
   **Да, если закрепить явную 4-ступенчатую шкалу состояний** (в [проекте знаний](micmac-agent-knowledge-draft.md)): (1) внутренний расчёт (`exit 0`, 8/8 камер, `0.29 px`, `135k` точек) доказывает только самосогласованность в условных единицах; (2) одна база задаёт номинальный масштаб; (3) независимые контрольные пары проверяют каркас/отсутствие изгиба; (4) реальные промеры граней проёма проверяют продуктовую точность кромок. Агенту прямо запрещено объявлять миллиметровую точность по `Residus.xml` или размеру PLY.
4. **Какую часть предлагаемой интеграции можно убрать без потери полезного сценария?**
   Можно и нужно убрать **сразу всё лишнее**: плагин `mrMicMac`, весь стек `MMVII`, любой конвертер `Ori-* ↔ AliceVision sfmData`, автоматический перенос `CCTag3` в MicMac, GUI-инструменты `Saisie*QT` и отдельный оркестратор. Остаётся только один опциональный CLI-рецепт `mm3d` (`v1.2.0`) на CPU в изолированном каталоге.

---

## 9. Минимальная следующая реализация (если решим внедрять)

До проведения сравнительного опыта из раздела 7 **менять код ядра и основной workflow не нужно**. Если после опыта CPU-ветка MicMac V1 подтвердит пользу, минимальный объём изменений:
1. Зафиксировать версию и SHA256 `micmac_linux.tgz` / `micmac_windows.zip` (`v1.2.0`) в отдельном небольшом lock-файле (например, `configs/micmac-1.2.json`) — **не** добавляя в обязательные зависимости основного runtime.
2. Перенести проверенный рецепт из [проекта знаний](micmac-agent-knowledge-draft.md) в отдельный короткий подраздел `docs/runbook.md` и добавить 1 строку-указатель в `docs/meshroom-modes.md` и 2 строки в `.agents/skills/photogrammetry-workflow/SKILL.md` (без раздувания skill).
3. Опционально — тонкий read-only Python-скрипт (~40 строк) для разбора `Ori-*/Residus.xml` + `AutoCal_*.xml` + заголовка `C3DC_*.ply` в единый JSON-отчёт (чтобы агент не парсил XML одноразовыми командами).

---

## Первичные источники

- [micmacIGN/micmac (v1.2.0, 2026-06-10)](https://github.com/micmacIGN/micmac/releases/tag/v1.2.0) — официальные бинарники `micmac_linux.tgz` и `micmac_windows.zip`.
- [MicMac Wiki: Tapas](https://micmac.ensg.eu/index.php/Tapas), [C3DC](https://micmac.ensg.eu/index.php/C3DC), [SBGlobBascule](https://micmac.ensg.eu/index.php/SBGlobBascule).
- [micmac-V2/MMVII (a311b8e2, 2026-11-26)](https://github.com/micmac-V2/MMVII/tree/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240): [MMVII_enums.h](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/include/MMVII_enums.h) (`eTyCodeTarget`, `eTopoObsType`), [Topo presentation](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/Doc/Programming-Session-2024-09-Topo/presentation.md), [DenseMatch README](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/DenseMatch/README.md).
- [MMVII-UseCaseDataSet](https://github.com/micmac-V2/MMVII-UseCaseDataSet): [cmds_Circular-Coded-Targets.sh](https://github.com/micmac-V2/MMVII-UseCaseDataSet/blob/main/Circular-Coded-Targets/cmds_Circular-Coded-Targets.sh) (3D XYZ мишеней) и [DevlopImage](https://github.com/micmac-V2/MMVII-UseCaseDataSet/tree/main/DevlopImage) (данные нашей пробы).
- [meshroomHub/mrMicMac (9e8f7483, 2026-10-27)](https://github.com/meshroomHub/mrMicMac/tree/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f): [node.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/common/node.py), [MicMacProject.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/project/MicMacProject.py), [MicmacBasic.mgt](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/MicmacBasic.mgt).
- [Meshroom pinned README (b12ea889, L103–106)](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/README.md#L103-L106) — статус `MeshroomMicMac` и ограничение инвалидации.
- [AliceVision pinned nodes (d012d055)](https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision): `CameraInit.py`, `CheckerboardDetection.py`, `CheckerboardCalibration.py`, `DistortionCalibration.py`, `ApplyCalibration.py`, `SfMDistances.py`, `SfMSurveyInjecting.py`.
