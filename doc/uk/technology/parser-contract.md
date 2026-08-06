# Контракт парсерів — pure-Python Codimension

> **Мова / Language:** Українська | [English](../../technology/parser-contract.md)

**Статус:** нормативний для `brief_ast` / `flow_ast` (shim `cdmpyparser` / `cdmcfparser`)  
**Python:** 3.10–3.13  
**План:** T001–T029 (завершено 2026-08; див. ChangeLog / Living Spec)  
**Дата:** 2026-08-03

Єдине джерело істини для коректності парсерів. Реалізація має відповідати `tests/conformance/` і `tests/test_source_spans.py`. Якщо поведінка старих C-розширень суперечить контракту — **перемагає контракт**; **імена** shim-модулів зберігаються.

---

## 1. Ролі

| Парсер | Shim | Відповідальність |
|--------|------|------------------|
| `codimension.parsers.brief_ast` | `cdmpyparser` | Brief-модель: імпорти, globals, класи, функції, атрибути, docstring, encoding |
| `codimension.parsers.flow_ast` | `cdmcfparser` | Дерево фрагментів CFG для Flow UI |

---

## 2. Кодування джерела

1. Відкриття файлів — **`tokenize.open(path)`** (PEP 263).
2. In-memory API отримує вже декодований `str`.
3. `open(..., encoding="utf-8", errors="replace")` у entry points **заборонено**.

---

## 3. Spans і позиції

### 3.1 Зміщення Python AST

Згідно з документацією `ast`:

- `lineno` / `end_lineno` — 1-based.
- `col_offset` / `end_col_offset` — **байти UTF-8** у рядку.
- `end_col_offset` — позиція **після** останнього символа (exclusive у byte-space).

### 3.2 Абсолютні позиції Codimension

Спільний модуль: `codimension.parsers.source_spans` (T003).

| Поле | Значення |
|------|----------|
| `begin` | 0-based **символьний** індекс у `str` |
| `end` | 0-based **exclusive** символьний індекс: `source[begin:end]` |
| `beginLine` / `endLine` | 1-based номери рядків |
| `beginPos` / `endPos` | 1-based **символьні** колонки (для UI) |

**Правила:**

1. Таблиця початків рядків — **один раз** на parse.
2. Byte offset → character offset через UTF-8 рядка.
3. **Без `end + 1`** після exclusive conversion.
4. Multibyte-символи перед вузлом не зміщують наступні.
5. За потреби — `ast.get_source_segment`.

### 3.3 Legacy-дефект (виправити)

Поточні `flow_ast` / `brief_ast` використовують `SourceIndex` (UTF-8 byte→char) і
exclusive-end offsets (`source[begin:end]`). Comment binder: `abs_from_character_column`
для tokenize (A07). Header class/function: precomputed `TokenIndex` розділяє
keyword / identifier / header colon (B04). Залишок кластера OPEN: CML/comments
(D04/B05), `case` (B06), multiline side comments (D06).

---

## 4. Brief-модель (`brief_ast`)

### 4.1 Функції

- `FunctionDef` і `AsyncFunctionDef` у всіх dispatch-точках.
- `isAsync=True` лише для `AsyncFunctionDef`.

### 4.2 Аргументи

- `posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kwarg`.
- Defaults зіставляються з відповідними trailing positional args (**не** усі на `arguments[-1]`).
- `kw_defaults` ↔ `kwonlyargs`.

### 4.3 Атрибути

- Instance: `self.NAME` / `cls.NAME` (`ast.Attribute`), не локальні `Name`.
- Class attributes: присвоєння імен у тілі класу.
- Збір усередині `if`/`for`/`try`/`with`/`match` і вкладених функцій — обов’язковий.

### 4.4 Присвоєння

- `AnnAssign`, `AugAssign`, unpacking, chained assign — без тихої втрати імен для brief UI.

---

## 5. Flow-фрагменти (`flow_ast`)

Числові `*_FRAGMENT` константи зберігаються для UI.

| Конструкція | Вимога |
|-------------|--------|
| `match`/`case` | Не лише silent `CODEBLOCK` — окремі kinds |
| `except*` | Відмінно від звичайного `TRY` (`TRY_STAR`) |
| `async for` / `async with` | Той самий kind + `isAsync=True`; `withItems` |
| comprehensions | `CodeBlock` з `isComprehension=True` і повним span |
| Module docstring | Один раз; без дубля як code block |
| Func/class docstring | Поля docstring заповнені |
| Comments / CML / shebang / encoding | Через `tokenize` (`comment_binder`); поля не порожні |

---

## 6. Продуктивність

Складність позицій: `O(source + nodes)`, не `O(nodes × lines)`.

---

## 7. Тести

Авторитетні: conformance + goldens + `source_spans`. «46 pytest» без них ≠ готовність парсера.

---

## 8. Non-goals контракту

- Редизайн UI Flow.
- Видалення імен shim.
- Повна parity з історичними багами C-парсерів.

---

## 9. Зміна контракту

Оновити en+uk, Living Spec, snapshots; при зміні spans — T028.1.
