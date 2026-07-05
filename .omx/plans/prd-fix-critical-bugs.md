# PRD: fix-critical-bugs (autopilot cycle 2)

## Acceptance
1. `flow_ast`: `from X import Y` parses without crash; unit test
2. `binfiles.getHexdump`: subprocess hexdump -C; unit test with mock
3. `editorsmanager.onHighlightInFS`: same condition as `onHighlightInPrj`
4. `mainwindow`: `tabsStatus` not `tabxsStatus`
5. ruff + mypy + pytest pass
