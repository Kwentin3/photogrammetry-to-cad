# Повторение технического пилота

Рецепт выбранной цепочки; фактический статус и незакрытые пункты — только в [Goal #2](goal-2.md). Версионные первоисточники и лицензии — [sources.md](sources.md#s16-закреплённый-runtime-пилота). Здесь нет обещания точности на беседке или готовности к изготовлению.

## Управляющая Windows-машина

Исходники хранятся в `REPO`, данные, venv, ключи и рабочая карточка — в отдельном `WORK` вне Git. Нужны обычные PowerShell, Python 3.11 и OpenSSH. Команды ниже выполняются штатными инструментами; ограничения локальных процессов задаёт клиент агента. Если среда требует собственного исполнителя, команды передаются через него согласно её правилам. На GPU срок, журнал и адресную остановку обеспечивает `remote_job.sh`.

```powershell
$ErrorActionPreference='Stop'
$repo='D:/src/photogrammetry-to-cad'
$work='D:/photogrammetry-work/goal2'
py -3.11 -m venv "$work/venv"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$work/venv/Scripts/python.exe" -m pip install -r "$repo/requirements-lock-win-py311.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

`requirements-lock-win-py311.txt` закрепляет 117 транзитивных пакетов проверенной Windows Server 2019 x64 / Python 3.11.9 среды. `requirements-local.txt` — контракт шести прямых зависимостей; Linux Meshroom использует отдельный native bundle. В новом процессе заново задавать `$repo`, `$work` и пути к venv ниже; активация/PATH не предполагаются. Ограничить установку сроком 30 минут средствами клиента и после timeout убедиться в завершении прежних процессов до повтора. Кириллический JSON передавать внешним процессам UTF-8-файлом, не stdin.

```powershell
$python="$work/venv/Scripts/python.exe"
$vastai="$work/venv/Scripts/vastai.exe"
& $python "$repo/scripts/fetch_dataset.py" dice --limit 20 --output "$work/input/dice"
& $python "$repo/scripts/fetch_dataset.py" cctag --output "$work/input/cctag"
& $python "$repo/scripts/make_marker_fixture.py" --output "$work/input/synthetic-markers"
```

Принимать только `complete=true` в manifest, ожидаемые количества/байты и совпавшие Git blob/SHA256. Dice: 20 фото, 47,086,536 байт; CCTag: 50 фото, 74,304,634 байт. Повторный fetch проверяет существующие файлы. Физической базы реального CCTag-набора нет. Pillow-fixture имеет отдельный `truth.json` и **виртуальную** базу 100 мм. Принятые изображения созданы Pillow 12.3.0; lock содержит 12.2.0. Для точного повторения брать сохранённые изображения с SHA256: тождество байтов после перерисовки другой версией не обещается.

До передачи и перед построением графов выполнить `fetch_dataset.py DATASET
--output INPUT_ROOT --verify-only` для всех трёх наборов (`synthetic-markers`
указывает на каталог с truth.json). Это проверяет точный набор, размеры и хэши;
лишняя фотография, вложенный каталог, пропущенный или изменённый файл останавливает
запуск. Посторонние файлы автоматически не удаляются. Linux `prepare_graphs.sh`
повторяет эту проверку до любого вызова Meshroom.

При фактической установке стандартный pip зависал на TLS-handshake с PyPI;
та же установка прошла без предложения ALPN только у этого процесса.
Если повторяется именно это расхождение, в отдельном процессе можно применить
проверенный обход ниже. Проверка TLS-сертификатов остаётся включена;
внешняя причина сетевой несовместимости не установлена:

```powershell
$python="$work/venv/Scripts/python.exe"
& $python -c "import ssl,runpy,sys; ssl.SSLContext.set_alpn_protocols=lambda self,protocols:None; sys.argv=['pip','install','-r',sys.argv[1]]; runpy.run_module('pip',run_name='__main__')" "$repo/requirements-lock-win-py311.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## Аренда: подготовить до создания

Нужны действующие права аккаунта, API-ключ в защищённом локальном хранилище, SSH-пара, разрешение и три предела: ставка, время, итоговая сумма. Для этого Goal разрешены $0.60/ч, 4 часа, $25 вместе с диском, трафиком, установкой и повторами. Проверить текущий баланс, существующие инстансы и карточку; запускать один инстанс. Штатного общего budget cap/TTL у Vast create нет.

Ниже `$vastai` — точный executable venv, не случайный PATH. Файл `$work/credentials/vast-api-key.txt` должен быть заранее предоставлен в защищённом WORK; читать его без вывода (альтернатива — уже настроенное native CLI secure store). Перед register создать отдельную SSH-пару; срок подготовки 60 секунд, keygen ограничен 20 секундами. Существующий приватный ключ не перезаписывается. При ошибке любого CLI-вызова не переходить к create. Native v1 `--limit` предотвращает интерактивную пагинацию:

```powershell
$python="$work/venv/Scripts/python.exe"; $vastai="$work/venv/Scripts/vastai.exe"
$env:VAST_API_KEY=[IO.File]::ReadAllText("$work/credentials/vast-api-key.txt").Trim()
New-Item -ItemType Directory -Force "$work/ssh" | Out-Null
if (!(Test-Path "$work/ssh/id_ed25519")) {
  & $python -c "import subprocess,sys; subprocess.run(['ssh-keygen','-q','-t','ed25519','-f',sys.argv[1],'-N',''],check=True,timeout=20)" "$work/ssh/id_ed25519"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (!(Test-Path "$work/ssh/id_ed25519.pub")) { throw 'Inspect existing SSH key pair' }
& $vastai --version
& $vastai show user --raw
& $vastai show instances-v1 --limit 25 --raw
& $vastai create ssh-key (Get-Content -Raw "$work/ssh/id_ed25519.pub").Trim()
& $vastai search offers 'gpu_name=RTX_3090 num_gpus=1 cpu_arch=amd64 verified=true rentable=true direct_port_count>=1 cpu_ram>=32 disk_space>=60 cuda_vers>=11.8 dph_total<=0.60' --storage 60 --type on-demand -o dph_total --limit 5 --raw
```

В установленном CLI 1.11.2 `cpu_ram>=32` означает 32 GB: `offers_mult` умножает значение на 1000, REST получает `cpu_ram.gte=32000` MB. Не переносить CLI-единицы в raw API без преобразования. Перед rent проверить цену с 60 ГБ диска, выделенную RAM/CPU, скорость/цену трафика в обе стороны. Смета: часы × ставка с диском + трафик + запас ≤ разрешённой суммы. Не расширять пределы молча; пустой результат оставить явным.

До create подготовить LF `onstart.sh`. Сжатый payload учитывает лимит onstart 4048 байт и запускает сторож **до SSH и установки пакетов**. Нужны curl, grep, flock, date, sleep, realpath, base64 и gzip; Python/CLI не нужны. Их наличие в выбранном образе проверить заранее. Сохранить рассчитанный deadline в приватной карточке до create:

```powershell
$deadlineEpoch=[DateTimeOffset]::UtcNow.AddMinutes(210).ToUnixTimeSeconds()
$vastai="$work/venv/Scripts/vastai.exe"; $env:VAST_API_KEY=[IO.File]::ReadAllText("$work/credentials/vast-api-key.txt").Trim()
$watchdogBytes=[IO.File]::ReadAllBytes("$repo/scripts/rental_deadline.sh")
$gzipBuffer=[IO.MemoryStream]::new()
$gzipStream=[IO.Compression.GZipStream]::new($gzipBuffer,[IO.Compression.CompressionMode]::Compress,$true)
$gzipStream.Write($watchdogBytes,0,$watchdogBytes.Length); $gzipStream.Dispose()
$watchdogB64=[Convert]::ToBase64String($gzipBuffer.ToArray()); $gzipBuffer.Dispose()
$onstart=@"
#!/bin/bash
set -euo pipefail
umask 077
mkdir -p /root/goal2/scripts /root/goal2/jobs
printf '%s' '$watchdogB64' | base64 -d | gzip -d >/root/goal2/scripts/rental_deadline.sh
nohup bash /root/goal2/scripts/rental_deadline.sh $deadlineEpoch /root/goal2/jobs/deadline >/root/goal2/jobs/deadline-launch.log 2>&1 </dev/null &
"@
$onstart=$onstart.Replace("`r`n","`n")
if ([Text.Encoding]::UTF8.GetByteCount($onstart) -gt 4048) { throw 'onstart exceeds native limit' }
[IO.File]::WriteAllText("$work/onstart.sh",$onstart,[Text.UTF8Encoding]::new($false))
if ([IO.File]::ReadAllText("$work/onstart.sh",[Text.Encoding]::UTF8) -ne $onstart) { throw 'UTF-8 readback differs' }
& $vastai create instance OFFER_ID --image nvidia/cuda:11.8.0-runtime-ubuntu22.04 --disk 60 --ssh --direct --cancel-unavail --label photogrammetry-goal2 --onstart "$work/onstart.sh" --raw
```

Onstart получает per-instance окружение провайдера. Срок не отсчитывать заново после SSH. Аккаунтный API-ключ на ноду не передавать.

Сразу после успешного create записать `new_contract` как ID, UTC начала, предложение/ставки, размер диска и абсолютный UTC deadline в приватную карточку **вне ноды и Git**, прежде настройки SSH. Для резерва на выгрузку сторож пилота назначен на 3ч30м; создание/загрузка тоже расходуют разрешённое время. Проверить actual status, логи и работающий PID/`waiting` сторожа. Это ещё не доказательство будущего stop. При ошибке create не создавать повторный инстанс без проверки списка.

## SSH и Linux runtime

Получить соединение штатным `& $vastai ssh-url INSTANCE_ID` в payload с теми же путём к executable и авторизацией. Первый ключ был принят по TOFU; затем закрепить отдельный known_hosts и `StrictHostKeyChecking=yes` в приватном `WORK/ssh_config`, alias `photogrammetry-goal2`. Для старого Windows OpenSSH при конкретной ошибке sntrup KEX помог `KexAlgorithms curve25519-sha256`; не отключать проверку ключей.

Если DNS proxy-host указывает на местный HTTPS-релей, проверить публичный ответ через DoH и использовать проверенный адрес для этого SSH-host с прежним HostKeyAlias. Не менять системный DNS. Это обход конкретного наблюдаемого расхождения, не общая настройка. SSH/SCP подчиняются политике локального клиента агента.

На Linux принять `RUN_ROOT=/root/goal2`, `REPO=$RUN_ROOT`, `MESHROOM_ROOT=$RUN_ROOT/runtime/Meshroom-2023.3.0`: здесь размещается копия `scripts/` и `configs/`, а не Git-checkout с сырьём. Данные перенести из локального WORK; аккаунтные токены/приватные ключи не копировать. Перед новой работой сверять инстанс, карточку, процессы и результаты. Все расчёты запускать с явным TTL; пример для установщика:

```bash
mkdir -p "$RUN_ROOT/jobs" "$RUN_ROOT/output"
nohup bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/bootstrap" 1800 -- \
  bash "$REPO/scripts/bootstrap_meshroom.sh" "$RUN_ROOT/runtime" \
  --sha256 92b81246356df3fd37ea08e1d09519392897aaa730843eb9fd4bd0582916d391 \
  >"$RUN_ROOT/jobs/bootstrap-launch.log" 2>&1 </dev/null &
```

Сторож вооружается из onstart, а не обычным SSH login: **неинтерактивная SSH-сессия фактически не содержит `CONTAINER_ID`/`CONTAINER_API_KEY`**. Проверить уже запущенный watchdog по его lock, status и точному cmdline. Он использует только native per-instance ключ, PUT stop собственного инстанса; аккаунтный ключ туда не подставлять и `env` не печатать. Архивный SHA измерен при первом скачивании, это не подпись издателя.

Дождаться `jobs/bootstrap/status`: `state=succeeded`, `cleanup=confirmed`; прочитать probes. После работающего сторожа установить системный `python3` штатным apt, если его нет: он нужен только для stdlib-адаптеров графа; установку также ограничить remote_job. Затем `source "$MESHROOM_ROOT/env.sh"` для прямых AV-команд. Проверить GPU, диск, выделенную RAM, версии. Справка не заменяет DepthMap. `OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8` ограничивают CPU пилота; не запускать конфликтующий второй тяжёлый расчёт.

## Граф, SfM и масштаб

`prepare_graphs.sh RUN_ROOT MESHROOM_ROOT` запускать через такой же `remote_job.sh` с отдельным каталогом и TTL. Он сохраняет native `.mg` для трёх входов. Для fixture FOV задаётся **в шаблоне до CameraInit.initialize**, потому что `--overrides` применяется позже; проверить 1200×900 и fx=1000 px. Dice использует SIFT, `minRequired2DMotion=2`, DepthMap downscale=4; CCTag сохраняет SIFT+cctag3.

```bash
source "$MESHROOM_ROOT/env.sh"
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8
nohup bash "$REPO/scripts/remote_job.sh" "$RUN_ROOT/jobs/synthetic-sfm" 1200 -- \
  "$MESHROOM_ROOT/meshroom_batch" --input "$RUN_ROOT/input/synthetic-markers/images" \
  --pipeline "$RUN_ROOT/projects/synthetic-markers.mg" --cache "$RUN_ROOT/cache/synthetic-markers" \
  --save "$RUN_ROOT/projects/synthetic-sfm.mg" --toNode StructureFromMotion_1 \
  >"$RUN_ROOT/jobs/synthetic-sfm-launch.log" 2>&1 </dev/null &
```

Для `cctag` заменить input/project/cache и имя job, сверить бюджет до старта. **Dice требует отдельного masked-профиля ниже; старое unmasked-облако не принято как источник детали.** Читать `status` и указанный там attempt log; завершение SSH не означает завершения job. Повтор того же command/cwd — только `--resume` перед `--`, после проверки прежней группы. Успешный job повторно не исполняется. Для прерванных native chunks `--forceStatus` применять осознанно после проверки процессов; кэш не удалять, `--forceCompute` автоматически не добавлять. Отмена — TERM записанному runner PID; дождаться cleanup и проверить его process group.

Изменение команды, аргументов или cwd — новое задание runner: сначала проверить
завершение прежнего PID/PGID, затем выбрать **новый JOB_DIR**. Старые command/status/log
сохраняются. Передать новой команде прежние native `--cache`/`--save` пути, если
это действительно тот же проект: Meshroom повторно использует успешные узлы,
а изменённые настройки определяют нужный пересчёт. Не удалять command.sha256 и
не подменять старую binding ради `--resume`; этот флаг допускает только неизменную
команду. Например, переход `--toNode ImageMasking_1` → `--toNode Meshing_1` использует
новый JOB_DIR при том же графе/кэше, после подтверждённого завершения первой стадии.

Dice строится заново из **установленного официального шаблона**, с маской до FeatureExtraction и общей маской для PrepareDenseScene:

```bash
python3 "$REPO/scripts/bind_dense_scene.py" "$MESHROOM_ROOT/lib/meshroom/pipelines/photogrammetry.mg" \
  '{StructureFromMotion_1.output}' "$RUN_ROOT/projects/dice-white-template.mg" \
  --mask-config "$REPO/configs/mask-turntable-white.json" --mask-features
"$MESHROOM_ROOT/meshroom_batch" --input "$RUN_ROOT/input/dice" \
  --pipeline "$RUN_ROOT/projects/dice-white-template.mg" --overrides "$REPO/configs/photos.json" \
  --cache "$RUN_ROOT/cache/dice-white" --save "$RUN_ROOT/projects/dice-white.mg" --compute no
```

В `--mask-features` допускается только точная строка `'{StructureFromMotion_1.output}'`. ImageMasking получает `{CameraInit_1.output}`, FeatureExtraction.masksFolder и PrepareDenseScene.masksFolders получают один `{ImageMasking_1.output}`. Поэтому зависимости ацикличны: CameraInit → ImageMasking → FeatureExtraction → SfM → dense; маска не читает SfM. Новый cache `dice-white` и новые UID не подмешивают отклонённый unmasked-результат. Применить `configs/photos.json`: SIFT, движение 2 px, downscale=4.

Эти команды и следующие стадии — bounded jobs с разными каталогами. Сначала `--toNode ImageMasking_1`: проверить все 20 PNG по VIEW_ID, размеры как у оригиналов, фон=0 и сохранённую предметную область. Белый ключ: Saturation 0–0.15, Value 0.7–1, invert=true; он задан по цвету фото, не по размерам объекта. Затем `--toNode StructureFromMotion_1` и проверить камеры/соответствие облака кубику. После — PrepareDenseScene с alpha-проверкой и Meshing в том же новом кэше. Во всех dense commandLine должен быть ABC текущего masked SfM UID; зафиксировать его SHA256. Точность и идентичность поверхности подтверждать результатом; валидный PLY или множество камер сами по себе недостаточны. Масштаб Dice без контрольного размера остаётся `unverified`.

По native сохранённому графу/commandLine выбрать **точный** SfM ABC успешного UID, назначить `SFM_ABC`; не брать первый результат wildcard. Экспортировать markers-only JSON с views/poses/intrinsics. Далее пример **только для fixture с известной виртуальной базой**:

```bash
SCALED_ABC="$RUN_ROOT/output/synthetic-scaled-100mm.abc"
aliceVision_convertSfMFormat --input "$SFM_ABC" --output "$RUN_ROOT/output/markers-before.json" --describerTypes cctag3
aliceVision_sfmTransform --input "$SFM_ABC" --output "$SCALED_ABC" \
  --method from_markers --landmarksDescriberTypes cctag3 --markers '0:0,0,0' '1:100,0,0' \
  --applyScale 1 --applyRotation 1 --applyTranslation 1 --scale 1
aliceVision_convertSfMFormat --input "$SCALED_ABC" --output "$RUN_ROOT/output/markers-after.json" --describerTypes cctag3
sha256sum "$SCALED_ABC" >"$RUN_ROOT/output/scaled.sha256"
```

Эти вычисления также выполняются внутри ограниченного job. Флаги 1/1/1 и scale=1 сверены с сохранённым `output/synthetic-transform.log`: принято общее преобразование всей сцены, не изменение взаимных углов. Python-check после копирования JSON: `check_marker_scale.py BEFORE AFTER --ids 0 1 --distance 100 --units mm --reference TRUTH_JSON --output REPORT_JSON`. Нужны реконструированные наблюдения обеих меток, сохранённые observation IDs и числовая ошибка. Реальному CCTag-набору Natowi нельзя назначать 100 мм без независимого расстояния; его масштаб остаётся `unverified`.

## Плотное облако и проверка масок

Не изменять содержимое принятого scaled ABC по прежнему пути: native UID учитывает путь, а не SHA файла. `bind_dense_scene.py` меняет четыре сериализованных dense-input и задаёт `header.template=true`; `--paramOverrides` связанных полей не разрывает рёбра. **Для synthetic** маска применяется только к PrepareDenseScene, без `--mask-features`:

```bash
python3 "$REPO/scripts/bind_dense_scene.py" "$RUN_ROOT/projects/synthetic-sfm.mg" "$SCALED_ABC" \
  "$RUN_ROOT/projects/synthetic-dense-template.mg" --mask-config "$REPO/configs/mask-synthetic-background.json"
"$MESHROOM_ROOT/meshroom_batch" --input "$RUN_ROOT/input/synthetic-markers/images" \
  --pipeline "$RUN_ROOT/projects/synthetic-dense-template.mg" --overrides "$REPO/configs/synthetic-markers.json" --cache "$RUN_ROOT/cache/synthetic-markers" \
  --save "$RUN_ROOT/projects/synthetic-dense.mg" --compute no
```

Это тоже bounded job. Проверить literal `SCALED_ABC` у PrepareDenseScene/DepthMap/DepthMapFilter/Meshing, новые native UID, отсутствие UidConflict и верность зависимых cache paths. Применить `configs/synthetic-markers.json` до генерации SfM-графа: FOV, SIFT+cctag3, downscale=1, а у Meshing `maxNbConnectedHelperPoints=0`, `saveRawDensePointCloud=true` сохраняются и в dense-профиле. Для fixture фон в исходнике — серый **110/255**, поэтому маска выделяет HSV Value **0.42–0.44**, Saturation 0–0.1, invert=true. Это цветовая маска исходных пикселей, не обрезка под известный размер; чёрный ключ здесь неверен.

Сначала запустить до `ImageMasking_1`, проверить PNG по каждому VIEW_ID, размеры 1200×900 и mask=0 на фоновом углу; проверить сохранённую предметную область. FeatureExtraction маски не получает. Затем запустить до `PrepareDenseScene_1`, проверить alpha=0 фона EXR и отсутствие предупреждения об игнорировании маски. Только после этого — до `Meshing_1`, через `nohup remote_job`, тот же граф/кэш, отдельные job directories и подходящий остаточный TTL. В emitted commandLine всех четырёх стадий сверить scaled input; после — SHA исходного ABC.

В финальном synthetic-профиле сохраняются оба облака: `densePointCloud_raw.abc` до graph cut и `densePointCloud.abc` после обработки. Сами helper-параметры не устранили наблюдавшиеся увеличенные габариты; причиной или исправлением их не объявлять. `saveRawDensePointCloud` имеет `uid=[]`: включение флага у готового старого кэша само не пересчитает Meshing. Использовать окончательный профиль с самого начала; старые диагностические результаты не подменяют его. Выбрать точный Meshing UID и экспортировать принятый `densePointCloud.abc` в PLY:

```bash
aliceVision_convertSfMFormat --input "$DENSE_ABC" --output "$RUN_ROOT/output/dense.ply" --describerTypes unknown
```

Проверить ненулевое число конечных точек, габариты и связь с source ABC. Числовая база и валидный PLY не подтверждают правильность конечной детали.

## Выгрузка и прекращение начислений — до локального CAD

Сохранить проекты, scaled/dense ABC, камеры, PLY, конфиги, runtime probes, status/logs и нужные UID кэша; сырьё уже должно иметь постоянную копию. Составить SHA256, упаковать согласованные результаты, скачать через SCP/штатный copy в `WORK` и сравнить хэш **и читаемость** файлов. Большой кэш выбирать осознанно, а не терять молча. Лишь затем проверять stop/destroy.

```powershell
scp -F "$work/ssh_config" photogrammetry-goal2:/root/goal2/deliverable.tar.gz "$work/deliverable.tar.gz"
Get-FileHash "$work/deliverable.tar.gz" -Algorithm SHA256
```

Stop-test запускается **в том же проверенном native окружении onstart**. Если запуск нужен из SSH, сначала сверить PID исходного watchdog по приватной карточке, `/proc/PID/cmdline` (точный deadline-скрипт и каталог задания) и ожидаемому instance ID. С отключённым xtrace считать из `/proc/PID/environ` только записи с именами `CONTAINER_ID` и `CONTAINER_API_KEY`, сохранить их только в памяти и экспортировать двум переменным дочернего процесса; проверить ID по карточке. Полный environ, значения ключа, argv с ключом и их логирование запрещены. Затем запустить отдельный `rental_deadline.sh` на now+5 секунд в `jobs/deadline-stop-test`, не продлевая исходный deadline. Без проверенного окружения такой SSH-вызов не является stop-test.

SSH может исчезнуть до записи ответа: принятие запроса ещё не доказывает остановку, состояние проверять **снаружи** через native v1 список. Признак подтверждённого stop: `cur_state=stopped` и `actual_status` в `{exited, stopped}`; `intended_status/next_state=stopped` дополняют проверку. Одиночный `exited` может быть аварией и не принимается. Stop сохраняет данные и платный диск. После подтверждённой выгрузки выполнить в том же защищённом контексте доступа `& $vastai destroy instance INSTANCE_ID -y`, затем независимо подтвердить отсутствие конкретного ID в нефильтрованном v1 списке, пройдя все страницы через `--next-token`, если они есть. **`-y` обязателен:** без него наблюдались интерактивный `Aborted` и exit0. Обработчик destroy даже с `--raw` не гарантирует JSON; общий JSON-парсер и exit code не заменяют проверку провайдера. Начисления и окончательный invoice сверяются отдельно. Не трогать чужие инстансы/тома. При неподтверждённом удалении задание не считать закрытым; фактический результат проверки отражается только в [записи Goal](goal-2.md).

## Облако → параметры → CAD на CPU

После освобождения ноды использовать локальный Python из venv. ROI выбрать по реальному просмотренному облаку, не по ожидаемому размеру; формат `XMIN YMIN ZMIN XMAX YMAX ZMAX` в единицах входа. Для synthetic scaled cloud `--meters-per-unit 0.001 --scale-status synthetic_reference`; для реального Dice без контрольного размера — `unverified`, 1 произвольная source unit = 1 условный CAD мм, не физический миллиметр. Пример payload (границы назначить до вызова):

```powershell
& $python "$repo/scripts/extract_plane.py" "$work/output/dense.ply" "$work/output/patch.json" --roi $xmin $ymin $zmin $xmax $ymax $zmax --meters-per-unit 0.001 --distance-mm 1 --scale-status synthetic_reference --scale-note 'Synthetic marker baseline; not measured capture accuracy'
```

Проверить `patch.svg` с подписанными вершинами/направлением normal, `patch.inliers.ply` и JSON: источник/SHA, плоскость, реальный выпуклый контур и residual. Порог RANSAC 1 мм — параметр отбора, не обещанная точность. Выпуклая оболочка может соединять дыры/отдельные области. Оси не являются измеренной вертикалью; скрытая толщина остаётся `unresolved`.

Для технического пилота явно записать в копии JSON поле `"thickness": {"value_mm": 2, "status": "test_assumption", "note": "Test extrusion; hidden thickness not measured"}`; для реальной детали — решение человека/замер. Не уравнивать стороны и не выпрямлять углы ради красивого STEP.

```powershell
& $python "$repo/scripts/build_cad.py" "$work/output/patch-decided.json" "$work/output/cad"
& $python "$work/output/cad/model.py" --output "$work/output/cad/rebuilt.step"
```

Проверить `inspection.json`, повторное чтение STEP, одно валидное тело, объём, положение и размеры. В самодостаточном `model.py` изменить только thickness 2→5 мм и пересоздать второй STEP; проверить изменение объёма при неизменном контуре. Исходник модели и оба результата сохранить. Готовность технической цепочки, точность собственных фото и пригодность к изготовлению оценивать раздельно в записи Goal.
