# Исследование #31: MicMac / MMVII — выбор, запуск и оценка результата агентом

> **Статус:** исследовательский отчёт по [Issue #31](https://github.com/Kwentin3/photogrammetry-to-cad/issues/31) на базе `main` (`9d4ad78483187d924bc50d39ca195fecfd28b7e8`, с учётом открытых PR #28 и PR #30 как невмерженных ориентиров). **MicMac/MMVII не установлены как штатный режим проекта**; проект дополнений к рабочим инструкциям вынесен отдельно в [проект знаний для агента](micmac-agent-knowledge-draft.md).

> **Актуальное решение Goal #37 (27 ноября 2026):** исследование и результаты CPU-пробы сохранены; **внедрение MicMac приостановлено (paused)**. Дополнительная ценность для нашей задачи, включая выигрыш в геометрической и пространственной точности, **не подтверждена**. Это не утверждение о равенстве возможностей MicMac и AliceVision. Предложения ниже описывают исторические варианты продолжения #31: новые опыты и внедрение не входят в [Goal #37](https://github.com/Kwentin3/photogrammetry-to-cad/issues/37) и не блокируют его поставку. Даты, ревизии и доказательства исследования не переобъявляются повторно проверенными.

## 1. Короткое решение

**Основной маршрут (`Meshroom/AliceVision 2026 + CCTag3` из #29/#30) остаётся главным.** Менять базовый движок, устанавливать плагин `mrMicMac` или переходить на `MMVII` сейчас **не обосновано**.

**Исторический кандидат для опционального подключения (paused):** **прямой headless-вызов классического MicMac V1 (`v1.2.0`, `mm3d`) на CPU в изолированном каталоге запуска** (`Tapioca → Tapas → AperiCloud → опционально C3DC QuickMac/MicMac → .ply`). Его практическая дополнительная ценность для нашей задачи не подтверждена.

С учётом того, что **CPU-проверка камер и калибровки уже доступна и в самом AliceVision** (`FeatureExtraction.forceCpuExtraction` + `StructureFromMotion`), исследование выделило две возможности MicMac V1 для возможной проверки пользы, а не доказанный выигрыш:
1. **Независимая вторая реализация SfM и физической самокалибровки (`FraserBasic` / `RadialStd` / `FishEyeEqui`)** с прозрачными XML (`AutoCal_*.xml`, `Residus.xml`) для кросс-проверки гипотез о калибровке и форме на одинаковых исходниках.
2. **Штатное плотное CPU-облако (`C3DC QuickMac`/`MicMac` → `.ply`)** на небольшом участке без CUDA GPU (в AliceVision плотный `DepthMap` требует CUDA).

Что **осознанно не подключаем** на этом этапе:
- **`mrMicMac`** (`meshroomHub/mrMicMac`): не даёт моста «калибровка/позы MicMac → MVS AliceVision», имеет незавершённую инвалидацию кэша Meshroom при общем мутабельном каталоге `project/`, содержит GUI-узлы `Saisie*QT`.
- **`MMVII`** (`micmac-V2/MMVII`): несовместим с `CCTag3` (поддерживает только `IGN*` и `CERN`), не содержит самостоятельного многовидового MVS уровня `C3DC`, а его локальный путь `Topo`/`LocalNONE` на наших съёмках запуском не проверен.
- **Смешанный конвейер `MicMac Ori-* → AliceVision MVS`**: штатного конвертера в `mrMicMac` и AliceVision нет, а модели дисторсии математически не идентичны (`ModPhgrStd` / `FishEyeEqui` ≠ `radialk3` / `brown` / `fisheye4`). Самописный конвертер до доказанной потребности не нужен.

---

## 2. Разделение компонентов: AliceVision vs MicMac V1 vs MMVII vs `mrMicMac`

Все факты ниже сверены по первичным исходникам и релизам на **26 ноября 2026 года**:

| Компонент и проверенная ревизия | Готовность и бинарники | Калибровка и SfM | Плотная геометрия (MVS) | Мишени и масштаб | Совместимость с нашим workflow |
|---|---|---|---|---|---|
| **Закреплённый AliceVision** `d012d055` / Meshroom `b12ea889` (`2026-11-21`) | Готовый Linux CUDA 12.8 bundle (`600 МБ`), уже встроен и проверен | `CameraInit` (`pinhole`: `radialk1`, `radialk3`, `brown`; `equidistant`: `radialk3pt`, `fisheye1`, `fisheye4`); внешняя калибровка `CheckerboardDetection` → `CheckerboardCalibration` / `DistortionCalibration` → `ApplyCalibration`; **SfM доступен и на CPU** (`FeatureExtraction.forceCpuExtraction` + `StructureFromMotion`) | CUDA GPU (`DepthMap` → `Meshing` → `dense.ply` + `mesh.obj`). Нет штатного CPU MVS | **Нативный `CCTag3`** (`Legacy` квалифицирован), скалярный `SfMTransform` по базе; `SfMDistances` для диагностики; `SfMSurveyInjecting` требует полные `survey_3d` XYZ | **Основной конвейер.** Полная связка с #29/#30 (`capture/measurements.csv`, `reconstruction_report.py`) |
| **MicMac V1** `micmacIGN/micmac` `v1.2.0` (`2026-06-10`, HEAD `f8fe4321`, бинарник `f357685`) | Официальные архивы: `micmac_linux.tgz` (`52.2 МБ`), `micmac_windows.zip` (`42.5 МБ`, включает `make/exiftool/exiv2/convert/proj/cs2cs`) | `Tapioca` + `Tapas` (`RadialBasic`, `RadialStd`, `RadialExtended`, `FraserBasic`, `Fraser`, `FishEyeBasic`, `FishEyeEqui`, `HemiEqui`, `Figee`, `AutoCal`); прозрачные XML `AutoCal_*.xml` и `Residus.xml` | **CPU-only `C3DC`** (`QuickMac`, `MicMac`, `BigMac`, `Statue`) → бинарный `.ply` с нормалями | **Нет штатного автоматического детектора `CCTag3` и готового без-GUI маршрута под комплект #29/#30.** Масштаб задаётся через `SBGlobBascule PostPlan=NONE DistFS=...` по XML `Mesure-S2D.xml` (2D-наблюдения `Ech1`/`Ech2`, подготовленные вручную или программно) либо `Campari` с GCP XYZ | **Рекомендуемый опциональный CPU-резерв** через прямой вызов `mm3d` в отдельном каталоге; в `Open3D`/`CloudCompare` отдаёт `.ply` |
| **MMVII (MicMac V2)** `micmac-V2/MMVII` HEAD `a311b8e2` (`2026-11-26`) | `mmvii_windows.zip` (`72.5 МБ`), Docker `ghcr.io/micmac-v2/mmvii:latest`, активная разработка | `OriCreateCalib`, `OriPoseEstimSpaceResection`, `OriBundleAdj` (BA + `Topo` + жёсткие блоки + клинометры) | **Нет самостоятельного multi-view MVS**: `DenseMatchEpipGen` делает парный эпиполярный матчинг через `MMV1` SGM или `PSMNet` и требует пофайловые маски | `CodedTargetCircExtract` / `CodedTargetExtract` — **только `eIGNIndoor`, `eIGNDroneSym`, `eIGNDroneTop`, `eCERN`** (`MMVII_enums.h`). `Topo` поддерживает простые 3D-расстояния (`eCompDist`, `mObsSetSimple`) без станций и без `RTL` (`LocalNONE` в `Topo.cpp:62`), с попыткой автоинициализации необъявленных точек (`SysCo.tex:170`), но применимость к нашим данным запуском не проверена | **Отложить.** Несовместим с `CCTag3`, не заменяет плотный MVS, на наших данных не проверялся |
| **`mrMicMac`** `meshroomHub/mrMicMac` HEAD `9e8f7483` (`2026-10-27`) | Плагин Meshroom 2026+ (`MESHROOM_PLUGINS_PATH`), 33 узла `mm3d` + 3 утилиты MMVII (`OriConvV1V2`, `MeshCheck`, `MeshCloudClip`) | Обёртка над `mm3d` (`Tapioca*`, `Tapas`, `Campari`, `SBGlobBascule`) | Обёртка над `mm3d C3DC`, `TiPunch`, `Tequila` | Через GUI-узлы `SaisieBascQT` / `SaisieAppuis*QT` (непригодны headless) | **Отклонить.** Не связывает MicMac с MVS AliceVision, ломает инвалидацию кэша Meshroom (`Meshroom README.md:L106`) |

### Проверка `CameraCalibration` и CPU-возможностей в закреплённом AliceVision (`d012d055`)

В старой документации `meshroom-manual` описан монолитный узел `CameraCalibration`. Проверка дерева [meshroom/aliceVision на коммите d012d055](https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision) показала, что **узла `CameraCalibration.py` в нашей версии нет**. Вместо него в комплекте уже присутствуют модульные штатные узлы:
- `CheckerboardDetection.py` и `CheckerboardCalibration.py` (калибровка по шахматной доске);
- `DistortionCalibration.py` (калибровка дисторсии по полноэкранной сетке, модели `3deanamorphic4`, `3declassicld`, `3deradial4`);
- `ApplyCalibration.py` (принудительная подстановка заранее откалиброванного `sfmData` в новую сцену);
- в `CameraInit.py` уже доступны `pinhole` + `brown` (3 радиальных + 2 тангенциальных коэффициента) и `equidistant` + `fisheye4` / `radialk3pt`;
- в `FeatureExtraction.py` есть `forceCpuExtraction`, а `StructureFromMotion.py` выполняется на CPU — значит **базовая CPU-проверка камер/калибровки возможна уже внутри основного стека без установки MicMac**.

**Практический вывод:** прежде чем тащить MicMac ради «более сложной калибровки», нужно проверить, использованы ли штатные возможности самого AliceVision (`brown` вместо `radialk3` при признаках децентрирования, либо предварительная `CheckerboardCalibration` + `ApplyCalibration` для конкретного фиксированного режима телефона).

---

## 3. Калибровка широкоугольного телефона (Huawei Mate 50): модели, перенос и диагностика

### Выбор модели без ложного предположения «широкий угол = fisheye»

- **Широкий угол на смартфоне сам по себе не означает fisheye.** В [PR #28](https://github.com/Kwentin3/photogrammetry-to-cad/pull/28) на 77 оригинальных JPEG `4160×3120` сверхширика `1.95 мм` (`13 мм` экв.) штатная модель `pinhole/radialk3` зарегистрировала 77/77 камер с медианой репроекции `0.910 px` и умеренными коэффициентами дисторсии `(-0.021, 0.009, -0.003)`. **Это не доказывает конкретный характер ISP-коррекции Huawei или физическую точность модели на длинных пролётах**, но даёт основание проверять ректилинейную модель (`pinhole`/`FraserBasic`) первой, а не переходить автоматически к `fisheye` только из-за фокусного `13 мм`.
- **Как выбирать модель в MicMac `Tapas`:**
  1. Основная камера `1x` (~24–26 мм экв.) и широкоугольный JPEG `0.5x` без выраженного бочкообразного изгиба прямых у краёв: начинать с **`FraserBasic`** (10 параметров: `F`, `PP`, `k1..k3`, `P1/P2`, `b1/b2`, с `PPa == PPs`). При малом числе фото (< 15) или плоской сцене сначала стабилизировать более простой **`RadialStd`** / **`RadialBasic`**, чтобы не переобучить параметры.
  2. Настоящий fisheye (сильно изогнутые прямые у краёв, FOV > 120–140° без ректификации, либо `RAW`/`DNG`): **`FishEyeBasic`** / **`FishEyeEqui`**. Проверять их обоснованно, если на резких кадрах с параллаксом `FraserBasic` оставляет систематический рост остатков у краёв кадра.

### Когда калибровку нельзя переносить между съёмками

Внутреннюю калибровку (`AutoCal_*.xml` в MicMac или откалиброванный `sfmData` в AliceVision) **запрещено переносить** при любом из следующих изменений:
- **Смена физического модуля** (`0.5x` ↔ `1x` ↔ `3.5x`) или любой цифровой/гибридный зум.
- **Смена разрешения или соотношения сторон** (`4:3` `4160×3120` ↔ `16:9` ↔ видео `1920×1080` / `3840×2160`): кроп меняет эффективную ширину матрицы и главную точку.
- **Фото ↔ видео:** видеорежим смартфона может включать электронную стабилизацию (EIS), динамический кроп и rolling shutter — внутренняя калибровка фото не переносится на видео и наоборот.
- **Автофокус на ближней дистанции (макро / < 0.8 м):** изменение дистанции фокусировки сдвигает фокусное расстояние `F` (focus breathing).
- **Переключение стороннего приложения камеры / RAW ↔ JPEG / режимов обработки.**

### Самокалибровка по рабочим фото vs отдельная калибровочная съёмка

- **По текущим рабочим фото** (`Tapas FraserBasic` / BA AliceVision) самокалибровка применима, когда в сцене есть глубина (не одна плоская стена), перекрывающиеся ракурсы с параллаксом и разнообразие углов наклона/крена.
- **Отдельная калибровочная съёмка** оправдана, если рабочая сцена почти плоская (одна ровная стена/фасад, где `F` и глубина вырождены) или вытянута без перекрёстных взглядов.
- **Минимальная инструкция человеку для калибровки режима (если реально понадобится):**
  1. Зафиксировать **ровно один** фото-режим (один объектив, 4:3, без зума).
  2. Сделать `15–25` резких фото объёмной контрастной сцены (угол с рельефом либо плоская печатная шахматная доска на жёсткой подложке) с дистанции, близкой к рабочей (`1.5–2.5 м`).
  3. Заполнять деталями не только центр, но и **углы кадра** (иначе дисторсия по краям слабо определена).
  4. Сделать часть кадров горизонтально и **4–6 кадров с поворотом телефона на ±90° вокруг оптической оси** (разнообразие крена развязывает главную точку и дисторсию от положения камеры).
  5. Передать оригиналы без пересжатия; в MicMac калибровку сохраняют в `Ori-Calib/` и подают в рабочую съёмку через `Tapas Figee ... InCal=Calib` (замороженная) или `Tapas AutoCal ... InCal=Calib` (уточнение).

### Диагностика: калибровка vs параллакс / смаз / текстура / ракурсы

| Наблюдаемый симптом | Что проверить в первую очередь | Вероятнее ошибка калибровки | Вероятнее дефект съёмки / данных | Что остаётся гипотезой |
|---|---|---|---|---|
| Камеры не связываются (как `17/160` на видео #25) | Оригиналы 1:1 (резкость, смаз), пары и общие детали, изменение точки съёмки | Если кадры резкие, перекрытие высокое, а линии у краёв сильно выгнуты | Наблюдаемый смаз, слабый параллакс, однотонные стены, пересветы | Отдельный вклад смаза, EIS, перекрытия и калибровки без контрольного теста |
| Все камеры сошлись, репроекция `< 1 px`, но на независимых контрольных промерах есть систематическое расхождение или плоская стена «выгнута дугой» | Ошибка на независимых `check`-отрезках, плоский срез стены в `CloudCompare`/`Open3D` | **Возможная недокомпенсация радиальной дисторсии / дрейф `F`** | Также может быть слабая связка между зонами (узкий проход без перекрёстных кадров) | Исправит ли это `FraserBasic` / другая оптика — покажет только сравнительный прогон |
| Края одного проёма рваные/бугристые при приемлемых контрольных отрезках | Исходники проёма 1:1, экспозиция окна, число ракурсов по высоте | Маловероятно | Однотонная поверхность, контровой пересвет, мало ракурсов | Поможет ли `downscale=1` / `C3DC MicMac` — проверять на том же участке |

### Ориентиры по стоимости CPU-маршрута MicMac

Проба на 8 JPEG `1296×972` **не задаёт жёсткого универсального порога числа фото** (например, «отказ после 60–80»). На практике стоимость определяется отдельно для **SfM** (`Tapioca` + `Tapas`) и для **плотного расчёта** (`C3DC`) и зависит от разрешения кадров (`1296×972` vs `4160×3120`), параметра масштаба (`Tapioca` `800`/`1500`, `C3DC` `ZoomF=4`/`2`/`1`) и доступных CPU/RAM:
- **Начальный ориентир для малого CPU-прогона:** `10–40` фото при `Tapioca MulScale 400 1500` и `C3DC QuickMac` (`ZoomF=4`) — для проверки работоспособности, калибровки и формы на небольшом участке. В нашей пробе 8 фото `1296×972` заняли `156.2 с` на 2 процессах в пределах `2 GiB` RAM (из них `86.6 с` на SfM и `65.4 с` на `C3DC QuickMac`).
- **Где CPU становится узким местом:** плотный расчёт `C3DC BigMac` (`ZoomF=1`) на больших полноразмерных наборах `4160×3120` кратно растёт по времени и RAM; для крупных полных сцен наш проверенный Vast.ai GPU-маршрут (`$0.25` за 77 фото в PR #28) остаётся существенно быстрее.

---

## 4. Способ подключения: прямой `mm3d` vs `mrMicMac` vs адаптер

### Почему `mrMicMac` не подходит для агентного workflow

Анализ исходников `meshroomHub/mrMicMac` (`9e8f7483`):
1. **Нет моста в AliceVision MVS:** [MicMacProject.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/project/MicMacProject.py) читает `CameraInit.output` лишь для того, чтобы **скопировать JPEG-файлы** в `{nodeCacheFolder}/project`. В [MicmacBasic.mgt](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/MicmacBasic.mgt) вся цепочка `TapiocaMulScale → Tapas → AperiCloud / C3DC` выполняется внутри MicMac. Узлов экспорта `Ori-* → AliceVision sfmData` в `mrMicMac` нет.
2. **Риск чтения устаревших результатов:** [Meshroom README.md:L106](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/README.md#L106) прямо предупреждает: *"While the plugin does not yet support Meshroom's full invalidation system"*. Причина видна в [node.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/common/node.py): все узлы работают с одним общим каталогом `projectDir` и мутируют в нём `Homol/`, `Ori-*`, `PIMs-*`.
3. **Интерактивные GUI-узлы:** `SaisieBascQT`, `SaisieMasqQT`, `SaisieAppuisInitQT` требуют окна Qt и непригодны для автономного headless-агента.

### Штатный способ: прямой вызов `mm3d` в изолированном каталоге запуска

- **Установка:** официальный бинарный архив `v1.2.0` (`micmac_linux.tgz` / `micmac_windows.zip`, вне Git, с проверкой SHA256). В Windows-архиве все вспомогательные бинарники (`make`, `exiftool`, `exiv2`, `convert`, `proj`, `cs2cs`) уже внутри (`mm3d CheckDependencies`).
- **Обязательные флаги headless-запуска:** всегда добавлять `@ExitOnBrkp @ExitOnWarn @ExitOnNan` (иначе `mm3d` может ждать нажатия Enter при предупреждении).
- **Ограничение числа процессов:** MicMac порождает дочерние процессы через `make`. В среде с лимитом процессов/памяти (включая локальную Windows-политику `max_processes=32`, `2 GiB`) задавать `<NbMaxProc> 2 </NbMaxProc>` в `include/XML_MicMac/MM-Environment.xml` и `ByP=2` для `Tapioca`.
- **Чистота путей и regex:** каталог бинарников и каталог запуска — в **чистом ASCII без пробелов** (на Windows при кириллице в профиле пользователя работает Windows 8.3 short path или ASCII-каталог рабочей зоны). В шаблоне имён файлов на Windows **не писать обратный слэш `\.`** (`P10561.*jpg`, а не `P10561.*\.jpg` — иначе `mm3d.cpp:73` трактует `\` как разделитель каталога и падает с `FileLogMM3d: cannot open file for writing`).
- **Защита от устаревших файлов при повторе:** **каждый запуск с новыми входами или настройками — в новом пустом каталоге** `$WORK/micmac-run-<id>/`. При сравнении двух моделей калибровки на тех же `Homol/` задавать разные имена `Out=Rel_RadialStd` и `Out=Rel_FraserBasic` и отдельные имена PLY (`Out=C3DC_QuickMac.ply`).
- **Выходные файлы и соглашения:**
  - `Ori-<Out>/AutoCal_*.xml` — внутренняя калибровка (`F` и `PP` в пикселях, `SzIm`, `ModPhgrStd` / `ModRad` / `ModFishEye`, конвенция `eConvApero_DistM2C`).
  - `Ori-<Out>/Orientation-<image>.xml` — внешние позы (`Centre`, `ParamRotation/CodageMatr` L1..L3, контрольные проекции `<Verif><Appuis>`).
  - `Ori-<Out>/Residus.xml` — история всех итераций BA (`AverageResidual`, по каждому кадру `Residual`, `PercOk`, `NbPts`, `NbPtsMul`).
  - `AperiCloud_<Out>.ply` — разреженное облако + пирамиды камер (binary little-endian PLY, XYZ + RGB).
  - `C3DC_<Mode>.ply` — плотное облако (binary little-endian PLY, `x y z nx ny nz red green blue`), пригодное к прямому открытию в `Open3D` / `CloudCompare`.
  - **Единицы координат:** после `Tapas` — **произвольные относительные единицы (`scale = unknown`)**, оси произвольные. Единицы появляются только после явного масштабирования (`SBGlobBascule PostPlan=NONE DistFS=...` либо внешнего подтверждённого переноса масштаба с записью происхождения).

---

## 5. Связь с мишенями (`CCTag3` / #29), масштабом и независимым контролем

### Совместимость семейств мишеней и точные границы MicMac V1 / MMVII

1. **MicMac V1 (`v1.2.0`):** в проверенном списке команд `mm3d` нет штатного автоматического детектора `CCTag3` и готового без-GUI маршрута под наш комплект #29/#30. Отдельные старые/специализированные подсистемы мишеней в кодовой базе MicMac не обеспечивают автоматической работы с `CCTag3`.
2. **MMVII (`a311b8e2`):** в [include/MMVII_enums.h](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/include/MMVII_enums.h) перечислены **все** поддерживаемые семейства (`eTyCodeTarget`):
   - `eIGNIndoor` (шахматная мишень),
   - `eIGNDroneSym` / `eIGNDroneTop` (шахматные с кодом),
   - `eCERN` (центральный круг + внешнее битовое кольцо в стиле AICON/Metashape).
   - **`CCTag3` (концентрические кольца AliceVision) в MMVII не поддерживается.** Похожий «круглый» вид `eCERN` не означает совместимости.
3. **Фактические возможности и ограничения MMVII `Topo` на `a311b8e2` (сверено по исходникам):**
   - **Простые 3D-расстояния без станций:** [ctopodata.cpp:L285–296](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/Topo/ctopodata.cpp#L285-L296) помещает наблюдения `eCompDist` (OBS code `3`) в `mObsSetSimple` отдельно от станционных наблюдений.
   - **Локальная система без `RTL`:** [Topo.cpp:L62–64](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/Topo/Topo.cpp#L62-L64) допускает отсутствие `SysCo` при отсутствии вертикализации и использует `LocalNONE`.
   - **Известные XYZ vs приближённые начальные координаты:** нужно различать фиксированные/взвешенные измеренные 3D-координаты (как `Panel_3D_coordinates.txt` в официальном примере `Circular-Coded-Targets`) и приближённые координаты для старта нелинейного МНК; [SysCo.tex:L170](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/Doc/CommandReferences/SysCo.tex#L170) описывает попытку автоинициализации необъявленных точек по имеющимся точкам и наблюдениям. Это **не доказывает**, что произвольную сеть можно восстановить только из таблицы длин, и **применимость этого локального пути к нашим данным запуском не проверена**.
   - **Почему MMVII всё равно оставляем в резерве:** несовместимость с `CCTag3` (потребовала бы замену комплекта #29/#30 на `CERN`/`IGN`), отсутствие самостоятельного многовидового MVS уровня `C3DC` ([DenseMatch README](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/DenseMatch/README.md) — только парный эпиполярный матчинг с масками) и непроверенность локального `Topo`-пути на наших данных.

### Замкнутый headless-путь масштабирования в MicMac V1 (когда понадобится метрическое сравнение)

Отсутствие автодетектора `CCTag3` в MicMac V1 **не означает обязательность Qt GUI (`SaisieBascQT`)**. Проверка [CPP_SBGlobBascule.cpp](https://github.com/micmacIGN/micmac/blob/v1.2.0/src/uti_phgrm/CPP_SBGlobBascule.cpp#L92-L127) и [MesBasc-S2D.xml](https://github.com/micmac-V2/MMVII-UseCaseDataSet/blob/main/DevlopImage/DataAux/MesBasc-S2D.xml) показывает штатный текстовый XML-вход `SetOfMesureAppuisFlottants` и флаг `PostPlan=NONE` (без масок плоскости):

1. **Подготовленные 2D-наблюдения масштабной базы (`Ech1`, `Ech2`):** обычный XML `Mesure-S2D.xml` с пиксельными координатами `<NameIm>` и `<NamePt>Ech1</NamePt>/<NamePt>Ech2</NamePt>` минимум на 2+ ориентированных кадрах. На совместном наборе с `CCTag3` эти 2D-координаты можно взять без GUI из уже выполненной детекции `aliceVision_featureExtraction` (`cctag3` в `sparse-before.json` / `check_capture_kit.py`) через небольшой сериализатор в XML **либо** снять вручную (с обязательным учётом ручного труда).
2. **Штатное масштабирование в MicMac V1 (без подгонки контрольных пар):**
   ```bash
   mm3d SBGlobBascule "<PAT>" Rel Mesure-S2D.xml Scaled PostPlan=NONE DistFS=<L_base> \
     @ExitOnBrkp @ExitOnWarn @ExitOnNan
   ```
   Выход: `Ori-Scaled/` в тех же физических единицах, в которых задано `DistFS` (только одна подтверждённая пара `Ech1`–`Ech2`; контрольные пары и размеры проёма в `SBGlobBascule` не передаются).
3. **Плотное облако в физических единицах:**
   ```bash
   mm3d C3DC MicMac "<PAT>" Scaled ZoomF=2 Out=C3DC_Scaled.ply \
     @ExitOnBrkp @ExitOnWarn @ExitOnNan
   ```
4. **Независимый контроль:**
   - **Размеры физических граней/проёма** (ширина, высота, диагональ) снимаются напрямую по `C3DC_Scaled.ply` в `Open3D`/`CloudCompare` тем же способом, что и по облаку AliceVision (сравнение с независимым ручным промером).
   - **Контрольная пара `CCTag` `2–3`:** `SBGlobBascule` не выдаёт отчёт по дополнительным парам; для получения 3D-центров `2–3` в `Ori-Scaled/` требуется либо прямая многовидовая триангуляция их 2D-наблюдений по `Ori-Scaled/Orientation-*.xml` + `AutoCal_*.xml`, либо снятие центров на `C3DC_Scaled.ply` (с большей неопределённостью выбора точки).
   - **Честная граница статуса:** этот маршрут `Mesure-S2D.xml → SBGlobBascule → C3DC_Scaled.ply` **проверен по исходникам, но ещё не исполнялся на реальных данных**. Поэтому **первый** минимальный CPU-опыт (раздел 7) намеренно ограничен проверкой запуска, охвата и формы в `scale = unknown` без претензии на метрическое сравнение.

| Задача | AliceVision + #29/#30 (основной путь) | MicMac V1 (`mm3d`) | MMVII (`a311b8e2`) |
|---|---|---|---|
| **1. Найти ID и 2D-центр на фото** | Автоматически (`cctag3`) | Подготовленный XML `Mesure-S2D.xml` (конверсия из 2D `cctag3` либо ручной ввод; автодетектора `CCTag3` нет) | Автоматически (`CodedTarget*Extract`), но только `CERN`/`IGN` |
| **2. Получить 3D-центр мишени** | Автоматически из `scene.json` (`check_marker_scale.py`) | Для базы `Ech1`/`Ech2` — внутри `SBGlobBascule`; для доп. `check`-пар нужен отдельный шаг триангуляции или снятие по облаку | Внутри `OriBundleAdj` (`PointsMeasure`) |
| **3. Задать масштаб / контроль** | `SfMTransform` по 1 базе + `reconstruction_report.py` по всем `check`-парам | `SBGlobBascule PostPlan=NONE DistFS=...` по 1 базе (рецепт по исходникам, не прогнан); контроль по `C3DC_Scaled.ply` / триангуляции | `OriBundleAdj TopoDirIn` (`eCompDist` в `mObsSetSimple`, `LocalNONE` допустим; на наших данных не прогнан) |

---

## 6. Выполненная минимальная CPU-проба (реальные входы → команды → выходы)

Выполнен реальный локальный прогон **MicMac V1 `v1.2.0`** на CPU Windows (внутри обязательного исполнителя `agent-exec.v3.exe`, лимит `2 GiB` RAM, `32` процесса, `$0` GPU).

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

### Граница непроверенного
- Проба подтверждает работоспособность цепочки `вход → mm3d CPU → AutoCal/Residus/PLY` и валидность бинарного PLY на малом публичном наборе.
- Проба **НЕ** подтверждает: физическую точность в миллиметрах (масштаб `unknown`), работу на полноразмерных `4160×3120` фото Huawei Mate 50 (`0.5x` или `1x`), качество кромок проёма, маршрут `SBGlobBascule` и преимущество над AliceVision.

---

## 7. Историческое предложение следующего опыта (paused)

**Статус по Goal #37:** опыт не назначен к выполнению и не является условием завершения поставки. Вопрос и условия ниже сохранены из #31 для возможного отдельного решения владельца о возобновлении исследования.

В #31 смешаны три разных вопроса: (а) практичность CPU-резерва, (б) проверка гипотезы о калибровке `0.5x`, (в) точность CAD-размеров с метками. Их **нельзя смешивать в одном опыте**: новая съёмка `1x` не объяснит поведение `0.5x`, а проверка CPU-резерва не должна ждать новой съёмки владельца.

### Выбранный первый опыт: проверка CPU-резерва и формы на связном фрагменте доступной съёмки `0.5x` (#27)

- **Один проверяемый вопрос:** *даёт ли прямой CPU-маршрут MicMac V1 (`Tapioca MulScale` → `Tapas FraserBasic` → `AperiCloud` → `C3DC QuickMac`/`MicMac`) приемлемые время/RAM и сопоставимую или более ровную геометрию плоскостей/проёма по сравнению с уже имеющимся `Standard` AliceVision на одинаковых `15–25` оригиналах `0.5x` (`4160×3120`) из сохранённого набора #27?*
- **Почему именно этот первый вопрос:**
  1. Не блокируется ожиданием новой съёмки владельца и не требует аренды GPU (`$0`).
  2. Использует **те же самые оригиналы `0.5x`**, поэтому честно проверяет и практичность CPU на реальном разрешении `4160×3120`, и гипотезу о разнице моделей калибровки (`FraserBasic` vs `pinhole/radialk3`) именно для этого режима камеры.
  3. **Честная граница опыта:** масштаб остаётся `scale = unknown` (`INTERNAL_ONLY`). Метрическая точность в миллиметрах в этом шаге **не заявляется** — оцениваются только: доля зарегистрированных камер, фактические время/RAM на `4160×3120`, охват и плоскостность стен/проёма в `Open3D`/`CloudCompare` рядом с фрагментом `Standard` #27, и объём ручной работы.
- **Условия продолжения:**
  - **Если** MicMac V1 CPU укладывается в разумные время/память на `15–25` кадрах `4160×3120` и даёт практическую пользу (либо лучшую плоскостность/калибровку на `0.5x`, либо работоспособный бесплатный CPU-резерв) → переходим ко **второму отдельному шагу (метрическое сравнение для CAD)** уже на первой обмерной съёмке с `CCTag3` (#29/#30) + независимыми промерами проёма: с явной проверкой headless-цепочки `Mesure-S2D.xml → SBGlobBascule PostPlan=NONE DistFS=... → C3DC_Scaled.ply` (учитывая трудозатраты и не подавая контрольные отрезки и промеры проёма в подгонку).
  - **Если** на реальных `4160×3120` кадрах CPU-маршрут оказывается слишком тяжёлым или не даёт выигрыша по охвату/форме перед `AliceVision` → закрываем ветку MicMac без внедрения второго бинарника.

---

## 8. Ответы на 4 обязательных вопроса из Issue #31

1. **Какую конкретную проблему это решает сверх возможностей текущего AliceVision?**
   Поскольку CPU SfM/калибровка доступны уже в самом AliceVision (`forceCpuExtraction` + `StructureFromMotion`), добавочная польза MicMac V1 — это: (а) **независимая вторая реализация SfM/самокалибровки** (`FraserBasic` / `RadialStd` / `FishEyeEqui`, прозрачные `AutoCal_*.xml` и `Residus.xml`) для перекрёстной проверки гипотез о калибровке; (б) **штатное плотное CPU-облако (`C3DC`)** на малом участке без CUDA GPU. Задачи «`CCTag3` + масштаб + контроль» (#29/#30) и «большие плотные сцены на GPU» (#27/#28) уже лучше закрыты основным конвейером.
2. **Не пытаемся ли мы исправить отсутствующие наблюдения более сложной калибровкой?**
   **Да, этот риск реален — и его нужно жёстко отсекать.** Ни `FraserBasic` в MicMac, ни `OriBundleAdj` в MMVII не восстановят смазанные кадры, отсутствие параллакса, пересвеченные стёкла или невидимые стороны. Количественный сравнительный выигрыш между улучшением съёмки (`1x`, разнос по высоте, крупные планы, метки) и сменой модели калибровки у нас ещё не измерен, но физически модель дисторсии никогда не заменяет отсутствующие наблюдения.
3. **Сможет ли следующий агент отличить хороший внутренний расчёт от точного физического результата?**
   **Да, при использовании 4-ступенчатой шкалы состояний** (в [проекте знаний](micmac-agent-knowledge-draft.md)): (1) `INTERNAL_ONLY` (`rc=0`, 8/8 камер, `0.29 px`, `135k` точек — только внутренняя согласованность в условных единицах); (2) `SCALED_SINGLE_BASE` (масштаб по одной базе, без проверки остальной сцены); (3) `CONTROL_CHECKED` (независимые проверенные отрезки подтверждают **именно эти конкретные расстояния** в пределах допуска и неопределённости, не гарантируя автоматически точность всех камер или отсутствие изгиба всей сцены); (4) `GEOMETRY_EDGE_CHECKED` (проверка реальных физических кромок/проёмов объекта).
4. **Какую часть предлагаемой интеграции можно убрать без потери полезного сценария?**
   Можно и нужно убрать **всё лишнее**: плагин `mrMicMac`, весь стек `MMVII`, любой конвертер `Ori-* ↔ AliceVision sfmData`, попытку автодетекции `CCTag3` внутри MicMac, GUI-инструменты `Saisie*QT` и отдельный оркестратор. Остаётся только один опциональный CLI-рецепт `mm3d` (`v1.2.0`) на CPU в изолированном каталоге.

---

## 9. Исторический проект внедрения (paused; если опыт подтвердит пользу)

**Внедрение приостановлено по Goal #37.** Перечень ниже не является текущим заданием и не добавляет зависимостей в действующий workflow.

До выполнения первого опыта из раздела 7 **менять код ядра, `SKILL.md` и `docs/runbook.md` не нужно**. Если опыт подтвердит пользу CPU-ветки MicMac V1, минимальный объём внедрения:
1. Зафиксировать версию и SHA256 `micmac_linux.tgz` / `micmac_windows.zip` (`v1.2.0`) в отдельном lock-файле (например, `configs/micmac-1.2.json`) — **не** делая MicMac обязательной зависимостью основного runtime.
2. Перенести проверенный рецепт из [проекта знаний](micmac-agent-knowledge-draft.md) в отдельный короткий подраздел `docs/runbook.md`, добавить 1 строку-указатель в `docs/meshroom-modes.md` и 2 строки в `.agents/skills/photogrammetry-workflow/SKILL.md`.
3. Опционально — тонкий read-only Python-скрипт (~40 строк) для разбора `Ori-*/Residus.xml` + `AutoCal_*.xml` + заголовка `C3DC_*.ply` в JSON-отчёт.

---

## Первичные источники

- [micmacIGN/micmac (v1.2.0, 2026-06-10)](https://github.com/micmacIGN/micmac/releases/tag/v1.2.0) — официальные бинарники `micmac_linux.tgz` и `micmac_windows.zip`; [CPP_SBGlobBascule.cpp](https://github.com/micmacIGN/micmac/blob/v1.2.0/src/uti_phgrm/CPP_SBGlobBascule.cpp#L92-L127).
- [MicMac Wiki: Tapas](https://micmac.ensg.eu/index.php/Tapas), [C3DC](https://micmac.ensg.eu/index.php/C3DC), [SBGlobBascule](https://micmac.ensg.eu/index.php/SBGlobBascule).
- [micmac-V2/MMVII (a311b8e2, 2026-11-26)](https://github.com/micmac-V2/MMVII/tree/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240): [MMVII_enums.h](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/include/MMVII_enums.h) (`eTyCodeTarget`, `eTopoObsType`), [Topo.cpp:L62](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/Topo/Topo.cpp#L62), [ctopodata.cpp:L285](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/Topo/ctopodata.cpp#L285), [SysCo.tex:L170](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/Doc/CommandReferences/SysCo.tex#L170), [DenseMatch README](https://github.com/micmac-V2/MMVII/blob/a311b8e20458a43ba1ce7e2b4a97a5612ba6c240/src/DenseMatch/README.md).
- [MMVII-UseCaseDataSet](https://github.com/micmac-V2/MMVII-UseCaseDataSet): [cmds_Circular-Coded-Targets.sh](https://github.com/micmac-V2/MMVII-UseCaseDataSet/blob/main/Circular-Coded-Targets/cmds_Circular-Coded-Targets.sh), [DevlopImage](https://github.com/micmac-V2/MMVII-UseCaseDataSet/tree/main/DevlopImage), [MesBasc-S2D.xml](https://github.com/micmac-V2/MMVII-UseCaseDataSet/blob/main/DevlopImage/DataAux/MesBasc-S2D.xml).
- [meshroomHub/mrMicMac (9e8f7483, 2026-10-27)](https://github.com/meshroomHub/mrMicMac/tree/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f): [node.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/common/node.py), [MicMacProject.py](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/project/MicMacProject.py), [MicmacBasic.mgt](https://github.com/meshroomHub/mrMicMac/blob/9e8f7483ec8fd92fbad28693ad68a92ce39cc23f/meshroom/MicmacBasic.mgt).
- [Meshroom pinned README (b12ea889, L103–106)](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/README.md#L103-L106) — статус `MeshroomMicMac` и ограничение инвалидации.
- [AliceVision pinned nodes (d012d055)](https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision): `CameraInit.py`, `FeatureExtraction.py` (`forceCpuExtraction`), `StructureFromMotion.py`, `CheckerboardDetection.py`, `CheckerboardCalibration.py`, `DistortionCalibration.py`, `ApplyCalibration.py`, `SfMDistances.py`, `SfMSurveyInjecting.py`.
