# Источники и пределы проверки

Дата проверки опорных утверждений: **20 ноября 2026 года**. Проверены документация и исходные файлы upstream; программы и сквозной конвейер в ходе упаковки контекста не запускались.

Выбор стека и KISS-границы — договорённости проекта, а не вывод о победителе бенчмарков. Публикация функции в документации не подтверждает её наличие в произвольной сборке. `stable`, `latest` и ветки разработки изменяемы; перед запуском фиксируются фактические версии.

**S01–S12 ниже относятся только к актуальным документам `docs/`.** Архивный отчёт имеет свой независимый реестр S01–S34 за 11 ноября; номера между ними не сопоставляются.

## S01. Отбор кадров

- [AliceVision: Keyframe Selection](https://alicevision.readthedocs.io/en/stable/md__home_docs_checkouts_readthedocs_8org_user_builds_alicevision_checkouts_stable_src_aliceVision_keyframe_README.html).
- [Meshroom API: KeyframeSelection](https://meshroom.readthedocs.io/en/latest/generated/meshroom.nodes.aliceVision.KeyframeSelection.KeyframeSelection.html).
- [Историческое руководство узла](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/KeyframeSelection.html).

Подтверждают входные видео/изображения, отбор по резкости и движению, экспорт кадров и SfMData. Для видео выход `NONE` не создаёт нужных файлов кадров. Историческая страница описывает ограничения MR 2020.x; подключение узла в современный граф проверяется отдельно.

## S02. Meshroom, CLI и CUDA

- [Официальный репозиторий Meshroom](https://github.com/alicevision/Meshroom).
- [Официальные релизы](https://github.com/alicevision/meshroom/releases).
- [CUDA FAQ](https://meshroom-manual.readthedocs.io/en/latest/faq/needs-cuda/needs-cuda.html).
- [Командная строка](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/cmd/).

Подтверждают штатный процесс, CLI и CUDA-зависимость выбранного плотного этапа. Для опубликованного релиза 2025.1.0 указаны CUDA 12 и compute capability от 5.0; это пример версионных требований, не уже выбранная/установленная сборка нашего проекта. Старые минимумы из manual нельзя смешивать с новыми пакетами.

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

Подтверждают семейства, поля, матовое плоское основание и ориентир около 30 px радиуса внешнего кольца. Генератор поддерживает кольца 3/4, ID, крестик и PDF. Прочитанный blob `5138d35b89301171dd3784d16302decdde758bd8` начинает ID и имена с 0. Нужные PDF здесь ещё не сгенерированы. Количество 6–8 и конкретное размещение — предложение пилота, не норматив источника.

## S06. Масштабирование CCTag в Meshroom

- [Официальная Wiki CCTAG scaling](https://github.com/alicevision/Meshroom/wiki/CCTAG-scaling).
- [Исходный Markdown той же Wiki](https://raw.githubusercontent.com/wiki/alicevision/Meshroom/CCTAG-scaling.md).
- [SfMTransform](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/SfMTransform.html).

Подтверждают сохранение SIFT, настройку CCTag и преобразование SfMData. ID старых готовых PDF может отличаться от имени файла; старые примеры единиц не являются стандартом проекта. Два центра дают информацию о масштабе, но не фиксируют всю ориентацию. Контрольные измерения вне подгонки — правило пилота.

## S07. Командный интерфейс CloudCompare

- [Command line mode](https://www.cloudcompare.org/doc/wiki/index.php?title=Command_line_mode).

Документирует фильтрацию, нормали и `-RANSAC` (с v2.11) с выбором примитивов и параметров. Страница включает команды разных версий; фактический `--help`/справка и плагины установленного пакета приоритетны. Наличие GUI/CLI не доказывает готовый мост в build123d.

## S08. RANSAC-плагин и сборка

- [RANSAC Shape Detection](https://www.cloudcompare.org/doc/wiki/index.php/RANSAC_Shape_Detection_(plugin)).
- [CloudCompare BUILD.md](https://github.com/CloudCompare/CloudCompare/blob/master/BUILD.md).

Подтверждают примитивы, поддерживающие точки и роль нормалей. `PLUGIN_STANDARD_QRANSAC_SD` — опциональная сборочная возможность. Проверка доступности и реального экспорта параметров остаётся задачей первого runtime.

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

Подтверждают штатные средства управления и ключи API. Создание нод, выдача ключей и платные вызовы в рамках подготовки этих документов не выполнялись.

## Как обновлять этот список

После первого запуска добавить фактические версии, проверенные команды и ссылку на карточку результата. Не повышать доказанность по одному чтению документации. Новые источники нужны при изменении решения или конкретном техническом вопросе, а не ради расширения каталога.
