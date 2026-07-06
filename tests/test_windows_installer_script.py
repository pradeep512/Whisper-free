"""Automated coverage for #21: Windows Inno Setup per-user installer.

There's no Inno Setup compiler (ISCC.exe) in this environment, so the
installer .exe itself can't be built or smoke-tested here -- that needs a
human on real Windows hardware per the issue's acceptance criteria. What is
testable without ISCC is that packaging/windows/installer.iss is present and
declares the per-user, no-admin install this issue requires, and that its
autostart registry value matches what
app.platform.windows.autolaunch.set_open_at_login() itself writes/reads (so
the installer's "Open at login" checkbox and the in-app Settings toggle never
disagree about which registry value controls autostart).
"""

from pathlib import Path

from app.platform.windows.autolaunch import _RUN_KEY_PATH, _RUN_VALUE_NAME

ISS_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "windows" / "installer.iss"
)


def _read_iss() -> str:
    return ISS_PATH.read_text(encoding="utf-8")


def test_installer_script_exists():
    assert ISS_PATH.is_file()


def test_installer_is_per_user_no_admin():
    text = _read_iss()
    assert "PrivilegesRequired=lowest" in text
    assert "{localappdata}\\Programs\\" in text


def test_installer_has_start_menu_shortcut_and_uninstaller():
    text = _read_iss()
    assert "[Icons]" in text
    assert "{uninstallexe}" in text
    assert "Uninstall {#MyAppName}" in text


def test_installer_registry_value_matches_autolaunch_module():
    text = _read_iss()
    # The .iss Subkey/ValueName strings should match the exact registry
    # location app.platform.windows.autolaunch reads/writes at runtime.
    assert _RUN_KEY_PATH in text
    assert f'ValueName: "{_RUN_VALUE_NAME}"' in text
    assert "Tasks: openatlogin" in text
