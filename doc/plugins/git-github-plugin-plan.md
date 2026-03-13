# План створення плагіна Git/GitHub для Codimension IDE

**Версія:** 1.0  
**Дата:** 2025-03  
**Статус:** План

---

## 1. Мета та контекст

### 1.1 Ціль

Реалізувати плагін для повноцінної роботи з Git та GitHub безпосередньо в IDE:

- **Git:** status, add, commit, push, pull, branch, checkout, merge, stash, diff, log
- **GitHub:** pull request (створення, перегляд), clone, fork (через gh CLI або API)

### 1.2 Категорія плагіна

**VersionControlSystemInterface** — існуюча категорія для VCS-плагінів. Забезпечує:

- `getStatus(path, flag)` — статус файлів/директорій (викликається у окремому потоці)
- `getCustomIndicators()` — іконки для Project Browser та status bar
- `populateMainMenu()` — пункти в головному меню
- `populateFileContextMenu()` — контекстне меню для файлу
- `populateDirectoryContextMenu()` — контекстне меню для директорії
- `populateBufferContextMenu()` — контекстне меню для буфера редактора

### 1.3 Архітектурні рішення

| Аспект | Рішення | Обґрунтування |
|--------|---------|---------------|
| Виконання Git | `subprocess` / `QProcess` | Git CLI — стандарт, не потребує Python-бібліотек |
| GitHub PR | `gh` CLI (GitHub CLI) | Офіційний інструмент, OAuth, не потребує API token для базових операцій |
| Альтернатива GitHub | PyGithub / REST API | Для користувачів без `gh`, потребує token |
| Індикатори статусу | getCustomIndicators() | Modified, Added, Deleted, Untracked, Conflict — 5+ іконок |

---

## 2. Структура плагіна

### 2.1 Дерево файлів

```
cdmplugins/git/
├── git.cdmp                    # Опис плагіна (Name, Module, Documentation)
├── __init__.py                 # GitPlugin(VersionControlSystemInterface)
├── gitdriver.py                # Виконання git/gh команд (QProcess)
├── gitstatusparser.py          # Парсинг git status --porcelain
├── gitdialogs.py               # Діалоги: Commit, Push, Pull, CreateBranch, CreatePR
├── gitconfig.py                # Конфіг: шлях до git/gh, default remote
└── icons/                      # Іконки статусів (опційно, або через getPixmap)
    ├── git-modified.png
    ├── git-added.png
    ├── git-deleted.png
    ├── git-untracked.png
    └── git-conflict.png
```

### 2.2 Залежності

