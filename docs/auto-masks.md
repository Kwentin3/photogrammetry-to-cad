# Автоматические маски объекта для Meshroom

Генератор получает проверенные снимки и текст объекта, сохраняет PNG, диагностику
и наложения на настоящие фотографии. Это отключаемый шаг перед обычным harness.
**Статус: локальная подготовка; inference моделей и маскированная реконструкция
ещё не выполнены.** Обязательная практическая проверка остаётся в [Goal #12](goal-12.md).

## Окружение и сохранённые файлы

Используется отдельное Linux x86_64 / Python 3.12 окружение: torch 2.5.1,
torchvision 0.20.1, transformers 4.51.3, SAM2.1-small и HF GroundingDINO-tiny.
[Lock с хэшами](../requirements-auto-masks-linux-py312.txt) фиксирует зависимости;
[manifest моделей](../configs/auto-mask-models.json) — исходники, веса, tokenizer
и конфиги. Базовый bootstrap и Python Meshroom остаются прежними.

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
и сравнить с обычным Standard на тех же кадрах/настройках. Этот этап ещё не выполнен.
Для отключения задать `masks: null`, новый RUN и запускать прежний базовый рецепт.
