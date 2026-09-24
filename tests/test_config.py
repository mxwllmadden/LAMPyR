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
