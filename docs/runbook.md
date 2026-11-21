# Запуск закреплённой Meshroom 2026

Основной комплект этой поставки — pinned nightly 2026: реальный Dice и отдельный
синтетический метрический пример прошли до исходника/STEP. Результаты и границы —
в [отчёте](reports/2026-11-21/meshroom-2026.md), статус приёмки/публикации —
только в [Goal #4](goal-4.md). Исправленная база 2023.3 сохранена коммитом
`f3173b3fdfe27f7e760b84e23f6845b11a937b65` и её
[прежним рецептом](https://github.com/Kwentin3/photogrammetry-to-cad/blob/f3173b3fdfe27f7e760b84e23f6845b11a937b65/docs/runbook.md).
Для её повторения использовать checkout именно этого коммита; активные команды
ниже относятся к 2026. Старые облака — материал сравнения, не новый результат.

## Windows: исходники, данные и постоянный архив

Нужны PowerShell, Python 3.11, Git, OpenSSH и tar. Ни активация venv, ни личная
утилита агента не требуются. Ограничения процессов задаёт среда исполнителя;
агент передаёт эти обычные команды своему обязательному ограничителю.
`WORK` находится вне Git; в новом PowerShell заново задавать переменные.

```powershell
$ErrorActionPreference='Stop'
$repo='D:/src/photogrammetry-to-cad'
$work='D:/photogrammetry-work/goal4'
New-Item -ItemType Directory -Force $work | Out-Null
py -3.11 -m venv "$work/venv"
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
$python="$work/venv/Scripts/python.exe"; $vastai="$work/venv/Scripts/vastai.exe"
& $python -m pip install -r "$repo/requirements-lock-win-py311.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip failed' }
$pin=Get-Content -Raw -Encoding UTF8 "$repo/configs/runtime-2026.json" | ConvertFrom-Json
$archive=[IO.Path]::GetFullPath((Join-Path $repo $pin.retained_copy_relative_to_checkout))
if ((Get-Item -LiteralPath $archive).Length -ne $pin.archive_bytes) { throw 'Archive size' }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.archive_sha256) { throw 'Archive SHA256' }
```

Ожидается полный `Meshroom-2026.11.21-b12ea88-linux-full.tar.gz`, **600156630 байт**,
SHA256 `4ca3cfb0898b8000def4e68d513468a199b948329b63cdb6b257e427d295163b`.
Постоянная копия владельца: `../photogrammetry-to-cad-work/runtime-archives/`
относительно checkout. Перенести этот файл и lock на другую управляющую машину
можно обычным копированием, сохранив хэш и настроив путь `$archive`.
[Rolling nightly](https://github.com/alicevision/Meshroom/releases/tag/nightly)
может удалить asset; ссылка не заменяет сохранённый архив. Без доступной полной
копии не арендовать ноду. Закреплены Meshroom `b12ea8896e7e95cc9911b4ec39c272914e4da726`
и AliceVision `d012d05589b528dcf57a2a0c805c0a5709df8613`.

```powershell
& $python "$repo/scripts/fetch_dataset.py" dice --limit 20 --output "$work/input/dice"
if ($LASTEXITCODE -ne 0) { throw 'Dice fetch' }
& $python "$repo/scripts/fetch_dataset.py" cctag --output "$work/input/cctag"
if ($LASTEXITCODE -ne 0) { throw 'CCTag fetch' }
# Только для нового fixture; принятый сохранённый набор не перерисовывать.
if (!(Test-Path "$work/input/synthetic-markers/truth.json")) {
  & $python "$repo/scripts/make_marker_fixture.py" --output "$work/input/synthetic-markers"
  if ($LASTEXITCODE -ne 0) { throw 'Fixture generation' }
}
foreach ($case in @('dice','cctag','synthetic-markers')) {
  & $python "$repo/scripts/fetch_dataset.py" $case --output "$work/input/$case" --verify-only
  if ($LASTEXITCODE -ne 0) { throw "Input verification: $case" }
}
git -C $repo archive --format=tar --output="$work/source.tar" HEAD scripts configs
if ($LASTEXITCODE -ne 0) { throw 'Source archive' }
tar -cf "$work/inputs.tar" -C $work input
if ($LASTEXITCODE -ne 0) { throw 'Input archive' }
```

Перед `git archive` сохранить нужные изменения коммитом: архивирует именно HEAD.
Записать commit и SHA256 обоих tar в приватную карточку. Preflight сверяет точные
наборы и хэши до CameraInit: Dice20, реальный CCTag50, synthetic10. Старый fixture
нарисован Pillow12.3.0, Windows lock содержит12.2.0; повторная генерация не обещает
одинаковые байты. Сохранённые картинки с `truth.json` остаются опорой сравнения.

## Vast: доступ и пределы до create

Для #4 разрешены **$0.60/ч, до4часов, $25 всего** с диском и трафиком. До создания
проверить существующие инстансы и карточку, доступные средства, цену диска и
передачи в обе стороны. Смета: часы×ставка с диском + загрузки/выгрузки + запас.
Vast не даёт этим рецептом общего жёсткого денежного cap; watchdog остановит
compute при работающей ноде/API, диск продолжит оплачиваться до destroy.

```powershell
$env:VAST_API_KEY=[IO.File]::ReadAllText("$work/credentials/vast-api-key.txt").Trim()
& $vastai --version
& $vastai show instances-v1 --limit 25 --raw
if ($LASTEXITCODE -ne 0) { throw 'Inspect native v1 access' }
New-Item -ItemType Directory -Force "$work/ssh" | Out-Null
if (!(Test-Path "$work/ssh/id_ed25519")) {
  & $python -c "import subprocess,sys; subprocess.run(['ssh-keygen','-q','-t','ed25519','-f',sys.argv[1],'-N',''],check=True,timeout=20)" "$work/ssh/id_ed25519"
  if ($LASTEXITCODE -ne 0) { throw 'SSH key generation' }
}
& $vastai create ssh-key (Get-Content -Raw "$work/ssh/id_ed25519.pub").Trim()
if ($LASTEXITCODE -ne 0) { throw 'SSH key registration' }
& $vastai search offers 'gpu_name=RTX_3090 num_gpus=1 cpu_arch=amd64 verified=true rentable=true direct_port_count>=1 cpu_ram>=32 disk_space>=60 cuda_vers>=12.8 dph_total<=0.60' --storage 60 --type on-demand -o dph_total --limit 5 --raw
if ($LASTEXITCODE -ne 0) { throw 'Offer search' }
```

CLI1.11.2: использовать `instances-v1`, пройти все страницы `--next-token` при их
наличии; старый list `/api/v0/instances/` устарел. `cpu_ram>=32` в CLI —32GB,
REST получает32000MB. До create отдельно сверить фактические `cuda_max_good>=12.8`
и `driver_version>=570.26`, архитектуру/GPU и выделенные RAM/CPU. Образ lock:
`nvidia/cuda:12.8.0-runtime-ubuntu24.04`, linux/amd64, закреплённый digest.
Не менять build/image лишь ради обхода проверки; native ELF/ldd/CUDA предстоит
проверить на ноде. Компиляция ядер на арендованной GPU запрещена.

До create подготовить LF onstart. Абсолютный deadline **новый для этой аренды**,
3ч30м от момента перед create, с резервом до4ч; не пересчитывать его после SSH.

```powershell
$deadlineEpoch=[DateTimeOffset]::UtcNow.AddMinutes(210).ToUnixTimeSeconds()
[IO.File]::WriteAllText("$work/deadline-epoch.txt",[string]$deadlineEpoch,[Text.UTF8Encoding]::new($false))
$bytes=[IO.File]::ReadAllBytes("$repo/scripts/rental_deadline.sh")
$buffer=[IO.MemoryStream]::new()
$gzip=[IO.Compression.GZipStream]::new($buffer,[IO.Compression.CompressionMode]::Compress,$true)
$gzip.Write($bytes,0,$bytes.Length); $gzip.Dispose()
$b64=[Convert]::ToBase64String($buffer.ToArray()); $buffer.Dispose()
$onstart=@"
#!/bin/bash
set -euo pipefail
umask 077
mkdir -p /root/goal4/jobs
printf '%s' '$b64' | base64 -d | gzip -d >/root/goal4/rental_deadline.sh
nohup bash /root/goal4/rental_deadline.sh $deadlineEpoch /root/goal4/jobs/deadline >/root/goal4/jobs/deadline-launch.log 2>&1 </dev/null &
"@
$onstart=$onstart.Replace("`r`n","`n")
if ([Text.Encoding]::UTF8.GetByteCount($onstart) -gt 4048) { throw 'Native onstart limit' }
[IO.File]::WriteAllText("$work/onstart.sh",$onstart,[Text.UTF8Encoding]::new($false))
if ([IO.File]::ReadAllText("$work/onstart.sh",[Text.Encoding]::UTF8) -ne $onstart) { throw 'UTF8 readback' }
$createStartedUtc=[DateTimeOffset]::UtcNow.ToString('o')
$created=& $vastai create instance OFFER_ID --image $pin.image --disk 60 --ssh --direct --cancel-unavail --label photogrammetry-goal4 --onstart "$work/onstart.sh" --raw
if ($LASTEXITCODE -ne 0) { throw 'Inspect v1 list before retrying create' }
$result=($created -join "`n") | ConvertFrom-Json
if (!$result.success -or !$result.new_contract) { throw 'Inspect creation result/list' }
$instanceId=[string]$result.new_contract
@{instance_id=$instanceId;started_utc=$createStartedUtc;deadline_epoch=$deadlineEpoch;source_commit=(git -C $repo rev-parse HEAD)} | ConvertTo-Json | Set-Content -Encoding UTF8 "$work/rental-private.json"
& $vastai ssh-url $instanceId
```

Заменить `OFFER_ID` проверенным оффером. Запись ID/UTC/deadline **сразу после create,
до SSH-настройки**, вне ноды/Git; добавить оффер/ставки, размер диска, текущую
стадию и следующие действия. При неоднозначном ответе сначала v1 список, затем
решение о повторе. Account API key остаётся на управляющей машине.
Onstart использует только провайдерские `CONTAINER_ID/CONTAINER_API_KEY`.
Проверить `jobs/deadline/status`, PID и `waiting` до пакетов/расчётов. Нет armed
watchdog — не начинать расчёт; адресно остановить/удалить принадлежащую аренду.

## SSH, раскладка и bootstrap

По `ssh-url` создать приватный `$work/ssh_config` с alias `photogrammetry-goal4`,
HostName/Port/User, IdentityFile, отдельным UserKnownHostsFile. Первый ключ принять
осознанно по TOFU, затем `StrictHostKeyChecking yes`. При конкретном сбое старого
Windows OpenSSH допустим `KexAlgorithms curve25519-sha256`; host-key checking не
отключать. При DNS-проблеме допустим проверенный public-DoH proxy только для
этого SSH-соединения, не глобальная смена DNS. Нужны реальное подключение и
проверка сохранённого host key, не только полученный адрес.

```powershell
ssh -F "$work/ssh_config" photogrammetry-goal4 'mkdir -p /root/goal4/repo /root/goal4/run /root/goal4/runtime'
# SCP допустим для небольших файлов управления; большие файлы — способом ниже.
scp -F "$work/ssh_config" "$work/source.tar" photogrammetry-goal4:/root/goal4/
Get-FileHash -LiteralPath "$work/source.tar" -Algorithm SHA256
ssh -F "$work/ssh_config" photogrammetry-goal4 'sha256sum /root/goal4/source.tar'
```

До распаковки сравнить локальный и удалённый SHA256 исходников с карточкой запуска.

**Большие передачи выполнять параллельно/многопоточно в обе стороны.** Не выбирать
однопоточный SCP для runtime, фото или результатов. Для публичного закреплённого
runtime использовать aria2 с8 connections/segments; копия владельца остаётся
постоянной опорой после удаления rolling asset. Для фото —8 файлов одновременно.
Передать небольшие manifest/truth и synthetic images вместе с управляющими файлами;
для приватного большого `inputs.tar` или полного архива использовать параллельный
SFTP ниже. При отмене прежней передачи сначала подтвердить завершение её процессов
и закрытие удалённых файлов, затем запускать новый маршрут.

На Linux установить штатный aria2; каждую передачу запускать через remote_job
с собственным JOB_DIR, явным TTL и резервом до deadline. Пример payload runtime:

```bash
aria2c -j8 -x8 -s8 -k16M --continue=true --check-integrity=true \
  --auto-file-renaming=false --allow-overwrite=false --file-allocation=none \
  --max-tries=3 --retry-wait=5 --connect-timeout=20 --timeout=30 \
  --checksum=sha-256=4ca3cfb0898b8000def4e68d513468a199b948329b63cdb6b257e427d295163b \
  --dir=/root/goal4/runtime --out=Meshroom-2026.11.21-b12ea88-linux-full.tar.gz \
  https://github.com/alicevision/Meshroom/releases/download/nightly/Meshroom-2026.11.21-b12ea88-linux-full.tar.gz
```

Для фото составить стандартный `photos.aria2` из **files выбранного manifest**:
каждая запись `url`, затем строки с отступом `dir=/root/goal4/run/input/CASE`,
`out=NAME`, `checksum=sha-256=SHA256`. Не брать неполный список или весь source_files
вместо выбранных Dice20; URL/SHA брать из тех же проверенных records, не угадывать.
Payload: `aria2c -j8 -x8 -s8 -k16M --continue=true --check-integrity=true
--auto-file-renaming=false --allow-overwrite=false --max-tries=3 --retry-wait=5
--timeout=30 --connect-timeout=20 --input-file=photos.aria2`.
После transfer проверить runtime размер/SHA и все три `fetch_dataset.py --verify-only`;
успех загрузчика сам не подтверждает полноту входа. Если rolling URL исчез — брать
сохранённый файл тем же хэшем, без перехода на другую nightly.

### Приватные архивы и backup: проверенный rclone SFTP

Согласно [документации rclone](https://rclone.org/docs/#multi-thread-streams),
`--multi-thread-streams 8 --multi-thread-cutoff 16M` включает сегменты для больших
файлов. Проверенный профиль: chunk4M, transfers1/checkers1. Для upload в SFTP дополнительно нужен
[`--sftp-multithread-upload`](https://rclone.org/sftp/#sftp-multithread-upload).
Это поддержка нескольких соединений, а не только outstanding requests одного SSH.
Не задавать `--sftp-connections`/`--sftp-disable-concurrent-writes`: они отключают
такой upload. Нужен сервер с random-offset writes (OpenSSH).

В Goal #4 rclone **v1.76.0 Windows amd64** проверен на32MiB в каждом направлении:
реально8 SSH-соединений,8 сегментов, совпали исходный/удалённый/скачанный SHA256,
соединения закрылись, тестовые файлы убраны. Upload153.015с (0.209MiB/s),
download49.438с (0.647MiB/s): это измерение конкретного канала, не обещание скорости.
Доказательства вне Git: `WORK/transfer-qualification/{summary.json,qualification.json,*sanitized.log}`.
EXE SHA256 `acd80683e23151e93bbe0d6ffa74d26e542ec510332f630beecb9944f8d1a623`.
Готовый инструмент сохранён вне Git: `WORK/tools/rclone-v1.76.0/rclone.exe`.
Для другой машины — официальный
[Windows amd64 ZIP v1.76.0](https://github.com/rclone/rclone/releases/download/v1.76.0/rclone-v1.76.0-windows-amd64.zip),
32193987 байт, SHA256
`8b4fd2737ade4e70c057ef4a49deb7cffe94b0fb9d7587c189d149823f21a1dc`.
Его первоначальная доставка также проверена восемью HTTP Range-потоками.

Приватный rclone.conf содержит named remote `goal4`, `type=sftp`, явные host/user/
port, `key_file` и `known_hosts_file` из WORK. **Без known_hosts_file rclone по
умолчанию не проверяет host key.** Ключи/секреты не помещать в argv; конфиг вне Git.
Встроенный SFTP не предполагает чтение OpenSSH alias/ProxyCommand: заполнить его
настройки явно. Если выбран внешний `--sftp-ssh`, конфигурация/проверка ключа
переходит внешнему SSH; этот путь отдельно не проверялся. Обезличенный config
ниже сохранить в защищённом `$work/rclone.private.conf`, заменив HOST/PORT своими
значениями и пути — своими абсолютными путями. Алгоритм `ssh-ed25519` выбирает
**уже доверенный** ключ из known_hosts; проверку доверия не ослабляет:

```ini
[goal4]
type = sftp
host = NODE_HOST
port = NODE_SSH_PORT
user = root
key_file = D:/photogrammetry-work/goal4/ssh/id_ed25519
known_hosts_file = D:/photogrammetry-work/goal4/known_hosts
host_key_algorithms = ssh-ed25519
shell_type = unix
```

В квалификации без явного host_key_algorithms Go выбирал другой host key;
исправлено выбором существующего доверенного алгоритма, без смены ключа.
Пример переноса retained runtime с теми же проверенными параметрами:

```powershell
$rclone="$work/tools/rclone-v1.76.0/rclone.exe"
$transferArgs=@('--config',"$work/rclone.private.conf",'--multi-thread-streams','8','--multi-thread-cutoff','16M','--multi-thread-chunk-size','4M','--sftp-multithread-upload','--transfers','1','--checkers','1','--retries','1','--low-level-retries','1','--timeout','30s','--contimeout','15s','--max-duration','10m','--stats','5s')
& $rclone copyto $archive "goal4:/root/goal4/runtime/$($pin.archive_name)" @transferArgs
if ($LASTEXITCODE -ne 0) { throw 'Inspect transfer/processes before retry' }
# Для приватного/сохранённого набора вместо повторной загрузки публичных фото:
& $rclone copyto "$work/inputs.tar" 'goal4:/root/goal4/inputs.tar' @transferArgs
if ($LASTEXITCODE -ne 0) { throw 'Input archive transfer incomplete' }
Get-FileHash -LiteralPath "$work/inputs.tar" -Algorithm SHA256
ssh -F "$work/ssh_config" photogrammetry-goal4 'sha256sum /root/goal4/inputs.tar'
```

Ветку `inputs.tar` выбирать вместо aria2 для фото; перед распаковкой обязательно
сравнить эти SHA256. Публичный downloader также использует до8 параллельных файлов
и публикует полный manifest только после успешной проверки всех хэшей.

`10m` — явный предел примера: до запуска сопоставить размер/измеренную скорость
с оставшимся deadline и резервом на cleanup. Фактический32MiB probe был ограничен
165с; успех probe не обещает завершения полного архива за10мин. На получателе
проверить полный SHA256 против runtime lock; исходную постоянную копию сохранить.

Для backup перед удалением ноды сформировать source SHA256 рядом с **готовым**
архивом: `cd /root/goal4/run && sha256sum deliverable.tar.gz >deliverable.tar.gz.sha256`.
Скачать архив многопоточно, маленький checksum тем же доверенным SFTP; существующие
принятые копии не перезаписывать. Пример в том же PowerShell с transferArgs:

```powershell
New-Item -ItemType Directory -Force "$work/backup" | Out-Null
$backup="$work/backup/deliverable.tar.gz"
if (Test-Path $backup) { throw 'Inspect existing backup; choose a fresh destination' }
& $rclone copyto 'goal4:/root/goal4/run/deliverable.tar.gz' $backup @transferArgs
if ($LASTEXITCODE -ne 0) { throw 'Backup transfer incomplete; inspect before retry' }
& $rclone copyto 'goal4:/root/goal4/run/deliverable.tar.gz.sha256' "$backup.sha256" @transferArgs
if ($LASTEXITCODE -ne 0) { throw 'Source checksum unavailable' }
$expected=([IO.File]::ReadAllText("$backup.sha256").Trim() -split '\s+')[0]
if ($expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid source SHA256' }
if ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'Backup SHA256 mismatch' }
tar -tzf $backup | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Backup archive unreadable' }
```

После распаковки проверить содержимое и native USDA/USDC, не только tar index.
Не считать `--sftp-concurrency 8` доказательством8 соединений: это запросы одного
файла. Проверять реальную параллельность/скорость и SHA, не отключать TLS/host-key
контроль. На Windows многопоточный download может создать sparse-файл; это не
ошибка SHA. Большие приватные файлы переносить этим готовым клиентом; новый
собственный chunker для backup не требуется.

Далее Linux Bash через SSH. Каждая длительная команда — отдельный bounded job.
`RUN_ROOT` **вне REPO**: helper откажет при вложении. Перед bootstrap проверить
watchdog; минимальные системные зависимости curl/python3/tar/flock/timeout/ldd
установить пакетным менеджером с ограниченным сроком. Штатный системный Python
нужен bootstrap для чтения lock; после env все Python-вызовы — bundled3.11.

```bash
set -euo pipefail
export REPO=/root/goal4/repo RUN_ROOT=/root/goal4/run
timeout --signal=TERM --kill-after=15s 120s apt-get update
timeout --signal=TERM --kill-after=15s 180s apt-get install -y --no-install-recommends python3 curl ca-certificates util-linux coreutils tar gzip aria2
tar -xf /root/goal4/source.tar -C "$REPO"
# Если выбран приватный inputs.tar, распаковать его; при aria2 фото уже в run/input.
if [[ -f /root/goal4/inputs.tar ]]; then tar -xf /root/goal4/inputs.tar -C "$RUN_ROOT"; fi
mkdir -p "$RUN_ROOT/jobs" "$RUN_ROOT/output"
cd "$RUN_ROOT"
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/bootstrap2026" 600 -- \
  bash "$REPO/scripts/bootstrap_meshroom.sh" /root/goal4/runtime \
  --archive /root/goal4/runtime/Meshroom-2026.11.21-b12ea88-linux-full.tar.gz \
  >"$RUN_ROOT/jobs/bootstrap2026-launch.log" 2>&1 </dev/null
```

Дождаться `state=succeeded`, `cleanup=confirmed`, прочитать logs/probes. Bootstrap
проверяет размер/SHA, ldd, native help и импорт Graph; это ещё не GPU-приёмка.
Проверить `nvidia-smi`, драйвер и реальное CUDA/CCTag вычисление до основного MVS.
Нерешённая зависимость — воспроизводимый блокер, не повод компилировать ядро.

```bash
export MESHROOM_ROOT=/root/goal4/runtime/Meshroom-2026.11.21-b12ea88-linux
source "$MESHROOM_ROOT/env.sh"
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/prepare2026" 300 -- \
  bash "$REPO/scripts/prepare_graphs.sh" "$RUN_ROOT" "$MESHROOM_ROOT" \
  >"$RUN_ROOT/jobs/prepare2026-launch.log" 2>&1 </dev/null
```

Каждый новый SSH-shell заново задаёт REPO/RUN_ROOT/MESHROOM_ROOT и source env.
Он задаёт официальный `MESHROOM_INSTALL_DIR`, PATH, `aliceVision/lib64` и bundled
Python, включая Python-пути AliceVision из bootstrap. После `source env.sh`
**все Linux Python-команды** запускать только через `"$MESHROOM_PYTHON"`, включая
короткие JSON-проверки и scripts экспорта/preflight. Системные `python3` и
`/usr/bin/python3` Ubuntu3.12 под этим PYTHONPATH получают bundled3.11 `.pyc` и
могут завершиться `bad magic number`; не смешивать интерпретаторы. Системный
Python допустим для начального bootstrap до source env. Native binaries доступны
через штатные versioned symlinks. Не заменять их вручную.

## Штатные графы, стадии и продолжение

Helper использует `aliceVision/share/meshroom/photogrammetryLegacy.mgt` и публичный
Graph API, не редактирование serialized UID. Проверяет входы до CameraInit,
применяет FOV/настройки **до initialize**, сохраняет `projects2026/CASE.mg` и
явный `cache2026/CASE`. Связанные настройки сверяются с владельцем; противоречия
не разрывают рёбра молча. Existing project не перезаписывается.

- Dice20: белая HSV-маска от CameraInit → FeatureExtraction и PrepareDenseScene;
  SIFT, minRequired2DMotion2, downscale4. Маска не читает SfM, цикла нет.
- Реальный CCTag50: SIFT+cctag3, до StructureFromMotion; физическая шкала неизвестна.
- Synthetic10: FOV из truth; native SfMTransform от SfM задаёт центры0/1 из truth
  (−50/+50мм, база100мм), applyScale/Rotation/Translation=true, scale1.
  Серая маска110/255 действует только на dense. Четыре dense input идут через
  штатные aliases от transformed SfM; Meshing helper0/raw=true из финального config.

Перед compute проверить native graph: ноль compatibility nodes/UIDConflict,
точные views из manifest, ацикличность, действующие inputLink/output UID/cache
и commandLine. В synthetic все четыре dense-команды должны читать **новый
transformed USDA**, в Dice — новый masked SfM. Штатное расширение USDA читается
через AliceVision, координаты вручную из USD не разбирать. USDA ссылается на
необходимый соседний `*_landmarks.usdc`: сохранять **весь UID-каталог**, не один
текстовый файл. SHA проверять для обоих; перенос USDA без USDC неполон.

Ниже запускать **по одному блоку**, после `state=succeeded` и `cleanup=confirmed`
предыдущего job, проверки его log/output. Задать `CASE=dice`, `cctag` или
`synthetic-markers`, а `STAGE_TTL` — явное число секунд ≤ остатка до deadline
минус резерв выгрузки. Длительности каждой стадии пересматривать отдельно;
background launch не является разрешением запускать следующие стадии параллельно.

```bash
CASE=synthetic-markers
PROJECT="$RUN_ROOT/projects2026/$CASE.mg"
CACHE="$RUN_ROOT/cache2026/$CASE"
cd "$RUN_ROOT"
```

Для **Dice сначала** ImageMasking, поскольку его маска нужна FeatureExtraction.
После этого проверить PNG по viewID/размерам, фон0 и сохранённый объект.
Для synthetic этот блок выполнить **после SfMTransform**: маска читает его output.
Реальный CCTag не имеет стадии маски.

```bash
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/$CASE-mask2026" "$STAGE_TTL" -- \
  "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode ImageMasking_1 \
  >"$RUN_ROOT/jobs/$CASE-mask2026-launch.log" 2>&1 </dev/null
```

Sparse выполнить для всех трёх случаев. У real CCTag это последний compute;
проверить50 камер и восстановленные3D CCTag observations, физическую шкалу не назначать.

```bash
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/$CASE-sparse2026" "$STAGE_TTL" -- \
  "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode StructureFromMotion_1 \
  >"$RUN_ROOT/jobs/$CASE-sparse2026-launch.log" 2>&1 </dev/null
```

Только synthetic: следующим отдельным job native масштабирование, затем mask
по блоку выше. Выгрузить JSON до/после и численно проверить метки; продолжать dense
только с принятым transformed UID.

```bash
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/synthetic-transform2026" "$STAGE_TTL" -- \
  "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode SfMTransform_1 \
  >"$RUN_ROOT/jobs/synthetic-transform2026-launch.log" 2>&1 </dev/null
```

**Dice и synthetic: после sparse/transform и маски отдельно подготовить все dense
изображения по проверенному профилю ниже.** В Legacy наблюдались size0/ноль chunks: отдельный
`meshroom_compute --toNode PrepareDenseScene_1` для Dice вернул SUCCESS, но создал
0 EXR. Поэтому ни SUCCESS, ни сам отдельный PDS compute не доказывают полноту.
У synthetic отдельный compute работал после SfMTransform и создал10 EXR; затем
Meshing прошёл CUDA и дал15659 точек в native unknown-PLY. Это подтверждение стадии,
не приёмка backup/CAD.

`prepare_dense_images.py` строго загружает штатный граф, выбирает его PDS node,
строит `NodeChunk(desc.Range())` и запускает **native buildCommandLine** с
`provider.runtimeEnv`. Range-флаги отклоняются: native default rangeStart=-1
означает все views. Настройки/рёбра/UID не дублируются, граф, ядро и Meshroom
status не переписываются. Для **Dice** этим путём получены20 EXR, проверены alpha
и metadata. Для **synthetic-markers** используется native PDS compute: получены10 EXR,
проверены alpha/metadata и последующий CUDA-расчёт. Повторно переписывать принятые
synthetic EXR helper-ом не требуется. Это два профиля одного закреплённого runtime.
Helper Dice — временная тонкая адаптация: удалить после проверки
исправленного native DynamicNodeSize/chunk planning на новом закреплённом runtime.

```bash
if [[ $CASE == dice ]]; then
  setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/$CASE-prepare-images2026" "$STAGE_TTL" -- \
    "$MESHROOM_PYTHON" "$REPO/scripts/prepare_dense_images.py" "$PROJECT" --cache "$CACHE" \
    >"$RUN_ROOT/jobs/$CASE-prepare-images2026-launch.log" 2>&1 </dev/null
elif [[ $CASE == synthetic-markers ]]; then
  setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/$CASE-prepare-dense2026" "$STAGE_TTL" -- \
    "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode PrepareDenseScene_1 \
    >"$RUN_ROOT/jobs/$CASE-prepare-dense2026-launch.log" 2>&1 </dev/null
else
  printf '%s\n' 'PDS is only required for dice or synthetic-markers' >&2
  exit 2
fi
```

Каждый PDS запускается отдельным bounded job; для Dice helper использован **новый
JOB_DIR**: прежний PDS compute имеет другую команду и не возобновляется под прежним
binding. Принятый synthetic PDS повторно не запускать; сначала проверить его статус
и файлы. Доказательства для обоих — успешный bounded job, native command/log и
все20/10 файлов после проверки. После Dice helper Meshroom PDS status может
остаться NONE/ноль chunks; не назначать ему фиктивный SUCCESS/force-success.
В принятом Dice-прогоне последующий native compute сам повторил PDS той же
командой и входами и записал настоящий SUCCESS; EXR QA выполнена до этого повтора.
Выбрать **точные** PDS_DIR и
MASK_DIR текущих UID по native graph/commandLine, SFM_JSON — native JSON текущего
sparse/transformed output с views. Не искать первый каталог wildcard. Быстрая
проверка количества/имён и заголовков; она не заменяет декодирование EXR/alpha QA:

```bash
"$MESHROOM_PYTHON" - "$SFM_JSON" "$PDS_DIR" "$MASK_DIR" "$CASE" <<'PY'
import json, pathlib, struct, sys
views = json.loads(pathlib.Path(sys.argv[1]).read_text())['views']
assert len(views) == {'dice': 20, 'synthetic-markers': 10}[sys.argv[4]], 'Incomplete views'
expected = {str(v['viewId']): v for v in views}
assert len(expected) == len(views) and views, 'Duplicate or absent view IDs'
for directory, suffix in ((sys.argv[2], '.exr'), (sys.argv[3], '.png')):
    files = {p.stem: p for p in pathlib.Path(directory).glob('*' + suffix)}
    assert set(files) == set(expected), (directory, 'EXTRA/MISSING', set(files) ^ set(expected))
    for view_id, path in files.items():
        with path.open('rb') as stream:
            header = stream.read(24)
        if suffix == '.exr':
            assert header[:4] == b'\x76\x2f\x31\x01', path
        else:
            assert header[:8] == b'\x89PNG\r\n\x1a\n', path
            size = struct.unpack('>II', header[16:24])
            view = expected[view_id]
            assert size == (int(view['width']), int(view['height'])), (path, size)
    print(suffix, 'view IDs/headers verified:', len(files))
PY
```

Дополнительно прочитать EXR изображения, проверить размеры/alpha0 фона и сохранённую
предметную область, отсутствие предупреждения об игнорировании маски. Только после
полного набора20 EXR для Dice /10 для synthetic запускать Meshing **новым JOB_DIR**:

```bash
setsid -f bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/$CASE-dense2026" "$STAGE_TTL" -- \
  "$MESHROOM_ROOT/meshroom_compute" "$PROJECT" --cache "$CACHE" --toNode Meshing_1 \
  >"$RUN_ROOT/jobs/$CASE-dense2026-launch.log" 2>&1 </dev/null
```

В native batch2026 кэш называется `--overrideCacheDir`; у compute — `--cache`.

Наблюдение: `cat JOB_DIR/status`, актуальный log, `process_group` и `ps` только
своей группы. `setsid -f` отделяет launcher от SSH; runner владеет сроком и группой.
После таймаута SSH сначала прочитать status, не дублировать расчёт. Перед продолжением проверить v1
инстанс/карточку, процесс/группу, cache statuses и существующие outputs.
`--resume` runner допустим только для прежних **command/cwd**: successful job
будет reused; живой старый process group отклоняется. Смена `--toNode`, executable
или input binding требует **нового JOB_DIR**, сохраняя тот же native cache только
если граф/входы прежние. Runner не меняет force flags. Не применять forceStatus
до проверки отсутствия живого владельца; неизвестный cleanup не считать остановкой.

## Native exports и метрическая проверка

Выбрать точные успешные UID/output paths из сохранённого графа и emitted commands,
задать SFM_USDA/SCALED_USDA/DENSE_USDA; wildcard первого файла недопустим.
Экспорты тоже выполнять через runner с отдельными JOB_DIR/TTL, после source env:

```bash
aliceVision_convertSfMFormat --input "$SFM_USDA" --output "$RUN_ROOT/output/markers-before.json" --describerTypes sift,cctag3 --views true --intrinsics true --extrinsics true
aliceVision_convertSfMFormat --input "$SCALED_USDA" --output "$RUN_ROOT/output/markers-after.json" --describerTypes sift,cctag3 --views true --intrinsics true --extrinsics true
aliceVision_convertSfMFormat --input "$DENSE_USDA" --output "$RUN_ROOT/output/dense.ply" --describerTypes unknown --views false --intrinsics false --extrinsics false
# Pinned native writer keeps landmarks in an adjacent payload, not in USDA.
scaled_payload="${SCALED_USDA%.usda}_landmarks.usdc"
dense_payload="${DENSE_USDA%.usda}_landmarks.usdc"
test -s "$scaled_payload" && test -s "$dense_payload"
sha256sum "$SCALED_USDA" "$scaled_payload" "$DENSE_USDA" "$dense_payload" \
  >"$RUN_ROOT/output/native-sources.sha256"
```

Флаги экспорта сверить с help именно retained binary перед запуском. В2026 пустой
describerTypes удаляет landmarks; JSON должен сохранить views/poses/intrinsics
и cctag3 observations, PLY — конечные dense points. Для Dice экспортировать его
собственный dense output в отдельный `dice-dense.ply`; не подменять synthetic.
Файлы источников после выбора неизменны: путь/UID не заменяет SHA содержимого.
Writer/loader AliceVision не задаёт/не использует метаданные единиц USD: ±50 в
target задаёт численную базу100 по прикладному соглашению **мм**; native PLY
сохраняет эти числа, Open3D получает meters_per_unit0.001, CAD — миллиметры.
Не добавлять преобразование координат в метры только ради формата USD.
После выгрузки проверить метки существующим checker:

```powershell
& $python "$repo/scripts/check_marker_scale.py" "$work/output/markers-before.json" "$work/output/markers-after.json" --ids 0 1 --distance 100 --units mm --reference "$work/input/synthetic-markers/truth.json" --output "$work/output/marker-scale-check.json"
if ($LASTEXITCODE -ne 0) { throw 'Marker scale verification' }
```

Известные100мм относятся только к виртуальной сцене. У real CCTag нужны реальное
распознавание и reconstructed3D observations; назначать ему100мм нельзя. Сравнить
новые плотные границы/форму с фото и старым результатом, не обрезать под truth.
Helper/remap не объявлять причиной старого диагностического расширения.

Для отдельного real CCTag sparse output задать его точный `REAL_SFM_USDA`.
Следующие payloads тоже выполняются в ограниченных jobs; цель проверки —
3D-центры и posed observations выбранных уникальных ID, без назначения масштаба:

```bash
aliceVision_convertSfMFormat --input "$REAL_SFM_USDA" --output "$RUN_ROOT/output/real-cctag-markers.json" --describerTypes cctag3 --views true --intrinsics true --extrinsics true
"$MESHROOM_PYTHON" - "$REPO/scripts" "$RUN_ROOT/output/real-cctag-markers.json" <<'PY'
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from check_marker_scale import read_json, markers_from_scene
result = markers_from_scene(read_json(pathlib.Path(sys.argv[2])), [0, 1], 'real-cctag')
print(json.dumps(result, indent=2))
print('Distance above is arbitrary native units; physical baseline is unknown.')
PY
```

## Сохранить, удалить GPU, затем CAD

Сохранить graph/configs/input manifests, probes/versions, commands/status/logs,
source hashes, полные sparse/transformed/dense UID-каталоги (USDA **и все USDC**),
JSON и PLY текущих UID, необходимый кэш. Упаковать выбранные файлы **без ключей/environ**,
создать SHA256; скачать **параллельно** в WORK, сверить SHA и читаемость архива
и payload файлов, включая native чтение сохранённого USDA с соседними USDC. Объём невзятых данных
и постоянные копии записать явно. **До локального CAD** завершить аренду.

Stop-test — из исходного native onstart env; обычный SSH не содержит per-instance
переменных. При необходимости использовать проверенный PID исходного watchdog:
сверить cmdline/каталог/ID с карточкой, извлечь в память только CONTAINER_ID и
CONTAINER_API_KEY без xtrace, argv/логов/полного environ. Отдельный watchdog now+5
не продлевает исходный deadline. Account key на GPU не копировать.

Подтверждение снаружи: `cur_state=stopped` и `actual_status` в `{exited,stopped}`;
одиночный exited или отказ SSH недостаточен. Затем на управляющей машине в том
же защищённом контексте: `& $vastai destroy instance $instanceId -y` и независимый
нефильтрованный v1 list со всеми страницами: свой ID отсутствует. Без `-y` CLI
могут дать Aborted/exit0; `--raw` destroy не обещает JSON. Stop оставляет платный
диск; только verified destroy закрывает ресурс. Сохранить UTC аренды/удаления и
invoice именно этой аренды с диском/трафиком, не выводить стоимость из account balance.

На CPU использовать неизменённые extract_plane/build_cad/check_marker_scale API
из [базового рецепта](runbook.md#облако--параметры--cad-на-cpu), но **новые PLY**.
Выбрать ROI по просмотренной новой поверхности; старые ROI не гарантируют её
идентичность. Для synthetic: meters_per_unit0.001, scale_status synthetic_reference;
для Dice без baseline:0.001/unverified, условные CAD мм, не физические миллиметры.
Проверить source SHA, plane/support/hull, подписанный SVG, положение/наклон и residual.
Скрытая толщина unresolved → явный test_assumption в копии JSON → build_cad →
самодостаточный model.py → STEP read-back: единицы, bounds, valid solid/volume.
Изменить только толщину, пересоздать STEP и проверить пропорцию объёма при прежней
форме/положении. Не выпрямлять углы и не назначать физические размеры по картинке.
Существенные изменения относительно2023.3 объяснить в отчёте; старые облака не
засчитываются как новое вычисление. При блокере сохранить базу и точное следующее
действие в Goal #4; переключение основного комплекта — только после его приёмки.
