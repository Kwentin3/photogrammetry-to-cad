# Источники и пределы проверки

Дата проверки опорных утверждений: **20 ноября 2026 года**. Проверены документация и исходные файлы upstream; программы и сквозной конвейер в ходе упаковки контекста не запускались.

Выбор стека и KISS-границы — договорённости проекта, а не вывод о победителе бенчмарков. Публикация функции в документации не подтверждает её наличие в произвольной сборке. `stable`, `latest` и ветки разработки изменяемы; перед запуском фиксируются фактические версии.

**S01–S15 ниже относятся к актуальным документам проекта.** Архивный отчёт имеет свой независимый реестр S01–S34 за 11 ноября; номера между ними не сопоставляются. Источники Open3D и адресных резервов добавлены после [ревью #1](https://github.com/Kwentin3/photogrammetry-to-cad/issues/1), Codex и управления Vast.ai — после выбора исполнителя пилота.

## S01. Отбор кадров

- [AliceVision: Keyframe Selection](https://alicevision.readthedocs.io/en/stable/md__home_docs_checkouts_readthedocs_8org_user_builds_alicevision_checkouts_stable_src_aliceVision_keyframe_README.html).
- [Meshroom API: KeyframeSelection](https://meshroom.readthedocs.io/en/latest/generated/meshroom.nodes.aliceVision.KeyframeSelection.KeyframeSelection.html).
- [Историческое руководство узла](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/KeyframeSelection.html).
- [FFmpeg: официальная документация](https://ffmpeg.org/ffmpeg.html).

Подтверждают входные видео/изображения, отбор по резкости и движению, экспорт кадров и SfMData. Для видео выход `NONE` не создаёт нужных файлов кадров. Историческая страница описывает ограничения MR 2020.x; подключение узла в современный граф проверяется отдельно.

FFmpeg документирует извлечение изображений из видео. Это резерв при проблеме штатного узла, не ещё один обязательный этап и не автоматическая гарантия хорошего отбора.

## S02. Meshroom, CLI и CUDA

- [Официальный репозиторий Meshroom](https://github.com/alicevision/Meshroom).
- [Официальные релизы](https://github.com/alicevision/meshroom/releases).
- [CUDA FAQ](https://meshroom-manual.readthedocs.io/en/latest/faq/needs-cuda/needs-cuda.html).
- [Командная строка](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/cmd/).
- [NVIDIA: Blackwell Compatibility Guide](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/index.html).

Подтверждают штатный процесс, CLI и CUDA-зависимость выбранного плотного этапа. Для опубликованного релиза 2025.1.0 указаны CUDA 12 и compute capability от 5.0; это пример версионных требований, не уже выбранная/установленная сборка нашего проекта. Старые минимумы из manual нельзя смешивать с новыми пакетами.

NVIDIA описывает роль совместимого cubin и PTX в запуске на новой архитектуре. Поэтому общего запрета RTX 50xx не вводим; проверяем конкретную сборку реальным вычислением DepthMap. Эта проверка выбранной нами среды ещё не выполнена.

## S03. Плотный результат Meshing

- [Документация Meshing](https://meshroom.readthedocs.io/en/stable/generated/meshroom.nodes.aliceVision.Meshing.Meshing.html).
- [AliceVision develop: Meshing.py](https://github.com/alicevision/AliceVision/blob/develop/meshroom/aliceVision/Meshing.py).

Подтверждают объединение карт глубины и выход Dense SfMData. Прочитанный файл в `develop` указывает `densePointCloud.usda` (blob `5d0e34a1903c7997c30223473721479ec7507dfa`). Это снимок исходника, а не обещание формата всех релизов. Плотное и разреженное облака различаются.

## S04. Экспорт облака

- [ConvertSfMFormat, руководство v2023.1.0](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/ConvertSfMFormat.html).

Описывает преобразование `densePointCloud.abc` из Meshing в PLY и настройку типа признаков `unknown` для такого экспорта. Это документированный исторический пример; точный вход, расширение и параметры проверяются на выбранной версии. Экспорт не создаёт CAD-тела.

## S05. CCTag: мишени и генератор

- [Markers usage](https://cctag.readthedocs.io/en/latest/markers/markers.html).
- [Исходник генератора](https://github.com/alicevision/CCTag/blob/develop/markersToPrint/generators/generate.py).

Подтверждают семейства, поля, матовое плоское основание и ориентир около 30 px радиуса внешнего кольца. Генератор поддерживает кольца 3/4, ID, крестик и PDF. Прочитанный blob `5138d35b89301171dd3784d16302decdde758bd8` начинает ID и имена с 0. Нужные PDF здесь ещё не сгенерированы. Две метки на рейке — начальный вариант пилота, не норматив достаточного покрытия объекта.

Таблица сантиметров в памятке — наш расчёт по проекции: `D = 2 × Z × tan(FOVh / 2) × p / W`, где `p` — диаметр в пикселях, `W` — ширина обработанного кадра, `Z` — расстояние. Условия: фронтальная плоскость, горизонтальный угол 80°, без уменьшения. Это не эмпирическая гарантия обнаружения.

## S06. Масштабирование CCTag в Meshroom

- [Официальная Wiki CCTAG scaling](https://github.com/alicevision/Meshroom/wiki/CCTAG-scaling).
- [Исходный Markdown той же Wiki](https://raw.githubusercontent.com/wiki/alicevision/Meshroom/CCTAG-scaling.md).
- [SfMTransform](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/SfMTransform.html).

Подтверждают сохранение SIFT, настройку CCTag и преобразование SfMData. ID старых готовых PDF может отличаться от имени файла; старые примеры единиц не являются стандартом проекта. Два центра дают информацию о масштабе, но не фиксируют всю ориентацию. Контрольные измерения вне подгонки — правило пилота.

## S07. Командный интерфейс CloudCompare

- [Command line mode](https://www.cloudcompare.org/doc/wiki/index.php?title=Command_line_mode).

Документирует фильтрацию, нормали и `-RANSAC` (с v2.11) с выбором примитивов и параметров. Страница включает команды разных версий; фактическая справка и плагины установленного пакета приоритетны. В уточнённом плане CloudCompare используется для просмотра и обрезки; его CLI не является обязательным мостом в build123d.

## S08. RANSAC-плагин и сборка

- [RANSAC Shape Detection](https://www.cloudcompare.org/doc/wiki/index.php/RANSAC_Shape_Detection_(plugin)).
- [CloudCompare BUILD.md](https://github.com/CloudCompare/CloudCompare/blob/master/BUILD.md).

Подтверждают примитивы, поддерживающие точки и роль нормалей. `PLUGIN_STANDARD_QRANSAC_SD` — опциональная сборочная возможность. Источник сохранён для ранее обсуждавшегося варианта; наличие этого плагина и экспорт его параметров больше не являются условием первого запуска.

## S09. build123d и STEP

- [Официальная документация build123d](https://build123d.readthedocs.io/en/stable/).
- [Importing and exporting](https://build123d.readthedocs.io/en/latest/how_to/import_export.html).
- [Реализация export_step](https://build123d.readthedocs.io/en/stable/_modules/exporters3d.html#export_step).
- [OCCT STEP Translator](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html).

Подтверждают экспорт готовой формы/сборки, геометрии, имён, цветов и единиц. В нашем процессе исходная программа построения сохраняется отдельно. Вывод о том, что этот экспорт не сохраняет Python-историю, относится к данному API; это не утверждение обо всех возможностях стандарта STEP. CAD-валидность и точность размеров проверяются независимо.

## S10. Vast.ai: образ, шаблон и окружение

- [Templates](https://docs.vast.ai/guides/templates/introduction).
- [Docker Execution Environment](https://docs.vast.ai/guides/instances/docker-environment).

Подтверждают штатные шаблоны, особенности entrypoint/onstart и выделения ресурсов. Образ для нашего Meshroom ещё не проверен. Упоминание RTX 3090/4090 и 32–64 ГБ RAM — стартовый ориентир проекта, не гарантия достаточности.

## S11. Vast.ai: файлы и жизненный цикл

- [Data Movement](https://docs.vast.ai/guides/instances/storage/data-movement).
- [Managing Instances](https://docs.vast.ai/guides/instances/manage-instances).

Подтверждают штатное копирование файлов, продолжающуюся оплату диска при `stop`, отсутствие резерва GPU после остановки и удаление локальных данных при `destroy`. Тарифы и наличие хостов здесь не проверялись.

## S12. Vast.ai: автоматизация и доступ

- [Официальный vast-cli](https://github.com/vast-ai/vast-cli).
- [Manage API keys](https://docs.vast.ai/guides/reference/api-keys).
- [Using Vast.ai with Agents](https://docs.vast.ai/guides/get-started/agents).

Подтверждают CLI для поиска и управления инстансами, API-ключи с ограничиваемыми правами и отдельную роль SSH-ключей. Документация для агентов описывает официальную интеграцию с Codex; она может помогать исполнителю, но не заменяет доступы и проверку Meshroom. Создание нод, выдача ключей и платные вызовы в рамках подготовки этих документов не выполнялись. Упомянутые $0.50/ч — наблюдение владельца, не проверка рынка в этом документе.

## S13. Open3D: облако и плоскости

- [Point cloud: plane segmentation](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html#Plane-segmentation).
- [Point cloud outlier removal](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud_outlier_removal.html).

Документируют готовые операции над облаком, фильтрацию и `segment_plane`: коэффициенты плоскости и индексы поддерживающих точек. Этот результат не содержит автоматически границы деталей или их готовое CAD-представление. Повторная подгонка по областям и передача параметров — тонкая связующая логика нашего будущего скрипта. Скорость, точность и версии локального окружения ещё не проверены.

## S14. Маски и сопоставление признаков — только резерв

- [Meshroom: штатные входы масок](https://meshroom-manual.readthedocs.io/en/latest/tutorials/turntable/turntable.html).
- [SAM 2: статья авторов, ограничения метода](https://arxiv.org/html/2408.00714v1).
- [Grounded-SAM 2: авторский репозиторий](https://github.com/IDEA-Research/Grounded-SAM-2).
- [LightGlue: авторский репозиторий](https://github.com/cvg/LightGlue).

Meshroom описывает применение масок в FeatureExtraction и PrepareDenseScene. SAM 2 допускает ошибки на тонких деталях; гарантии пиксельных границ нет. Grounded-SAM 2 связывает выделение по текстовому описанию с сегментацией. LightGlue сопоставляет локальные признаки и поддерживает несколько их типов, включая SIFT. Ни одна из этих ссылок не подтверждает готовый перенос масок в метрические детали нашей беседки или проверенный стык нового matcher с Meshroom. Эти компоненты не установлены и не включены в обязательный маршрут.

## S15. Codex как исполнитель

- [OpenAI: Codex CLI](https://learn.chatgpt.com/docs/codex/cli).
- [OpenAI: инструкции проекта в AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Подтверждают работу Codex с локальным репозиторием и терминальными инструментами, настройки разрешений и использование AGENTS.md. В доступном окружении дополнительно прочитаны `codex --version` и `codex --help` (CLI 0.169.0); это не выбор обязательной версии и не проверка доступа к Vast.ai с машины владельца. Решение сначала использовать Codex, а перенос в Hermes рассмотреть позже — договорённость проекта. Сравнение надёжности двух агентов здесь не проводилось.

## Как обновлять этот список

После первого запуска добавить фактические версии, проверенные команды и ссылку на карточку результата. Не повышать доказанность по одному чтению документации. Новые источники нужны при изменении решения или конкретном техническом вопросе, а не ради расширения каталога.
