import pytest

from lampyr.managers.hardware import RigManager
from lampyr.rigs.abstract import NullRig
from lampyr.rigs.automationrig import AutomationRig


class ManagerConfig:
    def __init__(self, rig_type, mice_directory):
        self.values = {
            "rig.rig_type": rig_type,
            "lampyr.mice_directory": str(mice_directory),
        }
        self.rigconfig = {}

    def get(self, key):
        return self.values[key]


@pytest.mark.parametrize(
    ("rig_type", "rig_class"),
    [("NullRig", NullRig), ("AutomationRig", AutomationRig)],
)
def test_rig_manager_connects_calibrates_and_disconnects_hardware_free_rigs(
    tmp_path, rig_type, rig_class
):
    config = ManagerConfig(rig_type, tmp_path)
    manager = RigManager(config=config)
    manager._input_func = lambda _prompt="": ""
    manager._output_func = lambda _message: None

    assert manager.rig_cls is rig_class
    assert rig_class.is_configured(config)
    assert rig_class.is_calibrated(config)

    manager.connect()
    assert manager.connected is True
    assert isinstance(manager.rig, rig_class)

    manager.disconnect()
    assert manager.connected is False

    # The manager owns connect/disconnect around calibration when initially idle.
    manager.calibrate()
    assert manager.connected is False
    assert isinstance(manager.rig, rig_class)
