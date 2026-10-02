import lampyr.actions as actions
from lampyr.rigs.abstract import NullRig, all_rig_definitions


class FakeConfig:
    def __init__(self):
        self.values = {}
        self.rigconfig = {}
        self.saved = False

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.saved = True


class FakeRigManager:
    def __init__(self, rig_cls):
        self.rig_cls = rig_cls


class FakeLampyr:
    def __init__(self):
        self.config = FakeConfig()
        self.rigmanager = FakeRigManager(NullRig)


class HandednessRig(NullRig):
    CONFIGURATION = {
        "handedness": {
            "prompt": "handedness",
            "type": int,
            "choices": [1, -1],
            "default": 1,
        },
    }


def test_select_rig_lists_selects_and_runs_setup(monkeypatch):
    lampyr = FakeLampyr()
    rig_names = sorted(all_rig_definitions().keys())

    monkeypatch.setattr(actions.click, "echo", lambda *a, **k: None)
    monkeypatch.setattr(actions.click, "prompt", lambda *a, **k: 1)
    monkeypatch.setattr(actions.socket, "gethostname", lambda: "test-host")

    actions.select_rig(lampyr)

    assert lampyr.config.values["rig.rig_type"] == rig_names[0]
    assert lampyr.config.values["rig.name"] == "test-host"


def test_configure_rig_defaults_name_to_hostname(monkeypatch):
    lampyr = FakeLampyr()
    monkeypatch.setattr(actions.socket, "gethostname", lambda: "test-host")

    actions.configure_rig(lampyr)

    assert lampyr.config.values["rig.name"] == "test-host"
    assert lampyr.config.saved is True


def test_configure_rig_keeps_existing_name(monkeypatch):
    lampyr = FakeLampyr()
    lampyr.config.values["rig.name"] = "Existing"
    monkeypatch.setattr(actions.socket, "gethostname", lambda: "test-host")

    actions.configure_rig(lampyr)

    assert lampyr.config.values["rig.name"] == "Existing"


def test_configure_rig_prompts_declared_fields(monkeypatch):
    lampyr = FakeLampyr()
    lampyr.rigmanager.rig_cls = HandednessRig
    monkeypatch.setattr(actions.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(actions.click, "prompt", lambda *a, **k: "1")

    actions.configure_rig(lampyr)

    assert lampyr.config.rigconfig["handedness"] == 1
    assert lampyr.config.values["rig.name"] == "test-host"


def test_rename_rig_prompts_and_sets_name(monkeypatch):
    lampyr = FakeLampyr()
    monkeypatch.setattr(actions.click, "prompt", lambda *a, **k: "MyRig")
    monkeypatch.setattr(actions.socket, "gethostname", lambda: "test-host")

    actions.rename_rig(lampyr)

    assert lampyr.config.values["rig.name"] == "MyRig"
