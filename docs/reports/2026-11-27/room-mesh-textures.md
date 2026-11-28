# Комната: сетка, фотографические текстуры и Meshroom

Для комнаты #27 получены raw cloud/mesh, filtered OBJ и отдельный облегчённый
MeshDecimate OBJ с фотографическим OBJ/MTL и одиннадцатью PNG. Сохранены граф
выполненного продолжения и полная предыдущая версия с десятью PNG.
Это результат [Goal #40](../../goal-40.md). Native GUI и обычный launcher
проверены независимым агентом после удаления compute; личный осмотр владельцем
ожидается отдельно. Состояние публикации и источники проверки — в записи Goal.
Физический масштаб остаётся unknown, пригодность комнаты для обмеров — PARTIAL.

## Полная исходная версия, 27 ноября

Использована прежняя реконструкция, без нового SfM, DepthMap или Meshing.
Проверены 494 исходных payload-файла, 77 JPEG и SHA retained Linux runtime.
Native graph загрузился строго: 18/18 UID, без compatibility nodes.
Вычислительный комплект сохранён: Meshroom `b12ea889`, AliceVision `d012d055`.

В Standard восстановлены только ExportImages: 77 EXR, 2877637987 байт.
Actual QA прочитал все image inputs. Первый job истёк после 70 файлов;
после подтверждённого завершения дерева повторена только вторая native chunk.
Исторический SUCCESS при отсутствующих EXR не использовался как доказательство
готовности входов. DepthMap/DepthMapFilter EXR для Texturing не потребовались.

Новые настройки сохранены отдельными RUN с явным shared cache. Сопоставление
графов подтвердило переиспользование upstream; при выборе нового Texture UID
изменились только Texturing/CopyFiles. Искусственных UID/SUCCESS нет.

| Выбранный узел | Фактические настройки и результат |
|---|---|
| MeshFiltering | smoothingIterations=0, keepLargestMeshOnly=false, filteringIterations=1, filterLargeTrianglesFactor=60, filterTrianglesRatio=0; SUCCESS |
| Texturing | Basic, UDIM, working8192/downscale4, PNG/sRGB, correctEV=true, high-band1/прочие0, fillHoles=false, subdivisionTargetRatio=0; SUCCESS |

Filter UID — `5aa45d0797fb9e3bacf50409b31a838bbb066b13`.
Texture UID — `3bc587f0d9c4745839e6f57a32d0b261575ea21e`.
Получены десять 2048×2048 RGB PNG, 8 bit; суммарно 126053240 байт.
У всех проверены CRC, IEND и native `AliceVision:ColorSpace=srgb`.
Фотографии и карты не перекодировались для совместимости с GUI.

Первый Basic2048/downscale1 создавал 161 атлас и был адресно остановлен.
Кандидат8192/downscale4 выбрал десять, но при hard3GiB был убит OOM на downscale
первого атласа. Native ERROR, oom_kill=1 и cleanup confirmed сохранены вместе
с log/status. После проверки ресурсов тот же graph повторён с 3GiB RAM и
не более 2GiB существующего swap, 2CPU/128PID, job TTL1800s. Он завершился
без OOM; observed swap peak911249408B, native Texturing954.212s.
Параметры качества после OOM не менялись.

Штатный provider не определил cgroup budget корректно. Тонкий
[CPU helper](../../../scripts/texturing_cpu.py) передал реальные native
`--maxMemoryAvailable 2147483648 --maxCoresAvailable 2` через временный PATH
provider.runtimeEnv. Actual argv/log подтвердили оба значения. Это подсказки
алгоритму; hard cgroup и срок задаются отдельно. Planning, executeGraph,
статусы и журналы остаются штатными. Core не изменён.

## Отдельный вариант для лимита GUI, 28 ноября

Полный результат выше сохранён. На этой Windows-машине обычный render полной
текстурированной сетки превысил Job limit 2 GiB и в Mesa, и в native D3D11;
сбой воспроизведён без capture, со снятым sparse и Material до event loop.
Окно было exposed и рисовало кадры; отключённая RDP-сессия не является
установленной причиной. Loader-ready/hasTextures не приняты за просмотр материала.

Для нового viewer-варианта добавлен штатный MeshDecimate после того же filter.
Сохранён native template, normal prepare --template создал новый RUN: 19 узлов,
0 compatibility nodes; 16 прежних upstream UID сохранены, у Texturing/CopyFiles
новые UID. MeshDecimate factor=0.5 — доля вершин, nb/min/maxVertices=0,
flipNormals=false. Алгоритм quadric без exposed boundary lock/max error.
MD UID `e1f1a39ec06c67ca3a74181722f348604ca284a3`; новый Texture UID
`ec5befd187d02a5cd51d2b4d36518a818d7c33cf`. Texturing SUCCESS за 867.056 s:
11 PNG 2048×2048 RGB8/sRGB, 138658564 байта; CRC/IEND проверены.
Новый native argv применил те же soft2GiB/2cores. Hard3GiB RAM+до2GiB swap,
2CPU/128PID/TTL1800; observed swap peak700497920B, oom/oom_kill=0.
Реальная GUI-проверка выбранного варианта завершена ниже.

MeshDecimate завершился native SUCCESS: 292056 вершин, 578910 треугольников.
OBJ SHA256 `6a191350a87bd345f2128676c258fb712b55b6b576f25a013a27de1851ece9d1`.
Native components 1392→1392, boundary edges 50→50, длина границы
18.6200538→18.6200560 условных единиц. После exact-XYZ welding components17→174:
это чувствительный к округлению тест совпадений, не доказательство появления
157 физических фрагментов. Нельзя называть вариант lossless.

Без fit/registration выполнены по 120096 ограниченных запросов в каждую сторону
(60000 area samples, 60000 vertices и 96 boundary samples) к Float32 поверхности.
Filtered→MD: p99=0.00365296, sampled max=0.0289462; MD→filtered:
p99=0.00111350, sampled max=0.00408093. Это scene units и конечная выборка,
не миллиметры и не строгая Hausdorff-граница. На общих проекциях XY/XZ/YZ
сохранены крупный силуэт и boundary loops; worst ROI и ближайшие XYZ сохранены
для сопоставления с фотографиями. Число граней не заменяет эту проверку.

MD выдаётся как ручная native operation с node/settings/source/output SHA;
это не расширение export-derived на MeshDecimate. Старые raw/filter/full texture
и их backup остаются отдельными. Новый textured OBJ: 448269 v / 285867 уникальных
XYZ / 578891 triangles. Все грани имеют допустимые UV, используются 11 materials.
XYZ совпадают с MD с двусторонним NN max2.78934e-7, bbox delta2.5e-7, без fit.
Однозначное reciprocal/injective сопоставление с учётом writer roundtrip выявило
19 удалённых triangle occurrences: 16 нулевой площади и 3 ненулевые общей
площадью0.17145017 условных единиц²; добавленных/перевёрнутых нет.
Это tolerant mapping с измеренным bound, не заявление об exact XYZ/lossless.
Новый OBJ SHA256 `0269185e430beb3b47df245409bdca221b982db49fd7fd9ef1b5d0ce4cee254d`.

Новый backup проверен полностью: 895 файлов / 5011378169 байт,
manifest SHA256 `e902bf5160180d189e1d16fae0fe6c0295d7df87d89fe637f5007df8db0677c9`.
Native raw mesh, dense.ply и scene.json побайтно совпали с прежней выдачей.
View — 410 файлов / 1041336457 байт, 77 JPEG, exact19-node graph без правки
UID/path/status; выбранные native USD payloads и OBJ/MTL/PNG closure проверены.
Native RUN textures-decimated скопирован под viewing alias textures;
shared cache сохранён. EXR/jobs/невыбранные UID и descriptor binaries остаются
в backup, точный список исключений сохранён в audit.

Новый контейнер удалён 28 ноября 08:09:01 UTC, его root — 08:09:59 UTC.
Все 15 baseline контейнеров сохранили ID/состояния. До удаления проверены backup
и retained runtime; текущий GUI не может читать удалённый compute root.
Native GUI уже показал материал, поворот и Material2→Shaded0→Material2 в том же
сохранённом ракурсе камеры оконного участка. Цвет возвращается к тому же кадру;
исходный JPEG этого участка открыт в native Image Viewer после выгрузки mesh.
Показана грубая, рваная поверхность. На фотографическом виде есть белые участки,
причина которых остаётся UNKNOWN. Проверены все 11 MTL/UV bindings и native
Repeat/Repeat; Material2 работает без освещения. Подтверждённого нарушения
материалов/UV не установлено; причина этих пикселей остаётся неизвестной.
Raw/filter/MD, параметры и журналы также открыты в GUI.

## Геометрия и происхождение полной исходной версии

Raw export и native Meshing OBJ сохранили SHA256
`87139e0fe9d0a92abc5db6afa53704d311ae54c0581dd76fceec00be1c6d8f4b`.
Filtered OBJ SHA256 —
`1d257aa4dbb2163f857d3fe9362ba8034c649cdb6eaf30cc51d92d4c34c3f101`.

| Показатель | Raw | Filtered |
|---|---:|---:|
| Строки OBJ `v` | 584109 | 584113 |
| Уникальные точные XYZ | 572228 | 572227 |
| Треугольники | 1163039 | 1163024 |
| Native boundary edges | 33 | 50 |
| Длина boundary, условные единицы | 9.2843 | 18.6201 |

Bbox совпал. Положения сохранившихся вершин согласуются с NNmax7.3e-12;
fitting/registration не применялись. Удалены 15 ненулевых граней и одна XYZ
позиция. Это лишь 0.00129% граней, но 1.89946% площади raw: счётчик граней
скрывал бы величину изменения. На трёх общих проекциях изменения образуют веер
крупных треугольников в разреженном конце комнаты. Рост строк `v` связан с
topology/дублированными координатами и не является новыми измерениями.
Удалённая позиция отстоит от ближайшей filtered на 0.35569 условных единиц.
Замкнутость и отсутствие потери полезных деталей по одним этим числам не заявлены.

Fixed native OBJ→cloud `diag(1,-1,-1)`, translation0, scale1 проверены по всем
584106 dense-точкам: NNmax8.51e-6 против identity median0.491/max2.965.
Поворот применялся только в памяти, оригинальные файлы сохранены.
Это подтверждает оси этого комплекта, не физический масштаб.
У raw есть три mesh-only позиции; равенство bbox mesh/cloud не заявляется.

Textured OBJ содержит 845891 строку `v`, те же 572227 уникальных XYZ и тот же
bbox. Оба NN max равны 7.3e-12; все filtered позиции сохранены. Рост на 261778
записей связан с дублированными XYZ/UV seams, новых геометрических позиций нет.
У 1163020 граней проверены UV-индексы, используются десять материалов.
При этом native Texturing удалил ещё четыре ненулевые грани общей площадью
0.312713134214 условных единиц² — около 0.17635% filtered площади. Их индексы
и координаты сохранены в audit; эффект не сводится к UV-дублированию.
Добавленных и перевёрнутых граней нет. Textured SHA256 —
`2b0c90595ae1d3d06cbd2d17094843eba74e4a209514b93e4ba26c8f1873da5b`.

Существующий report CLI выполнен на перенесённом final RUN с raw и двумя
`--derived`: status=reported, оба derived mesh проверены, scale=unknown.
Report SHA256 — `96bfb6816bd61c2bfabb258e5031b4651d172953dac105bbf713b455080c2b7f`.
Это проверка файлов/provenance; визуальное качество принимается отдельно.

`export-derived` отдельно сохраняет выбранный native output, полный material
closure, graph/settings snapshots и SHA receipt. Raw bindings не заменяются.
Выполнены оба реальных экспорта; portable model bundles содержат provenance.
Проверка включает все MTL/maps и связанные native USD payloads. CopyFiles
не использовался как замена backup.

## Выдача и локальный просмотр

В постоянном хранилище владельца сохранены:

- `models/raw`, `models/filtered`, `models/textured` — сохранённая полная версия;
- `models/decimated` — manual native MeshDecimate bundle с provenance;
- `models/textured-decimated` — полный связанный материал выбранного облегчённого RUN;
- `compute-backup` — 870 файлов, 4810677259 байт; каждый SHA сверён с frozen
  manifest после завершения всех jobs, до удаления контейнера;
- `view` — 523 файла, 1360881066 байт, с JPEG, native scenes/payloads, mesh,
  полным исходным материалом, фактическими status/logs и проектом продолжения;
- `compute-backup-decimated` — проверенные 895 файлов нового продолжения;
- `view-decimated` — выбранные 410 файлов / 1041336457 байт, exact19-node graph,
  77 JPEG, native scenes, raw/filter/MD/textured и доступные status/logs;
- `software`, `Open-Meshroom.cmd`, инструкция и `audit` — локальный запуск
  и проверяемое происхождение выдачи.

Manifest backup SHA256:
`7081422bfbf5580b2663fb159a43347d5e9e00c3e93310f3ddcf7aedc23da169`.
Из view исключены EXR, jobs, невыбранные RUN и невыбранные Texture caches;
точный список записан в audit. В полном selected-tail backup восстановленные
ExportImages EXR сохранены. DepthMap/DepthMapFilter EXR отсутствовали ещё в
исходном backup #27. Unpacked Linux runtime и повторные upload-архивы не дублируются:
закреплённый полный архив уже сохранён владельцем отдельно.

В view вычисленный `runs/textures-view` скопирован как `runs/textures` без
изменения graph bytes; shared cache остаётся `runs/standard/cache`.
Private staging перемещён и отсутствует. Граф original сохранён отдельно
от выполненного продолжения. Compute-resume Windows viewing subset не квалифицирован.

Квалифицированный маршрут — полный
[Windows Meshroom8df9560](https://github.com/alicevision/Meshroom/releases/download/nightly/Meshroom-2026.11.27-8df9560-windows-full.zip),
[Mesa26.3.1 x64](https://github.com/pal1000/mesa-dist-win/releases/download/26.3.1/mesa3d-26.3.1-release-msvc.7z)
и [native launcher](../../../scripts/meshroom_view.py). Сверены все 9574 software
файла, 2216246790 байт. Windows archive SHA
`93423f7ed9c6e8ca4c1629b258fe95e2543f6e222a89eda9ec357160c26f0038`;
Mesa archive SHA `64e84cf13d67dd354640bf443ed0445e6a83afd06a5729f0750b3744d633b3f1`.

App-local Mesa устранил наблюдаемую несовместимость Intel OpenGL4.3 с GLSL460;
native 8-bit/HDR-off открыл исходный JPEG. В отдельной перенесённой пробе видны
77 камер, фото и raw; 452 файла сохранили SHA, native loading=false/error='',
normal close0, mapping удалён. CameraInit VersionConflict12.1→12.2 сохранён;
node ради просмотра не обновлялся. Это не утверждение о Windows compute.
Фотографический комплект `view-decimated` уже открыт native GUI после удаления
обоих compute roots: actual цвет, поворот, Material↔Shaded, raw/filter/MD в ракурсе
оконного участка, исходное фото, 77 камер, параметры и реальный Texturing log.
Использован Qt readback собственного уже отрендеренного окна; rejected OS captures
и пустые кадры не принимаются. Windows view остаётся отдельным от compute pin.

Native default PBR недоступен для смены до окончания загрузки. Launcher теперь
выбирает проверенный Material один раз при создании MeshEntry штатным
Instantiator.objectAdded. Core, loader, graph/status не заменяются; пользователь
после загрузки может переключить Shading. Source/deployed launcher SHA256
`89538d15127ea0aa3fb1766cdd2ea8d70dbdfd6db3e6e8a8a396d3ffa9e38416`.
Полный обычный CMD→parentPython→gui-child показал full Texturing с этим public
default до ready; private shading/renderer overrides не применялись. Normal exit0,
cleanup confirmed, active0, свой drive снят, 410 SHA после запуска совпали.
Peak всего Job2123735040B при прежнем hard2147483648B; capture — собственное
уже отрендеренное Qt-окно. Штатная навигация и источник фото также проверены.
Личная приёмка владельцем ожидается отдельно от подтверждённого открытия агентом.

## Проверки и состояние ресурсов

77 reconstruction tests, 6 CPU-helper tests и 3 native Windows drive tests PASS.
Независимые scoped code reviews exporter/report/двух адаптеров — PASS.
Другой агент без истории чата разобрал cloud-only, важные края, SUCCESS без EXR
и красивый цвет поверх неверной геометрии; решения сверены с native contracts — PASS.
Проверено ограничение optional MeshDecimate: текущий exporter поддерживает
MeshFiltering/Texturing OBJ, другие выходы требуют отдельной квалификации.
Изменённые пути не запускают существующий capture-kit CI; его код не менялся.

Вычислительный контейнер удалён17:19:27UTC после проверенного backup.
Все15 baseline контейнеров VPS сохранили ID/состояние. Другие сервисы не менялись.
Vast-инстансы этой задачей не создавались, новых арендных расходов нет.
Task-owned remote data удалены 17:33:15 UTC после проверки backup и сохранности
owner runtime archive; прежний вычислительный root отсутствует физически.

На новом перенесённом RUN также выполнен существующий report CLI: status=reported,
два verified derived meshes, units=unknown. Native raw mesh/cloud/scene SHA
совпали с прежней выдачей. Новый контейнер/root удалены 28 ноября, см. выше.
Независимая приёмка feature/data/GUI — PASS; source-scoped review final профиля — PASS.
Код и инструкции опубликованы в [PR #41](https://github.com/Kwentin3/photogrammetry-to-cad/pull/41).
Уборка своей временной рабочей копии подтверждается после проверки remote head;
текущее состояние и следующий шаг — в единственной записи
[Goal](../../goal-40.md). Частные фото, mesh/cloud, raw logs и адреса доступа в Git
не включены. CAD и точность изготовления не проверялись.
