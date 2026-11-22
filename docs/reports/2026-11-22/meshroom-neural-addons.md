# Опциональные маски и нейроматчинг: решение для Meshroom harness

Исследование [issue #9](https://github.com/Kwentin3/photogrammetry-to-cad/issues/9),
проверено 22 ноября 2026. **Рекомендация, не реализованная интеграция.**
GPU, зависимости и веса не устанавливались; расходы $0. Код не менялся.
База — [runtime-2026.json](../../../configs/runtime-2026.json), Meshroom
`b12ea889…`, AliceVision `d012d055…`, Python3.11, Ubuntu24.04/CUDA12.8.
Harness и результаты #8 изучены по [снимку f5b7984][harness8], независимо от
того, влит ли PR #10. CAD, 3DGS, генеративные модели и нейроглубина вне задачи.

## Что выбрать

| Задача | Первое решение | Резерв и условие перехода |
|---|---|---|
| Автомаски по тексту | **B: SAM2.1-small + локальный HF GroundingDINO-tiny → PNG**, отдельное ML-окружение и штатный вход masksFolder | **A: native mrSegmentation, RAM++ → GroundingDINO → SAM1**, если на конкретном материале обнаружится ограничение B или потребуется встроенный producer-граф |
| Нейросопоставление | **В резерве: native mrRomatch + совместимый авторский fork RoMaV2**, после подтверждённой проблемы DSPSIFT на реальной съёмке | LightGlue: только при конкретном недостатке native пути; готового Meshroom bridge не найдено |
| Базовая съёмка | Прежние Standard/Legacy + DSPSIFT | Ничего не устанавливать ради наличия опции |

После [внешнего ревью][review-priority] первым выбираем **B на обычной неподвижной
сцене**. Отдельный генератор PNG использует предусмотренный вход Meshroom и не
зависит от pyalicevision в ML-окружении. Тонкий batch/output адаптер оправдан этой
границей: модели можно заменить без пересборки Meshroom. Веса B занимают меньше
места; преимущество по VRAM, времени и качеству масок ещё предстоит измерить.
Native A остаётся резервом; фактура обоих путей ниже сохранена.
SAM3 сейчас не выбираем: есть конкретные ABI/установочные ограничения. Meshroom
под другой Python ради масок не пересобираем; будущая внешняя модель использует
своё окружение и тот же PNG-контракт. Для RoMa сохраняем native архитектуру в
резерве, **не объявляя её готовой**: нужны реальная проблема DSPSIFT, согласованные
pins/API и уточнение лицензирования, затем отдельный smoke.

Маски не добавляют текстуру металлу, а neural matching не создаёт достоверных
соответствий на невидимой, совершенно однотонной или отражающей поверхности.
Сначала исключить смаз, недостаток параллакса/перекрытия, неверный объектив и
ошибочные маски; при необходимости изменить съёмку/добавить допустимую текстуру.

## Маски: что действительно есть

**A, pin mrSegmentation `66866d139c…`.** В закреплённых Object/Turntable/TwoSides
стоят `ImageDetectionPrompt → ImageSegmentationBox`: это **SAM1 ViT-H**, не SAM2
или SAM3. Object маскирует плотную стадию; Turntable — признаки и MVS. TwoSides
имеет две группы/ветви, маскированные и немаскированные признаки и native merge;
одна папка масок не заменяет его согласование сторон. [Шаблоны][templates],
[детектор][detect], [Box][box].

Цель задаётся `prompt`, `synonyms`, `forceDetection`, `thresholdDetection`;
`bboxFolder` принимает native JSON, точки Box — через Nuke `.nk`, а не произвольный
points JSON. `forceDetection=true` **не исключает RAM**: конструктор загружает
RAM и DINO. Box предлагает `extensionOut=png`, `keepFilename=true` для stem либо
false для viewId, `maskInvert=false` для белого объекта. Внешний prompt остаётся
данными задания; пути/порог/модель не зашиваются в код под объект.

Install использует torch2.5.1/cu124, torchvision0.20.*, SAM1, groundingdino-py0.4.0
и неприкреплённые Git-зависимости. Это **не готовый lock для нашей ноды**:
нужны отдельные pins, совместимый cp311 pyalicevision и проверка CUDA/torch.
CUDA12.8 образ не требует буквально wheel cu128 и сам не доказывает совместимость.
Native GroundingDINO может потребовать сборки CUDA operator: подготовить совместимые
артефакты до аренды, а не компилировать/отлаживать их на оплачиваемой GPU.
[Установка][seginstall]; [issue #30][segissue] показывает проблему выбора Python
в другом, 2025.1 окружении — это повод проверить interpreter, не доказательство
ошибки нашего pin.

**B, SAM2.1-small + HF detector.** SAM2 принимает bbox/positive-negative points,
имеет automatic proposals, но сам не выбирает объект по тексту. Для текста нужен
отдельный GroundingDINO; выбран локальный Transformers/HF путь без облачного API.
Он не требует pyalicevision в ML-окружении. SAM2: Python≥3.10, torch≥2.5.1,
torchvision≥0.20.1; optional CUDA postprocessing имеет описанный upstream fallback.
Исходный demo не является готовым Meshroom batch-exporter: ещё нужны цикл по
manifest, вывод lossless PNG, восстановление исходной геометрии и binding файлов.
[SAM2][sam2], [Grounded-SAM2 HF demo][gsam].

HF-путь убирает зависимость от `groundingdino-py`, однако SAM2 по умолчанию
пытается собрать собственное CUDA-расширение. Штатный `SAM2_BUILD_CUDA=0`
позволяет его отключить; тогда пропускается удаление мелких дыр и пятен в маске.
Выбор фиксировать в настройках и проверять на preview, особенно для тонких
элементов и отверстий. Это описано в [инструкции SAM2][sam2-install]. Общий вход
масок есть у Standard и Legacy; успешный ML-прогон и полезность для обоих графов
пока не подтверждены.

**SAM3 отдельно.** Его descriptor уже есть в mrSegmentation, но старые INSTALL/
requirements его не устанавливают. SAM3 требует Python≥3.12, torch≥2.7/CUDA≥12.6;
сам descriptor напрямую импортирует бинарный pyalicevision, закреплённый как cp311.
Просто выбрать другой checkpoint или venv недостаточно. Плюс HF-доступ к весам
требует одобрения/аутентификации, лицензия собственная SAM License. Нужен отдельный
совместимый runtime/provider, сейчас его не проектируем. [Descriptor][sam3node],
[требования и доступ][sam3].

### Контракт native маски и проверка до MVS

Использовать оригинальные кадры после штатного отбора, без повторного неучтённого
resize/EXIF-поворота. Маска: одноканальный PNG, 0=исключить, 255=оставить;
lossless, точные **W и H** и ориентация исходного native изображения. Возврат из
model resize/padding — явно в исходные пиксели, categorical nearest-neighbour.
Native lookup: `<viewId>.png` прежде `<source_stem>.png`. Для stem нужны уникальные
имена; viewId между двумя CameraInit нельзя считать одинаковым без проверки.

FeatureExtraction читает `masksFolder/maskExtension/maskInvert`; ExportImages и
PrepareDenseScene — `masksFolders/maskExtension`, zero→alpha0. У dense нельзя
надеяться на maskInvert. Legacy сохраняет EXR/alpha/metadata. Missing mask может
означать продолжение **без** фильтрации, а dense проверяет площадь W×H, не обе
размерности. Поэтому существующий строгий preflight harness сохраняем.
[FeatureExtractor][fe], [ExportImages][ei], [PDS][pds].

До SfM/MVS предложен маленький `mask-diagnostics.json`, без сервиса качества:

- На каждый кадр: source/view ID и SHA, имя/размеры/ориентация маски, decode,
  mask SHA, уникальные значения, `keep_fraction`, zero/full flags, missing/
  ambiguous/extra matches. Общий binding — input manifest, native graph, prompt/
  настройки, plugin/model SHA и фактические Python/torch/CUDA версии.
- Missing, unreadable, wrong W/H и неоднозначность блокируют расчёт. Неожиданная
  чёрная/белая маска требует разбора: объект может отсутствовать или занять весь
  кадр. Нет универсального порога площади «годно». Исключение кадра — явное
  решение с новым manifest, не скрытое пропускание.
- Preview 4–8 overlays: начало/середина/конец, min/max площади и подозрительные
  кадры. Проверить тот же объект, тонкие края, отверстия и фон. Имена/W/H сами
  не доказывают правильную семантику. Только после этого запускать MVS.

Для turntable фон исключается **до признаков**, `masks.features=false` не решает
его SfM. Для масштаба CCTag должны сохраняться в нужных масках/наблюдениях;
на вращающемся объекте неподвижные фоновые метки не задают его систему.
Маски можно сохранить для следующих этапов вместе с камерами/manifest, но это
не готовые 3D-метки деталей: нужны проекция и учёт перекрытий, вне этой issue.

## Нейроматчинг: native путь и границы

Актуальный официальный репозиторий — **mrRomatch**, pin `e3c2e0d…`, а не
предполагаемый старый mrRoma. `RomaPrepare → RomaMatcher → MatchMasking →
RomaSampler/RomaReducer` подают native регионы/соответствия в геометрическую
фильтрацию, TracksBuilding и модульный SfM. В pinned `cameraTrackingRoma.mgt`
нет MoGe, но есть вспомогательные SAM3/keyframes/calibration и **нет MVS**.
Для пилота нужен малый native `.mgt` с Roma-подграфом и существующей классической
dense-цепочкой; не включать весь cameraTracking или MoGe лишь ради RoMa.
Это будущая композиция, не уже поставленный профиль. [Плагин][roma], [шаблон][romagt].

`FeatureExtraction.describerTypes=["roma"]` не включает inference:
[ImageDescriber_Roma][romadesc] умеет читать подготовленные регионы, а describe
не реализован. Standard модульный SfM показан в native шаблоне. Legacy интерфейс
feature/match folders существует, но совместимость RoMa с ним и объединение
CCTag3 не проверены. Новые ROMA matches не являются ID меток или физической шкалой.

Найдено конкретное API-расхождение: plugin передаёт `Descriptor.Cfg.module_path`
и `RoMaV2.Cfg.weights`, отсутствующие в upstream/main `95c9968…`. Совместимые поля
есть в **авторском fork dev/localModels `b780da6…`**: выбираем этот существующий
pin, не наш патч ядра. Задать `ROMATCH_MODELS_PATH` с `romav2.0.1.pt` и DINOv3
source `adc2544…`; иначе есть fallback на старый URL весов. По constructor пути
отдельный DINO checkpoint не загружается: pretrained=false, затем полный RoMa
state_dict. Это source inference; offline-доступы/ключи проверить smoke.
[romaCore][romacore], [совместимый fork][romafork].

В snapshot нет dependency lock/pyproject/LICENSE плагина и его записи в
[registry `e149697c…`][registry]: команда `meshroom_plugins install mrRoma` не обоснована. Использовать
native plugin-folder/venv после разрешения этих вопросов. Python≥3.10 позволяет
3.11 формально, но torch без pin, torchvision≥0.23, fused-local-corr, pyalicevision и ABI
нуждаются в проверке. Отсутствующую лицензию нельзя унаследовать от Meshroom.

RoMa prepare предлагает turbo320/fast512/base640/precise800→1280; выше разрешение —
больше память/стоимость. Автор оценивает RAM-кэш precise примерно в 25MB/кадр
([RomaMatcher][romamatcher]); это features/images, не вся память процесса.
Оценка GPU-кэша в коде тоже не верхний предел всего VRAM;
torch.compile добавляет холодный старт, sampler создаёт ProcessPoolExecutor.
Для первого smoke ограничить пары/CPU/RAM, не запускать неограниченное N².
Owner тест трёх кадров в [PR #7 плагина][romapr] не равен реальному полному SfM/MVS.
Есть конкретные отчёты о [16GB OOM][romaoom], [росте памяти][romaleak] и
[CUDA/driver mismatch][romacuda]; это риски проверки, не доказательство сбоя здесь.

**LightGlue — sparse matcher**, ему нужны ключевые точки и descriptors
(SIFT/SuperPoint/DISK/ALIKED). В pinned комплекте/registry готовый native bridge
не найден. Понадобится адаптация AV feature IDs, pixel centre/corner convention,
нормализации/типов descriptors и match indices. Это больше собственной логики,
поэтому не первый путь. Нагрузка/память matcher зависят от числа keypoints и
adaptive pruning; image resize принадлежит extractor. Бенчмарк авторов RTX3080:
150FPS при 1024 и 50FPS при 4096 keypoints — только matcher, не извлечение
признаков, подготовка, SfM или наш материал. [LightGlue][lg].

**Триггер агента:** потерянные камеры/компоненты или нужная поверхность по просмотру
после проверки съёмки и масок. `registered_fraction` — сигнал, не произвольный
quality threshold. Сравнивать те же manifest/маски/pair budget: IDs камер,
геометрические inliers, пространственный охват и длины tracks, распределение
reprojection residuals и объект на нескольких видах. Больше matches/камер не
доказывает точность; плохую геометрию остановить до MVS. Базовый config и cache
сохраняются отдельно для отката.

## Лицензии, объём и подготовка

Размеры ниже — **HEAD/официальная metadata**, без скачивания тел. Это веса,
не размер Python/CUDA окружения. Альтернативные форматы одного checkpoint
не суммируются. Размер файла не равен необходимой VRAM.

| Путь / артефакты | Байты | Лицензия / ограничение |
|---|---:|---|
| A: SAM1 ViT-H + DINO SwinT + RAM++ | 2 564 550 879 + 693 997 677 + 3 010 210 801 = **6 268 759 357** | [Plugin code MPL2][seglicenses]; [SAM1 code/weights][sam1license] и [RAM++ card][w-ram] Apache2; [DINO code Apache2][dinolicense], отдельной лицензии release checkpoint не найдено |
| B: SAM2.1-small + HF DINO-tiny safetensors | 184 416 285 + 689 359 096 = **873 775 381** | [SAM2 code/weights Apache2][samlicenses], optional cc_torch BSD3; [demo][gsamlicense]/[DINO][w-hfdino] Apache2, зависимости отдельно |
| SAM2.1-large вместо small | 898 083 611 | Та же лицензия SAM2; не нужен первому пилоту |
| SAM3 .pt / альтернативный safetensors | 3 450 062 241 / 3 439 938 512 | Custom SAM License, gate HF; не Apache и не два обязательных файла [C][sam3license] |
| RoMaV2 v2.0.1 checkpoint | **1 095 883 548** | [Code MIT][romacodelicense] кроме [DINOv3 custom terms][dinolicense3]. Не называть весь checkpoint MIT: [вопрос автора #52][romalicense] остаётся открытым |
| LightGlue | Не загружается на этом этапе | Code + matcher weights Apache2; лицензии выбранного extractor/его весов проверять отдельно, особенно SuperPoint [LightGlue][lg] |

Точные ссылки артефактов: [SAM1][w-sam1], [DINO release][w-dino], [RAM++][w-ram],
[SAM2-small][w-sam2s], [SAM2-large][w-sam2l], [HF DINO-tiny][w-hfdino],
[SAM3 metadata][w-sam3], [RoMa release][w-roma]. RoMa SHA256:
`1557dec0d21b62366465f7ff4d5fdf228cc695d0582e196ad2b80e05230828b7`.
Для остальных файлов в будущем получить/проверить SHA до использования;
HF commit pin/размер сами по себе checksum тела не заменяют.

При 100Mbit/s нижняя граница только весов A — 8.36мин, B — 1.17мин;
tokenizer, torch/CUDA зависимости на несколько GB, установка и проверка сверху.
**Плановые оценки, не измерение:** A15–40мин, B10–30мин первой подготовки на уже
совместимой ноде; неизвестная сеть/сборка может выйти за них. SAM3 gate не имеет
ограниченного времени ожидания. VRAM/latency на нашей ноде пока не измерены ни
для A/B, ни для RoMa/LightGlue; публикационные FPS не подставлять в бюджет Vast.
Для пилота разумно планировать 24GB GPU и измерить peak, не объявлять это минимумом.

## Минимальная агентная упаковка — предложение

Ядро и base bootstrap не меняются. Для B генератор масок запускается в отдельном
ML-окружении и получает manifest, цель выделения и настройки. Его выход — PNG
и диагностика; Meshroom принимает готовую папку через существующий контракт.
Новый registry, общий provider API или планировщик для этого не нужны.

Для резервных A/RoMa native [plugin-folder/venv][plugins] уже изолирует Python-node
subprocess; pins и `MESHROOM_PLUGINS_PATH` включаются только в выбранном запуске.
`requirements` metadata — описание, не проверка GPU. Provider наследует
PATH/PYTHONPATH/LD_LIBRARY_PATH, поэтому это не sandbox и не гарантия ABI: перед
inference проверить реальный Python, torch.cuda, pyalicevision и пути библиотек.
[Pinned env][env], [исполнение node][node].

Для первой интеграции масок **новых полей основной схеме не нужно**. Генератор
B выполняется до base prepare, его PNG передаются существующим полям:

```json
{
  "masks": {
    "folder": "../segmentation-run/masks",
    "extension": "png",
    "features": true,
    "invert": false
  }
}
```

Это фрагмент существующего reconstruction config, не отдельный запускаемый файл.
`features=true` нужен столу; обычной сцене выбирается по задаче. Для B prompt,
пороги, модель и pins задаются параметрами отдельного шага и сохраняются вместе
с его диагностикой; имя объекта не должно быть зашито в исходниках.

Для резервного A остаются native attrs
`ImageDetectionPrompt_1.prompt/synonyms/thresholdDetection`, Box —
`extensionOut/keepFilename/maskInvert`, в сохранённом `.mgt` или через native
`--paramOverrides`. Эти настройки относятся к producer-графу, а не к Standard,
где таких узлов нет.

Для квалифицированного RoMa-профиля в следующем Goal допустим **один optional
`template` path** к сохранённому native `.mgt`, существующие `nodes` для его
настроек и прежний config для fallback. Сейчас поле не реализовано, профиль ещё
не поставлен; ни `pipeline=roma`, ни один describer switch пока не готовый режим.
Не вводить registry провайдеров, новый job DSL или второй planner. До квалификации
управлять native графом/CLI по явному рецепту, не обещать автоматический выбор.

Диагностика дополняет существующие preflight/report: binding source/model/plugin
pins → реальные masks/matches, preview и измеренные времена/память. Смена весов
по прежнему пути требует нового producer RUN/cache и сравнения SHA, а не доверия
одному SUCCESS. Отсутствующий явно выбранный плагин — понятная ошибка;
отключённая опция вообще не импортирует torch и не меняет базовый bootstrap.

## Следующий короткий проверочный Goal

1. **Начать с B: SAM2.1-small + HF GroundingDINO-tiny → PNG.** Взять 12–16
   неизменённых кадров реального Objectron cereal_box/batch-1/1 из #6: материал
   уже сохранён, объект и фон понятны. Оба новых сравнения делают на этом же
   subset/resolution: DSPSIFT без масок и DSPSIFT с внешними автомасками через
   штатный masksFolder. Это тест стыка/отсечения пола,
   не доказательство turntable или низкотекстурного matching (у #6 уже 37/37 камер).
2. До аренды зафиксировать dependency/model pins и доступы, сохранить артефакты
   владельцу. Большие загрузки aria2/rclone многопоточно, с resume/скоростью/SHA.
   На GPU сначала **один кадр**: ML-окружение/CUDA, prompt, PNG и overlay;
   затем все маски/диагностика; только после содержательной проверки — SfM/MVS.
3. Сравнить камеры и требуемый участок, leakage фона, края/пропуски mesh,
   ручные поправки. Записать отдельно setup/inference/SfM/MVS, peak RAM/VRAM,
   transfer и деньги; сохранить cloud/mesh/графы/receipts до удаления ноды.
4. Предложенный предел будущего пилота: **до 2h и $5 всего** с диском/трафиком,
   например ставка ≤$0.60/h даёт ≤$1.20 compute. Это не текущая котировка Vast
   и не разрешение на аренду: конкретный offer/все charges и допуск сверить
   отдельно. Прерывать по deadline/ресурсам/невозможности корректной маски, а не
   расходовать остаток на подбор установок. При конкретном недостатке B отдельно
   решить, поможет ли A; обе реализации в один пилот не включать.
5. Turntable/TwoSides проверять позднее на настоящей соответствующей съёмке.
   RoMa начать отдельным 3-view/ограниченным pair smoke, затем 12–20 реальных
   кадров с наблюдаемым срывом DSPSIFT; такой материал ещё нужен. Проверить
   API/model/license/offline loads, native format/IDs и геометрию до MVS.
   Не использовать спокойный Objectron baseline как доказательство улучшения
   на гладком металле. License/API вопросы из этого отчёта — условия этого этапа.

**Подтверждено сейчас:** состав/контракты/pins по исходникам, конкретные API/ABI
расхождения, metadata весов и лицензионные документы. **Не подтверждено:** Linux
установка выбранных ML env, их VRAM/скорость, inference и полезность для 3D,
выполнение advanced графов или заявленных будущих схем. Исследование закончено
решением и проверяемым планом; реализация остаётся отдельным заданием.

[harness8]: https://github.com/Kwentin3/photogrammetry-to-cad/tree/f5b7984c09165b34ed986492938f3cc9a169636b
[templates]: https://github.com/alicevision/AliceVision/tree/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom
[detect]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/meshroom/rds/ImageDetectionPrompt.py
[box]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/meshroom/rds/ImageSegmentationBox.py
[seginstall]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/INSTALL.md
[segissue]: https://github.com/meshroomHub/mrSegmentation/issues/30
[sam2]: https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/README.md
[gsam]: https://github.com/IDEA-Research/Grounded-SAM-2/blob/b7a9c29f196edff0eb54dbe14588d7ae5e3dde28/grounded_sam2_hf_model_demo.py
[sam3node]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/meshroom/sam3/ImageSegmentationSam3.py
[sam3]: https://github.com/facebookresearch/sam3/blob/31cb7e624e4fe95301b1be1d4e809111593d2e45/README.md
[fe]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/featureEngine/FeatureExtractor.cpp
[ei]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/utils/main_exportImages.cpp
[pds]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/software/pipeline/main_prepareDenseScene.cpp
[roma]: https://github.com/meshroomHub/mrRomatch/tree/e3c2e0d07e2577c45b35c7711d6f8ac356adca2a
[registry]: https://github.com/meshroomHub/pluginRegistry/blob/e149697c8af790686b7845a81153b11417064d0b/meshroomHub.json
[romamatcher]: https://github.com/meshroomHub/mrRomatch/blob/e3c2e0d07e2577c45b35c7711d6f8ac356adca2a/meshroom/roma/RomaMatcher.py
[romagt]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/meshroom/cameraTrackingRoma.mgt
[romadesc]: https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/feature/virtual/ImageDescriber_Roma.cpp
[romacore]: https://github.com/meshroomHub/mrRomatch/blob/e3c2e0d07e2577c45b35c7711d6f8ac356adca2a/python/romaCore.py
[romafork]: https://github.com/servantftransperfect/RoMaV2/tree/b780da6118de6f6f0a83a586e529102c212fefc9
[romapr]: https://github.com/meshroomHub/mrRomatch/pull/7
[romaoom]: https://github.com/Parskatt/RoMaV2/issues/17
[romaleak]: https://github.com/Parskatt/RoMaV2/issues/40
[romacuda]: https://github.com/Parskatt/RoMaV2/issues/48
[romalicense]: https://github.com/Parskatt/RoMaV2/issues/52
[lg]: https://github.com/cvg/LightGlue/blob/5a650c444718caffc2669dc0094cde908f42dd73/README.md
[seglicenses]: https://github.com/meshroomHub/mrSegmentation/blob/66866d139cf43a7736da0a3ead5b2c1405550576/LICENSE
[samlicenses]: https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/README.md#license
[sam1license]: https://github.com/facebookresearch/segment-anything#license
[dinolicense]: https://github.com/IDEA-Research/GroundingDINO/blob/main/LICENSE
[gsamlicense]: https://github.com/IDEA-Research/Grounded-SAM-2/blob/b7a9c29f196edff0eb54dbe14588d7ae5e3dde28/LICENSE
[romacodelicense]: https://github.com/Parskatt/RoMaV2/blob/95c9968145c8906b7b59383258e9f73b02853d89/LICENSE
[dinolicense3]: https://github.com/facebookresearch/dinov3/blob/adc254450203739c8149213a7a69d8d905b4fcfa/LICENSE.md
[sam3license]: https://github.com/facebookresearch/sam3/blob/31cb7e624e4fe95301b1be1d4e809111593d2e45/LICENSE
[w-sam1]: https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth
[w-dino]: https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth
[w-ram]: https://huggingface.co/xinyu1205/recognize-anything-plus-model/tree/84d4aee3a0265c4e0df1f714f0572011d1bf2ec3
[w-sam2s]: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt
[w-sam2l]: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
[w-hfdino]: https://huggingface.co/IDEA-Research/grounding-dino-tiny/tree/a2bb814dd30d776dcf7e30523b00659f4f141c71
[w-sam3]: https://huggingface.co/api/models/facebook/sam3/tree/3c879f39826c281e95690f02c7821c4de09afae7?recursive=true
[w-roma]: https://github.com/Parskatt/RoMaV2/releases/download/v2.0.1/romav2.0.1.pt
[plugins]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/INSTALL_PLUGINS.md
[env]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/meshroom/core/plugins/env.py
[node]: https://github.com/alicevision/Meshroom/blob/b12ea8896e7e95cc9911b4ec39c272914e4da726/meshroom/core/desc/node.py
[review-priority]: https://github.com/Kwentin3/photogrammetry-to-cad/pull/11#issuecomment-7077543016
[sam2-install]: https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/INSTALL.md
