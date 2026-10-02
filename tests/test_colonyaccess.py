import csv
import json

import pytest

import lampyr.config as config_module
from lampyr.config import Config
from lampyr.rigs.automationrig import ColonyAccess


@pytest.fixture
def config(monkeypatch, tmp_path):
    app_dir = tmp_path / "AppData"
    monkeypatch.setattr(config_module.Config, "_APP_DATA_DIR", str(app_dir))
    monkeypatch.setattr(
        config_module.Config, "_CONFIG_FILE_PATH", str(app_dir / "config.json")
    )
    return Config(sync=False)


def _write_mouse(mice_dir, mouse_id, session_ids):
    mouse_dir = mice_dir / mouse_id
    mouse_dir.mkdir(parents=True, exist_ok=True)
    (mouse_dir / f"{mouse_id}_mouse.lampyr.json").write_text(
        json.dumps({"mouseid": mouse_id}), encoding="utf-8"
    )
    with (mouse_dir / f"{mouse_id}_history.lampyr.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["sessionid"])
        for sid in session_ids:
            writer.writerow([sid])


def test_colonyaccess_finds_candidate_sessions(tmp_path, config):
    mice_dir = tmp_path / "mice"
    _write_mouse(mice_dir, "M-1", ["session_1", "session_2"])
    _write_mouse(mice_dir, "AUTOMATION", ["ignored"])

    config.set("lampyr.mice_directory", str(mice_dir))

    access = ColonyAccess(config)

    assert access.candidate_sessions() == [
        ("M-1", "session_1"),
        ("M-1", "session_2"),
    ]
    # Failsafe is disabled internally, so no pending sessions are published.
    assert access.colony.data.enable_failsafe is False


def test_colonyaccess_never_writes_config(tmp_path, config):
    ColonyAccess(config)

    assert not (tmp_path / "AppData" / "config.json").exists()
