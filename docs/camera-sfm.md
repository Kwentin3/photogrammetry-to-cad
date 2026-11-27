# Камера и ранняя диагностика SfM

Эта памятка помогает выбрать одну обоснованную проверку до дорогого dense.
Основной маршрут и команды запуска — в [runbook](runbook.md); варианты графа —
в [описании режимов](meshroom-modes.md). Основание технических деталей ниже —
AliceVision `d012d05589b528dcf57a2a0c805c0a5709df8613`, закреплённый
в `configs/runtime-2026.json`. Фактический объём native-проверок и ограничения
фиксируются в [отчёте #35](reports/2026-11-26/camera-sfm.md).

## Сначала проверь фактические данные

Сохрани оригиналы и их manifest. По EXIF и изображению проверь объектив,
фокусное, разрешение, кроп/зум и обработку; затем сопоставь каждый файл с
`viewId` и `intrinsicId` из результата CameraInit. Название телефона само по себе
не означает одну калибровку для всех его объективов и режимов.

Сверь запрос с итоговым графом после `prepare`, затем с native-выходом CameraInit
и сценой после SfM: состав групп, размеры, `type`, `distortionType`, фокусное
с единицами, `principalPoint`, коэффициенты и блокировки. Значение в исходном
settings ещё не доказывает, что потребитель его применил. В pinned CameraInit
`initialize()` заново создаёт `viewpoints` и `intrinsics`; параметры внутри
`intrinsics` должны применяться после этой инициализации и проверяться чтением
результата. Модель камеры (`pinhole`, `equidistant`, `equirectangular`) и модель
дисторсии (`radialk3`, `brown`, `fisheye4` и другие) — разные поля;
`brown` не является верхним атрибутом узла. [CameraInit, поля и инициализация](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L72-L151),
[сброс и заполнение](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L503-L527).

Если фокусное вызывает сомнение, проверь источник sensor width в логе. При
найденной записи sensor DB и положительном физическом фокусном 35-мм эквивалент
не заменяет выбранную ширину сенсора. При отсутствии ширины native-код может
оценить её из EXIF physical/35-mm focal и отношения сторон. Такая инициализация
не доказывает физическую калибровку конкретного объектива; неизвестную ширину
не назначай по правдоподобию. [ImageInfo.cpp](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/sfmData/ImageInfo.cpp#L201-L319).

## Симптом → проверка → действие → остановка

| Симптом | Что проверить в native-данных | Обоснованный рычаг | Когда остановиться |
|---|---|---|---|
| Несколько объективов/режимов попали в одну группу или одинаковые кадры неожиданно разделились | EXIF, размеры/кроп, файл → `intrinsicId`, параметры каждой группы; различия должны иметь объяснение | Исправить подтверждённую группировку в CameraInit или подать подходящую native-калибровку. Сверить итоговые группы | Не объединять группы только ради регистрации камер и не дробить каждый кадр ради свободы оптимизации; при неизвестном режиме оставить неопределённость |
| Плоскости систематически выгнуты, фокусное заметно меняется после SfM | Сравнить CameraInit и SfM по каждой группе, наблюдения у краёв кадра, совпадения, независимые контрольные размеры. Вид изгиба сам по себе не устанавливает причину | Проверить модель/источник фокусного; при обосновании испытать одну другую модель или соответствующую калибровку на том же материале | Если эффект не подтверждён сравнением геометрии/наблюдений, не объявлять выбранную модель точнее; не подбирать её под контрольные длины |
| Зарегистрирована только часть кадров, разрыв между зонами | Имена выпавших кадров, их резкость/перекрытие/параллакс; список пар ImageMatching, наличие результатов FeatureMatching и связей между зонами; фактические `describerTypes` | Если нужных пар нет — адресно изменить `ImageMatching.method`/число соседей либо проверить Exhaustive на ограниченном наборе. Для последовательности есть Sequential и SequentialAndVocabularyTree | Когда пары уже проверялись, повторный поиск пар не добавляет наблюдений. Не запускать dense, если важная зона не связана или неверно расположена |
| Пары выбраны, но геометрически проверенных совпадений мало | Просмотреть проблемную пару и её features/matches, маски, смаз, повторяющийся рисунок, actual describer types на всём пути | При достаточном изображении проверить одну настройку FeatureExtraction/FeatureMatching; `guidedMatching` использует уже найденную геометрическую модель | Не отключать геометрическую проверку ради счётчика. Если нет различимых общих деталей/переноса камеры, нужна конкретная досъёмка этого разрыва |
| Все камеры зарегистрированы, но комната двоится или неполна | Настоящее sparse-облако и камеры с исходными фото; покрытие стен, пола, потолка, углов, проёмов; локальные наблюдения и результаты оптимизации | Проверить ошибочные связи/калибровку; продолжить dense только для ясно связанной и полезной геометрии с перечисленными пропусками | Регистрация всех камер не равна точности, заполнению скрытых областей или готовности к обмерам. Не исправлять наблюдения сглаживанием mesh |

ImageMatching выбирает пары; FeatureMatching проверяет соответствия. У pinned
ImageMatching порог перехода VocabularyTree к перебору задаёт `minNbImages`;
универсального правила «после 100 кадров» нет. Exhaustive повышает число
проверяемых пар, но не создаёт параллакс или текстуру. [ImageMatching](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ImageMatching.py#L56-L124),
[геометрическая проверка и guidedMatching](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/FeatureMatching.py#L85-L178).

Ранний маршрут уже существует: native sparse и его экспорт точек/камер до MVS
описаны в runbook и [реальном отчёте комнаты](reports/2026-11-26/room-photos.md).
Для обычных tracks, наблюдений и residuals используй полную native SfM-сцену,
логи и соответствующие features/matches. Проектный `sparse-before.json`
сохраняет views/poses/intrinsics, но его `structure` экспортируется для CCTag:
по нему нельзя считать общее число обычных tracks или их длины.
Доля камер и единичная малая ошибка репроекции не заменяют этот осмотр.

## Готовая калибровка и свобода оптимизации

Если калибровка получена отдельно, штатный узел `ApplyCalibration` или его CLI
принимает native SfMData; нестандартный граф можно сохранить как `.mg` и
выполнить штатным `meshroom_batch`/`meshroom_compute`. Общий manifest фотографий
для этого не нужно превращать в загрузчик произвольных сцен.

```bash
"$ALICEVISION_ROOT/bin/aliceVision_applyCalibration" \
  --input "$INPUT_SFM" --calibration "$CALIBRATION_SFM" \
  --output "$CALIBRATED_SFM" --useJson false
```

Это отдельный выход, который нужно подключить к следующему native-узлу графа.
В pinned CLI поддержаны калибровка с одним intrinsic либо многокамерная с одним
rig; калибровка с одним intrinsic применяется к входным intrinsics, поэтому её
нельзя без проверки переносить на смешанные объективы. Учитываются режимы
`CALIBRATED`, размеры и совместимость aspect ratio. Пустой calibration лишь
копирует сцену. Проверь лог и численные параметры выхода: успех команды сам по
себе не доказывает перенос нужной калибровки. [ApplyCalibration node](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/ApplyCalibration.py#L8-L57),
[native перенос и проверки](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_applyCalibration.cpp#L32-L228),
[CLI](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_applyCalibration.cpp#L390-L469).

Обычный выход CameraInit с `estimated`/`none` не является готовой калибровкой:
native ApplyCalibration пропускает группу, если ни intrinsic, ни distortion
не помечены `CALIBRATED`. Такая проба на закреплённом runtime вернула 0 и
сохранила прежнюю модель. Не меняй этот статус ради успешной команды — сначала
установи действительный источник калибровки и проверь её фактический перенос.

Свободная оптимизация вправе уточнять начальную EXIF-оценку. Изменение фокусного
не является само по себе потерей настройки. `locked` фиксирует весь intrinsic;
`scaleLocked`, `offsetLocked`, `distortionLocked` и `pixelRatioLocked` задают
отдельные ограничения. Перенос ApplyCalibration не заменяет осознанный выбор
блокировок: focal после переноса получает режим `ESTIMATED`, distortion —
`CALIBRATED`. Зафиксированная неверная калибровка тоже может дать плохую форму.
Сохраняй начальные и итоговые значения, объяснение locks и независимую проверку;
не обещай улучшения точности только от фиксации. [Флаги CameraInit](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/aliceVision/CameraInit.py#L80-L126),
[Bundle Adjustment, constant/free и focal prior](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/sfm/bundle/BundleAdjustmentCeres.cpp#L399-L451).

## Поворот сцены и физический масштаб

Пример native-поворота на 90° вокруг Z без изменения расстояний:

```bash
"$ALICEVISION_ROOT/bin/aliceVision_sfmTransform" \
  --input "$INPUT_SFM" --output "$ORIENTED_SFM" \
  --method manual --manualTransform "0,0,0,0,0,90,1" \
  --scale 1 --applyScale false --applyRotation true --applyTranslation false
```

`manualTransform` задаёт `tx,ty,tz,rx,ry,rz,s`; углы в градусах, порядок ZXY.
Это пример выбора осей, не определение вертикали комнаты. Перед принятием
проверь реальные координаты одних и тех же точек/центров камер до и после:
поворот должен измениться, евклидовы расстояния — сохраниться с численной
погрешностью. Сохрани actual Scale/Rotation/Translate из лога и идентичность
сцен. Один `applyScale=false` в settings такой проверки не заменяет.
[Разбор manual](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_sfmTransform.cpp#L176-L220),
[применение флагов и вывод преобразования](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_sfmTransform.cpp#L777-L814).

`auto_from_cameras` вычисляет также нормирующий масштаб. `align_ground`
вычисляет перенос уровня земли, ожидая уже ориентированную сцену; при
`applyTranslation=false` этот перенос отключён. Намеренное масштабирование
остаётся штатной отдельной операцией с явным назначением и подтверждённой
базой. Ориентация не устанавливает физические единицы и не даёт метрологической
точности. Преобразование SfM не поворачивает автоматически уже выданные PLY/OBJ:
применяй его до последующих стадий графа либо согласованно ко всей выдаче.
[auto_from_cameras](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/sfm/utils/alignment.cpp#L1063-L1114),
[align_ground](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_sfmTransform.cpp#L770-L804).
