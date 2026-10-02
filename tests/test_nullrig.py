from lampyr.config import Config
from lampyr.rigs.abstract import NullRig, all_rig_definitions


def test_null_rig_is_discoverable():
    assert "NullRig" in all_rig_definitions()


def test_null_rig_has_no_components_or_interfaces():
    rig = NullRig()
    assert rig.components == {}
    assert rig.interfaces == {}
    assert rig.services == {}


def test_null_rig_is_trivially_calibrated_and_configured():
    rig = NullRig()
    assert rig.is_calibrated() is True
    assert rig.is_configured() is True
    assert rig.calibrate() is True
    assert rig.configure() is True


def test_null_rig_lifecycle_is_noop():
    rig = NullRig()
    rig.start()
    rig.stop()
    rig.disconnect()


def test_null_rig_is_the_default_rig_type():
    assert Config.DEFAULT_CONFIG["rig"]["rig_type"] == "NullRig"
