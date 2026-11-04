from lampyr.config import Config
from lampyr.rigs.abstract import NullRig, all_rig_definitions


def test_null_rig_is_discoverable():
    assert "NullRig" in all_rig_definitions()


def test_automation_rig_is_discoverable():
    # RigManager imports supported rig classes to register them with the
    # subclass-based discovery mechanism used by `lampyr rig select`.
    import lampyr.managers.hardware  # noqa: F401

    assert "AutomationRig" in all_rig_definitions()


def test_null_rig_has_no_components_or_interfaces():
    rig = NullRig()
    assert rig.components == {}
    assert rig.interfaces == {}
    assert rig.services == {}


def test_null_rig_is_trivially_calibrated_and_configured():
    rig = NullRig()
    assert NullRig.is_calibrated({}) is True
    assert NullRig.is_configured({}) is True
    assert rig.calibrate(None, None) is True
    assert rig.configure(None, None) is True


def test_null_rig_lifecycle_is_noop():
    rig = NullRig()
    rig.start()
    rig.stop()
    rig.disconnect()


def test_null_rig_is_the_default_rig_type():
    assert Config.DEFAULT_CONFIG["rig"]["rig_type"] == "NullRig"


def test_default_rig_name_is_the_hostname():
    import socket

    assert Config.DEFAULT_CONFIG["rig"]["name"] == socket.gethostname()
