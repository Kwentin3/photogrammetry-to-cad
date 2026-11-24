# Печатный комплект CCTag3 — Goal #15

Подготовлены [четыре страницы PDF](../../../templates/capture-kit/cctag3-print.pdf),
[форма фактических замеров](../../../templates/capture-kit/measurements.csv)
и [manifest](../../../templates/capture-kit/manifest.json). ID **0, 1, 2, 3** —
нативные, с нуля. Каждая страница A4 содержит одну метку внешним диаметром
100 мм, серый центр и два контрольных отрезка печати X/Y по 100 мм.
Готовые листы используют один раз на сцену: одинаковые ID не дублировать.

На 24 ноября цифровая проверка **PASS**: просмотрены все четыре страницы и
штатный CCTag CPU-детектор распознал ID/центры на растрах именно этого PDF.
[Успешный CI](https://github.com/Kwentin3/photogrammetry-to-cad/actions/runs/45386538315)
проверил commit `2d57ab469cd75c7d5a216cd0985932bf8ab4f96d`.
Физическая распечатка, читаемость с рабочей дистанции, новая съёмка и метрическая
точность пока не проверены. Ниже сохранены также неудачные попытки и их причины.

## Происхождение и выбор механизма

Используется неизменённый официальный
[generate.py](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/markersToPrint/generators/generate.py)
и его [банк cctag3.txt](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/markersToPrint/generators/cctag3.txt),
revision `71021443af3f7946e8e9025a37634b57e7aad77d`, лицензия CCTag MPL-2.0.
SHA-256 обоих входов зафиксированы в manifest и проверяются до исполнения.
Скрипт проекта [make_capture_kit.py](../../../scripts/make_capture_kit.py)
только вызывает официальный генератор и размещает его SVG на листах с подписями,
контролем печати и формой; собственного кодирования колец нет.

Штатный `--generatePdf` **также фактически проверен** тем же Python/источником:
`generate.py --rings 3 --radius 500 --margin 400 --addCross --whiteBackground
--generatePdf --outdir <новый private каталог>` создал 32 PDF, exit 0 за 1.1 с.
У `0000.pdf` страница 1400×1400 points, то есть 493.889×493.889 мм; извлечённый
текст пуст, поскольку `--addId` в этой команде не включён. Это рабочий штатный
механизм, дополнительного fallback по ошибке библиотек не требовалось. Тонкая
компоновка закрывает конкретный разрыв: A4/A3 с заданным физическим диаметром,
двумя 100-мм проверками печати и согласованной карточкой замеров не являются
выходом генератора. Его SVG используются без правки геометрии. Probe сохранён
в `../photogrammetry-to-cad-work/issue-15/official-pdf-probe/`.

Сохранено соотношение штатных полей: `--radius 500 --margin 400`. Это белое
поле по 20 мм с каждой стороны метки диаметром 100 мм. Центр добавляет штатный
`--addCross`; подпись ID размещается отдельно за пределами поля. Координаты
центров листов сохранены в manifest; их нельзя использовать как расстояния
между раздельно установленными листами.

[Разработчики CCTag](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/doc/sphinx/source/markers/markers.rst)
рекомендуют жёсткое плоское матовое основание и ориентир: внешний радиус в
изображении примерно от 30 пикселей. Поэтому 100 мм — пример, а не обещание
дальности для любого телефона. Размер выбирают по пробным оригинальным кадрам.
Для более крупной метки доступны `--paper A3 --diameter-mm 160`; такой изменённый
PDF нужно снова проверить native-детектором. A4/100 мм — фактически созданный
комплект этой поставки.

## Что проверено локально

- PDF SHA-256: `40c1f4cff6c056eb171c73f81b0ced9dbf8751a13f318cfad7bc2a4cd5598801`.
- PyMuPDF 1.26.5 прочитал четыре страницы A4 210×297 мм; векторный внешний
  диаметр на всех страницах 100×100 мм. ID в извлечённом тексте совпадают с
  manifest. Отдельно открыты четыре PNG, полученные из конечного PDF при 150 dpi:
  поля, серые центры, подписи, контрольные отрезки и колечки не обрезаны.
- Семь focused unittest проходят: реальный сохранённый native `.feat/.desc`,
  нулевая нумерация ID, отказ при повреждении/неверном ID/центре, геометрия PDF,
  единая схема CSV и отсутствие придуманных измеренных длин. Реальная замена
  заголовка ID 1 на ID 10 в копии PDF с обновлённым SHA отвергается до детектора;
  корректный комплект продолжает проходить `prepare_inputs`. Тесты парсера
  не заменяют штатную детекцию растрового PDF.
- Форма сохраняет поля существующего `templates/measurements.csv`. Установочная
  база — центры ID 0–1; независимые пары 0–2 и 1–3 — проверки. Ещё две строки
  предназначены для измерений самого объекта с описанными и сфотографированными
  концами. `measured_mm` и погрешность пусты; принтерные 100 мм указаны только как
  номинал в notes. Принтерные отрезки не задают масштаб сцены.

Evidence вне Git: `../photogrammetry-to-cad-work/issue-15/pdf-raster/`,
`pdf-raster-72dpi/`, `pdf-driver-preparation/`, `cctag-source/`,
`windows-detector-members.json`. Эти относительные пути нужны для текущей локальной
приёмки; воспроизводимый маршрут ниже не требует этой частной папки.

## Локальный Windows native probe и установленная причина

Взят готовый официальный
[AliceVision 3.3.0 Windows ZIP](https://github.com/alicevision/AliceVision/releases/download/v3.3.0/AliceVision-3.3.0-Windows.zip),
asset ID `284032862`, размер 1549136674 байта. Выборочно извлечены
`aliceVision_featureExtraction.exe`, OCIO config и 68 DLL его eager-зависимостей:
33 952 872 сжатых байта. Для каждого PE member проверены ZIP CRC32 и SHA-256;
полный SHA-256 архива при выборочном чтении **не проверялся**. Эта отдельная версия
служит проверке печатного CCTag3 и не меняет закреплённый runtime реконструкции.

Детектор загрузился и сообщил наличие `cctag3`, `forceCpuExtraction`, `maxThreads`
и `maxCoresAvailable`. Обе попытки использовали CPU и один поток/ядро; в логе
явно `Extracting cctag3 ... [cpu]`. Результаты:

| PDF raster | RunId | Итог |
| --- | --- | --- |
| 150 dpi, 1241×1754 | `7e0898d96aa24cef8639dc7c3ab4cd2c` | exit 137, `job_memory_limit`, cleanup confirmed |
| 72 dpi, 596×842 | `9a89c7301463443e84014d1970cd4727` | exit 137, `job_memory_limit`, cleanup confirmed |

Во втором запуске `--maxMemoryAvailable 1073741824`; этот параметр ограничивает
планирование конкурентной обработки, но не фиксированные аллокации библиотеки.
У CCTag [Types.hpp](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/src/cctag/Types.hpp)
задаёт `MAX_POINTS=2^24` и `MAX_VOTERLIST_SIZE=16*MAX_POINTS`.
[Types.cpp](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/src/cctag/Types.cpp)
выделяет эти массивы независимо от размера кадра: только список голосующих
содержит 268435456 `int`, то есть 1 GiB, помимо списка EdgePoint и остальных
массивов. [Multiresolution.cpp](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/src/cctag/Multiresolution.cpp)
создаёт коллекции по уровням пирамиды. Понижение dpi не устраняет эту причину.
Ядро и общий Windows policy не изменялись; работающих потомков после остановок
не осталось. WSL с зарегистрированной Ubuntu не запустился: «Указанное сетевое
имя более недоступно»; его ремонт и запуск других сред не выполнялись.

## Выбор рабочего Linux-детектора

[CI run 45384802537](https://github.com/Kwentin3/photogrammetry-to-cad/actions/runs/45384802537)
завершился failure. Полный официальный архив AliceVision 3.3.0 Linux прошёл
SHA-256; binary запустился на CPU, затем завершился с
`Invalid imageDescriber : cctag3` до extraction. Generic help с именем `cctag3`
не подтверждает, что именно эта сборка умеет создавать данный describer.
Сообщение об отсутствии CUDA не установлено причиной этой ошибки. Контейнер
CI удалён; незавершённого расчёта нет.

Следующий [run 45385763293](https://github.com/Kwentin3/photogrammetry-to-cad/actions/runs/45385763293)
также завершён с удалением контейнера: малый архив Meshroom 132097741 байт
содержит приложение без AliceVision. Его локальный index (2830 members) подтвердил
отсутствие detector и libCCTag. Правильная поставка для native-проверки — **full**;
наличие нужных файлов проверяется до следующего запуска. Малый архив не
объявляется рабочим runtime и не меняет принятую базу реконструкции.

Принятый отдельный runtime детектора — официальный
[Meshroom nightly 2026-11-24, 596c70d, Linux full](https://github.com/alicevision/Meshroom/releases/download/nightly/Meshroom-2026.11.24-596c70d-linux-full.tar.gz),
600166523 байта, SHA-256
`f1f540e2349542446524799c4e368be22afe16bb98b950c0a98c04300c92ff36`.
Полная копия сохранена вне Git в `photogrammetry-to-cad-work/runtime-archives/`.
Локально проверены SHA и 12486 записей архива: есть native featureExtraction,
OCIO и `libCCTag.so.1.0.4`. Средняя скорость 8-поточной выгрузки — 4.0 MiB/s.
Upstream nightly rolling: если файл удалён,
использовать сохранённую копию с тем же SHA в разрешённом Linux CPU-сеансе;
не подменять архив другим nightly под старым хэшем.
Отдельно повторно проверены SHA обоих полных архивов 21/24 ноября и
побайтовое совпадение шести файлов: detector ELF, CCTag, feature/featureEngine,
OCIO и FeatureExtraction.py; совпали также четыре symlink targets.
Это equivalence на перечисленной границе, остальные библиотеки не сравнивались.
Основной закреплённый runtime реконструкции от 21 ноября не меняется.

## Итоговая native-проверка конечного PDF

Run `45386538315`, job `138418801641`, commit
`2d57ab469cd75c7d5a216cd0985932bf8ab4f96d`: **success**, CPU, без GPU.
PyMuPDF 1.26.5 создал четыре PNG 596×842 при 72 dpi из конечного PDF,
его SHA совпал с manifest. Native detector SHA-256
`2cb2c238e49494d522aef82987140403874070fae16dd6283d64a00e454f2c2e`
совпадает с принятым ELF 21 ноября. Нет переиспользованных features/cache.

| Страница | Ожидаемый / найденный native ID | Отклонение центра от PDF, px |
|---|---|---:|
| 1 | 0 / 0 | 0.811 |
| 2 | 1 / 1 | 0.891 |
| 3 | 2 / 2 | 0.468 |
| 4 | 3 / 3 | 0.532 |

Каждая страница дала ровно один ожидаемый ID. Driver завершился за 1.762 s;
допуск центра 2 px применялся к цифровому растру, не к физическим размерам.
Восемь потоков aria2 дали 813 MiB/s в CI, полный archive SHA подтверждён.
После success штатно удалены контейнер и его сеть; артефакты/cache на GitHub
не создавались. Raw log и извлечённый `validation-native.json` сохранены вне Git
в `issue-15/ci/`, equivalence — `issue-15/detector-equivalence.json`.
Флаги physical_print_validated и metric_capture_validated остались **false**.

## Воспроизведение PDF и native-проверки

Готовый PDF не требует установленного генератора. Для пересоздания нужны Python
3.11+ и optional [requirements-capture-kit.txt](../../../requirements-capture-kit.txt):

```bash
python3 -m venv /tmp/capture-venv
/tmp/capture-venv/bin/pip install -r requirements-capture-kit.txt
/tmp/capture-venv/bin/python scripts/make_capture_kit.py \
  --source-dir /tmp/cctag-source --download-source \
  --output /tmp/recreated-capture-kit
```

Для svglib/pycairo на Linux могут потребоваться `libcairo2-dev`, `pkg-config` и
заголовки Python; native-проверке готового PDF нужен только `PyMuPDF==1.26.5`.
Поэтому CI может установить один PyMuPDF, не устанавливая генератор.

[check_capture_kit.py](../../../scripts/check_capture_kit.py) растеризует именно
готовый PDF, создаёт минимальный native `.sfm`, запускает штатный детектор и
читает его результаты. Формат `.desc` подтверждён официальными
[Descriptor.hpp](https://github.com/alicevision/AliceVision/blob/v3.3.0/src/aliceVision/feature/Descriptor.hpp)
и [ImageDescriber_CCTAG.cpp](https://github.com/alicevision/AliceVision/blob/v3.3.0/src/aliceVision/feature/cctag/ImageDescriber_CCTAG.cpp).
Тот же формат независимо сверен в принятом source revision d012d055:
[Descriptor.hpp](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/feature/Descriptor.hpp),
[ImageDescriber_CCTAG.cpp](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/feature/cctag/ImageDescriber_CCTAG.cpp).
Это контракт хранения:
64-битный little-endian `size_t` count и 128 байтов на descriptor, один byte 255
на позиции нативного ID. Драйвер проверяет длину, число `.feat`, единственный
ожидаемый ID страницы, его положение до 2 пикселей, SHA PDF/manifest/растра/выходов.
PDF ID извлекается также из печатной подписи. Это чтение native-формата, не
реализация детектора.

Метка `native_abi` в JSON описывает формат, а не версию переданного binary;
его точные байты обозначает отдельный `detector_sha256`.

Для native-проверки выполнить [единый CPU-рецепт](../../capture.md#cpu-проверка-pdf-и-пробных-кадров)
из корня репозитория, задав абсолютные `$WORK` вне Git и `ALICEVISION_ROOT` на
каталог `aliceVision` проверенного full bundle. Его SHA указан выше.
Рецепт создаёт `$WORK/capture-env` с одним pinned PyMuPDF, задаёт явный
`CAPTURE_PYTHON="$WORK/capture-env/bin/python"`, `ALICEVISION_ROOT` и native
`LD_LIBRARY_PATH`. Meshroom `env.sh` не загружается, `$MESHROOM_PYTHON` не используется,
`PYTHONHOME`/`PYTHONPATH` очищаются. Для этой проверки генератор не устанавливается.
Команды проверки не дублируются: [workflow](../../../.github/workflows/capture-kit.yml)
извлекает отмеченный Bash-блок из `capture.md` и исполняет его в чистом CPU-контейнере.

Ранее приведённый здесь голый `python` не выбирал среду с PyMuPDF. После замечания
[review PR #16, пункт 1](https://github.com/Kwentin3/photogrammetry-to-cad/pull/16#issuecomment-7131614932)
публикуется этот общий рецепт. Прежние успешные run выше подтверждают прежнюю
проверку PDF. Новая редакция фактически выполнена в чистом Linux CPU-контейнере:
[CI 45396841296](https://github.com/Kwentin3/photogrammetry-to-cad/actions/runs/45396841296),
commit `97ab7d6e9b97f5a53972bc317c073afaa6133f52`, **success**.
CI извлёк и исполнил ровно опубликованный блок (SHA-256
`68a821620874a1d14860981ff33927cdb2e6234c97b33f20d8c23490ee302db6`),
driver использовал `/tmp/capture-proof/capture-env/bin/python` с PyMuPDF 1.26.5.
Native PDF-проверка нашла ровно ID 0–3 за 2.190 s, отклонения центров
0.811/0.891/0.867/0.468 px. Затем те же Python/environment выполнили 7 адресных
тестов за 0.294 s, PASS. PDF SHA остался прежним; контейнер и сеть удалены.
Реальные пробные фотографии в этом CI не обрабатывались: вариант `--images`
использует тот же явный Python, но физическая проба остаётся отдельным шагом.

`--output` должен быть новым каталогом: старые native-файлы не переиспользуются.
Внутри — `input.sfm`, PNG, `.feat/.desc`, `native.log`, `validation.json`.
Native timeout 180 секунд, один CPU worker; лимит памяти/времени и остановка дерева
дополнительно принадлежат среде запуска. `PASS` разрешён только при совпадении
всех четырёх ID и центров. Даже этот PASS оставляет
`physical_print_validated=false` и `metric_capture_validated=false`.

## Пробные реальные кадры

Оператору сначала нужны 3–5 оригиналов с окончательной рабочей дистанции:
крупный прямой вид, рабочий общий вид и наклонные ракурсы, без пересылочного
сжатия. После распечатки проверить X/Y линейкой, жёстко закрепить листы, измерить
установочную базу и независимые расстояния. Положение меток между кадрами одной
сцены не менять. Инструкция оператору находится в основной памятке Goal #15.

В том же подготовленном Linux owner использовать вариант `--images` из
[CPU-рецепта](../../capture.md#cpu-проверка-pdf-и-пробных-кадров), с тем же
`$CAPTURE_PYTHON` и native environment; путь — на исходные пробные кадры,
`--output` — новый каталог. Приватные оригиналы в public CI не передаются.

В JSON для каждого оригинала будут ID, центры и радиусы. `PREFLIGHT_REVIEW_REQUIRED`
означает только завершённое чтение native-выходов: агент ещё сопоставляет найденные
метки с видимыми, проверяет отсутствие дублей ID и достаточную видимость
установочной/проверочных пар в ракурсах. Ноль найденных меток не является PASS.
При потере метки просить конкретное действие: приблизить кадр/увеличить метку,
убрать блик или наклон, закрепить лист плоско; затем повторить тот же пробный
ракурс. Этот тест не доказывает точность 3D и не подменяет реальную измеренную базу.
