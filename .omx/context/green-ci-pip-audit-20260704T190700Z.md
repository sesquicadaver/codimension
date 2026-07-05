# Context: green-ci-pip-audit

## Task
Зробити CI smoke job зеленим: pip-audit + залишкові швидкі фікси.

## Facts
- `pip-audit` (full venv) падає через mistune CVE + starlette (транзитивна залежність pip-audit)
- `pip-audit -r requirements.txt --ignore-vuln ...` для mistune → exit 0
- mistune пін `<2.0` через API (md.py використовує mistune.Renderer)

## Plan
1. ci.yml: audit лише requirements.txt + documented ignores для mistune
2. depsitems.py: увімкнути scene.addItem(connector)
3. Оновити living-specification + requirements comment
