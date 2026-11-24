# Автоматические маски объекта для Meshroom

Генератор получает проверенные снимки и текст объекта, сохраняет PNG, диагностику
и наложения на настоящие фотографии. Это отключаемый шаг перед обычным harness.
**Статус на 22 ноября 2026: GPU inference, native PNG/EXR и новый Standard
cloud/mesh проверены на 37 кадрах.** Маски убрали пол, сохранили широкую лицевую
поверхность; боковины и нижние края остаются неполными. [Сопоставимые виды и ресурсы](reports/2026-11-22/auto-masks.md).
GPU удалена, backup проверен, текущий ledger $0.255. Независимая приёмка PASS —
в [Goal #12](goal-12.md), поставка [PR #13](https://github.com/Kwentin3/photogrammetry-to-cad/pull/13).

## Окружение и сохранённые файлы

Используется отдельное Linux x86_64 / Python 3.12 окружение: torch 2.5.1,
torchvision 0.20.1, transformers 4.51.3, SAM2.1-small и HF GroundingDINO-tiny.
[Lock с хэшами](../requirements-auto-masks-linux-py312.txt) фиксирует зависимости;
[manifest моделей](../configs/auto-mask-models.json) — исходники, веса, tokenizer
и конфиги. Базовый bootstrap и Python Meshroom остаются прежними.

При обновлении ML-версий сначала изменить `requirements-auto-masks-linux-py312.in`
и пересобрать `.txt` с хэшами. В том же изменении синхронизировать `expected`
в `scripts/mask_models.py`, version assertions в `scripts/bootstrap_auto_masks.sh`
(включая CUDA build suffix `+cu124`) и версии в этой инструкции. Эти проверки
намеренно закрепляют принятую комбинацию. Новую комбинацию проверить в свежем
отдельном окружении: bootstrap, один настоящий кадр, затем полный набор;
результаты прежнего GPU-прогона не квалифицируют обновлённые зависимости.

До запуска сохранить вне Git полный wheelhouse из lock, архив исходников SAM2
и все файлы моделей по manifest. Для крупных передач использовать параллельную
загрузку/aria2 или rclone, проверяя скорость и SHA. Bootstrap ничего не скачивает.
Нужны Ubuntu 24.04 с `python3.12-venv`, совместимые NVIDIA driver/GPU и отдельный
допуск на платный запуск. Сам рецепт такого допуска не предоставляет.

Linux-команды ниже выполняются в свежем SSH shell **до source окружения Meshroom**.
Пути — пример размещения; каждый новый bootstrap/run/job получает новый каталог.
Пределы RAM/VRAM, срок аренды и остановка принадлежат [облачному runbook](runbook.md).

```bash
set -euo pipefail
export REPO=/root/photo-cad/repo WORK=/root/photo-cad/work
export ML_ENV="$WORK/auto-masks-env-01" MODELS="$WORK/auto-mask-models"
mkdir -p "$WORK/jobs" "$WORK/config"
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/auto-masks-setup-01" 900 -- \
  bash "$REPO/scripts/bootstrap_auto_masks.sh" "$ML_ENV" \
  --wheelhouse "$WORK/auto-mask-wheelhouse" \
  --sam-source "$MODELS/sam2-2b90b9f5ceec907a1c18123530e92e794ad901a4.tar.gz"
source "$ML_ENV/env.sh"
```

Bootstrap проверяет source SHA, устанавливает пакеты offline и пишет
`environment.json`. SAM2 устанавливается с `SAM2_BUILD_CUDA=0`: необязательного
CUDA extension нет. Predictor использует `max_hole_area=0` и
`max_sprinkle_area=0`; мелкие дырки/пятна автоматически не исправляются.
HF detector использует штатный PyTorch с отключёнными custom kernels.

## Снимки и настройки

Подготовить capture manifest штатной командой `reconstruction.py manifest` из
[runbook](runbook.md). CLI принимает минимум два кадра по контракту capture verifier;
нужны все перечисленные снимки с неизменными SHA и байтами.
Скопировать [пример настроек](../configs/auto-masks.example.json) вне Git и изменить
его поля. Все пути разрешаются относительно **файла настроек**, не текущей папки.

```json
{
  "schema_version": 1,
  "images": "../capture/images",
  "input_manifest": "../capture/manifest.json",
  "models_manifest": "/root/photo-cad/repo/configs/auto-mask-models.json",
  "model_directory": "../auto-mask-models",
  "prompt": "a wooden chair.",
  "selection": "single",
  "box_threshold": 0.3,
  "text_threshold": 0.25,
  "device": "cuda",
  "preview_count": 6
}
```

Это общий пример: объект задаётся `prompt`, другая съёмка — images/manifest.
`single` требует ровно один найденный объект; `union` явно объединяет все
подходящие экземпляры. Ноль находок и несколько при `single` означают ошибку
с сохранёнными boxes, а не первую находку/белую маску. Пороги задаются явно;
доступны `cpu`, `cuda`, `cuda:N`. CPU не квалифицирован по скорости.

Площадь каждой выбранной SAM-маски записывается до объединения в
`frames[].segments`: `candidate_index` (индекс с нуля в `candidates` этого кадра),
`keep_pixels`, `keep_fraction`, `zero`, `full` и SAM score. Пустая или полная
маска любого выбранного экземпляра означает ошибку кадра даже при непустом
общем `union`. Частичный PNG и previews сохраняются для разбора, run получает
`status=error` и не публикует успешный контракт `mask_inputs`.

```bash
export MASK_SETTINGS="$WORK/config/auto-masks.json" MASK_RUN="$WORK/masks/run-01"
"$AUTO_MASK_PYTHON" "$REPO/scripts/generate_masks.py" --settings "$MASK_SETTINGS" --validate-only
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/auto-masks-01" 600 -- \
  "$AUTO_MASK_PYTHON" "$REPO/scripts/generate_masks.py" \
  --settings "$MASK_SETTINGS" --output "$MASK_RUN"
```

`--help` и `--validate-only` не импортируют ML. Проверка входов сверяет снимки
и все локальные файлы моделей; это не inference. Первый GPU smoke на одном кадре
в пилоте вызывается отдельно через actual `ModelInference`, затем CLI обрабатывает
полный manifest в новом MASK_RUN. Отдельного режима одного кадра у CLI нет.
Существующий output не перезаписывается; после ошибки сохраняются частичные PNG
и `mask-diagnostics.json` со статусом `error`. Перед повтором проверить status
своего remote_job и завершение его дерева. Успешный run имеет `status=complete`.

## Проверить маски, затем передать штатному графу

В `masks/` каждый `<source_stem>.png` — grayscale, только 0/255: 0 исключить,
255 оставить. Stem должны быть уникальны. Размеры и ориентация — raw raster
исходника: EXIF записывается, `exif_transpose` и скрытый resize не применяются.
Штатные APIs возвращают bbox/маску в исходные пиксели; неверные W/H блокируются.

Проверить `mask-diagnostics.json`: SHA источников/настроек/моделей, число кандидатов,
площади, empty/full/errors, касание края, время, peak RSS и CUDA allocated/reserved.
Открыть 4–8 файлов `previews/` (все при меньшем наборе), включая min/max и подозрительные.
Убедиться, что выделен нужный объект, сохранены края/отверстия, фон исключён.
Счётчики и confidence не подтверждают семантику. Ручную правку/исключение кадра
зафиксировать отдельно и создать новый набор/run; исходный результат сохранить.

После просмотра задать в копии обычного Standard settings:

```json
"masks": {"folder": "../masks/run-01/masks", "extension": "png", "features": false, "invert": false}
```

Это фрагмент reconstruction settings, не самостоятельный JSON. Для пилота маски
влияют только на dense: фон остаётся для оценки камер неподвижного объекта.
Для turntable такой выбор не квалифицирован. В свежем shell загрузить Meshroom
env и выполнить обычные prepare/verify/compute/export из [runbook](runbook.md)
с новым RUN/cache. Сверить native mask path/SHA каждого source с producer diagnostic:
native lookup сначала ищет viewId, потом stem. Prepare проверяет реальный reader/W/H.
До MVS нужны успешные native preflight и dense-image QA; затем открыть cloud/mesh
и сравнить с обычным Standard на тех же кадрах/настройках.
Для отключения задать `masks: null`, новый RUN и запускать прежний базовый рецепт.

## Повтор с принятым native cache после переноса

Для новой съёмки остаётся обычный prepare выше. Для **повтора того же принятого
опыта** одного source SHA недостаточно: AliceVision может включать файловый mtime
в view UID при отсутствии DateTimeOriginal/imageCounter/DateTime; при недостатке
device metadata имеет значение и путь. Это видно в [закреплённом uid.cpp, строки 20–94](https://github.com/alicevision/AliceVision/blob/d012d05589b528dcf57a2a0c805c0a5709df8613/src/aliceVision/sfmData/uid.cpp#L20-L94).
В пилоте архив с нормализованным `mtime=0` сохранил байты, пути и image metadata,
но дал 74 отличия view/pose ID. Перегенерированные IDs не совместимы с прежним cache.

Владельцем прежней идентичности служат сохранённые native CameraInit inputs.
После сверки baseline/снимков/настроек подготовить полный новый шаблон с масками
и прежним явным cache через `prepare ... --cache ...`. Затем в **новом** RUN
импортировать только принятые CameraInit inputs штатным SDK, обновить graph,
сохранить проект и заново связать mask receipt с actual CameraInit. Не переносить
UID/status вручную и не менять solved geometry. Ниже содержимое короткого Python
шага для существующего `remote_job.sh` в окружении Meshroom; BASELINE, PREPARED,
BRANCHED — проверенный прежний, новый подготовленный и ещё не существующий RUN.
Этот дополнительный рецепт повторяет принятый baseline Goal #6; новая съёмка
использует обычный `prepare` выше и собственную CameraInit.

```python
import copy, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[4]) / 'scripts'))  # REPO
from reconstruction import (load, settings, sha, write, outside, node, preflight_masks,
                            validate_masks, camera_mask_views)
_, old, _, _ = load(sys.argv[1])       # BASELINE
_, current, graph, module = load(sys.argv[2])  # PREPARED
target = outside(sys.argv[3])         # BRANCHED; reject checkout before mkdir
target.mkdir(exist_ok=False)
with module.GraphModification(graph):
    settings(graph.node('CameraInit_1'),
             copy.deepcopy(old['nodes']['CameraInit_1']['inputs']))
graph.update()
project = target / 'project.mg'
graph.save(str(project))
effective = copy.deepcopy(current)
effective.update(project=str(project), nodes={n.name: n.toDict() for n in graph.nodes},
    camera_init_provenance={'source_project': old['project'],
        'source_project_sha256': sha(old['project']), 'preserved_native_inputs': True})
effective['mask_inputs'] = validate_masks(
    *preflight_masks(pathlib.Path(effective['settings_file']).parent,
                     effective['settings']['masks']),
    camera_mask_views(graph.node('CameraInit_1')))
write(target / 'effective-settings.json', effective)
_, saved, graph, _ = load(target)
graph.update()
assert all(graph.node(name).toDict()['uid'] == value['uid']
           for name, value in saved['nodes'].items())
assert camera_mask_views(graph.node('CameraInit_1')) == [
    {key: frame[key] for key in ('image', 'view_id', 'width', 'height')}
    for frame in saved['mask_inputs']['files']]
dense = {node(graph, kind).name for kind in
         ('ExportImages', 'DepthMap', 'DepthMapFilter', 'Meshing')}
upstream = (set(old['nodes']) & set(saved['nodes'])) - dense
assert len(upstream) == 11  # Accepted pinned baseline/template in this repeat
assert all(saved['nodes'][name]['uid'] == old['nodes'][name]['uid'] for name in upstream)
assert all(saved['nodes'][name]['uid'] != old['nodes'][name]['uid'] for name in dense)
planned, _ = graph.dfsToProcess(startNodes=graph.findNodes([saved['result_nodes']['meshing']]))
assert {n.name for n in planned} == dense  # Before the first masked ExportImages
write(target / 'native-plan.json', {'nodes': [n.name for n in planned]})
```

Сохранить код в `$WORK/branch.py` и вызвать внутри штатного bounded job:

```bash
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/branch-masked-01" 180 -- \
  "$MESHROOM_PYTHON" "$WORK/branch.py" "$BASELINE" "$PREPARED" "$BRANCHED" "$REPO"
```

Проверить план перед
compute: в пилоте полный граф имел 18 nodes, 11 upstream UID совпали; изменились
только ExportImages, DepthMap, DepthMapFilter и Meshing. Native план содержал эти
четыре узла, после успешного ExportImages — три. Иной план требует разбора до MVS.

## Что фактически проверено на GPU

Offline ML bootstrap завершился за 74 с, runtime bootstrap — за 17 с.
Генератор обработал все 37 сохранённых кадров с `prompt="cereal box."`:
`status=complete`, failed=0, ambiguous=0, на каждом кадре ровно один candidate.
Общее время — 21.8959 с; генерация — 13.7498 с, загрузка моделей — 4.7242 с,
проверка входов — 1.1729 с. Peak RSS — 1858478080 байт; CUDA allocated/reserved —
2190115840 / 2361393152 байт. Это измерения данного запуска, не требования к минимуму RAM.

На восьми просмотренных overlays коробка выделена, пол исключён. На кадрах
00000/00006/00012 местами потеряна узкая тёмная нижняя грань; на 00084/00090 верх
уже обрезан исходной съёмкой. Ручных правок и исключённых кадров не было.
Native PNG binding и чтение прошли для 37/37 кадров. Все 37 EXR прошли dense-image
QA/alpha: 54.16–70.42% пикселей стали прозрачным фоном, RGB непрозрачной области
точно совпал с baseline. После MVS actual cloud/mesh прочитаны Open3D и просмотрены
с двух одинаковых ракурсов: пол исключён, широкая лицевая панель сохранена,
боковины и нижние края остаются неполными/неровными. Физический масштаб неизвестен;
полезность и ограничения отделены от работы интеграции в [отчёте](reports/2026-11-22/auto-masks.md).
