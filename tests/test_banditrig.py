import time
from types import SimpleNamespace

import pytest

from lampyr.rigs.abstract import AbstractHardwareRig
from lampyr.rigs.banditrig import BanditRig


class FakeConfig:
    def __init__(self, rigconfig):
        self.rigconfig = rigconfig


def test_bandit_rig_configured_requires_handedness():
    assert BanditRig.is_configured(FakeConfig({})) is False
    assert BanditRig.is_configured(FakeConfig({"handedness": 1})) is True
    assert BanditRig.is_configured(FakeConfig({"handedness": -1})) is True
    assert BanditRig.is_configured(FakeConfig({"handedness": 0})) is False


def test_bandit_rig_calibration_requires_fresh_entry():
    assert BanditRig.is_calibrated(FakeConfig({})) is False

    stale = FakeConfig({"sipper_calib": {"size": 10000, "calibrated_at": 0}})
    assert BanditRig.is_calibrated(stale) is False

    fresh = FakeConfig({"sipper_calib": {"size": 10000, "calibrated_at": time.time()}})
    assert BanditRig.is_calibrated(fresh) is True


@pytest.mark.parametrize("rigconfig, expected_size", [
    ({"sipper_calib": {"size": 12345}}, 12345),
    ({"sipper_calib": {}}, 10000),
    ({}, 10000),
])
def test_start_applies_calibration_after_starting_interfaces(
    monkeypatch, rigconfig, expected_size
):
    calls = []
    monkeypatch.setattr(
        AbstractHardwareRig, "start", lambda self: calls.append("started")
    )
    # Bypass setup so this lifecycle test never connects to hardware.
    rig = object.__new__(BanditRig)
    rig.config = FakeConfig(rigconfig)
    rig.reward = SimpleNamespace(setsize=lambda size: calls.append(size))

    rig.start()

    assert calls == ["started", expected_size]
