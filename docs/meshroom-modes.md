# Режимы закреплённой Meshroom 2026

Это справочник возможностей для выбора режима. Команды подготовки, запуска,
продолжения и сохранения результата находятся в [runbook](runbook.md).
Состояние текущей работы — в [Goal #6](goal-6.md).

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

## Выбор по съёмке

| Съёмка или задача | Штатный путь и требования | Статус и решение сейчас |
|---|---|---|
| Неподвижный объект или сцена | `photogrammetry.mgt`: новый модульный SfM, IntrinsicsTransforming и ExportImages, затем DepthMap → DepthMapFilter → Meshing. Нужны перекрывающиеся резкие кадры с различимыми деталями поверхности | **Базовый путь проверен на 37 реальных кадрах: 37/37 камер, 121291 конечная точка.** Выбран для обычного фото/видео: сопоставимый наблюдаемый охват без PDS adapter; физическая точность не измерялась |
| Тот же материал через Legacy | `photogrammetryLegacy.mgt`: StructureFromMotion → PrepareDenseScene → плотная реконструкция | **Проверен на тех же кадрах: 37/37 камер, 121513 конечных точек.** Запасной путь и основа для CCTag; один явный whole-scene PDS adapter сохранён, затем native compute и неизменность EXR подтверждены |
| Готовые маски объекта | FeatureExtraction принимает masksFolder; Legacy PrepareDenseScene и новый ExportImages — masksFolders. Маски должны соответствовать исходным кадрам по размеру и имени либо view UID | **Доступно в архиве; изучено.** Передавать маски отдельной настройкой. Для поворотного стола исключать фон уже при выделении признаков |
| Простой однотонный фон | ImageMasking: HSV либо AutoGrayscaleThreshold; есть инверсия и изменение границ. MaskProcessing/MaskEroding обрабатывают готовые маски | **Доступно в архиве; изучено.** Возможный вариант без ML при подходящем фоне; качество маски проверять на кадрах |
| Автоматическое отделение обычного объекта | `photogrammetryObject.mgt` использует ImageDetectionPrompt → ImageSegmentationBox; маска применяется перед плотной стадией | **Шаблон доступен в архиве; изучено.** Эти segmentation nodes и веса в архив не входят. Дополнение не включаем в базовую установку без конкретной необходимости |
| Поворотный стол | `photogrammetryObjectTurntable.mgt` добавляет segmentation mask в FeatureExtraction до SfM. Жёсткий объект вращается, неподвижный фон должен исключаться из признаков | **Шаблон доступен в архиве; изучено.** Требует отсутствующего segmentation plugin либо явной настройки уже готовых масок; фактический прогон не выполнен |
| Объект с переворотом, две стороны | `photogrammetryObjectTwoSides.mgt`: отдельные съёмки/SfM, признаки объекта под масками, сопоставление сторон, SfMMerge `from_landmarks`, повторная триангуляция. Нужны общие видимые участки самого объекта | **Шаблон доступен в архиве; изучено.** Маски/дополнение и отдельный прогон обязательны перед объявлением режима проверенным |
| Реальное видео | KeyframeSelection выбирает кадры; дальше используется выбранный фотограмметрический граф. Требуются резкость, перекрытие и изменение точки наблюдения | **Regular отбор и реконструкция проверены:** настоящий Objectron MOV → 37 кадров → плотное PLY обоими графами. Source SHA/native views/точные файлы связаны manifest; smart selection отдельно не запускался |
| Метки и известный размер | Есть CCTag features и SfMTransform. Неизвестный масштаб сохраняется неизвестным; координаты меток и измеренное расстояние между двумя метками — разные входные контракты | **CCTag сохраняется в Legacy.** Native scalar scale проверен на историческом synthetic SfM, не на новой измеренной рулеткой базе. Standard CCTag ID encoding не квалифицирован, общий adapter отвергает этот путь. Marker_coords зарезервирован; исторический native XYZ-рецепт отдельный |

Шаблоны лежат в `aliceVision/share/meshroom/` внутри архива;
[точные исходники этих шаблонов и AV nodes](https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom)
закреплены тем же revision.

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
