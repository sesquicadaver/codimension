# GPL v3 — Зміни коду для відповідності ліцензії

Цей документ описує **рекомендовані зміни коду** для повної відповідності GPL v3 у модифікованій версії. Поки що ці зміни **не внесені** — лише задокументовані.

## Вимоги GPL v3 (Section 5)

- **5a:** Модифікована робота повинна містити помітні повідомлення про зміни та дату.
- **5b:** Повідомлення про ліцензію та умови мають бути збережені.

## Рекомендовані зміни

### 1. About Dialog (`codimension/ui/about.py`)

**Поточний стан:** Copyright (c) Sergey Satskiy 2010-2019

**Рекомендація:** Додати рядок про модифікацію, наприклад:

```python
"</b><p>Copyright (c) Sergey Satskiy 2010-2019</p>"
"<p>Modified version. See FORK.md.</p>")
```

Або розширити copyright:

```python
"</b><p>Copyright (c) Sergey Satskiy 2010-2019. Modified 2025.</p>"
```

### 2. Посилання на codimension.org

**Файли:** `about.py`, `welcomewidget.py`, `mainwindow.py`, `helpwidget.py`, `versions.py`

**Поточний стан:** Посилання на http://codimension.org (сайт може бути недоступний або застарілим)

**Рекомендація:** Залишити як є — це історичні посилання на оригінальний проєкт. Додати посилання на цей форк у About та Welcome (опційно).

### 3. setup.py / pyproject.toml

**Поточний стан:** `url='https://github.com/SergeySatskiy/codimension'`

**Рекомендація:** Змінити на URL форку або додати `project_urls` з посиланням на форк. Автор залишається Sergey Satskiy (attribution).

### 4. Заголовки файлів

**Поточний стан:** Більшість файлів мають `# Copyright (C) 2010-20XX Sergey Satskiy`

**Рекомендація:** Залишити без змін. GPL не вимагає змінювати copyright у кожному файлі — достатньо помітного повідомлення в About та README.

### 5. Файл NOTICE або COPYRIGHT

**Рекомендація:** Створити `NOTICE` або розширити README секцією:

```
This is a modified version of Codimension (https://github.com/SergeySatskiy/codimension).
Original Copyright (c) Sergey Satskiy. Modified 2025.
Licensed under GPL v3. See LICENSE.
```

## Підсумок

| Зміна | Пріоритет | Складність |
|-------|-----------|------------|
| About dialog — додати "Modified" | Високий | Низька |
| setup.py url → fork | Середній | Низька |
| NOTICE / README секція | Середній | Низька |
| Посилання codimension.org | Низький | — |

Після внесення змін оновити цей документ.