- **git** — системна утиліта (обов'язково)
- **gh** (GitHub CLI) — опційно, для PR та GitHub-специфічних операцій
- **Python:** лише stdlib + PyQt5 (вже є в Codimension)

---

## 3. Фази імплементації

### Фаза 0: Підготовка (1–2 дні)

| Крок | Дія | Результат |
|------|-----|-----------|
| 0.1 | Створити `cdmplugins/git/` | Базова структура |
| 0.2 | git.cdmp, __init__.py з заглушками | Плагін завантажується |
| 0.3 | getCustomIndicators(), getStatus() — заглушка | VCS framework приймає плагін |
| 0.4 | Додати в setup.py, package_data | Плагін встановлюється з IDE |

**Критерій готовності:** Плагін з’являється в Plugin Manager, активується без помилок.

---

### Фаза 1: Git Status (2–3 дні)

**Пріоритет:** Високий. Без status решта операцій не має сенсу.

| Крок | Дія | Результат |
|------|-----|-----------|
| 1.1 | GitStatusParser: парсинг `git status --porcelain=v2` | Словник path → status |
| 1.2 | getStatus(path, flag): виклик git, парсинг, повернення списку (path, id, msg) | Іконки в Project Browser |
| 1.3 | getCustomIndicators(): Modified, Added, Deleted, Untracked, Conflict | 5 іконок |
| 1.4 | Обробка .gitignore, піддиректорій | Коректний статус для директорій |

**Формат git status --porcelain=v2:** Стабільний, машинно-читабельний.

**Критерій готовності:** У Project Browser відображаються іконки статусу для файлів у Git-репозиторії.

---

### Фаза 2: Базові Git-операції (3–4 дні)

**Пріоритет:** Високий.

| Крок | Дія | Результат |
|------|-----|-----------|
| 2.1 | GitDriver: `runGit(cwd, args) -> (stdout, stderr, returncode)` | Універсальний виконавець |
| 2.2 | populateDirectoryContextMenu: Commit, Push, Pull, Create branch | Контекстне меню для кореня репо |
| 2.3 | populateFileContextMenu: Add, Discard, Diff | Контекстне меню для файлу |
| 2.4 | CommitDialog: поле повідомлення, чекбокс "Amend" | Діалог коміту |
| 2.5 | Після commit/push/pull — оновити VCS status (requestStatus) | IDE оновлює іконки |

**Контекстні меню:**

- **Директорія (корінь .git):** Commit, Push, Pull, Create branch, Stash, Log
- **Файл (modified):** Add, Discard changes, Show diff
- **Файл (untracked):** Add

**Критерій готовності:** Commit, Push, Pull виконуються з контекстного меню.

---

### Фаза 3: Гілки та Stash (2–3 дні)

**Пріоритет:** Середній.

| Крок | Дія | Результат |
|------|-----|-----------|
| 3.1 | CreateBranchDialog: ім’я гілки, base (поточна/інша) | Діалог створення гілки |
| 3.2 | CheckoutDialog: список гілок, переключення | Діалог checkout |
| 3.3 | StashDialog: stash push/pop/list | Робота зі stash |
| 3.4 | populateMainMenu: Git → Commit, Push, Pull, Branches, Stash | Головне меню |

**Критерій готовності:** Створення гілки, checkout, stash push/pop.

---

### Фаза 4: GitHub Pull Request (3–4 дні)

**Пріоритет:** Середній. Потребує `gh` CLI (або PyGithub).

| Крок | Дія | Результат |
|------|-----|-----------|
| 4.1 | Перевірка наявності `gh`: `gh auth status` | Визначити, чи є GitHub CLI |
| 4.2 | CreatePRDialog: base branch, title, body (опційно) | Діалог створення PR |
| 4.3 | Виконання: `gh pr create --base X --title Y --body Z` | Створення PR |
| 4.4 | Опція в меню: "View pull requests" → `gh pr list` у виводі | Перегляд PR |
| 4.5 | Конфіг: шлях до gh, fallback на GitHub API (опційно) | Гнучкість |

**Обмеження:** Без `gh auth login` створення PR не працюватиме. Документувати в README.

**Критерій готовності:** Створення PR з поточної гілки через діалог.

---

### Фаза 5: Інтеграція з буфером та додаткові операції (2–3 дні)

**Пріоритет:** Низький.

| Крок | Дія | Результат |
|------|-----|-----------|
| 5.1 | populateBufferContextMenu: Commit, Add, Diff | Контекстне меню для відкритого файлу |
| 5.2 | Гаряча клавіша Ctrl+Shift+G (Git) | Швидкий доступ |

**Критерій готовності:** Операції з файлу в редакторі.

---

### Фаза 6: Тести та документація (2 дні)

| Крок | Дія | Результат |
|------|-----|-----------|
| 6.1 | Unit-тести: GitStatusParser | tests/test_gitstatusparser.py |
| 6.2 | Unit-тести: GitDriver (mock subprocess) | tests/test_gitdriver.py |
| 6.3 | Оновити doc/plugins/plugins.md | Опис плагіна |
| 6.4 | Оновити Living Specification | doc/plugins/living-specification.md |

---

## 4. Технічні деталі

### 4.1 Визначення кореня репозиторію

```python
def findGitRoot(path: str) -> str | None:
    """Повертає шлях до кореня .git або None."""
    current = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
```

### 4.2 Мапінгування git status на індикатори

| git status --porcelain | Індикатор ID | Опис |
|------------------------|--------------|------|
| M (modified) | 0 | Modified |
| A (added) | 1 | Added |
| D (deleted) | 2 | Deleted |
| ? (untracked) | 3 | Untracked |
| U (unmerged) | 4 | Conflict |

### 4.3 Потік виконання операцій

1. Користувач обирає пункт меню (Commit, Push, …).
2. Плагін викликає `findGitRoot(path)` для path з контексту.
3. Якщо корінь не знайдено — повідомлення "Not a Git repository".
4. GitDriver виконує команду через `QProcess` або `subprocess`.
5. Після успіху — `self.ide.vcsManager.requestStatus(path)` для оновлення UI.
6. Помилки — QMessageBox з stderr.

### 4.4 Конфігурація (getConfigFunction)

- Шлях до `git` (за замовчуванням: `git` з PATH)
- Шлях до `gh` (за замовчуванням: `gh` з PATH)
- Default remote (origin)
- **GitHub username** — для Git credential (HTTPS push/pull), відповідь на запит Git
- **GitHub token (PAT)** — для REST API (Create PR, View PRs). Fine-grained або classic (ghp_xxx).
- **Repository (override)** — ручне введення owner/repo або URL. Якщо задано — використовується замість git remote. Дозволяє View PRs без git-репо.
- Доступ: Plugin Manager → Git → іконка налаштувань; Repository (override) — **Project → Git repository...** (меню Project)

---

## 5. Ризики та обмеження

| Ризик | Мітигація |
|-------|------------|
| Git не встановлено | Перевірка при activate, повідомлення в Plugin Manager |
| gh не встановлено | PR-функції недоступні, інформаційне повідомлення |
| Великі репозиторії (status повільний) | getStatus вже в окремому потоці (VCSPluginThread) |
| Конфлікт з іншими VCS-плагінами | Git і SVN можуть співіснувати; перевірка .git |
| Конфлікт гарячих клавіш | Ctrl+Shift+G — перевірити в існуючих плагінах |

---

## 6. Порядок виконання

```
Фаза 0 (підготовка)
    ↓
Фаза 1 (Status)
    ↓
Фаза 2 (Commit, Push, Pull)
    ↓
Фаза 3 (Branches, Stash)     Фаза 4 (GitHub PR)
    ↓                              ↓
Фаза 5 (Buffer, shortcuts)
    ↓
Фаза 6 (Тести, документація)
```

**Паралелізація:** Фази 3 і 4 можна виконувати паралельно після Фази 2.

---

## 7. Оновлення setup.py

```python
# getPackages()
'cdmplugins.git',

# package_data
('cdmplugins.git', 'cdmplugins/git/'),
```

---

## 8. Критерії готовності (MVP)

- [ ] Плагін завантажується, активується
- [ ] Git status відображається в Project Browser
- [ ] Commit, Push, Pull з контекстного меню
- [ ] Create branch, Checkout
- [ ] Create PR (за наявності gh)
- [ ] Документація оновлена
- [ ] Unit-тести для парсера

---

## 9. Посилання

- [VersionControlSystemInterface](vcsiface.py) — інтерфейс VCS
- [VCSPluginThread](vcspluginthread.py) — потік для getStatus
- [plugins-implementation-plan.md](plugins-implementation-plan.md) — референсний план
- [GitHub CLI](https://cli.github.com/)
