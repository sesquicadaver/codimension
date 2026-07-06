# GPL v3 — Відповідність ліцензії у форку

**Дата оновлення:** 2026-07-06  
**Форк:** https://github.com/sesquicadaver/codimension  
**Upstream:** https://github.com/SergeySatskiy/codimension (Sergey Satskiy)

## Статус (виконано)

| Вимога GPL v3 (§5) | Реалізація |
| ------------------ | ---------- |
| Помітне повідомлення про модифікацію | `codimension/ui/about.py` — «Modified version. See FORK.md» |
| Збереження ліцензії | `LICENSE`, GPL v3 |
| Attribution оригіналу | Copyright Sergey Satskiy у заголовках файлів; [FORK.md](../FORK.md), [README.md](../README.md) |
| Посилання на форк | `pyproject.toml` `[project.urls]`, `setup.py` `url` → sesquicadaver/codimension |

## Документація модифікацій

- [FORK.md](../FORK.md) — перелік змін форку
- [README.md](../README.md) — активний репозиторій, не upstream
- [ChangeLog](../ChangeLog) — історія змін

## Історичні посилання

Посилання на http://codimension.org у `about.py`, `helpwidget.py` тощо залишені як **архівні** (оригінальний проєкт). Актуальна розробка — лише у форку.

## Рекомендації для нових змін

1. Не видаляти copyright upstream у модифікованих файлах.
2. При суттєвих змінах — запис у `ChangeLog` і за потреби `FORK.md`.
3. Нові файли форку: `# Copyright (C) 2025–2026 Codimension fork contributors` або аналог.

## Підсумок

Форк відповідає мінімальним вимогам GPL v3 щодо помітної модифікації та attribution. Деталі ліцензії — [LICENSE](../LICENSE).
