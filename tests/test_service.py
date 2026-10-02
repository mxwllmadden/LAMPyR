import pytest

from lampyr.rigs.abstract import AbstractHardwareRig, AbstractService


class RecordingService(AbstractService):
    def setup(self, name, log):
        self.name = name
        self.log = log
        self.log.append(("setup", name))

    def start(self):
        self.log.append(("start", self.name))

    def stop(self):
        self.log.append(("stop", self.name))

    def disconnect(self):
        self.log.append(("disconnect", self.name))


class NoopService(AbstractService):
    def setup(self):
        pass


class ServiceRig(AbstractHardwareRig):
    def setup(self):
        self.log = []
        self.register_service("worker", RecordingService("worker", self.log))

    def is_calibrated(self):
        return True

    def is_configured(self):
        return True

    def calibrate(self):
        pass

    def configure(self):
        pass


def test_service_calls_setup_on_construction():
    log = []
    service = RecordingService("svc", log)
    assert log == [("setup", "svc")]


def test_service_lifecycle_defaults_are_noop():
    service = NoopService()
    service.start()
    service.stop()
    service.disconnect()


def test_register_service_exposes_attribute_and_dict():
    rig = ServiceRig()
    assert list(rig.services) == ["worker"]
    assert rig.services["worker"] is rig.worker
    assert isinstance(rig.worker, RecordingService)


def test_register_service_rejects_reserved_name():
    rig = ServiceRig()

    class OtherService(AbstractService):
        def setup(self):
            pass

    with pytest.raises(ValueError):
        rig.register_service("start", OtherService())
    with pytest.raises(ValueError):
        rig.register_service("interfaces", OtherService())
    with pytest.raises(ValueError):
        rig.register_service("worker", OtherService())


def test_rig_lifecycle_drives_services(monkeypatch):
    monkeypatch.setattr("lampyr.rigs.abstract.time.sleep", lambda seconds: None)
    rig = ServiceRig()
    rig.start()
    rig.stop()
    rig.disconnect()

    assert rig.log == [
        ("setup", "worker"),
        ("start", "worker"),
        ("stop", "worker"),
        ("disconnect", "worker"),
    ]


def test_rig_without_services_still_runs_lifecycle(monkeypatch):
    monkeypatch.setattr("lampyr.rigs.abstract.time.sleep", lambda seconds: None)

    class EmptyRig(AbstractHardwareRig):
        def setup(self):
            pass

        def is_calibrated(self):
            return True

        def is_configured(self):
            return True

        def calibrate(self):
            pass

        def configure(self):
            pass

    rig = EmptyRig()
    assert rig.services == {}
    rig.start()
    rig.stop()
    rig.disconnect()
