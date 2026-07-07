> **Language / Мова:** English | [Українська](../LICENSE_COMPLIANCE.md)

# GPL v3 — Code Changes for License Compliance

This document describes **recommended code changes** for full GPL v3 compliance in the modified version. These changes have **not been applied yet** — they are documented only.

## GPL v3 Requirements (Section 5)

- **5a:** The modified work must contain prominent notices stating that it was modified and the date.
- **5b:** License notices and terms must be preserved.

## Recommended Changes

### 1. About Dialog (`codimension/ui/about.py`)

**Current state:** Copyright (c) Sergey Satskiy 2010-2019

**Recommendation:** Add a line about modification, for example:

```python
"</b><p>Copyright (c) Sergey Satskiy 2010-2019</p>"
"<p>Modified version. See FORK.md.</p>")
```

Or extend the copyright:

```python
"</b><p>Copyright (c) Sergey Satskiy 2010-2019. Modified 2025.</p>"
```

### 2. Links to codimension.org

**Files:** `about.py`, `welcomewidget.py`, `mainwindow.py`, `helpwidget.py`, `versions.py`

**Current state:** Links to http://codimension.org (the site may be unavailable or outdated)

**Recommendation:** Leave as is — these are historical links to the original project. Optionally add a link to this fork in About and Welcome.

### 3. setup.py / pyproject.toml

**Current state:** `url='https://github.com/SergeySatskiy/codimension'`

**Recommendation:** Change to the fork URL or add `project_urls` with a link to the fork. Author remains Sergey Satskiy (attribution).

### 4. File Headers

**Current state:** Most files have `# Copyright (C) 2010-20XX Sergey Satskiy`

**Recommendation:** Leave unchanged. GPL does not require changing copyright in every file — a prominent notice in About and README is sufficient.

### 5. NOTICE or COPYRIGHT File

**Recommendation:** Create a `NOTICE` file or extend README with a section:

```
This is a modified version of Codimension (https://github.com/SergeySatskiy/codimension).
Original Copyright (c) Sergey Satskiy. Modified 2025.
Licensed under GPL v3. See LICENSE.
```

## Summary

| Change | Priority | Complexity |
|--------|----------|------------|
| About dialog — add "Modified" | High | Low |
| setup.py url → fork | Medium | Low |
| NOTICE / README section | Medium | Low |
| codimension.org links | Low | — |

Update this document after applying the changes.
