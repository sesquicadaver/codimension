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

from core.ai_config import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    KNOWN_PROVIDERS,
    PROVIDER_LABELS,
    PROVIDER_OFFLINE,
    PROVIDER_OLLAMA,
    AiConfig,
    clear_ai_api_key,
    has_ai_api_key,
    load_ai_config,
    save_ai_config,
    store_ai_api_key,
)
from core.ai_ui import (
    AI_UI_ENV,
    ai_ui_env_override_active,
    describe_ai_ui_settings,
    set_ai_ui_enabled,
)

from .qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class AiSettingsDialog(QDialog):
    """Enable AI UI, choose provider, and store an API key (never echoed back)."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("AI settings")
        self.setModal(True)
        self.__initial_provider = PROVIDER_OFFLINE

        layout = QVBoxLayout(self)
        self.__enableCb = QCheckBox("Enable AI (experimental)", self)
        layout.addWidget(self.__enableCb)

        self.__statusLabel = QLabel(self)
        self.__statusLabel.setWordWrap(True)
        layout.addWidget(self.__statusLabel)

        form = QFormLayout()
        self.__providerCombo = QComboBox(self)
        for provider in KNOWN_PROVIDERS:
            self.__providerCombo.addItem(PROVIDER_LABELS[provider], provider)
        self.__providerCombo.currentIndexChanged.connect(self.__onProviderChanged)
        form.addRow("Provider:", self.__providerCombo)

        self.__modelEdit = QLineEdit(self)
        self.__modelEdit.setPlaceholderText("Model id (provider default if empty)")
        form.addRow("Model:", self.__modelEdit)

        self.__baseUrlEdit = QLineEdit(self)
        self.__baseUrlEdit.setPlaceholderText("API base URL")
        form.addRow("Base URL:", self.__baseUrlEdit)

        key_row = QHBoxLayout()
        self.__apiKeyEdit = QLineEdit(self)
        self.__apiKeyEdit.setEchoMode(QLineEdit.Password)
        self.__apiKeyEdit.setPlaceholderText("Leave blank to keep the stored key")
        key_row.addWidget(self.__apiKeyEdit)
        self.__clearKeyCb = QCheckBox("Clear stored key", self)
        key_row.addWidget(self.__clearKeyCb)
        form.addRow("API key:", key_row)

        self.__keyStatusLabel = QLabel(self)
        self.__keyStatusLabel.setWordWrap(True)
        form.addRow("", self.__keyStatusLabel)
        layout.addLayout(form)

        info = QLabel(
            "Actions: editor context menu → AI → Explain / Suggest.\n"
            "Default provider is Offline (local CFG/symbol summary; no network).\n"
            "API keys are stored in the OS keyring when available, otherwise in "
            "~/.codimension3/ai_api_key (mode 0600). Keys are never written into the project.\n"
            f"Environment override: {AI_UI_ENV}=1|0 (wins over the Enable checkbox).",
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
        """Refresh controls from feature flags and AI config."""
        snap = describe_ai_ui_settings()
        env_locked = bool(snap["env_override_active"])
        self.__enableCb.setChecked(bool(snap["enabled"]))
        self.__enableCb.setEnabled(not env_locked)

        cfg = load_ai_config()
        self.__initial_provider = cfg.provider
        index = self.__providerCombo.findData(cfg.provider)
        if index < 0:
            index = self.__providerCombo.findData(PROVIDER_OFFLINE)
        self.__providerCombo.blockSignals(True)
        self.__providerCombo.setCurrentIndex(max(0, index))
        self.__providerCombo.blockSignals(False)
        self.__modelEdit.setText(cfg.model)
        self.__baseUrlEdit.setText(cfg.base_url)
        self.__apiKeyEdit.clear()
        self.__clearKeyCb.setChecked(False)
        self.__refreshProviderDependent()

        if env_locked:
            self.__statusLabel.setText(
                f"Flag is overridden by {snap['env_key']} "
                f"(store path: {snap['flags_path']}).\n"
                f"Backend: {snap['backend_label']}"
            )
        else:
            self.__statusLabel.setText(
                f"Persistent flag file: {snap['flags_path']}\nBackend: {snap['backend_label']}"
            )

    def __current_provider(self) -> str:
        data = self.__providerCombo.currentData()
        return str(data) if data else PROVIDER_OFFLINE

    def __onProviderChanged(self, _index: int = 0) -> None:
        """Fill defaults when the user switches provider."""
        provider = self.__current_provider()
        if not self.__modelEdit.text().strip():
            self.__modelEdit.setText(DEFAULT_MODELS.get(provider, ""))
        if not self.__baseUrlEdit.text().strip() or self.__initial_provider != provider:
            # When switching provider, refresh base URL to that provider's default
            # unless the user already typed a custom URL for the same provider.
            current_url = self.__baseUrlEdit.text().strip()
            previous_default = DEFAULT_BASE_URLS.get(self.__initial_provider, "")
            if not current_url or current_url == previous_default:
                self.__baseUrlEdit.setText(DEFAULT_BASE_URLS.get(provider, ""))
        self.__initial_provider = provider
        self.__refreshProviderDependent()

    def __refreshProviderDependent(self) -> None:
        """Enable/disable key fields and show key status for the provider."""
        provider = self.__current_provider()
        offline = provider == PROVIDER_OFFLINE
        ollama = provider == PROVIDER_OLLAMA
        self.__modelEdit.setEnabled(not offline)
        self.__baseUrlEdit.setEnabled(not offline)
        self.__apiKeyEdit.setEnabled(not offline)
        self.__clearKeyCb.setEnabled(not offline)
        if offline:
            self.__keyStatusLabel.setText("Offline provider: no API key used.")
            return
        if has_ai_api_key(provider):
            note = "A key is stored (not shown). Leave the field blank to keep it."
        else:
            note = "No key stored yet."
            if ollama:
                note += " Ollama usually works without a key."
            else:
                note += " Enter a key below to enable remote calls."
        self.__keyStatusLabel.setText(note)

    def accept(self) -> None:
        """Persist enable flag, provider settings, and optional API key changes."""
        if not ai_ui_env_override_active():
            set_ai_ui_enabled(self.__enableCb.isChecked())

        provider = self.__current_provider()
        model = self.__modelEdit.text().strip()
        base_url = self.__baseUrlEdit.text().strip()
        if provider != PROVIDER_OFFLINE:
            if not model:
                model = DEFAULT_MODELS.get(provider, "")
            if not base_url:
                base_url = DEFAULT_BASE_URLS.get(provider, "")
        else:
            model = ""
            base_url = ""
        save_ai_config(AiConfig(provider=provider, model=model, base_url=base_url))

        if provider != PROVIDER_OFFLINE:
            if self.__clearKeyCb.isChecked():
                clear_ai_api_key(provider)
            else:
                typed = self.__apiKeyEdit.text().strip()
                if typed:
                    store_ai_api_key(provider, typed)

        QDialog.accept(self)
