# Фото/видео → облако, mesh и связанные результаты

Текущий [Goal #8](goal-8.md) сохраняет обычный JSON съёмки, полный native Meshroom
project/cache и штатный CLI. Принятое видео Goal #6 дало **37 кадров**; оба графа
прошли Meshing, создав dense cloud и отдельный raw OBJ. В Goal #8 эти сохранённые
выходы фактически прочитаны локально, без повторного расчёта. Для базовой съёмки выбран Standard без PDS adapter;
результаты и ограничения — в [отчёте](reports/2026-11-21/photo-video-3d.md).
Команда в инструкции не означает приёмку результата. Актуальный статус — в Goal,
дополнительные режимы и зависимости — в [матрице](meshroom-modes.md).
Выделение деталей и построение CAD остаются следующим отдельным этапом.

Быстрый выбор: обычное фото/видео → Standard → Meshing (облако **и** raw mesh);
метки CCTag3 → Legacy. Фильтрация и текстуры — отдельное продолжение того же
полного графа. Для масок, стола и переворота сначала открыть соответствующую
строку [карты сценариев](meshroom-modes.md), затем нужный рецепт.
Для готового backup можно сразу перейти к [локальному отчёту](#локальный-отчёт).
Базовый бюджет Goal #8 — $0: новая аренда для чтения сохранённых файлов не нужна.

Завершённый Goal #4 сохраняет
[полный принятый рецепт 2026](https://github.com/Kwentin3/photogrammetry-to-cad/blob/b907fb4c95f3d0c9a5a3150b45e15f2057389509/docs/runbook.md),
[подготовку исторических наборов](https://github.com/Kwentin3/photogrammetry-to-cad/blob/b907fb4c95f3d0c9a5a3150b45e15f2057389509/scripts/prepare_graphs_2026.py)
и [отчёт](reports/2026-11-21/meshroom-2026.md). Для обычной новой съёмки читать их
не требуется. Исправленная 2023.3 —
[историческая точка возврата](https://github.com/Kwentin3/photogrammetry-to-cad/blob/f3173b3fdfe27f7e760b84e23f6845b11a937b65/docs/runbook.md).

## До аренды: файлы, доступ и пределы

Нужны полная постоянная копия runtime, съёмка, место для backup, доступ к Vast/SSH
и действующий денежный допуск. Для #6 подтверждены **$0.60/ч, 4 часа от первой
аренды, $25 суммарно**, включая диск/трафик; автоматический stop — через 3.5 часа.
Повтор/смена ноды не обнуляют срок и бюджет. Другой Goal требует сверки допуска.

Данные, параметры конкретной съёмки, кэш, карточка аренды, ключи и частные адреса
хранятся **вне Git**. Приведённые команды обычные; агент передаёт их обязательному
ограничителю своей среды. На Windows нужны PowerShell, Python 3.11, Git,
OpenSSH, tar и готовый rclone. Существующую venv повторно создавать не нужно;
новая устанавливается из `requirements-lock-win-py311.txt`.

```powershell
$repo='D:/src/photogrammetry-to-cad'
$work='D:/photogrammetry-work/goal6'
$python="$work/venv/Scripts/python.exe"
$vastai="$work/venv/Scripts/vastai.exe"
$pin=Get-Content "$repo/configs/runtime-2026.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$archive=[IO.Path]::GetFullPath((Join-Path $repo $pin.retained_copy_relative_to_checkout))
if ((Get-Item $archive).Length -ne $pin.archive_bytes) { throw 'Runtime size' }
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.archive_sha256) { throw 'Runtime SHA256' }
```

Ожидается `Meshroom-2026.11.21-b12ea88-linux-full.tar.gz`, 600156630 байт,
SHA256 `4ca3cfb0898b8000def4e68d513468a199b948329b63cdb6b257e427d295163b`.
Путь постоянной копии и image digest — в [runtime lock](../configs/runtime-2026.json).
Rolling nightly может исчезнуть. Без полной доступной копии ноду не арендовать;
ядра на GPU не компилировать.

До create сверить карточку, незавершённые процессы/аренды и все страницы native
`show instances-v1 --limit 25 --raw` (`--next-token` при наличии). Проверить полную
стоимость оффера, выделенные RAM/CPU, CUDA ≥12.8, драйвер ≥570.26, linux/amd64.
Пример поиска, не универсальный минимум:

```powershell
& $vastai search offers 'gpu_name=RTX_3090 num_gpus=1 cpu_arch=amd64 verified=true rentable=true direct_port_count>=1 cpu_ram>=32 disk_space>=60 cuda_vers>=12.8 dph_total<=0.60' --storage 60 --type on-demand -o dph_total --limit 5 --raw
```

## Создание, deadline и передача

Account key остаётся в защищённом контексте управляющей машины. **До create**
подготовить LF onstart, который запускает существующий `rental_deadline.sh`
из native окружения с per-instance ключом. Чтобы уложиться в onstart limit,
упаковать исходник в gzip/base64; это данные скрипта, не секрет:

```powershell
# Только для первой аренды; при повторе взять сохранённый deadlineEpoch из карточки.
$deadlineEpoch=[DateTimeOffset]::UtcNow.AddMinutes(210).ToUnixTimeSeconds()
$buffer=[IO.MemoryStream]::new()
$gzip=[IO.Compression.GZipStream]::new($buffer,[IO.Compression.CompressionMode]::Compress,$true)
$bytes=[IO.File]::ReadAllBytes("$repo/scripts/rental_deadline.sh")
$gzip.Write($bytes,0,$bytes.Length); $gzip.Dispose()
$payload=[Convert]::ToBase64String($buffer.ToArray()); $buffer.Dispose()
$onstart=@"
#!/bin/bash
set -euo pipefail
umask 077
mkdir -p /root/photo-cad/jobs
printf '%s' '$payload' | base64 -d | gzip -d >/root/photo-cad/rental_deadline.sh
nohup bash /root/photo-cad/rental_deadline.sh $deadlineEpoch /root/photo-cad/jobs/deadline >/root/photo-cad/jobs/deadline-launch.log 2>&1 </dev/null &
"@
$onstart=$onstart.Replace("`r`n","`n")
if ([Text.Encoding]::UTF8.GetByteCount($onstart) -gt 4048) { throw 'Onstart size' }
[IO.File]::WriteAllText("$work/onstart.sh",$onstart,[Text.UTF8Encoding]::new($false))
if ([IO.File]::ReadAllText("$work/onstart.sh",[Text.Encoding]::UTF8) -ne $onstart) { throw 'UTF8 readback' }
$createdUtc=[DateTimeOffset]::UtcNow.ToString('o')
& $vastai create instance OFFER_ID --image $pin.image --disk 60 --ssh --direct --cancel-unavail --label photogrammetry-goal6 --onstart "$work/onstart.sh" --raw
```

Заменить OFFER_ID проверенным оффером. Сразу записать полученный instance ID,
UTC начала, абсолютный deadline, ставки/ресурсы, commit и следующий шаг в
приватную карточку **вне GPU/Git**, до настройки SSH. При неоднозначном ответе
сначала проверить все страницы списка. Deadline после SSH не продлевать.
До расчётов проверить собственный watchdog PID, его cmdline и `state=waiting`
в state directory. Нет armed watchdog — расчёт не начинать.

По `ssh-url INSTANCE_ID` настроить приватный SSH alias с отдельным known_hosts;
после осознанного первого доверия — `StrictHostKeyChecking yes`. Передавать
исходники известного commit с SHA256 упаковки; `git archive` не включает
незакоммиченные изменения. SHA сравнить на обеих сторонах до распаковки.

Большие передачи в обе стороны — параллельно: для HTTP native aria2
(`-j8 -x8 -s8`, resume, `--checksum=sha-256=...`), для приватных файлов — rclone
1.76.0 SFTP. Приватный remote `worker` содержит host/port/user/key_file и
**known_hosts_file**; без последнего rclone по умолчанию не проверяет host key.
Проверенный профиль для OpenSSH с random-offset writes:

```powershell
$rclone="$work/tools/rclone-v1.76.0/rclone.exe"
$transfer=@('--config',"$work/rclone.private.conf",'--multi-thread-streams','8','--multi-thread-cutoff','16M','--multi-thread-chunk-size','4M','--sftp-multithread-upload','--transfers','1','--checkers','1','--retries','1','--low-level-retries','1','--timeout','30s','--contimeout','15s','--max-duration','10m','--stats','5s')
& $rclone copyto $archive "worker:/root/photo-cad/runtime/$($pin.archive_name)" @transfer
```

Не задавать `--sftp-connections`/`--sftp-disable-concurrent-writes`: они отключают
многопоточный upload. В начале измерить фактическую скорость и сопоставить размер,
срок и резерв на cleanup; `10m` — пример. После timeout/cancel подтвердить
завершение своей передачи и закрытие файлов до повтора. Доставка, облачный цикл
и полномочия подробнее описаны в [инфраструктуре](infrastructure.md).

## Linux: runtime, JSON и ресурсы

Дальше Bash на GPU. Установить системные python3/curl/ca-certificates/tar/gzip/
util-linux/coreutils/aria2 пакетным менеджером с ограниченным сроком. Пути — пример:

```bash
set -euo pipefail
export REPO=/root/photo-cad/repo WORK=/root/photo-cad/work
mkdir -p "$WORK/jobs" "$WORK/config" "$WORK/capture"
cd "$WORK"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/bootstrap" 600 -- \
  bash "$REPO/scripts/bootstrap_meshroom.sh" /root/photo-cad/runtime \
  --archive /root/photo-cad/runtime/Meshroom-2026.11.21-b12ea88-linux-full.tar.gz \
  >"$WORK/jobs/bootstrap-launch.log" 2>&1 </dev/null
```

Дождаться `state=succeeded`, `cleanup=confirmed`, прочитать probes/logs,
проверить `nvidia-smi`. Bootstrap проверяет архив/ldd/CLI/imports, не dense PASS.
Один раз создать настройки новой съёмки. Команда откажет, если файл уже существует:

```bash
(set -o noclobber; cat "$REPO/configs/reconstruction.example.json" >"$WORK/config/standard.json")
```

При первом входе и в каждом новом SSH shell заново задать все пути и загрузить
окружение. Здесь используется уже сохранённый JSON; повторно копировать шаблон
поверх него нельзя:

```bash
set -euo pipefail
export REPO=/root/photo-cad/repo WORK=/root/photo-cad/work
export MESHROOM_ROOT=/root/photo-cad/runtime/Meshroom-2026.11.21-b12ea88-linux
source "$MESHROOM_ROOT/env.sh"
export SETTINGS="$WORK/config/standard.json"
test -f "$SETTINGS"
```

После source все Linux Python-команды — только `"$MESHROOM_PYTHON"` (bundled 3.11),
включая короткие проверки JSON. Системный Ubuntu Python 3.12 получает несовместимые
frozen модули. Отредактировать копию JSON вне Git: images/input_manifest и masks
разрешаются относительно файла настроек; pipeline — standard или legacy.
Пример задаёт threads8, DSPSIFT normal/normal, DepthMap downscale2 и лимиты Meshing.
Это параметры малого опыта, не условия по имени объекта или обязательному числу
кадров. Для сравнения сделать legacy.json с теми же входами и сопоставимыми nodes.

```bash
THREADS=$("$MESHROOM_PYTHON" - "$SETTINGS" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['resources']['threads'])
PY
)
CPUS=$("$MESHROOM_PYTHON" - "$THREADS" <<'PY'
import os, sys
n=int(sys.argv[1]); allowed=sorted(os.sched_getaffinity(0))
if n<1 or n>len(allowed): raise SystemExit('threads exceed allocated affinity')
print(','.join(map(str,allowed[:n])))
PY
)
export OMP_NUM_THREADS="$THREADS" OPENBLAS_NUM_THREADS="$THREADS" OMP_THREAD_LIMIT="$THREADS"
```

`taskset` ниже выбирает первые N доступных CPU, не предполагаемые 0..7.
Он **не ограничивает RAM**. До MVS проверить выделенный cgroup memory.max
(либо v1 memory.limit_in_bytes), записать допустимый RSS/VRAM и наблюдать своё
дерево. RAM хоста не равен выделению контейнера. При отсутствии подтверждённого
hard cap согласованный RSS-порог означает ручную адресную остановку, не защиту от OOM.

## Вход: фотографии или видео

Фотографии: flat capture/images, резкие перекрывающиеся виды неподвижного объекта
с параллаксом. Посторонние подпапки, symlinks и неучтённые изображения отвергаются.

```bash
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" manifest "$WORK/capture/images" \
  --source 'Источник, автор/дата съёмки и условия использования' --output "$WORK/capture/manifest.json"
```

Видео: сохранить настоящий исходный ролик и keyframe.json вне Git. Ниже native
настройки, давшие 37 из 220 кадров Objectron; для другой длительности/резкости
параметры меняются в JSON. Общий код ничего не знает об Objectron или числе 220.

```json
{
  "selectionMethod.useSmartSelection": false,
  "selectionMethod.regularSelection.minFrameStep": 1,
  "selectionMethod.regularSelection.maxFrameStep": 0,
  "selectionMethod.regularSelection.maxNbOutFrames": 40,
  "renameKeyframes": false,
  "outputExtension": "jpg"
}
```

```bash
"$MESHROOM_PYTHON" "$REPO/scripts/video_frames.py" prepare "$WORK/capture/video.MOV" \
  "$MESHROOM_ROOT" "$WORK/capture/video-keyframes.mg" --output "$WORK/capture/images" --settings "$WORK/config/keyframe.json"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/keyframes" 180 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$WORK/capture/video-keyframes.mg" \
  --cache "$WORK/capture/video-keyframes.cache" --toNode KeyframeSelection_1 \
  >"$WORK/jobs/keyframes-launch.log" 2>&1 </dev/null
# После succeeded/cleanup=confirmed и просмотра кадров:
"$MESHROOM_PYTHON" "$REPO/scripts/video_frames.py" seal "$WORK/capture/images" \
  --source "$WORK/capture/video.MOV" --output "$WORK/capture/manifest.json"
```

Prepare создаёт один native узел, project/cache и source receipt. Seal сверяет
source SHA, проект, native views и точные файлы. Numeric filenames при
renameKeyframes=false сохраняют zero-based source indices; native frameId не
считается индексом. Для VFR не делить индекс на номинальный fps. Необязательный
`seal --probe ffprobe.json` связывает файл метаданных по SHA; timestamps требуют
реального decoded-frame mapping. Проверить всю траекторию, blur, перекрытие и
portrait orientation до MVS. При blur доступен native smart отбор по sharpness/flow;
он изучен по интерфейсу, но в Goal #6 реально проверен только regular отбор.
Отдельный самописный ранжировщик не нужен.

## Подготовка, sparse, масштаб, dense и экспорт

Стадии запускать последовательно, проверяя завершение предыдущей и остаток
deadline с резервом на backup. TTL ниже — явные примеры. Для Standard/Legacy
использовать разные RUN и JOB_DIR, сохраняя одинаковые изображения/manifest.

```bash
export RUN="$WORK/runs/standard"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/prepare-standard" 300 -- \
  taskset -c "$CPUS" "$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" prepare "$SETTINGS" "$RUN" "$MESHROOM_ROOT" \
  >"$WORK/jobs/prepare-standard-launch.log" 2>&1 </dev/null
```

Prepare проверяет manifest, применяет настройки **до native CameraInit**,
загружает установленный template и сохраняет project.mg/cache/effective-settings.json.
Сохраняется весь шаблон, включая MeshFiltering, Texturing и CopyFiles;
это не запускает их. `result_nodes` содержит реальные имена конечных узлов.
Existing RUN не перезаписывается. От prepare до завершения входные настройки,
manifest, изображения и выбранные маски сохраняются неизменными. Команда `verify`
без загрузки runtime сверяет их с сохранёнными SHA и receipt масок; перед каждым
native compute требуется её успешное завершение. После succeeded прочитать
фактический маршрут:

```bash
mapfile -t ROUTE < <("$MESHROOM_PYTHON" - "$RUN/effective-settings.json" <<'PY'
import json, sys
e=json.load(open(sys.argv[1])); p=e['settings']['pipeline']
for k in ('project','cache','sparse_node','dense_node'): print(e[k])
kind='ExportImages' if p=='standard' else 'PrepareDenseScene'
names=[n for n,v in e['nodes'].items() if v['nodeType']==kind]
if len(names)!=1: raise SystemExit('ambiguous native producer')
print(names[0])
PY
)
[[ ${#ROUTE[@]} == 5 ]]
PROJECT=${ROUTE[0]}; CACHE=${ROUTE[1]}; SPARSE=${ROUTE[2]}; DENSE=${ROUTE[3]}; IMAGES_NODE=${ROUTE[4]}
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/sparse-standard" 900 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode "$SPARSE" \
  >"$WORK/jobs/sparse-standard-launch.log" 2>&1 </dev/null
```

После sparse вызвать scale **даже при unknown**: он сохраняет native sparse JSON
и scale-plan. При известной базе добавляет подтверждённое преобразование;
последующий native compute выполнит его как предка dense images.

```bash
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/scale-standard" 120 -- \
  taskset -c "$CPUS" "$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" scale "$RUN"
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/images-standard" 600 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode "$IMAGES_NODE" \
  >"$WORK/jobs/images-standard-launch.log" 2>&1 </dev/null
```

Standard использует **ExportImages**, без PDS adapter. Legacy использует
**PrepareDenseScene**. Если Legacy вернул успех, но нулевой chunk не создал полный
набор EXR, после проверки sparse/transform и завершения job применить существующий
adapter отдельным новым JOB_DIR, **до dense QA**:

```bash
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/pds-adapter-legacy" 600 -- \
  taskset -c "$CPUS" "$MESHROOM_PYTHON" "$REPO/scripts/prepare_dense_images.py" "$PROJECT" --cache "$CACHE" \
  >"$WORK/jobs/pds-adapter-legacy-launch.log" 2>&1 </dev/null
```

Он вызывает native command builder целой сцены, не меняет граф/UID/status.
Не назначать фиктивный SUCCESS. Судьбу adapter решает реальное сравнение графов.
До DepthMap проверить фактический route и все EXR:

```bash
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/qa-standard" 300 -- \
  taskset -c "$CPUS" "$MESHROOM_PYTHON" "$REPO/scripts/check_dense_images.py" "$RUN"
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/dense-standard" 1800 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode "$DENSE" \
  >"$WORK/jobs/dense-standard-launch.log" 2>&1 </dev/null
# После успешного Meshing:
bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/export-standard" 180 -- \
  taskset -c "$CPUS" "$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" export "$RUN"
```

Checker требует exit0 и dense-images-check.json status=passed: точные DepthMap
input/imagesFolder, зарегистрированные view IDs, размеры/конечность RGBA/alpha
и metadata. Для ExportImages нужны EXR/viewid/обычный image window; его exposure
metadata отличаются от PDS projection fields. Если compute заново записал EXR,
повторить QA новых байтов. Export берёт точные native outputs графа и создаёт
scene.json/dense.ply и байтовую копию отдельного Meshing.outputMesh (обычно
mesh.obj); при известном масштабе — SHA-bound scale-evidence.json.
`artifacts.mesh/native_mesh` и `mesh_export` записывают точные пути/хэш/размер.
OBJ, FBX и STL — отдельные native файлы. Для glTF exporter сохраняет весь
Meshing UID-каталог в `meshing-output`, чтобы не потерять соседний buffer;
это упаковка файлов, не новый расчёт или проверка glTF конкретным просмотрщиком.
Не выбирать первый попавшийся UID/glob.

Повторить стадии Legacy с его SETTINGS/RUN и другими JOB_DIR. Сохранить отдельные
outputs, время и ручные действия; сравнить восстановленные части, пропуски и
искажения. Количество точек и smooth mesh не доказывают физическую точность.

## Продолжить до фильтрации или текстур

После Meshing можно остановиться: облако и raw mesh уже созданы. В полном графе
новой подготовки доступны `result_nodes.meshing/filtering/texturing`.
Выбрать только нужный конец; этот пример — рецепт для среды с разрешённым
вычислением, в Goal #8 он не запускает новую GPU:

```bash
TARGET_KIND=filtering # либо texturing
TARGET=$("$MESHROOM_PYTHON" - "$RUN/effective-settings.json" "$TARGET_KIND" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['result_nodes'][sys.argv[2]])
PY
)
"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/$TARGET_KIND-standard" 900 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode "$TARGET" \
  >"$WORK/jobs/$TARGET_KIND-standard-launch.log" 2>&1 </dev/null
```

Сначала задать нужные настройки **при подготовке**. MeshFiltering по умолчанию
включает сглаживание: для одной очистки отключить его явно; raw mesh сохранять
отдельно. Менять JSON завершённого RUN нельзя: это требует новой подготовки с
новыми settings/RUN; native UID может повторно использовать неизменённые upstream
этапы только при явно сохранённом том же кэше. Здесь изменение настройки не
подменяет продолжение исходного неизменённого проекта.

Для новой конфигурации после подтверждённого завершения прежнего JOB можно
передать прежний native cache явно: `reconstruction.py prepare "$NEW_SETTINGS"
"$NEW_RUN" "$MESHROOM_ROOT" --cache "$CACHE"` (одна строка shell-команды).
Без `--cache` новый RUN получает свой cache. Не запускать конфликтующие вычисления
в общем кэше одновременно. При backup учитывать фактический `effective.cache`,
который с этой опцией может находиться вне нового RUN.

Без forceCompute native planner пропускает SUCCESS chunks. Нужны сохранные
файлы, их UID/статусы и неизменные входы. Новый JOB_DIR для новой цели; `--resume`
только для прежних argv/cwd. Старые урезанные проекты #6 сами не обретают удалённые
узлы: они остаются историческими, полнота графа относится к новой подготовке.
Локальный native planner #8 сохранил старые UID после восстановления downstream
в приватных копиях; Standard планировал только filter/texture, Legacy ещё PDS.
Filtering/Texturing на Linux в этом Goal не вычислялись. Подробнее —
[native рецепты и ограничения](meshroom-modes.md#продолжение-штатного-графа).

Texturing выдаёт комплект: OBJ + MTL + все карты/UDIM tiles (либо связанные файлы
выбранного формата), а не один mesh. После успеха сохранить весь native output
каталог, сверить ссылки и открыть комплект. CopyFiles сохранён в графе, но
не выполняется при `--toNode Texturing`: публикация им — отдельная native цель
с явно настроенным каталогом. Текстурированная выдача здесь остаётся рецептом.

## Наблюдение и продолжение

Существующий remote_job.sh использует flock, timeout и атомарный status;
переживает SSH disconnect. Linux subreaper `owned_process.py` охватывает также
native workers, создающие отдельные сессии. Отдельный receipt попытки подтверждает
отсутствие оставшихся потомков через kernel ECHILD; один PGID этого не доказывает.
Перед ресурсоёмкой стадией выбрать порог RSS/VRAM и наблюдать всё своё дерево:

```bash
PGID=$(cat "$JOB/process_group")
LOG=$(sed -n 's/^log=//p' "$JOB/status")
RECEIPT=${LOG%.log}.owned-process
OWNER=$(sed -n 's/^subreaper_pid=//p' "$RECEIPT")
"$MESHROOM_PYTHON" - "$REPO/scripts" "$OWNER" <<'PY'
import sys, subprocess
sys.path.insert(0, sys.argv[1])
from owned_process import descendants
pids=descendants(int(sys.argv[2]))
if pids:
    subprocess.run(['ps','-p',','.join(map(str,pids)), '-o','pid,ppid,pgid,rss,comm'], check=True)
PY
tail -n 40 "$LOG"
# Только после сверки JOB/PGID/command.txt с карточкой — остановка своего дерева:
kill -TERM -- "-$PGID"
```

После timeout/cancel/unknown проверить status и receipt: обоим требуется
`cleanup=confirmed`. Helper даёт TERM 15 секунд, затем KILL и до 5 секунд на
подтверждение; внешний запас остановки — 25 секунд сверх TTL. Unknown/missing
receipt запрещает resume и требует проверки оставшихся PID:start из receipt.
Старая попытка без process-tree receipt тоже требует ручной проверки. Возврат
инструмента или отсутствие одного PGID не доказывает завершения всех участников.
Resume: `bash remote_job.sh JOB TTL --resume -- COMMAND ...` — только тот же cwd
и точный argv. После нового SSH-входа восстановить пути/окружение по разделу выше,
выбрать прежний RUN из карточки, заново прочитать его ROUTE и выполнить
`"$MESHROOM_PYTHON" "$REPO/scripts/reconstruction.py" verify "$RUN"` до resume.
Изменённая команда/cwd требует нового JOB; изменённые съёмка, настройки или маски —
нового RUN/project. Старые немаскированные RUN поддерживаются; masked RUN без
receipt не продолжается и требует новой подготовки. Native успешные chunks используются повторно
без forceCompute. Не добавлять force/status flags и не рисовать SUCCESS.
У compute — `--cache`, у batch — `--overrideCacheDir`.

## Backup, освобождение аренды и локальный отчёт

До удаления сохранить capture/manifest/config, projects/effective-settings,
scale plan/evidence, scene/PLY/raw mesh, QA, logs/status и нужный native cache. USDA требует
**всего UID-каталога с соседними USDC payloads**, не только текстового файла.
Выбранные относительные пути записать в paths-to-keep.txt, исключив ключи/environ:

```bash
cd "$WORK"
tar -czf deliverable.tar.gz -T paths-to-keep.txt
sha256sum deliverable.tar.gz >deliverable.tar.gz.sha256
```

Скачать тем же параллельным SFTP, не перезаписывая принятую копию:

```powershell
$backup="$work/backup/deliverable.tar.gz"
if (Test-Path $backup) { throw 'Choose a fresh backup destination' }
& $rclone copyto 'worker:/root/photo-cad/work/deliverable.tar.gz' $backup @transfer
if ($LASTEXITCODE -ne 0) { throw 'Backup incomplete' }
& $rclone copyto 'worker:/root/photo-cad/work/deliverable.tar.gz.sha256' "$backup.sha256" @transfer
if ($LASTEXITCODE -ne 0) { throw 'Source checksum missing' }
$expected=([IO.File]::ReadAllText("$backup.sha256").Trim() -split '\s+')[0]
if ((Get-FileHash $backup -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'Backup SHA256' }
tar -tzf $backup
```

Распаковать в новую локальную папку, проверить payload hashes/читаемость,
включая native USDA+USDC. Единственную копию на ноде не удалять. Проверить stop
снаружи: cur_state=stopped **вместе** с actual_status в {exited,stopped}.
Обычный SSH не наследует per-instance env, исходный watchdog имеет его.
Принятый API request, одиночный exited или отказ SSH не доказывают stop.

Если один большой файл даже с 8 streams не укладывается в срок, после адресной
остановки и подтверждённого закрытия старых SFTP sessions можно использовать
штатные части. В #6 это подняло активную скорость с ~0.8 до ~2.45 MiB/s.
На Linux под тем же bounded runner, в новой папке:

```bash
cd "$WORK"
mkdir backup-parts
split -b 64M -d -a 3 -- deliverable.tar.gz backup-parts/part-
(cd backup-parts && sha256sum part-*) >backup-parts.sha256
sha256sum deliverable.tar.gz >deliverable.tar.gz.sha256
```

На Windows все команды по-прежнему внутри общего исполнителя. Профиль ниже
скачивает 8 файлов одновременно, до 4 streams на большой файл; завершённые части
можно переиспользовать после прерывания. SHA каждого файла и исходного полного
архива получить с ноды через тот же проверенный SFTP, до освобождения ресурса.

```powershell
$backupParts="$work/backup/parts"
$partsArgs=@('--config',"$work/rclone.private.conf",'--transfers','8','--checkers','4','--multi-thread-streams','4','--multi-thread-cutoff','16M','--multi-thread-chunk-size','4M','--retries','2','--timeout','30s','--contimeout','15s','--max-duration','24m','--stats','5s')
& $rclone copy 'worker:/root/photo-cad/work/backup-parts' $backupParts --include '/part-*' --exclude '**' @partsArgs
if ($LASTEXITCODE -ne 0) { throw 'Incomplete parts; retain completed files and inspect actors before resume' }
& $rclone copyto 'worker:/root/photo-cad/work/backup-parts.sha256' "$work/backup/parts.sha256" @transfer
if ($LASTEXITCODE -ne 0) { throw 'Missing part hashes' }
& $rclone copyto 'worker:/root/photo-cad/work/deliverable.tar.gz.sha256' "$work/backup/whole.sha256" @transfer
if ($LASTEXITCODE -ne 0) { throw 'Missing whole archive hash' }
$expected=([IO.File]::ReadAllText("$work/backup/whole.sha256").Trim() -split '\s+')[0]
foreach ($line in Get-Content "$work/backup/parts.sha256") {
  $hash,$name=$line -split '\s+',2
  if ($name -cnotmatch '^part-[0-9]{3}$') { throw 'Unexpected part' }
  if ((Get-FileHash -LiteralPath "$backupParts/$name" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Part SHA mismatch' }
}
$joined="$work/backup/deliverable-joined.tar.gz"
$output=[IO.File]::Open($joined,[IO.FileMode]::CreateNew)
try {
  foreach ($part in (Get-ChildItem -LiteralPath $backupParts -File | Where-Object Name -cmatch '^part-[0-9]{3}$' | Sort-Object Name)) {
    $inputFile=[IO.File]::OpenRead($part.FullName)
    try { $inputFile.CopyTo($output) } finally { $inputFile.Dispose() }
  }
} finally { $output.Dispose() }
# expected — SHA исходного полного архива, не SHA отдельных частей.
if ((Get-FileHash -LiteralPath $joined -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'Joined archive SHA mismatch' }
```

После общего SHA распаковать и проверить индекс всех файлов/payloads как для
обычного архива. Части и failed partial удалять только после этой приёмки,
адресно и в проверенной собственной папке; полный принятый архив сохранить.

```powershell
& $vastai destroy instance $instanceId -y
& $vastai show instances-v1 --limit 25 --raw
# Пройти все --next-token страницы: своего ID нигде нет.
& $vastai show invoices-v1 --charges --start-date YYYY-MM-DD --end-date YYYY-MM-DD --limit 100 --latest-first --raw
```

Сохранить UTC удаления и charges именно своей аренды с диском/трафиком; проверить
все страницы ledger. Stop оставляет платный диск. Destroy удаляет инстанс/данные;
его exit code сам по себе недостаточен. Account balance не заменяет invoices.

## Локальный отчёт

Локальный отчёт — после backup/освобождения GPU, в существующей Windows среде
Open3D/NumPy. Cloud effective-settings.json оставить неизменным. Явные параметры
`--manifest` и при известном масштабе `--scale-evidence` указывают на точные
локальные копии Linux-артефактов. Отчёт сверяет manifest с сохранённым
input_manifest_sha256, а scale evidence — со сценой, режимом, единицами и
источником масштаба; исходный JSON переписывать не требуется. В отчёт попадают
фактически прочитанные локальные пути и SHA. Output не может совпасть с входами.

```powershell
$unpacked="$work/backup/unpacked"
$runLocal="$unpacked/runs/standard"
$originalSettings="$runLocal/effective-settings.json"
$settings=Get-Content $originalSettings -Raw -Encoding UTF8 | ConvertFrom-Json
$manifestLocal=[IO.Path]::GetFullPath("$unpacked/capture/manifest.json")
$reportArgs=@('--scene',"$runLocal/scene.json",'--cloud',"$runLocal/dense.ply",'--settings',$originalSettings,'--manifest',$manifestLocal,'--output',"$runLocal/reconstruction-report.json")
$reportArgs+=@('--mesh',"$runLocal/mesh.obj")
if ($settings.scale.mode -in @('measured_baseline','marker_coords')) {
  $reportArgs+=@('--scale-evidence',"$runLocal/scale-evidence.json")
}
& $python "$repo/scripts/reconstruction_report.py" @reportArgs
if ($LASTEXITCODE -ne 0) { throw 'Reconstruction report failed' }
```

Отчёт читает настоящее PLY и сообщает registered/total, CCTag IDs/наблюдения,
точки/bbox и происхождение масштаба. status=reported не означает продуктовый PASS.
Открыть новое облако существующим инструментом геометрии/CloudCompare, сохранить
короткий вид и описать восстановленное, пропуски и нужную повторную съёмку.
Сверить несколько направлений с исходными кадрами: какие видимые поверхности
и края восстановлены, где есть разрывы, фон или лишняя геометрия. Это визуальная
проверка покрытия, без произвольного порога числа точек или доли камер.
Она не измеряет скрытые стороны, физическую точность и пригодность к изготовлению.

`--mesh` необязателен: прежний cloud-only отчёт сохранён. При его добавлении
Open3D фактически читает отдельную сетку, проверяет непустые vertices/triangles,
конечность координат/индексы, пишет bbox, SHA и units. Точки без граней mesh не
заменяют. Если есть native `mesh_export` receipt, его SHA проверяется; исходные
файлы не меняются. У raw OBJ Meshing оси отличаются от dense PLY: pinned
Mesh::save пишет `(x,-y,-z)`, тогда как SfMData PLY пишет XYZ. Report явно хранит
фиксированный `mesh_to_cloud=diag(1,-1,-1)` и bbox в общей системе, но **не**
поворачивает исходный OBJ. Это не fitted alignment и не изменение масштаба.
Open3D может объединять совпадающие OBJ vertices: его счётчик не всегда равен
числу строк `v`. Для других mesh-форматов конвенция reader здесь не квалифицирована.

У backup #6 mesh находился в исходном `cache/Meshing/<native UID>/mesh.obj`,
а не рядом с dense.ply. Его точный каталог берётся из `artifacts.native_dense`
сохранённого settings (это тот же Meshing UID) и native `outputMesh`/тип из nodes.
После rebasing корня backup можно передать этот точный файл в `--mesh` либо
скопировать без преобразования в локальный RUN. Не выбирать произвольный mesh
по glob. [Фактическая выдача #8](reports/2026-11-22/meshroom-harness.md) описывает
оба принятых файла и формат; частный путь к backup владелец передаёт отдельно.

### Открыть облако и raw OBJ

В интерактивной сессии использовать существующий CloudCompare (отдельно применив
описанный поворот OBJ) или штатный Open3D API ниже. Подставить фактические пути;
закрыть окно после осмотра. Этот GUI-рецепт не выполняется в headless приёмке #8:
там сохранены JSON и [просмотр одних и тех же файлов](reports/2026-11-22/meshroom-harness.md).
Агент передаёт запуск своему ограничителю с явным сроком и наблюдает свой процесс.

```powershell
@'
import os, sys
from pathlib import Path
import numpy as np
import open3d as o3d
cloud_path, mesh_path = (Path(x).resolve(strict=True) for x in sys.argv[1:3])
cloud = o3d.io.read_point_cloud(str(cloud_path))
previous = Path.cwd()
try:
    os.chdir(mesh_path.parent)
    mesh = o3d.io.read_triangle_mesh(mesh_path.name, enable_post_processing=False)
finally:
    os.chdir(previous)
mesh.rotate(np.diag([1., -1., -1.]), center=(0., 0., 0.))
mesh.compute_vertex_normals()
o3d.visualization.draw_geometries([cloud, mesh])
'@ | & $python - "$runLocal/dense.ply" "$runLocal/mesh.obj"
```

Это overlay по native осевому контракту raw OBJ, не ICP/fit и не запись новых
байтов на диск. Для оценки пропусков смотреть несколько направлений и исходные
кадры; объединение cloud+mesh в одном окне само не подтверждает покрытие.
Для такого сравнения сохранить исходный capture вместе с manifest: небольшой
пакет scene/PLY/OBJ достаточен для чтения результата, но не заменяет кадры.

## Маски, масштаб и дополнительные режимы

Готовые маски: masks.folder/extension/features/invert. Требуется полное покрытие
всех кадров; partial masking общий путь не поддерживает. После native CameraInit,
до создания RUN и основного расчёта, проверяется соответствие: сначала
`<viewId>.<extension>`, затем `<source_stem>.<extension>`, в порядке native lookup.
У выбранной маски должны совпадать ширина и высота исходного кадра. Receipt
связывает выбранные файлы с SHA; `verify` проверяет их неизменность до compute/resume.
Для masked Legacy обязательны EXR с alpha и camera metadata: adapter задаёт
outputFileType=exr и saveMetadata=true. Для dense нужна полярность keep=nonzero,
reject=zero. Эти проверки общего adapter локальные; нового masked GPU-прогона
не было, полный masked Standard не квалифицирован. Автосегментация, turntable
и две стороны остаются изученными, пока нет их реального прогона;
зависимости/ограничения — в [матрице](meshroom-modes.md).

По умолчанию scale.mode=unknown: произвольные SfM units, без физических мм.
Для измеренной базы выбрать **Legacy**, включить cctag3 в FeatureExtraction и
FeatureMatching и передать measured_baseline: два разных IDs 0..31, положительное
distance, units mm/cm/m и measurement_source реального замера. Adapter вычисляет
отношение к native базе и передаёт scalar SfMTransform без смены углов/осей/начала.
Положения меток и наблюдения должны быть однозначны. В Goal #6 native scalar
проверен на отдельном синтетическом SfM; реальные видео имеют unknown scale.
Локальные проверки adapter и численный synthetic probe не квалифицируют
измеренную базу на новой реальной съёмке и не доказывают физическую точность.
Любой describer с префиксом cctag, без учёта регистра, отклоняется в Standard:
CCTag ID encoding нового DAG пока не квалифицирован.
В Legacy разрешено только native написание `cctag3`: другие CCTag-семьи
и варианты написания отклоняются до runtime, поскольку экспорт и расчёт базы
рассчитаны на CCTag3.

Локальные Python-проверки: `python -m unittest discover -s tests -p 'test_*.py'`.
Они используют Open3D/build123d и Pillow для настоящего чтения тестовых PNG.
Pillow не становится зависимостью GPU runtime: маски там читает bundled
pyalicevision. Локальный тест decoder boundary не является native masked compute.

marker_coords с полными XYZ зарезервирован и общим adapter отвергается:
использовать только отдельно проверенный исторический native from_markers рецепт
с происхождением координат. Synthetic 100 мм на реальные кадры не переносить.
Goal #6 завершают новая плотная геометрия, диагностика, просмотр, сравнение графов
и verified освобождение ресурсов; один JSON/exit0 или отбор кадров их не заменяет.
