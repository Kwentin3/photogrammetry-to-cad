# Печатный комплект CCTag3 — Goal #15

Подготовлены [четыре страницы PDF](../../../templates/capture-kit/cctag3-print.pdf),
[форма фактических замеров](../../../templates/capture-kit/measurements.csv)
и [manifest](../../../templates/capture-kit/manifest.json). ID **0, 1, 2, 3** —
нативные, с нуля. Каждая страница A4 содержит одну метку внешним диаметром
100 мм, серый центр и два контрольных отрезка печати X/Y по 100 мм.
Готовые листы используют один раз на сцену: одинаковые ID не дублировать.

На 24 ноября цифровая проверка формы и размеров PDF выполнена, просмотрены все
четыре страницы. **Native-проверка ID окончательного PDF ещё требует evidence
Linux CI**: локальный Windows CPU-детектор остановлен общим лимитом commit 2 GiB.
Это не PASS детекции. Физическая распечатка, рабочая дистанция, новая съёмка и
метрическая точность пока не проверены. После native CI сюда добавляется
идентичность проверенного commit/run и результат для каждого ID.

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
- Шесть focused unittest проходят: реальный сохранённый native `.feat/.desc`,
  нулевая нумерация ID, отказ при повреждении/неверном ID/центре, геометрия PDF,
  единая схема CSV и отсутствие придуманных измеренных длин. Тесты парсера
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

## Воспроизведение PDF и native-проверки

Готовый PDF не требует установленного генератора. Для пересоздания нужны Python
3.11+ и optional [requirements-capture-kit.txt](../../../requirements-capture-kit.txt):

```bash
python -m venv /tmp/capture-venv
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
и [ImageDescriber_CCTAG.cpp](https://github.com/alicevision/AliceVision/blob/v3.3.0/src/aliceVision/feature/cctag/ImageDescriber_CCTAG.cpp):
64-битный little-endian `size_t` count и 128 байтов на descriptor, один byte 255
на позиции нативного ID. Драйвер проверяет длину, число `.feat`, единственный
ожидаемый ID страницы, его положение до 2 пикселей, SHA PDF/manifest/растра/выходов.
PDF ID извлекается также из печатной подписи. Это чтение native-формата, не
реализация детектора.

В подготовленном bounded Linux owner с официальным архивом AliceVision 3.3.0
сначала сверить полный SHA-256
`f43f498312859af627f2f7f65a6d33c2a3411b37989b8b680c04c8c690dcb640`,
распаковать без изменения ядер и выполнить:

```bash
export ALICEVISION_ROOT=/path/to/extracted/aliceVision
export LD_LIBRARY_PATH="$ALICEVISION_ROOT/lib:$ALICEVISION_ROOT/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=1
python scripts/check_capture_kit.py \
  --kit templates/capture-kit \
  --detector "$ALICEVISION_ROOT/bin/aliceVision_featureExtraction" \
  --output /tmp/pdf-check
cat /tmp/pdf-check/validation.json
```

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

В том же подготовленном Linux owner можно проверить originals без правки кода:

```bash
python scripts/check_capture_kit.py \
  --images /path/to/trial-originals \
  --detector "$ALICEVISION_ROOT/bin/aliceVision_featureExtraction" \
  --output /tmp/trial-check
cat /tmp/trial-check/validation.json
```

В JSON для каждого оригинала будут ID, центры и радиусы. `PREFLIGHT_REVIEW_REQUIRED`
означает только завершённое чтение native-выходов: агент ещё сопоставляет найденные
метки с видимыми, проверяет отсутствие дублей ID и достаточную видимость
установочной/проверочных пар в ракурсах. Ноль найденных меток не является PASS.
При потере метки просить конкретное действие: приблизить кадр/увеличить метку,
убрать блик или наклон, закрепить лист плоско; затем повторить тот же пробный
ракурс. Этот тест не доказывает точность 3D и не подменяет реальную измеренную базу.
