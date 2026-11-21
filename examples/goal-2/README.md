# Проверяемые результаты технического Goal #2

[Отчёт и происхождение](../../docs/reports/2026-11-21/technical-run.md),
[повторение расчётов](../../docs/runbook.md).

| Каталог | Что можно открыть | Граница результата |
|---|---|---|
| `real-dice` | model.py, model.step, changed.step, параметры, question.svg, QA | Выпуклый участок грани из реальных фото; масштаб и толщина неизвестны |
| `synthetic-markers` | model.py, model.step, changed.step, параметры, question.svg, QA | Дополнительная 10-view реконструкция известной виртуальной сцены; не точность реальной съёмки |

`parameters-unresolved.json` сохраняет исходный вопрос. В `parameters.json`
содержится явно помеченное агентское `test_assumption`; `parameters-changed.json`
меняет только толщину. Это не ответ человека. Исходники моделей самодостаточны,
длины в CAD мм; у Dice эти единицы **номинальные**, не физически измеренные.

В подготовленном окружении, внутри managed payload по Windows-правилам из runbook:

```powershell
& $python scripts/build_cad.py examples/goal-2/real-dice/parameters.json "$work/rebuilt-dice"
& $python examples/goal-2/synthetic-markers/model.py --output "$work/rebuilt-metric.step"
& $python scripts/build_cad.py examples/goal-2/synthetic-markers/parameters-changed.json "$work/changed-metric"
```

Для редактирования самого model.py меняется `PARAMETERS['thickness']['value_mm']`;
для обычного повторения удобнее JSON и штатный build_cad. Контур, плоскость и
положение получены из облака. Автоматического полного восстановления детали нет:
выпуклая экструзия может заполнить отверстия и неподтверждённые области.

## Атрибуция материалов

Геометрия и QA `real-dice` производны от фотографий **alansartlog**,
[Dice turntable dataset](https://gitlab.com/photogrammetry-test-sets/dice-turntable-strong-lights-heavily-textured-w-watercolors),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Изменения: отбор20кадров,
маскирование фона, реконструкция, подгонка плоской области и тестовая экструзия.
Эти производные геометрические/визуальные материалы распространяются с указанной
атрибуцией по CC BY 4.0; это не назначение лицензии всему программному коду репозитория.

Для отдельной реальной проверки меток использованы фото **Natowi**,
[cctag-dataset](https://github.com/natowi/cctag-dataset),
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Их фотографии,
облако и overlay не включены сюда; происхождение числовых результатов раскрыто в отчёте.

`synthetic-markers` получен собственным геометрическим генератором проекта;
использованный банк радиусов CCTag закреплён в generator/truth. Ни один его размер
не выдаётся за физический обмер реального объекта. Крупные PLY, исходные фотографии,
cache и частные журналы остаются вне Git.
