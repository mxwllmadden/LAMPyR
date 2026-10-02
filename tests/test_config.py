import json

import pytest

import lampyr.config as config_module
from lampyr.config import ConfigFile


def _temporary_files(path):
    return list(path.glob(".*.tmp"))


def test_atomic_save_replaces_complete_document(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigFile({"section": {"value": "original"}}, str(path))

    config.save()
    config.set("section.value", "updated")

    with path.open(encoding="utf-8") as file:
        assert json.load(file) == {"section": {"value": "updated"}}
    assert _temporary_files(tmp_path) == []


def test_partial_write_failure_preserves_file_and_rolls_back_memory(
    tmp_path, monkeypatch
):
    path = tmp_path / "config.json"
    config = ConfigFile({"section": {"value": "original"}}, str(path))
    config.save()
    original_bytes = path.read_bytes()

    def partial_dump(_data, file, indent=None):
        file.write('{"truncated":')
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(config_module.json, "dump", partial_dump)

    with pytest.raises(RuntimeError, match="simulated write failure"):
        config.set("section.value", "not-saved")

    assert config.get("section.value") == "original"
    assert path.read_bytes() == original_bytes
    assert _temporary_files(tmp_path) == []


def test_replace_failure_preserves_file_and_rolls_back_memory(
    tmp_path, monkeypatch
):
    path = tmp_path / "config.json"
    config = ConfigFile({"section": {"value": "original"}}, str(path))
    config.save()
    original_bytes = path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(config_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        config.set("section.value", "not-saved")

    assert config.get("section.value") == "original"
    assert path.read_bytes() == original_bytes
    assert _temporary_files(tmp_path) == []


def test_failed_save_removes_new_in_memory_key(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config = ConfigFile({"section": {}}, str(path))
    config.save()

    def fail_dump(_data, _file, indent=None):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(config_module.json, "dump", fail_dump)

    with pytest.raises(RuntimeError):
        config.set("section.new_key", "not-saved")

    with pytest.raises(KeyError):
        config.get("section.new_key")


def test_sync_false_keeps_changes_in_memory_only(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"section": {"value": "on-disk"}}), encoding="utf-8")
    config = ConfigFile({"section": {"value": "default"}}, str(path), sync=False)

    # Still reads the on-disk file on load.
    assert config.get("section.value") == "on-disk"

    config.set("section.value", "in-memory")

    # In-memory reflects the change, but the file is untouched.
    assert config.get("section.value") == "in-memory"
    assert json.loads(path.read_text(encoding="utf-8")) == {"section": {"value": "on-disk"}}
    assert _temporary_files(tmp_path) == []


def test_config_sync_false_reads_disk_without_writing(monkeypatch, tmp_path):
    app_dir = tmp_path / "AppData"
    cfg_path = app_dir / "config.json"
    app_dir.mkdir()
    cfg_path.write_text(
        json.dumps({"lampyr": {"mice_directory": "X:/custom"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module.Config, "_APP_DATA_DIR", str(app_dir))
    monkeypatch.setattr(config_module.Config, "_CONFIG_FILE_PATH", str(cfg_path))

    config = config_module.Config(sync=False)

    assert config.get("lampyr.mice_directory") == "X:/custom"
    config.set("lampyr.enable_saveload_failsafe", False)
    assert config.get("lampyr.enable_saveload_failsafe") is False

    assert json.loads(cfg_path.read_text(encoding="utf-8")) == {
        "lampyr": {"mice_directory": "X:/custom"}
    }
