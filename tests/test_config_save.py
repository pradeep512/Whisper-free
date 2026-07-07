"""Regression tests for ConfigManager.save() atomic write.

The atomic write must overwrite an existing config file. On Windows,
Path.rename() raises FileExistsError when the destination exists, so every
save after the first (i.e. every real settings change) failed with
"[WinError 183] Cannot create a file when that file already exists". The fix
uses Path.replace()/os.replace(), which overwrites atomically on POSIX AND
Windows. These tests run on any platform.
"""
import yaml

from app.data.config import ConfigManager


def test_save_overwrites_existing_config_file(tmp_path):
    cfg_path = tmp_path / "config.yaml"

    # First construction creates the file (first _save_config).
    cm = ConfigManager(config_path=str(cfg_path))
    assert cfg_path.exists()

    # Second save, with the file already present, must not raise.
    cm.set("whisper.model", "medium")
    cm.save()

    with open(cfg_path, "r", encoding="utf-8") as f:
        on_disk = yaml.safe_load(f)
    assert on_disk["whisper"]["model"] == "medium"


def test_repeated_saves_persist_latest_value(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cm = ConfigManager(config_path=str(cfg_path))

    for model in ("tiny", "base", "small", "medium"):
        cm.set("whisper.model", model)
        cm.save()

    reloaded = ConfigManager(config_path=str(cfg_path))
    assert reloaded.get("whisper.model") == "medium"


def test_failed_save_does_not_leave_temp_files(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cm = ConfigManager(config_path=str(cfg_path))

    # Force the atomic replace to fail and assert we raise and don't litter
    # .config_*.yaml.tmp files next to the config.
    def boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("pathlib.Path.replace", boom)

    cm.set("whisper.model", "medium")
    try:
        cm.save()
        assert False, "expected save() to raise"
    except RuntimeError:
        pass

    leftovers = list(tmp_path.glob(".config_*.yaml.tmp"))
    assert leftovers == [], f"temp files left behind: {leftovers}"
