from types import SimpleNamespace
import time

import pytest

from lampyr.interfaces.textual_tui import app as tui


class ConcreteTask(tui.Task):
    def setup(self):
        pass

    def loop(self):
        pass


class FakeConfig:
    def __init__(self, values):
        self.values = dict(values)
        self.set_calls = []

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        self.set_calls.append((key, value))
        self.values[key] = value


class FakeDataManager:
    def __init__(self):
        self.touches = 0

    def heartbeat_filetouch(self):
        self.touches += 1


class FakeHeartbeatApp:
    def __init__(self, config_values, behaviors=None, screens=None):
        self.lampyr = SimpleNamespace(
            config=FakeConfig(config_values),
            behaviors=behaviors or {},
            datamanager=FakeDataManager(),
        )
        self.screen_stack = screens or [tui.MainScreen()]
        self.screen = self.screen_stack[-1]
        self.started = 0
        self.notifications = []

    def push_screen(self, screen):
        self.screen_stack.append(screen)
        self.screen = screen

    def start_scheduled_run(self):
        assert self.lampyr.config.get(
            "lampyr.automated_task.last_run_window"
        ) == "2026-09-24"
        self.started += 1
        return True

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))


def _schedule_config(**overrides):
    values = {
        "rig.calibrated": time.time(),
        "lampyr.enable_automated_tasks": True,
        "lampyr.automated_task.task": "ConcreteTask",
        "lampyr.automated_task.start_time": "09:00",
        "lampyr.automated_task.end_time": "10:00",
        "lampyr.automated_task.last_run_window": None,
    }
    values.update(overrides)
    return values


def _local_time(year, month, day, hour, minute):
    return time.struct_time((year, month, day, hour, minute, 0, 0, 0, -1))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00:00", 0),
        ("09:07", 547),
        ("23:59", 1439),
        ("9:07", None),
        ("24:00", None),
        ("12:60", None),
        ("12.30", None),
        (None, None),
    ],
)
def test_strict_local_time_parsing(value, expected):
    assert tui._parse_local_time(value) == expected


def test_same_day_window_is_inclusive():
    assert tui._active_scheduled_window(
        "09:00", "10:00", _local_time(2026, 9, 24, 9, 0)
    ) == "2026-09-24"
    assert tui._active_scheduled_window(
        "09:00", "10:00", _local_time(2026, 9, 24, 10, 0)
    ) == "2026-09-24"
    assert tui._active_scheduled_window(
        "09:00", "10:00", _local_time(2026, 9, 24, 10, 1)
    ) is None


def test_overnight_window_uses_its_start_date_across_year_boundary():
    assert tui._active_scheduled_window(
        "22:00", "02:00", _local_time(2026, 12, 31, 23, 30)
    ) == "2026-12-31"
    assert tui._active_scheduled_window(
        "22:00", "02:00", _local_time(2027, 1, 1, 1, 30)
    ) == "2026-12-31"
    assert tui._active_scheduled_window(
        "22:00", "02:00", _local_time(2027, 1, 1, 3, 0)
    ) is None


def test_schedule_save_is_one_complete_config_write():
    config = FakeConfig({})
    switched = []
    notifications = []
    fake_app = SimpleNamespace(
        lampyr=SimpleNamespace(config=config),
        screen_stack=[],
        switch_screen=switched.append,
        notify=lambda *args, **kwargs: notifications.append((args, kwargs)),
    )
    screen = SimpleNamespace(
        app=fake_app,
        _task_class_name="ConcreteTask",
        _start_time="09:00",
        _end_time="10:00",
    )

    tui.ScheduleTimeScreen.on_save(screen)

    assert config.set_calls == [
        (
            "lampyr.automated_task",
            {
                "task": "ConcreteTask",
                "start_time": "09:00",
                "end_time": "10:00",
                "last_run_window": None,
            },
        )
    ]
    assert isinstance(switched[0], tui.MainScreen)
    assert notifications


def test_heartbeat_marks_window_before_launch_and_only_launches_once(monkeypatch):
    monkeypatch.setattr(
        tui, "_active_scheduled_window", lambda *_args, **_kwargs: "2026-09-24"
    )
    app = FakeHeartbeatApp(
        _schedule_config(), behaviors={"ConcreteTask": ConcreteTask}
    )

    tui.LampyrApp._heartbeat(app)
    tui.LampyrApp._heartbeat(app)

    assert app.started == 1
    assert app.lampyr.config.set_calls == [
        ("lampyr.automated_task.last_run_window", "2026-09-24")
    ]
    assert app.lampyr.datamanager.touches == 2


