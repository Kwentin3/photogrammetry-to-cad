# Фото/видео → плотная геометрия

Текущий [Goal #6](goal-6.md) использует обычный JSON съёмки, native Meshroom
project/cache и штатный CLI. Реальное видео дало **37 кадров**; оба графа прошли
до dense PLY и JSON. Для базовой съёмки выбран Standard без PDS adapter;
результаты и ограничения — в [отчёте](reports/2026-11-21/photo-video-3d.md).
Команда в инструкции не означает приёмку результата. Актуальный статус — в Goal,
дополнительные режимы и зависимости — в [матрице](meshroom-modes.md).
Выделение деталей и построение CAD остаются следующим отдельным этапом.

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
Каждый новый SSH shell заново задаёт пути и делает `source env.sh`:

```bash
export MESHROOM_ROOT=/root/photo-cad/runtime/Meshroom-2026.11.21-b12ea88-linux
source "$MESHROOM_ROOT/env.sh"
cp "$REPO/configs/reconstruction.example.json" "$WORK/config/standard.json"
export SETTINGS="$WORK/config/standard.json"
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
отдельный самописный ранжировщик не нужен.

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
Existing RUN не перезаписывается. После succeeded прочитать фактический маршрут:

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
setsid -f bash "$REPO/scripts/remote_job.sh" "$WORK/jobs/images-standard" 600 -- \
  taskset -c "$CPUS" "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode "$IMAGES_NODE" \
  >"$WORK/jobs/images-standard-launch.log" 2>&1 </dev/null
```

Standard использует **ExportImages**, без PDS adapter. Legacy использует
**PrepareDenseScene**. Если Legacy вернул успех, но нулевой chunk не создал полный
набор EXR, после проверки sparse/transform и завершения job применить существующий
adapter отдельным новым JOB_DIR, **до dense QA**:

```bash
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
scene.json/dense.ply; при известном масштабе — SHA-bound scale-evidence.json.
Не выбирать первый попавшийся UID/glob.

Повторить стадии Legacy с его SETTINGS/RUN и другими JOB_DIR. Сохранить отдельные
outputs, время и ручные действия; сравнить восстановленные части, пропуски и
искажения. Количество точек и smooth mesh не доказывают физическую точность.

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
и точный argv. Изменённая команда/cwd требует нового JOB; изменённые съёмка или
настройки — нового RUN/project. Native успешные chunks используются повторно
без forceCompute. Не добавлять force/status flags и не рисовать SUCCESS.
У compute — `--cache`, у batch — `--overrideCacheDir`.

## Backup, освобождение аренды и локальный отчёт

До удаления сохранить capture/manifest/config, projects/effective-settings,
scale plan/evidence, scene/PLY, QA, logs/status и нужный native cache. USDA требует
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

## Маски, масштаб и дополнительные режимы

Готовые маски: masks.folder/extension/features/invert; папка должна содержать
хотя бы один файл с указанным расширением до загрузки runtime. Для masked Legacy
обязательны EXR с alpha и camera metadata: adapter задаёт outputFileType=exr и
saveMetadata=true. Для dense уже нужна полярность keep=nonzero, reject=zero. Размеры/имена соответствуют кадрам или
native view IDs. Автосегментация, turntable и две стороны остаются изученными,
пока нет их реального прогона; зависимости/ограничения — в [матрице](meshroom-modes.md).

По умолчанию scale.mode=unknown: произвольные SfM units, без физических мм.
Для измеренной базы выбрать **Legacy**, включить cctag3 в FeatureExtraction и
FeatureMatching и передать measured_baseline: два разных IDs 0..31, положительное
distance, units mm/cm/m и measurement_source реального замера. Adapter вычисляет
отношение к native базе и передаёт scalar SfMTransform без смены углов/осей/начала.
Положения меток и наблюдения должны быть однозначны. Native исполнение/численная
проверка имеют отдельный статус в Goal #6; они не доказывают физическую точность.
Любой describer с префиксом cctag, без учёта регистра, отклоняется в Standard:
CCTag ID encoding нового DAG пока не квалифицирован.

marker_coords с полными XYZ зарезервирован и общим adapter отвергается:
использовать только отдельно проверенный исторический native from_markers рецепт
с происхождением координат. Synthetic 100 мм на реальные кадры не переносить.
Goal #6 завершают новая плотная геометрия, диагностика, просмотр, сравнение графов
и verified освобождение ресурсов; один JSON/exit0 или отбор кадров их не заменяет.
