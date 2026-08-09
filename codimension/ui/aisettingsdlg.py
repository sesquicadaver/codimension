# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""AI integration settings dialog (Options → AI → AI settings…)."""

from __future__ import annotations

from core.ai_ui import (
    AI_UI_ENV,
    ai_ui_env_override_active,
    describe_ai_ui_settings,
    set_ai_ui_enabled,
)

from .qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class AiSettingsDialog(QDialog):
    """Enable the experimental AI UI and show offline-backend notes."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("AI settings")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.__enableCb = QCheckBox("Enable AI (experimental)", self)
        layout.addWidget(self.__enableCb)

        self.__statusLabel = QLabel(self)
        self.__statusLabel.setWordWrap(True)
        layout.addWidget(self.__statusLabel)

        info = QLabel(
            "Actions: editor context menu → AI → Explain / Suggest.\n"
            "Backend: local offline summary from SymbolIndex + CFG "
            "(no network, no API key).\n"
            f"Environment override: {AI_UI_ENV}=1|0 (wins over this checkbox).",
            self,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.__reload()

    def __reload(self) -> None:
        """Refresh controls from the feature-flag store / env."""
        snap = describe_ai_ui_settings()
        env_locked = bool(snap["env_override_active"])
        self.__enableCb.setChecked(bool(snap["enabled"]))
        self.__enableCb.setEnabled(not env_locked)
        if env_locked:
            self.__statusLabel.setText(
                f"Flag is overridden by {snap['env_key']} "
                f"(store path: {snap['flags_path']}).\n"
                f"Backend: {snap['backend_label']}"
            )
        else:
            self.__statusLabel.setText(f"Persistent flag file: {snap['flags_path']}\nBackend: {snap['backend_label']}")

    def accept(self) -> None:
        """Persist the Enable checkbox unless an env override is active."""
        if not ai_ui_env_override_active():
            set_ai_ui_enabled(self.__enableCb.isChecked())
        QDialog.accept(self)
