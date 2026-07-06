"""Automated coverage for the #18 follow-up: the Settings "Open at Login"
checkbox must reflect the real HKCU Run key state on load, not the
persisted config value, so it can't drift out of sync if the registry
value is removed outside the app (e.g. by antivirus or a manual edit).
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.mark.skipif(
    sys.platform != "win32", reason="constructs the Windows settings group"
)
def test_open_at_login_checkbox_reflects_registry_not_stale_config(
    qapp, tmp_path, monkeypatch
):
    from app.data.config import ConfigManager
    from app.ui.settings_panel import SettingsPanel

    config_path = tmp_path / "config.yaml"
    config = ConfigManager(config_path=str(config_path))
    # Persisted config says disabled, but the registry (simulated) says enabled.
    config.set("windows.open_at_login", False)

    monkeypatch.setattr(
        "app.platform.windows.autolaunch.is_open_at_login_enabled", lambda: True
    )

    panel = SettingsPanel(config)

    assert panel.widgets["windows.open_at_login"].isChecked() is True


@pytest.mark.skipif(
    sys.platform != "win32", reason="constructs the Windows settings group"
)
def test_open_at_login_checkbox_falls_back_to_config_on_registry_error(
    qapp, tmp_path, monkeypatch
):
    from app.data.config import ConfigManager
    from app.ui.settings_panel import SettingsPanel

    config_path = tmp_path / "config.yaml"
    config = ConfigManager(config_path=str(config_path))
    config.set("windows.open_at_login", True)

    def _raise():
        raise OSError("registry unavailable")

    monkeypatch.setattr(
        "app.platform.windows.autolaunch.is_open_at_login_enabled", _raise
    )

    panel = SettingsPanel(config)

    assert panel.widgets["windows.open_at_login"].isChecked() is True