@pytest.mark.parametrize(
    ("config_override", "behaviors"),
    [
        ({"lampyr.enable_automated_tasks": False}, {"ConcreteTask": ConcreteTask}),
        ({"lampyr.automated_task.task": "MissingTask"}, {}),
        ({"lampyr.automated_task.start_time": "invalid"}, {"ConcreteTask": ConcreteTask}),
    ],
)
def test_heartbeat_ignores_disabled_or_invalid_schedules(
    monkeypatch, config_override, behaviors
):
    if config_override.get("lampyr.automated_task.start_time") == "invalid":
        active_window = None
    else:
        active_window = "2026-09-24"
    monkeypatch.setattr(
        tui, "_active_scheduled_window", lambda *_args, **_kwargs: active_window
    )
    app = FakeHeartbeatApp(_schedule_config(**config_override), behaviors=behaviors)

    tui.LampyrApp._heartbeat(app)

    assert app.started == 0
    assert app.lampyr.config.set_calls == []


def test_calibration_has_priority_over_scheduled_launch(monkeypatch):
    monkeypatch.setattr(
        tui, "_active_scheduled_window", lambda *_args, **_kwargs: "2026-09-24"
    )
    app = FakeHeartbeatApp(
        _schedule_config(**{"rig.calibrated": 0}),
        behaviors={"ConcreteTask": ConcreteTask},
    )

    tui.LampyrApp._heartbeat(app)

    assert isinstance(app.screen, tui.CalibrationConfirmScreen)
    assert app.started == 0
    assert app.lampyr.datamanager.touches == 1


def test_active_run_suppresses_touch_and_scheduled_launch(monkeypatch):
    monkeypatch.setattr(
        tui, "_active_scheduled_window", lambda *_args, **_kwargs: "2026-09-24"
    )
    screens = [tui.MainScreen(), tui.RunScreen("mouse", "ConcreteTask")]
    app = FakeHeartbeatApp(
        _schedule_config(),
        behaviors={"ConcreteTask": ConcreteTask},
        screens=screens,
    )

    tui.LampyrApp._heartbeat(app)

    assert app.started == 0
    assert app.lampyr.datamanager.touches == 0


def test_scheduled_run_creates_and_explicitly_loads_automouse():
    calls = []
    mousemanager = SimpleNamespace(
        exists=lambda mouseid: False,
        create=lambda mouseid: calls.append(("create", mouseid)),
        load=lambda mouseid: calls.append(("load", mouseid)),
    )
    screen = SimpleNamespace(
        AUTOMOUSE="AUTOMOUSE",
        app=SimpleNamespace(lampyr=SimpleNamespace(mousemanager=mousemanager)),
    )

    tui.ScheduledRunScreen._load_mouse(screen)

    assert calls == [("create", "AUTOMOUSE"), ("load", "AUTOMOUSE")]


def test_return_to_main_runs_heartbeat(monkeypatch):
    calls = []
    main_screen = tui.MainScreen()
    monkeypatch.setattr(
        tui.MainScreen,
        "pop_until_active",
        lambda self: calls.append("returned"),
    )
    app = SimpleNamespace(
        screen_stack=[main_screen],
        _heartbeat=lambda: calls.append("heartbeat"),
    )

    tui.LampyrApp._return_to_main(app)

    assert calls == ["returned", "heartbeat"]


def test_manual_and_scheduled_run_exits_use_return_to_main():
    manual_calls = []
    manual_screen = SimpleNamespace(
        _thread=None,
        _animal_timer=None,
        app=SimpleNamespace(_return_to_main=lambda: manual_calls.append("return")),
    )
    event = SimpleNamespace(button=SimpleNamespace())

    tui.RunScreen.on_action_btn(manual_screen, event)

    scheduled_calls = []
    scheduled_screen = SimpleNamespace(
        app=SimpleNamespace(
            lampyr=SimpleNamespace(close=lambda: scheduled_calls.append("close")),
            _return_to_main=lambda: scheduled_calls.append("return"),
        )
    )
    tui.ScheduledRunScreen.on_done(
        scheduled_screen, tui.RunScreen.RunDone(error=False)
    )

    assert manual_calls == ["return"]
    assert scheduled_calls == ["close", "return"]
