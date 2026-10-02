import csv
import json

import pytest

import lampyr.config as config_module
from lampyr.config import Config
from lampyr.rigs.automationrig import SessionJobTracker
from lampyr.rigs.services import AutomationCoordinationService


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


def _write_run(mice_dir, session_id, jobid, version):
    marker = mice_dir / "AUTOMATION" / ".runs" / session_id / f"{jobid}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": version}), encoding="utf-8")


def _make_tracker(config, mice_dir):
    config.set("lampyr.mice_directory", str(mice_dir))
    coordination = AutomationCoordinationService(mice_dir / "AUTOMATION")
    return SessionJobTracker(config, coordination)


def test_candidate_sessions_returns_all_unmarked_sessions(tmp_path, config):
    mice_dir = tmp_path / "mice"
    _write_mouse(mice_dir, "M-1", ["session_1", "session_2"])
    _write_mouse(mice_dir, "AUTOMATION", ["ignored"])

    tracker = _make_tracker(config, mice_dir)

    assert tracker.candidate_sessions([("job-a", 1)]) == [
        ("M-1", "session_1"),
        ("M-1", "session_2"),
    ]
    # Failsafe is disabled internally, so no pending sessions are published.
    assert tracker.colony.data.enable_failsafe is False


def test_candidate_sessions_filters_completed_and_stale_runs(tmp_path, config):
    mice_dir = tmp_path / "mice"
    _write_mouse(
        mice_dir, "M-1", ["session_1", "session_2", "session_3", "session_4"]
    )

    tracker = _make_tracker(config, mice_dir)
    jobs = [("job-a", 2), ("job-b", 1)]

    # session_1: complete at current versions -> excluded
    _write_run(mice_dir, "session_1", "job-a", 2)
    _write_run(mice_dir, "session_1", "job-b", 1)
    # session_2: job-a version incremented (1 < 2) -> stale -> candidate
    _write_run(mice_dir, "session_2", "job-a", 1)
    _write_run(mice_dir, "session_2", "job-b", 1)
    # session_3: missing job-b -> candidate
    _write_run(mice_dir, "session_3", "job-a", 2)

    assert tracker.candidate_sessions(jobs) == [
        ("M-1", "session_2"),
        ("M-1", "session_3"),
        ("M-1", "session_4"),
    ]


def test_mark_completed_writes_marker_under_gate(tmp_path, config):
    mice_dir = tmp_path / "mice"
    tracker = _make_tracker(config, mice_dir)

    tracker.mark_completed("job-a", 2, "session_1")

    marker = mice_dir / "AUTOMATION" / ".runs" / "session_1" / "job-a.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {"version": 2}
    assert not tracker.coordination.gate_path.exists()
    assert not list(marker.parent.glob("*.tmp"))


def test_mark_completed_uses_gate_to_guard_writes(tmp_path, config):
    mice_dir = tmp_path / "mice"
    tracker = _make_tracker(config, mice_dir)
    tracker.coordination.gate_path.touch()

    with pytest.raises(FileExistsError):
        tracker.mark_completed("job-a", 2, "session_1")

    marker = mice_dir / "AUTOMATION" / ".runs" / "session_1" / "job-a.json"
    assert not marker.exists()
    assert tracker.coordination.gate_path.exists()


def test_mark_completed_then_candidate_excludes_session(tmp_path, config):
    mice_dir = tmp_path / "mice"
    _write_mouse(mice_dir, "M-1", ["session_1"])

    tracker = _make_tracker(config, mice_dir)

    assert tracker.candidate_sessions([("job-a", 1)]) == [("M-1", "session_1")]

    tracker.mark_completed("job-a", 1, "session_1")

    assert tracker.candidate_sessions([("job-a", 1)]) == []


def test_sessionjobtracker_never_writes_config(tmp_path, config):
    mice_dir = tmp_path / "mice"
    _make_tracker(config, mice_dir)

    assert not (tmp_path / "AppData" / "config.json").exists()
