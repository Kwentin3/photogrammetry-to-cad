# Режимы закреплённой Meshroom 2026

Это точка выбора сценария **фото/видео → фотограмметрическая геометрия**.
Команды общего запуска, наблюдения, продолжения и сохранения результата —
в [runbook](runbook.md); принятый аудит — [Goal #8](goal-8.md),
проверенная автоматическая dense-маска — [Goal #12](goal-12.md).
CAD и распознавание деталей — следующие отдельные этапы. Весь цикл от подготовки
оператора — [короткий skill](../.agents/skills/photogrammetry-workflow/SKILL.md).
Контракты продолжения, defaults и переносимости разобраны в
[исследовании #38](https://github.com/Kwentin3/photogrammetry-to-cad/blob/f7b3d70c75f98af9262671fd4d8b5de48fb354fd/research/mesh-textures-meshroom-gui.md).
Исследование фиксирует исходные контракты. Реальное CPU-продолжение комнаты
до MeshFiltering/Texturing и граница локальной GUI-проверки описаны в
[отчёте #40](reports/2026-11-27/room-mesh-textures.md).

| Что нужно получить / как снято | Выбрать | Подробности |
|---|---|---|
| Обычные фото неподвижной сцены → облако и исходная сетка | Standard; до штатного Meshing, оба выхода создаются вместе | [Фото и граф](#фото-и-обычная-сцена), [выходы](#облако-и-исходная-сетка) |
| Видео → те же результаты | KeyframeSelection, затем Standard | [Кадры видео](#видео-и-выбор-кадров) |
| Нужны CCTag или запасной SfM | Legacy | [Фото и граф](#фото-и-обычная-сцена), [масштаб](#масштаб-и-ориентация) |
| Нужно исключить фон | Готовые маски, ImageMasking либо дополнительная ML-сегментация | [Маски](#маски-и-сегментация) |
| Объект вращается на столе | Маски **до признаков/SfM**, либо ObjectTurntable с дополнением | [Стол и переворот](#поворотный-стол-и-две-стороны) |
| Объект перевёрнут для съёмки низа | Две отдельные группы → ObjectTwoSides | [Стол и переворот](#поворотный-стол-и-две-стороны) |
| Удалить лишние части сетки / сгладить | Продолжить проект до MeshFiltering с явными настройками | [Фильтрация](#фильтрация-сетки) |
| Нужна модель с фотографической текстурой | Продолжить проект до Texturing, сохранить весь комплект | [Текстуры и экспорт](#текстуры-и-экспорт) |
| Иная задача из списка шаблонов | Сначала проверить её домен и зависимости | [Остальные шаблоны](#остальные-шаблоны-комплекта) |

Статусы различаем буквально: **выполнено** — есть фактические результаты;
**рецепт** — проверены файлы/контракты, но этот режим не вычислялся;
**нужно дополнение/данные** — сначала устранить названный пробел.
Наличие шаблона, успешное чтение графа и локальный тест не означают выполненную
реконструкцию. Масштаб без измеренного источника остаётся неизвестным.

## Как принять решение и проверить его

Выбирать нужный выход и причину изменения, а не включать все опции. Сначала
просмотреть входы и уже имеющиеся результаты; затем использовать строку ниже
и подробный раздел. Резервная ветка применяется по наблюдаемой проблеме.

| Выбор | Что просмотреть после запуска | При наблюдаемой неудаче |
|---|---|---|
| Фото / Regular / Smart | Оригиналы и все выбранные кадры: начало/конец, стороны, смаз, перекрытие | Изменить отбор в новом проекте; Smart полезен при неравномерном движении, но не создаст отсутствующий ракурс |
| Standard / Legacy | Камеры относительно кадров, cloud и raw mesh с нескольких направлений | Сначала проверить входы/камеры и native diagnostic; Legacy — подготовленный запасной SfM, CCTag требует Legacy |
| Dense-only / features-маски | Overlays тонких краёв/меток, EXR QA, нужные поверхности mesh | Уточнить маску и пересчитать зависимые стадии. При столе фон надо убрать до камер; ordinary обход допускает фон для камер |
| Стол / TwoSides | Состав групп и общие поверхности, согласованность меток, отсутствие двойной оболочки | Проверить жёсткость/перекрытие групп; запросить общие боковые ракурсы. Зависимости установить до compute, не обещать готовый путь без них |
| Масштаб / ориентация | Измеренная база и независимые размеры; отдельно принятая система осей | Без базы оставить неизвестные единицы; единый поворот не исправляет перекосы |
| Raw / фильтрация / текстуры | Mesh без текстуры до/после, неизменные ракурсы/масштаб; затем комплект материалов | Откатить фильтр, если исчезла нужная деталь; texture/smoothing не доказывают геометрического улучшения |
| Продолжить проект | Input SHA, native UID, фактический job/status и наличие всех входов endpoint | Не дублировать активный compute; при новых параметрах подготовить новый RUN с явным reuse cache; SUCCESS без EXR требует адресного восстановления |

Практический способ открыть файлы и сравнить изменение —
[визуальная проверка](geometry-review.md). Отсутствие наблюдений означает запрос
конкретной досъёмки, а не бесконечный перебор параметров.

| Наблюдаемая задача или симптом | Достаточное действие | Что не считать исправлением |
|---|---|---|
| Нужно только плотное облако | Meshing → native scene → PLY, осмотр охвата и масштаба | Запуск Texturing не улучшит точки |
| Нужна сетка с важными краями | Raw mesh как baseline; фильтр по видимому дефекту, smoothingIterations=0; сравнить края без материала | Отключённое smoothing не делает остальные фильтры тождественными |
| Нужен фотографический вид, ExportImages SUCCESS, EXR нет | Проверить dense scene/mesh/original paths, адресно восстановить ExportImages, затем Texturing | Полный forced SfM/dense либо старый SUCCESS не восстанавливают нужные файлы автоматически |
| Текстура красива, но геометрия неверна | Смотреть plain mesh и камеры/исходники; установить дефект камер, dense или нехватку наблюдений | Цвет и texture fillHoles не подтверждают форму/размеры |
| Материал отсутствует или розовый | Проверить MTL/пути, все карты, формат/цветовое пространство и перенос; открыть полный комплект | Новая геометрия не исправляет потерянную внешнюю карту |
| Цвет размыт или шов виден | Сопоставить резкость оригиналов, камеры, UV, экспозицию и фактический atlas size; одна адресная итерация | Больший atlas не добавит резкости смазанному источнику |
| Дыра mesh или поверхность не наблюдалась | Проверить маску/камеры и видимые исходники; запросить нужный ракурс при отсутствии данных | Заполнение текстурной дыры не создаёт измеренную поверхность |

## Что проверено в комплекте

2026-11-21 статически проверен полный архив
`Meshroom-2026.11.21-b12ea88-linux-full.tar.gz`: **600156630 байт**,
SHA256 `4ca3cfb0898b8000def4e68d513468a199b948329b63cdb6b257e427d295163b`.
Pins и путь сохранённой копии — в [runtime-2026.json](../configs/runtime-2026.json).
Архив содержит **12486 записей**, **27 шаблонов `.mgt`** и **112 Python-файлов
описаний AliceVision**, включая `__init__.py` и вспомогательные классы;
последнее число не является числом исполняемых узлов. Также присутствуют
встроенные general nodes, включая CopyFiles и GraphIO, CLI и менеджер плагинов.

Опора — Meshroom `b12ea8896e7e95cc9911b4ec39c272914e4da726` и AliceVision
`d012d05589b528dcf57a2a0c805c0a5709df8613`.
Ниже «доступно в архиве» означает наличие файлов, «изучено» — разбор их
контрактов. Эти статусы не подтверждают успешную обработку новой съёмки.
В Goal #6 одно реальное видео прошло native regular отбор и оба графа до плотного
PLY: у каждого зарегистрированы 37/37 камер. Для базового фото/видео выбран
Standard. Backup проверен локально, аренда удалена; публикация поставки
учитывается отдельно в рабочей записи Goal.
Факты и ограничения — в [отчёте фото/видео → 3D](reports/2026-11-21/photo-video-3d.md).
Историческая проверка Legacy описана отдельно в [отчёте Goal #4](reports/2026-11-21/meshroom-2026.md).

## Фото и обычная сцена

Нужны перекрывающиеся резкие фотографии неподвижного жёсткого объекта,
различимые детали поверхности и разные точки наблюдения. Фото, полученные
из видео, имеют тот же контракт после отбора. Блики, прозрачность, движение,
одинаковые повторяющиеся поверхности и невидимые стороны остаются источниками
пропусков; увеличение числа точек их не устраняет.

| Путь | Вход → основные настройки → выход | Наличие и фактическая проверка |
|---|---|---|
| [Standard: photogrammetry.mgt][standard] | CameraInit с фото → модульный SfM, IntrinsicsTransforming/ExportImages → DepthMap/DepthMapFilter → Meshing. Настройки: FOV при отсутствии калибровки, describerPreset/Quality, DepthMap.downscale, Meshing.maxInputPoints/maxPoints | В комплекте. **Выполнено** в #6: 37/37 камер, 121291 точка; базовый путь без PDS adapter. Физическая точность неизвестна |
| [Legacy: photogrammetryLegacy.mgt][legacy] | Те же фото → StructureFromMotion/PrepareDenseScene → DepthMap/DepthMapFilter/Meshing. Для CCTag используются cctag3 и отдельный контракт масштаба | В комплекте. **Выполнено** на тех же кадрах: 37/37 камер, 121513 точек; один whole-scene PDS adapter. Это fallback, не доказательство большей точности |

Простой поддерживаемый запуск — [runbook](runbook.md): входы и настройки
меняются через обычный JSON. Полный штатный граф сохраняется; вычисление
до Meshing не требует выполнять MeshFiltering/Texturing/CopyFiles.
Файлы шаблонов и descriptors — `aliceVision/share/meshroom/` внутри runtime.
Для нестандартного графа есть штатные [meshroom_batch][batch] и
[meshroom_compute][compute], без расширения списка режимов общей обвязки.

## Видео и выбор кадров

Нужно обходить объект с перекрытием и изменением точки наблюдения: панорамный
поворот камеры с одного места не даёт глубину. KeyframeSelection принимает
`inputPaths` (видео, каталог последовательности или SfMData), сведения о камере
`brands/models/mmFocals` при наличии; для видео `outputExtension` должен быть
`jpg`, `png` или `exr`, не `none`. Выходы — выбранные изображения,
`outputSfMDataKeyframes` и диагностические оценки, если включены.
`outputSfMDataFrames` с невыбранными views создаётся для последовательности
изображений; при видео невыбранные кадры не записываются и этого файла нет.

| Отбор | Когда и настройки | Статус / запуск |
|---|---|---|
| Regular | Предсказуемый шаг кадров: `selectionMethod.useSmartSelection=false`, `regularSelection.minFrameStep/maxFrameStep/maxNbOutFrames` внутри selectionMethod. Ограничение maxNbOutFrames вместе с шагом может оборвать охват до конца ролика | **Выполнено** в #6: Objectron MOV → 37 кадров → оба плотных результата. Готовые команды и manifest — [runbook](runbook.md) |
| Smart | Неравномерное движение и резкость: `selectionMethod.useSmartSelection=true`, `smartSelection.pxDisplacement/minNbOutFrames/maxNbOutFrames`; scores используют sharpness и optical flow. `maskPaths` при необходимости исключают фон из оценки | **Выполнено** 25 ноября: собственное видео → 160 проверенных кадров, flow 240/sharpness 720, экспорт 1080×2560. Обмерная геометрия комнаты не получена. [Фактический прогон](reports/2026-11-25/room-smart.md); имена параметров — [pinned KeyframeSelection.py][keyframes] |

Для smart используется тот же этап подготовки видео из runbook с выбором smart
и его параметрами; затем выбранные файлы поступают в обычную реконструкцию.
До дорогого расчёта просмотреть выбранные кадры: резкость, охват начала/конца,
ракурсы и пропуски. SfMData views и manifest должны описывать именно эти файлы.
Старая [страница руководства](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/KeyframeSelection.html)
описывает прежние параметры; для этого runtime приоритет у pinned descriptor.

## Маски и сегментация

Goal #12: [отдельный SAM2.1-small/HF GroundingDINO-tiny генератор](auto-masks.md)
передаёт PNG в существующий вход ниже. На 37 кадрах реально проверены inference,
native PNG/EXR и dense-only Standard cloud/mesh с теми же камерами.
[Сравнение и ограничения](reports/2026-11-22/auto-masks.md), [запись Goal #12](goal-12.md).

Маска сохраняет объект ненулевыми пикселями, исключает фон нулями. Проверяются
полное покрытие кадров, имена (`viewId`, затем stem исходника), размеры и
полярность. Ручная подготовка допустима; её объём записывается.

| Путь | Когда / входы / основные настройки / выход | Запуск, комплект и статус |
|---|---|---|
| Готовые маски | Любой способ получения масок → FeatureExtraction.masksFolder при исключении фона из SfM; ExportImages.masksFolders либо Legacy PrepareDenseScene.masksFolders для плотной стадии, с явным maskExtension. Выход — признаки объекта и EXR с alpha | Настройки `masks.folder/extension/features/invert` в [runbook](runbook.md). **Реальный Standard dense-only** с `features=false` проверен в #12, 37 кадров до cloud/mesh. Маски признаков/SfM, Legacy/стол остаются рецептами; частичные наборы не поддерживаются |
| SAM2.1-small + local HF GroundingDINO-tiny | Отдельное pinned ML-окружение, prompt/thresholds/single либо union → полный PNG набор → существующая строка выше | **Проверено в #12** на одном реальном Standard dense-only примере. [CLI, проверка и отключение](auto-masks.md); bottom-face/edge losses и неизвестная физическая точность указаны в отчёте |
| [ImageMasking][masking] | Однотонный фон: CameraInit.output → ImageMasking.input; algorithm=HSV (hsvHue/Range, Saturation/Value) либо AutoGrayscaleThreshold; invert, growRadius/shrinkRadius. Выход — каталог масок | В комплекте без ML. **Рецепт**: добавить node в сохранённый граф в GUI, связать CameraInit.output с input, вычислить до него, проверить маски и передать в предыдущую строку. [MaskProcessing][maskprocessing]/[MaskEroding][maskeroding] — дополнительные штатные операции над масками |
| [photogrammetryObject.mgt][object] | Неподвижный объект на сложном фоне: фото → ImageDetectionPrompt (`prompt`, `synonyms`, thresholdDetection) → ImageSegmentationBox → masks в PrepareDenseScene. Признаки исходного SfM здесь **не** маскированы | **Нужно дополнение** [mrSegmentation][segmentation], его зависимости и веса RAM++/GroundingDINO/SAM. Шаблон есть, nodes/веса отсутствуют в полном архиве. После установки: штатный batch с этим pipeline, ввод в CameraInit_1, остановка до нужного узла. Не выполнялось |

До применения HSV/ML проверить кадры с тонкими краями, отверстиями, тенями и
цветами, похожими на фон. Неправильная маска удаляет данные, которые движок
не восстановит. Не устанавливать ML ради обычной съёмки без проблемы фона.

**CCTag3 вместе с масками:** неподвижная сцена/рейка → Legacy и
`masks.features=false`, метки доступны до плотной стадии. Стол → маски до камер,
`features=true`, нужные метки внутри масок и жёстко движутся с предметом.
При перевороте отдельно фиксировать связь меток с предметом в обеих группах.
[Размещение и пробные кадры](capture.md#метки-вместе-с-масками-и-движением-объекта).
Реальный #12 квалифицирует только Standard dense-only без меток. Legacy +
автомаски + CCTag3 и стол с метками требуют проверки выбранной связки;
поддержка отдельных настроек сама по себе не подтверждает их совместный прогон.

## Поворотный стол и две стороны

Поворотный стол меняет движение объекта относительно неподвижного фона.
Для SfM нужны признаки **самого объекта**; фон исключают уже в FeatureExtraction.
Обсуждение [#1757](https://github.com/alicevision/Meshroom/issues/1757)
с ответом участника команды Meshroom указывает на новые object/turntable-шаблоны;
оно не подтверждает результат на наших данных.

| Сценарий | Штатный граф, данные и настройки | Выход, дополнение и статус |
|---|---|---|
| [photogrammetryObjectTurntable.mgt][turntable] | Один жёсткий объект, круги с разных высот, фон под маской. CameraInit_1 → detection/segmentation → FeatureExtraction_1.masksFolder; далее Legacy SfM/PDS и dense. Настроить prompt/маски до расчёта | Meshing_1.output + outputMesh, затем при необходимости filtering/texturing. **Нужно mrSegmentation и веса; рецепт без выполнения**. Вариант без ML — готовые маски с features=true в общем Legacy-пути; это отдельный рецепт, также не квалифицированный реальным запуском |
| [photogrammetryObjectTwoSides.mgt][twosides] | Два раздельных набора одного жёсткого объекта до/после переворота с общими различимыми участками поверхности. CameraInit_1 и _2, две сегментации; раздельные SfM, masked признаки для сопоставления сторон, SfMMerge_1.method=from_landmarks, повторная триангуляция | Объединённая сцена → Meshing_3.output/outputMesh. **Нужно mrSegmentation/веса и подходящая съёмка; рецепт без выполнения**. Полностью непересекающиеся стороны не получают достоверной взаимной позиции только из этого шаблона |

Точный native рецепт для двух сторон после установки дополнения, на Linux
с закреплённым runtime; `$MESHROOM_ROOT` и `$RUN` — пути из runbook, RUN новый:

```bash
"$MESHROOM_ROOT/meshroom_batch" --pipeline photogrammetryObjectTwoSides \
  --input 'CameraInit_1=/data/side-a' 'CameraInit_2=/data/side-b' \
  --output "$RUN/published" --save "$RUN/project.mg" \
  --overrideCacheDir "$RUN/cache" --compute no
# Проверить состав обеих CameraInit, prompt/маски и nodeType в сохранённом графе.
"$MESHROOM_ROOT/meshroom_compute" "$RUN/project.mg" --cache "$RUN/cache" --toNode Meshing_3
```

Имена выше сверены с pinned шаблоном. Не передавать обе папки без адресации:
штатный batch по умолчанию подаёт общие inputs **во все** Init Nodes.
`--output` также сохраняет штатные Output Nodes при инициализации шаблона;
без него native batch может убрать CopyFiles. Каталог published не заменяет
сохранение облака, raw mesh и полного комплекта из фактических outputs.
Для Object и ObjectTurntable соответственно заменить pipeline и передать один
`CameraInit_1=/data/images`, конечный узел взять из графа (в этих pins Meshing_1).
Выполнение не разрешает пропустить ограничение ресурсов, PDS QA и сохранение
результатов из runbook; эти рецепты не являются журналом выполненных запусков.
Известная граница: общий `prepare_dense_images.py` адресует только
PrepareDenseScene_1; у TwoSides плотная ветка использует PrepareDenseScene_3.
Если проявится уже известная ошибка PDS без chunks/EXR, этот helper нельзя
считать готовым обходом для TwoSides: требуется отдельный whole-scene native
вызов для фактического узла и проверка EXR/alpha/metadata. Этот участок
двухстороннего рецепта не квалифицирован запуском; чужие status не исправлять
фиктивным SUCCESS.

## Масштаб и ориентация

По умолчанию SfM units произвольны. **Выполнено:** native scalar SfMTransform
на историческом synthetic SfM; реальные 37 видеокадров не имеют физического
масштаба. Это не проверка новой измеренной рулеткой базы.

Для измеренной базы общий путь поддерживает **Legacy + cctag3** в
FeatureExtraction и FeatureMatching: два разных ID 0..31, положительное
distance, units=mm/cm/m и measurement_source реального замера. Adapter вычисляет
отношение к native базе и задаёт scalar scale без смены углов, осей и начала;
точные настройки — [runbook](runbook.md). Нужны распечатанные метки,
однозначные наблюдения и настоящий замер. Standard отвергает CCTag:
ID encoding нового DAG не квалифицирован.

Ориентация — отдельный штатный [SfMTransform][transform]: `auto`,
`auto_from_cameras`, `align_ground`, `from_single_camera` и другие методы;
явный `manual` задаёт manualTranslation/manualRotation/manualScale.
Флаги applyScale/applyRotation/applyTranslation позволяют ограничить изменение.
У Standard adapter без явных настроек сохраняется принятый identity default.
При задании `nodes.SfMTransform_1` его поля не перезаписываются default: для
ориентации явно выбрать method и applyRotation=true, а остальные флаги — по задаче.
Физический scale.mode=unknown от такого поворота не становится измеренным.
**Рецепт без нового выполнения:** настроить node в сохранённом графе до плотной
стадии; сохранить исходную сцену и описать преобразование. При изменении сцены
зависимые плотные стадии требуют соответствующего пересчёта. Auto orientation
не доказывает физическую вертикаль, а единый поворот не исправляет углы деталей.

Полные известные XYZ меток — `method=from_markers` и список markerId/markerCoord;
это иной контракт, чем два ID и расстояние. Общий `marker_coords` зарезервирован
и отвергается; историческая настройка сохранена в
[prepare_graphs_2026.py](../scripts/prepare_graphs_2026.py), результат — в
[отчёте Goal #4](reports/2026-11-21/meshroom-2026.md).
Synthetic 100 мм не переносить на реальные фото.

## Облако и исходная сетка

Meshing создаёт **два самостоятельных выхода** одной реконструкции:
`output` — densePointCloud.usda с visibility/SfMData, `outputMesh` —
`mesh.{outputMeshFileType}` (по умолчанию OBJ). Значение читать из узла, не
подменять mesh файлом dense.ply. Для обычной съёмки сохраняются оба:
дополнительный selector или Texturing для этого не нужны.
[Pinned Meshing][meshing] описывает также bounding box, maxInputPoints/maxPoints
и форматы obj/gltf/fbx/stl. Bounding box ограничивает область расчёта,
не делает пропущенные поверхности измеренными.

У файлов есть важная конвенция осей: native mesh export сохраняет
`(x, -y, -z)`, тогда как PLY из SfMData сохраняет координаты сцены.
Для совместного просмотра raw OBJ с облаком применяется единое преобразование
`R=diag(1,-1,-1)` к вершинам mesh; исходный файл сохраняется без изменения.
Это смена базиса, сохраняющая длины и углы, а не новый физический масштаб.
[Pinned Mesh::save](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/mesh/Mesh.cpp)
задаёт эту конвенцию. Для иного exporter/reader проверять фактические оси,
а не назначать новую ориентацию на глаз.

Плотное облако экспортируется штатным ConvertSfMFormat в PLY; raw OBJ читается
обычным mesh reader (например Open3D/CloudCompare). Выдача общего запуска,
точные пути, проверка и backup описаны в [runbook](runbook.md).
**Выполнено в #6:** плотное PLY обоих графов; наличие/чтение сохранённого
raw mesh и его координатная проверка учитываются отдельно в [Goal #8](goal-8.md).
Статическая проверка outputMesh не заменяет фактическое открытие файла.

## Фильтрация сетки

Исходный `Meshing.outputMesh` сохранять отдельно. В штатном графе
MeshFiltering.inputMesh связан с ним; `MeshFiltering.outputMesh` — новый файл.
Есть три разные операции:

| Операция | Штатная настройка и смысл |
|---|---|
| Оставить крупнейший связный фрагмент | keepLargestMeshOnly=true; может удалить нужную отдельную деталь |
| Удалить треугольники | filteringIterations/filteringSubset, filterLargeTrianglesFactor (0 отключает фильтр крупных треугольников), filterTrianglesRatio (0 отключает ratio-фильтр) |
| Сгладить вершины | smoothingIterations/smoothingSubset/smoothingLambda; smoothingIterations=0 отключает сглаживание. Значение по умолчанию **5**, поэтому default filtering уже меняет геометрию |

Для очистки без сглаживания явно выставить smoothingIterations=0; выбранные
параметры сохранить рядом с результатом. Сглаживание само по себе не улучшает
измеренную точность. Для важных краёв предпочитать raw либо обработку без
сглаживания; сокращение сетки нужно лишь при реальном лимите размера/просмотрщика.
Для этого есть отдельный bundled [MeshDecimate][decimate]; для задач по маскам/видимости —
[MeshMasking][meshmasking] и [MeshRemoveUnseenFaces][unseen]. Это вспомогательные
операции, не обязательные этапы; их новые прогоны не выполнялись.
`export-derived` поддерживает только MeshFiltering/Texturing. Для MeshDecimate
или другой native операции нужны отдельно сохранённое происхождение
(source/RUN/node/UID, параметры, файлы/SHA, преобразования), ручная выдача и её
собственная проверка геометрии/открытия. Это не новая поддержка обвязки и не
обязательный объём Goal #40; без такой необходимости остановиться на raw/filter.
Все настройки и формат выхода — [pinned MeshFiltering][filtering].

**Рецепт продолжения:** если нужные настройки уже сохранены, продолжить неизменный
проект до имени MeshFiltering. При смене настроек подготовить новый RUN с явным
reuse прежнего cache, сохранив original; конкретные команды — в
[runbook](runbook.md#продолжить-до-фильтрации-или-текстур). Завершённый RUN не редактировать.
Факт выполнения и сравнения производной учитывается в записи своего задания.

## Текстуры и экспорт

Выбирать для просмотра/передачи внешнего вида, когда доступны исходные фото,
intrinsics, плотная сцена с visibility и mesh. Штатный Texturing получает
Meshing.output (USDA с payloads), папку подготовленных undistorted изображений
по view ID из этого dense route и MeshFiltering.outputMesh. Простого PLY или
произвольной папки JPEG недостаточно. DepthMap EXR не являются прямым входом.
inputMesh можно явно связать с raw Meshing.outputMesh, если обработка не нужна;
это отдельная native edge-правка в новом проекте. Общий `nodes` JSON не заменяет
link edge, поэтому не обещает такое переключение. В первом пилоте штатная
MeshFiltering-ветка с smoothingIterations=0 сохраняет raw отдельно.

Основные настройки: textureSide, downscale, unwrapMethod (Basic/LSCM/ABF),
useUDIM, colorMapping.colorMappingFileType и outputMeshFileType.
В этих pins defaults — textureSide=8192, downscale=2, useUDIM=true,
colorMappingFileType=exr, outputMeshFileType=obj. Они отличаются от старых
примеров с PNG. Параметры и outputs — [pinned Texturing][texturing].
Эти defaults — свойства закреплённого descriptor, не настройки для любой сцены.
Для первого фотографического просмотра выбран кандидат PNG + sRGB с проверкой
конкретного получателя. Указать outputColorSpace явно; сохранить фактические
параметры и outputs в графе/receipt. Факт реального запуска и GUI отражает
[Goal #40](goal-40.md), а не наличие этого рецепта.

`textureSide` задаёт рабочий atlas; `downscale` уменьшает готовую карту, поэтому
не обещает такое же уменьшение пика RAM. Подберите разрешение по деталям исходных
изображений и бюджету. Basic допускает несколько атласов; имеющиеся UV могут
сохраниться без нового unwrap. Число карт выясняется по фактическому результату.
`fillHoles=false` оставляет явные пробелы цвета; true достраивает цвет, не геометрию.
`subdivisionTargetRatio=0` отключает subdivision. При включении новые вершины на
старой поверхности и дубли на UV seams увеличивают счётчик без новых измерений.
Texturing имеет CPU-путь: до полного расчёта проверить запуск закреплённого bundle,
лимиты/commandLine, RAM и время на выбранном Linux host. Source-контракт не
доказывает совместимость конкретной CPU-среды.

Передавать каталог целиком: OBJ + MTL + **все** texture_*.exr/png/...,
а также normal/height/displacement maps и другие файлы, на которые ссылается
материал, если они создавались. Сохранить относительные имена; открыть копию
из нового каталога и проверить материалы. Один OBJ не является комплектом
текстурированной модели. CopyFiles в базовых шаблонах публикует
Texturing.outputMesh/outputMaterial/outputTextures; для дополнительных карт
проверить фактические ссылки материала и включить их в backup явно.
Автоматический CopyFiles не является backup облака, raw mesh или кэша.
В [обсуждении #211](https://github.com/alicevision/Meshroom/issues/211#issuecomment-416184229)
разработчик fabiencastan объясняет связь unwrapMethod и нескольких атласов;
принудительное ожидание одного texture-файла неверно. Совместимость конкретного
читателя проверяется на всём комплекте, а не по одному успешному импорту OBJ.

При необходимости другого формата сначала выбрать поддержанный outputMeshFileType
в node; отдельный bundled [ConvertMesh][convertmesh] нужен только для конкретной
несовместимости читателя. STL не хранит фотографические текстуры.
[ConvertSfMFormat][convertsfm], ExportColoredPointCloud, ExportColmap,
ExportAlembic/ExportUSD — вспомогательные native интерфейсы обмена сценой,
а не замена проверки нужного выходного файла. Полные контракты —
[каталог descriptors][nodes].

## Продолжение штатного графа

Перед compute прочитать nodeType/имена из сохранённого project.mg. В базовых
Standard/Legacy шаблонах pins имена — Meshing_1, MeshFiltering_1, Texturing_1;
у двух сторон — суффикс _3. Для общего пути проект/кэш и подготовка Legacy
берутся из runbook. Продолжать неизменный граф; при новых параметрах создать
новый RUN штатным `prepare --cache`, сохранив прежний граф и settings.

```bash
# После подготовки/проверки общего пути, с тем же project.mg и cache:
"$MESHROOM_ROOT/meshroom_compute" "$RUN/project.mg" --cache "$RUN/cache" --toNode Meshing_1
"$MESHROOM_ROOT/meshroom_compute" "$RUN/project.mg" --cache "$RUN/cache" --toNode MeshFiltering_1
"$MESHROOM_ROOT/meshroom_compute" "$RUN/project.mg" --cache "$RUN/cache" --toNode Texturing_1
```

Это последовательные альтернативные глубины, а не требование запускать все три.
`--toNode` включает зависимости; `--node` требует уже готовые зависимости.
Не задавать forceCompute/forceStatus по умолчанию. Неизменные успешные стадии
переиспользуются при сохранных cache/status и совпадающих UID входов/настроек;
новые параметры меняют затронутые стадии. Проверять статус и фактические output
файлы до и после; SUCCESS без файла означает неполный кэш. Перенос одного
project.mg без кэша не переносит готовые вычисления.
При удалённых подготовленных изображениях Standard и сохранных upstream
использовать адресный `--node ExportImages_1 --forceCompute`, затем QA файлов;
не forced `--toNode` со всеми зависимостями. Пути originals внутри SfM должны
быть доступны; cache relocation их не переписывает. Подробный
[рецепт, производные и выдача](runbook.md#продолжить-до-фильтрации-или-текстур).
**Локально выполнено в #8:** native Meshroom core planner `dfsToProcess`
на частных копиях сохранённых графов, с восстановленными штатными downstream
узлами и неизменными upstream UID. Для Standard план до Meshing пуст, до
MeshFiltering содержит только MeshFiltering, до Texturing — filtering+texturing.
Для Legacy продолжение также включает PrepareDenseScene с неготовым статусом;
готовые SfM/DepthMap/Meshing в план пересчёта не входят. На Windows отсутствуют
Linux AV bindings: это проверка планирования с serialized CompatibilityNodes,
**не исполнение** AV, фильтрации или текстурирования. Подробные evidence —
в [Goal #8](goal-8.md). Штатный владелец планирования — [Meshroom graph.py][graph].

## Новый граф и обход PrepareDenseScene

В standard **нет PrepareDenseScene**. ExportImages получает исходный SfM из
SfMColorizing, целевые intrinsics — из IntrinsicsTransforming; DepthMap получает
эти целевые intrinsics и папку ExportImages. ExportImages использует
`avpar.DynamicViewsSize`, а прежний PrepareDenseScene —
`desc.DynamicNodeSize`. На 37 реальных кадрах Standard прошёл до dense без
PDS adapter; Legacy потребовал один явный whole-scene вызов adapter. Оба набора
EXR прошли QA, после последующего native compute их SHA сохранились.
Adapter остаётся для Legacy/fallback; его наличие не делает Legacy более точным.
[ExportImages.py](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ExportImages.py),
[PrepareDenseScene.py](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/PrepareDenseScene.py).

Для масок нужно явно передавать расширение: descriptor ExportImages по умолчанию
задаёт `png`, standard-шаблон переопределяет его на **`exr`**. Реализация переводит
нулевые пиксели внешней маски в alpha=0 и преобразует RGBA в целевые intrinsics.
Успешный exit не заменяет проверки полного набора читаемых EXR и alpha:
вызывающий цикл не проверяет возвращаемое значение `processImage`.
[Pinned реализация ExportImages](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_exportImages.cpp).

Выполненный Standard прогон также проверил конкретный unknown-exposure sentinel:
EV=-nan только при native Exposure=-1, partiallyDefined=false и evCorrection=false;
EVComp=1 и RGBA конечны. Это записано как неизвестная экспозиция, не разрешение
произвольных NaN. PDS projection metadata и ExportImages exposure metadata имеют
разные native контракты; их проверяет `check_dense_images.py`.

Оба графа дают Meshing.output в `densePointCloud.usda`; для существующего
геометрического этапа нужен штатный экспорт в PLY. Текстурирование для этого
не требуется. CopyFiles в этих шаблонах публикует текстурированные результаты,
поэтому сохранение плотного облака и его экспорта нужно указывать явно.
[Meshing.py](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/Meshing.py).

## Настройки, ресурсы и дополнения

Качество передаётся настройками: DepthMap.downscale допускает 1/2/4/8/16;
FeatureExtraction имеет describerPreset/describerQuality и maxThreads;
Meshing — maxInputPoints/maxPoints. Большее количество точек и меньшее
downscale сами по себе не подтверждают физическую точность.
[DepthMap.py](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/DepthMap.py),
[FeatureExtraction.py](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/FeatureExtraction.py).

Уровни CPU/RAM/GPU в descriptors не являются жёсткими лимитами. Штатный
AVCommandLineNode добавляет `--maxMemory`/`--maxCores`, если helper обнаружил
лимиты cgroup. **В закреплённом helper реализованы пути cgroup v1**
`memory.limit_in_bytes` и `cpuset.cpus`; автоматическое чтение cgroup v2
(`memory.max`, `cpu.max`) отсутствует. Поэтому на cgroup v2 нельзя считать
автоматическую передачу лимитов подтверждённой: действующие ограничения среды,
потоки и фактический commandLine проверяются при запуске по runbook.
[Владелец AV command line](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/meshroom/core/desc/node.py),
[cgroup helper](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/meshroom/core/cgroup.py).

`meshroom_batch --graphInput` присутствует, но пять рассмотренных
photogrammetry-шаблонов не объявляют именованных GraphIO inputs. Для них нужен
обычный ввод изображений и явные параметры узлов либо тонкая настройка графа.
[Pinned meshroom_batch](https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/bin/meshroom_batch).
Отдельный минимальный native GraphIO/CLI опыт scalar SfMTransform выполнен:
скаляр передан через именованный input и применён без задания полных XYZ меток.
Это проверка native интерфейса, не появление GraphIO inputs в базовых шаблонах.

Наличие шаблонов с ImageSegmentationBox/Sam3, MoGe или RoMa не означает
установки этих дополнений. В проверенном архиве нет соответствующих descriptors
и ML-весов. Предусмотренный отдельный
[mrSegmentation](https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/README.md)
опирается на RAM++, GroundingDINO и SAM; это дополнительная установка, которую
данный справочник не квалифицирует. До наблюдаемой проблемы фона используем
базовую обработку и при необходимости готовые маски.

**RoMa — резерв.** Возвращаемся к нему при конкретном провале штатного
сопоставления на резких перекрывающихся кадрах, после разбора исходников и
native diagnostic. Для запуска сначала нужны совместимые pinned plugin/API и
ML-зависимости, воспроизводимый вход и отдельные ресурсные пределы. Известны
расхождение API и отсутствие квалифицированного маршрута до плотной геометрии;
[разбор #9](reports/2026-11-22/meshroom-neural-addons.md#нейроматчинг-native-путь-и-границы)
сохраняет evidence. Установка/исправление RoMa в #15 не входят; новый эксперимент
потребует конкретного оставшегося недостатка или решения владельца.

## Остальные шаблоны комплекта

Всего в закреплённом архиве **27**, а не 27 дополнительных шаблонов.
Пять основных photogrammetry-шаблонов разобраны выше; оставшиеся 22 перечислены
полностью ниже. Ссылки ведут к точному штатному графу — исполняемому рецепту
авторов с входами/связями; nodeType и параметры раскрываются в
[descriptors][nodes]. Это **инвентарь без новых запусков**, а не набор
дополнительно поддерживаемых режимов обвязки. При отсутствии dedicated manual
не подменяем его догадкой о назначении узлов.

| Штатный шаблон / рецепт | Назначение | Связь с нашим доменом / предварительные требования |
|---|---|---|
| [photogrammetryDraft.mgt][draft] | Быстрый черновик по разреженной геометрии | Вспомогательный preview; нет DepthMap/DepthMapFilter, не эквивалент плотного MVS |
| [photogrammetryAndCameraTracking.mgt][photo-track] | Фотограмметрия плюс трекинг видеокамер | Смежная доставка камер/VFX; использует ImageSegmentationSam3, нужен соответствующий plugin/веса |
| [photogrammetryAndCameraTrackingLegacy.mgt][photo-track-legacy] | То же на Legacy SfM | Смежная доставка камер; ImageDetectionPrompt/ImageSegmentationBox требуют mrSegmentation |
| [cameraTracking.mgt][track] | Камеры видео с калибровкой | Камеры/VFX, не обязательный путь плотной модели; нужны калибровочные данные и Sam3 |
| [cameraTrackingWithoutCalibration.mgt][track-nocal] | Камеры видео без отдельной калибровки | Смежный режим камер с реконструкцией; Sam3 отсутствует в архиве |
| [cameraTrackingLegacy.mgt][track-legacy] | Камеры видео через Legacy SfM | Смежный режим; калибровка и mrSegmentation по графу |
| [cameraTrackingWithoutCalibrationLegacy.mgt][track-nocal-legacy] | Legacy камеры без отдельной калибровки | Смежный режим; mrSegmentation по графу |
| [cameraTrackingDepth.mgt][track-depth] | Трекинг с оценкой глубины | Вспомогательное monocular depth/track injection; MoGe и Sam3 требуют дополнений/весов |
| [cameraTrackingRoma.mgt][track-roma] | Камеры с нейросетевыми соответствиями | Смежный путь сопоставления; Roma* и Sam3 отсутствуют, нужна отдельная установка |
| [cameraTrackingLidarExperimental.mgt][track-lidar] | Связать камеры и LiDAR | Отдельный LiDAR/VFX-домен; survey/pose inputs, Sam3/VideoSam3; не осваивается в #8 |
| [cameraTrackingLidarWithMeshResection.mgt][track-resection] | Камеры относительно готовой сетки | Смежный mesh resection, не извлечение mesh из фото; нужен готовый mesh и Sam3 |
| [nodalCameraTracking.mgt][nodal] | Трекинг вращения камеры без перемещения | Камеры/VFX; не обещает глубину; калибровка и Sam3 по графу |
| [nodalCameraTrackingWithoutCalibration.mgt][nodal-nocal] | То же без отдельной калибровки | Смежный nodal режим; Sam3; не заменяет обход объекта |
| [distortionCalibration.mgt][distortion] | Калибровка дисторсии по шахматной доске | Полезная подготовка intrinsics; нужны кадры доски, не обязательна для обычного входа |
| [colorCalibration.mgt][color] | Коррекция цвета по цветовой мишени | Полезная подготовка цвета; нужен ColorChecker, не источник метрического масштаба |
| [rawImageConversion.mgt][raw] | Конвертация и обработка исходных изображений | Вспомогательный ввод RAW через ImageProcessing; проверять поддержку камеры и вывод |
| [hdrFusion.mgt][hdr] | Слияние экспозиционной серии в HDR | Вспомогательный imaging-домен; нужны согласованные экспозиционные серии |
| [panoramaHdr.mgt][panorama] | Панорама из экспозиционных серий | Отдельный panorama-домен, не плотная 3D-реконструкция |
| [panoramaFisheyeHdr.mgt][fisheye] | HDR панорама из fisheye | Отдельный panorama-домен с fisheye-входами |
| [photometricStereo.mgt][ps] | Нормали из разного освещения | Отдельная постановка съёмки: фиксированная камера, световая калибровка/сфера; не обычное видео |
| [multiViewPhotometricStereo.mgt][mvps] | Фотометрическое стерео с нескольких ракурсов | Смежная геометрия с отдельными требованиями к освещению и сферам; не запасной обычный MVS |
| [lidarMeshing.mgt][lidar] | Сетка из лазерных сканов E57 | Отдельный LiDAR-домен; E57 и scan metadata, не фотографии; не осваивается в #8 |

Для всех строк сначала проверить доступность node descriptors и конкретных
данных; таблица не утверждает установленность внешних ML-моделей.
Базовые camera/AV nodes присутствуют, дополнительные Sam3/MoGe/RoMa nodes — нет.
Менеджер плагинов входит в Meshroom, однако установка и совместимость нужного
плагина с закреплёнными pins требуют отдельной проверки перед расчётом.

[standard]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetry.mgt
[legacy]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryLegacy.mgt
[object]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryObject.mgt
[turntable]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryObjectTurntable.mgt
[twosides]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryObjectTwoSides.mgt
[batch]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/bin/meshroom_batch
[compute]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/bin/meshroom_compute
[graph]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/meshroom/core/graph.py
[nodes]: https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision
[keyframes]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/KeyframeSelection.py
[masking]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ImageMasking.py
[maskprocessing]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MaskProcessing.py
[maskeroding]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MaskEroding.py
[segmentation]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/README.md
[transform]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/SfMTransform.py
[meshing]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/Meshing.py
[filtering]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MeshFiltering.py
[decimate]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MeshDecimate.py
[meshmasking]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MeshMasking.py
[unseen]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/MeshRemoveUnseenFaces.py
[texturing]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/Texturing.py
[convertmesh]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ConvertMesh.py
[convertsfm]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ConvertSfMFormat.py
[draft]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryDraft.mgt
[photo-track]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryAndCameraTracking.mgt
[photo-track-legacy]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photogrammetryAndCameraTrackingLegacy.mgt
[track]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTracking.mgt
[track-nocal]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingWithoutCalibration.mgt
[track-legacy]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingLegacy.mgt
[track-nocal-legacy]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingWithoutCalibrationLegacy.mgt
[track-depth]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingDepth.mgt
[track-roma]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingRoma.mgt
[track-lidar]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingLidarExperimental.mgt
[track-resection]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingLidarWithMeshResection.mgt
[nodal]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/nodalCameraTracking.mgt
[nodal-nocal]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/nodalCameraTrackingWithoutCalibration.mgt
[distortion]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/distortionCalibration.mgt
[color]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/colorCalibration.mgt
[raw]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/rawImageConversion.mgt
[hdr]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/hdrFusion.mgt
[panorama]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/panoramaHdr.mgt
[fisheye]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/panoramaFisheyeHdr.mgt
[ps]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/photometricStereo.mgt
[mvps]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/multiViewPhotometricStereo.mgt
[lidar]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/lidarMeshing.mgt
