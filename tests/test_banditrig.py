import time

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
