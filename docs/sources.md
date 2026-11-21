# Источники и пределы проверки

Базовые источники проверены **20 ноября 2026 года**; источники фактической реализации S16–S21 добавлены **21 ноября**. Реальные фотографии и дополнительная виртуальная шкала прошли технический маршрут до CAD; [сквозная приёмка](reports/2026-11-21/technical-run.md) завершена. Точность собственной съёмки этим не подтверждается. Текущее состояние и доказательства собраны в единственной [записи Goal #2](goal-2.md).

Выбор стека и KISS-границы — договорённости проекта, а не вывод о победителе бенчмарков. Публикация функции в документации не подтверждает её наличие в произвольной сборке. `stable`, `latest` и ветки разработки изменяемы; перед запуском фиксируются фактические версии.

**S01–S21 ниже относятся к актуальным документам проекта.** Архивный отчёт имеет свой независимый реестр S01–S34 за 11 ноября; номера между ними не сопоставляются. Источники Open3D и адресных резервов добавлены после [ревью #1](https://github.com/Kwentin3/photogrammetry-to-cad/issues/1), Codex и управления Vast.ai — после выбора исполнителя пилота.

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

NVIDIA описывает роль совместимого cubin и PTX в запуске на новой архитектуре. Поэтому общего запрета RTX 50xx не вводим; проверяем конкретную сборку реальным вычислением DepthMap. Квалификация пилотной сборки описана в S16; RTX 50xx в этом опыте не проверялась.

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

Подтверждают штатные шаблоны, особенности entrypoint/onstart и выделения ресурсов. Фактическая квалификация runtime — S16. Упоминание RTX 3090/4090 и 32–64 ГБ RAM — стартовый ориентир проекта, не гарантия достаточности.

## S11. Vast.ai: файлы и жизненный цикл

- [Data Movement](https://docs.vast.ai/guides/instances/storage/data-movement).
- [Managing Instances](https://docs.vast.ai/guides/instances/manage-instances).

Подтверждают штатное копирование файлов, продолжающуюся оплату диска при `stop`, отсутствие резерва GPU после остановки и удаление локальных данных при `destroy`. Условия конкретной аренды учитываются в рабочей карточке; постоянной котировки этот документ не задаёт.

## S12. Vast.ai: автоматизация и доступ

- [Официальный vast-cli](https://github.com/vast-ai/vast-cli).
- [Manage API keys](https://docs.vast.ai/guides/reference/api-keys).
- [Using Vast.ai with Agents](https://docs.vast.ai/guides/get-started/agents).

Подтверждают CLI для поиска и управления инстансами, API-ключи с ограничиваемыми правами и отдельную роль SSH-ключей. Документация для агентов описывает официальную интеграцию с Codex; она может помогать исполнителю, но не заменяет доступы и проверку Meshroom. При первоначальной подготовке документов платные ресурсы не запускались; фактическая аренда началась 21 ноября, см. S17 и запись Goal. Упомянутые $0.50/ч — наблюдение владельца, не текущая котировка.

## S13. Open3D: облако и плоскости

- [Point cloud: plane segmentation](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html#Plane-segmentation).
- [Point cloud outlier removal](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud_outlier_removal.html).

Документируют готовые операции над облаком, фильтрацию и `segment_plane`: коэффициенты плоскости и индексы поддерживающих точек. `scripts/extract_plane.py` уже связывает эти операции с явным ROI, поддерживающим облаком, выпуклым контуром и JSON для CAD; автоматического распознавания отдельной детали нет. В Windows/Python 3.11.9 с Open3D 0.20.0 мост проверен на фактических Dice и synthetic MVS входах до STEP. Для Dice единицы номинальные, метрический перенос проверен только на виртуальной базе synthetic; физическая точность собственной съёмки не установлена. Версии и результаты привязаны к lock и техническому отчёту.

## S14. Нативные маски и резервные нейросетевые компоненты

- [Meshroom: штатные входы масок](https://meshroom-manual.readthedocs.io/en/latest/tutorials/turntable/turntable.html).
- [SAM 2: статья авторов, ограничения метода](https://arxiv.org/html/2408.00714v1).
- [Grounded-SAM 2: авторский репозиторий](https://github.com/IDEA-Research/Grounded-SAM-2).
- [LightGlue: авторский репозиторий](https://github.com/cvg/LightGlue).

Нативный ImageMasking уже применён: белая HSV-маска Dice перед FeatureExtraction и в PrepareDenseScene, серая маска synthetic — только в PrepareDenseScene. Это цветовые маски исходных пикселей, не подгонка 3D-границы под эталон. SAM 2 допускает ошибки на тонких деталях; Grounded-SAM 2 связывает текстовое выделение с сегментацией; LightGlue сопоставляет локальные признаки, включая SIFT. Эти нейросетевые компоненты не установлены и остаются резервом. Ни одна ссылка не доказывает метрические детали собственной беседки или проверенный стык нового matcher с Meshroom.

## S15. Codex как исполнитель

- [OpenAI: Codex CLI](https://learn.chatgpt.com/docs/codex/cli).
- [OpenAI: инструкции проекта в AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Подтверждают работу Codex с локальным репозиторием и терминальными инструментами, настройки разрешений и использование AGENTS.md. В доступном окружении дополнительно прочитаны `codex --version` и `codex --help` (CLI 0.169.0); это не выбор обязательной версии и не проверка доступа к Vast.ai с машины владельца. Решение сначала использовать Codex, а перенос в Hermes рассмотреть позже — договорённость проекта. Сравнение надёжности двух агентов здесь не проводилось.

## S16. Закреплённый runtime пилота

- [Meshroom 2023.3.0, официальный релиз](https://github.com/alicevision/Meshroom/releases/tag/v2023.3.0).
- [Linux-архив релиза](https://github.com/alicevision/Meshroom/releases/download/v2023.3.0/Meshroom-2023.3.0-linux.tar.gz).
- [AliceVision 3.2.0: сборка с CCTag/CUDA](https://github.com/alicevision/AliceVision/blob/v3.2.0/docker/Dockerfile_centos).

Использован Meshroom 2023.3.0 / AliceVision 3.2.0, CUDA 11, Linux x86_64. Архив: 1,244,889,970 байт; SHA256 `92b81246356df3fd37ea08e1d09519392897aaa730843eb9fd4bd0582916d391` вычислен при фактическом скачивании, это не подпись издателя. Нативные CCTag3, SfMTransform и плотные GPU-этапы проверены запуском. Прямым AliceVision-командам нужен bundled `aliceVision/lib` в `LD_LIBRARY_PATH`; рецепт сохраняет `env.sh`.

## S17. Проверенный интерфейс Vast и пределы сторожа

- [vast-cli 1.11.2: операции инстансов](https://github.com/vast-ai/vast-cli/blob/v1.11.2/vastai/api/instances.py), [HTTP-клиент](https://github.com/vast-ai/vast-cli/blob/v1.11.2/vastai/api/client.py).
- [Создание инстанса](https://docs.vast.ai/cli/reference/create-instance), [оплата](https://docs.vast.ai/guides/reference/billing), [ключ контейнера](https://docs.vast.ai/guides/instances/docker-environment).

Фактически работает `/api/v1/instances/`; старый список v0 вернул `deprecated_endpoint`. Нативный `stop` использует PUT `/api/v0/instances/{id}/`. Штатного предела общей суммы/TTL у create нет. Сторож использует только per-instance ключ и запущен; его ожидание не доказывает остановку. Он сохраняет данные и платный диск, зависит от работоспособности ноды и не гарантирует бюджет. Выгрузка, контроль SHA256 и проверка destroy остаются отдельной приёмкой.

## S18. Инициализация графа и перенос масштаба

- [meshroom_batch 2023.3.0](https://github.com/alicevision/Meshroom/blob/v2023.3.0/bin/meshroom_batch), [CameraInit](https://github.com/alicevision/Meshroom/blob/v2023.3.0/meshroom/nodes/aliceVision/CameraInit.py).
- [Graph.load и проверка UID](https://github.com/alicevision/Meshroom/blob/v2023.3.0/meshroom/core/graph.py), [SfMTransform](https://github.com/alicevision/AliceVision/blob/v3.2.0/src/software/utils/main_sfmTransform.cpp).

`initialize` выполняется до `--overrides`: известный FOV синтетического входа задаётся в шаблоне заранее. Фактические fx=1000 px проверены. У связанных входов `--paramOverrides` не удалил рёбра; простая правка сохранённого графа оставила конфликт UID. Адаптер меняет сериализованные входы, загружает их как native template и оставляет пересчёт UID Meshroom. Приняты только новые UID и реальные команды всех четырёх плотных узлов с масштабированным ABC; прежний unscaled-кэш отклонён. На синтетических 10 видах метки 0/1 дали baseline 100.0 мм после SfMTransform. Это проверка заданной виртуальной базы.

## S19. Данные и происхождение масштаба

- [Dice, alansartlog, закреплённый README/лицензия](https://gitlab.com/api/v4/projects/8723847/repository/files/README.md/raw?ref=78e0a887ba5263da66910fb4f4da0d9763e9177a): CC BY 4.0, revision `78e0a887ba5263da66910fb4f4da0d9763e9177a`.
- [Pinecones CCTAG, Natowi](https://github.com/natowi/cctag-dataset/tree/a04bedff34800e876c08bf1e4a46699d4a6439db): CC BY-SA 4.0, revision `a04bedff34800e876c08bf1e4a46699d4a6439db`.
- [Официальный банк CCTag3](https://github.com/alicevision/CCTag/blob/71021443af3f7946e8e9025a37634b57e7aad77d/markersToPrint/generators/cctag3.txt).

Проверены Git blob и собственные SHA256: 20 фото Dice и 50 Pinecones. У реального CCTag-набора не найдено контрольного физического расстояния; его нельзя назначать по картинке. Дополнение `make_marker_fixture.py` рисуется Pillow, использует закреплённые радиусы и известную виртуальную базу 100 мм. Оно не подменяет реальную съёмку и её метрическую приёмку.

## S20. Поворотный стол: инструкция и опыт сообщества

- [Meshroom: turntable](https://meshroom-manual.readthedocs.io/en/latest/tutorials/turntable/turntable.html).
- [Обсуждение пользователей](https://www.reddit.com/r/photogrammetry/comments/sdso0r/).

Штатное руководство предлагает Minimal 2D Motion=2 px и маски в FeatureExtraction и PrepareDenseScene. В обсуждении есть личные сообщения об успешных и неуспешных опытах, зависимости от фона, бликов и текстуры. Это опыт сообщества, не сравнительный бенчмарк и не основание менять выбранный стек. Настройка и маски применяются к конкретной наблюдаемой проблеме.

## S21. Helper points и содержимое плотного облака

- [Meshing 2023.3.0: параметры и UID](https://github.com/alicevision/Meshroom/blob/v2023.3.0/meshroom/nodes/aliceVision/Meshing.py).
- [AliceVision 3.2.0: экспорт облака](https://github.com/alicevision/AliceVision/blob/v3.2.0/src/software/pipeline/main_meshing.cpp), [обработка сетки](https://github.com/alicevision/AliceVision/blob/v3.2.0/src/aliceVision/mesh/meshPostProcessing.cpp).

`saveRawDensePointCloud=true` сохраняет облако до graph cut, удаляя точки без наблюдений; флаг имеет `uid=[]` и сам не инвалидирует кэш. `maxNbConnectedHelperPoints=0` штатно исключает helper-точки поверхности. Раздутые границы наблюдались у отклонённых диагностических результатов; финальное принятое облако получено штатной маской серого фона. Вклад helper/remap не установлен. Подгонка границы под известный размер не является проверкой точности.

## Как обновлять этот список

После принятой проверки дополнять фактические версии, команды и ссылку на карточку результата. Не повышать доказанность по одному чтению документации. Новые источники нужны при изменении решения или конкретном техническом вопросе, а не ради расширения каталога.
