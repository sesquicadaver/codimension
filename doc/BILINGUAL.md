# Двомовна документація / Bilingual Documentation

Документація проєкту Codimension доступна **українською** та **англійською** мовами.

Project documentation is available in **Ukrainian** and **English**.

## Структура / Structure

| Каталог / Directory | Мова / Language | Призначення / Purpose |
| ------------------- | --------------- | --------------------- |
| [doc/uk/](uk/README.md) | Українська | Переклади документів, оригінально англійською |
| [doc/en/](en/README.md) | English | Translations of originally Ukrainian documents |
| `doc/<topic>/` | Змішано / Mixed | Канонічні шляхи (legacy); у заголовку — посилання на переклад |

Кореневі файли:

| Українська | English |
| ---------- | ------- |
| [README.md](../README.md) | [README.en.md](../README.en.md) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | [CONTRIBUTING.en.md](../CONTRIBUTING.en.md) |
| [FORK.md](../FORK.md) | [FORK.en.md](../FORK.en.md) |
| [TODO_FIXME.md](../TODO_FIXME.md) | [TODO_FIXME.en.md](../TODO_FIXME.en.md) |
| [NOTES.md](../NOTES.md) | [NOTES.en.md](../NOTES.en.md) |
| [ROADMAP.md](../ROADMAP.md) | [ROADMAP.uk.md](../ROADMAP.uk.md) |

## Оновлення / Maintenance

При зміні функціоналу оновлюйте **обидві** мовні версії відповідного документа (або додайте посилання, якщо повний переклад відкладено).

When changing functionality, update **both** language versions of the relevant document.

Обов'язковий чекліст:

1. `ChangeLog`
2. Відповідний розділ у `doc/uk/` або `doc/en/`
3. Канонічний файл у `doc/<topic>/`, якщо він існує
4. [plugins/living-specification.md](plugins/living-specification.md) — при зміні модулів або тестів
5. [TODO_FIXME.md](../TODO_FIXME.md) — при закритті або виявленні проблем

## Індекси / Indexes

- [doc/README.md](README.md) — головний двомовний індекс
- [doc/index.md](index.md) — короткий двомовний зміст
- [doc/uk/README.md](uk/README.md) — індекс українською
- [doc/en/README.md](en/README.md) — index in English
