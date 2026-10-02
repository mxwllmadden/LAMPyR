from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier, Event

import pytest

from lampyr.rigs.automationrig import AutomationRig, JobReservation
from lampyr.rigs.services import AutomationCoordinationService


@pytest.fixture(autouse=True)
def cleanup_services(monkeypatch):
    instances = []
    original_setup = AutomationCoordinationService.setup

    def setup(instance, *args, **kwargs):
        original_setup(instance, *args, **kwargs)
        instances.append(instance)

    monkeypatch.setattr(AutomationCoordinationService, "setup", setup)
    yield
    for instance in instances:
        instance.stop()


def short_coordinator(directory):
    return AutomationCoordinationService(directory, lease_seconds=10, renew_interval=2)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("lampyr.rigs.services.time.time", lambda: now[0])
    return now


def test_service_stores_automation_and_lock_paths(tmp_path):
    automation_dir = tmp_path / "AUTOMATION"
    service = AutomationCoordinationService(automation_dir)

    assert service.automation_dir == automation_dir
    assert service.lock_dir == automation_dir / ".locks"
    assert service.gate_path == service.lock_dir / "automation.lock"


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan")])
def test_invalid_lease_duration(tmp_path, duration):
    with pytest.raises(ValueError):
        AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=duration)


def test_lock_creation_fails_if_valid_lease_exists(tmp_path, clock):
    service = short_coordinator(tmp_path / "AUTOMATION")
    lease = service.lock("colony", "analysis-job")
    record = json.loads(lease.path.read_text(encoding="utf-8"))

    assert record == {"token": lease.token, "expires_at": 1010.0}
    assert not service.gate_path.exists()
    with pytest.raises(FileExistsError):
        service.lock("colony", "analysis-job")
    assert not service.gate_path.exists()

    service.release_file(lease)
    assert not lease.path.exists()


@pytest.mark.parametrize("scope", ["colony", "session", "arbitrary"])
def test_distinct_ids_can_coexist_within_scope(tmp_path, scope):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    first = service.lock(scope, "first")
    second = service.lock(scope, "second")

    assert first.path != second.path
    service.release_file(first)
    service.release_file(second)


@pytest.mark.parametrize("first_scope, second_scope", [
    ("colony", "session"),
    ("session", "colony"),
])
def test_colony_and_session_leases_exclude_each_other(tmp_path, first_scope, second_scope):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    lease = service.lock(first_scope, "resource")

    with pytest.raises(FileExistsError, match="cannot overlap"):
        service.lock(second_scope, "other-resource")
    assert not service.gate_path.exists()

    service.release_file(lease)
    service.lock(second_scope, "other-resource")


def test_arbitrary_lock_is_fully_independent(tmp_path):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    arbitrary = service.lock("arbitrary", "resource-1")

    assert arbitrary.path.name.startswith("arbitrary_")

    # Coexists with session locks and other arbitrary locks.
    session = service.lock("session", "session-1")
    other_arbitrary = service.lock("arbitrary", "resource-2")
    assert arbitrary.path != session.path != other_arbitrary.path

    service.release_file(other_arbitrary)
    service.release_file(session)

    # A colony job is not blocked while the arbitrary lock is held.
    colony = service.lock("colony", "analysis")
    service.release_file(colony)

    # The same arbitrary resource cannot be locked twice.
    with pytest.raises(FileExistsError, match="already locked"):
        service.lock("arbitrary", "resource-1")

    service.release_file(arbitrary)


@pytest.mark.parametrize("first_scope, second_scope", [
    ("colony", "arbitrary"),
    ("arbitrary", "colony"),
])
def test_colony_and_arbitrary_do_not_exclude_each_other(tmp_path, first_scope, second_scope):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    first_lease = service.lock(first_scope, "resource-1")
    second_lease = service.lock(second_scope, "resource-2")

    assert first_lease.path != second_lease.path
    assert not service.gate_path.exists()
    service.release_file(first_lease)
    service.release_file(second_lease)


@pytest.mark.parametrize("scope", ["colony", "session", "arbitrary"])
def test_occupied_gate_blocks_acquisition_without_removing_gate(tmp_path, scope):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    service.gate_path.write_text("existing gate", encoding="utf-8")

    with pytest.raises(FileExistsError):
        service.lock(scope, "resource-1")

    assert service.gate_path.read_text(encoding="utf-8") == "existing gate"
    assert list(service.lock_dir.iterdir()) == [service.gate_path]


def test_gate_is_held_during_resource_creation(tmp_path, monkeypatch):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    other = AutomationCoordinationService(tmp_path / "AUTOMATION")
    original_open = Path.open

    def checked_open(path, *args, **kwargs):
        if path.name.startswith("session_") and args and args[0] == "x":
            assert service.gate_path.exists()
            with pytest.raises(FileExistsError):
                other.lock("colony", "other-job")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    lease = service.lock("session", "session-1")

    assert lease.path.is_file()
    assert not service.gate_path.exists()


def test_unexpired_lease_can_be_renewed(tmp_path, clock):
    service = short_coordinator(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    clock[0] = 1005.0

    assert service._renew_file(lease) == 1015.0
    record = json.loads(lease.path.read_text(encoding="utf-8"))
    assert record == {"token": lease.token, "expires_at": 1015.0}
    assert not list(service.lock_dir.glob("*.tmp"))
    assert not service.gate_path.exists()


def test_expired_lease_cannot_be_revived(tmp_path, clock):
    service = short_coordinator(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    original = lease.path.read_bytes()
    clock[0] = 1010.0

    with pytest.raises(TimeoutError):
        service._renew_file(lease)
    assert lease.path.read_bytes() == original
    assert not service.gate_path.exists()


@pytest.mark.parametrize("same_manager", [True, False])
def test_expired_claim_cannot_renew_or_release_replacement(tmp_path, clock, same_manager):
    old_owner = short_coordinator(tmp_path / "AUTOMATION")
    new_owner = old_owner if same_manager else AutomationCoordinationService(tmp_path / "AUTOMATION")
    old_lease = old_owner.lock("session", "session-1")
    clock[0] = 1010.0
    new_lease = new_owner.lock("session", "session-1")
    replacement = new_lease.path.read_bytes()

    assert old_lease.path == new_lease.path
    assert old_lease.token != new_lease.token
    with pytest.raises(PermissionError):
        old_owner._renew_file(old_lease)
    with pytest.raises(PermissionError):
        old_owner.release_file(old_lease)
    assert new_lease.path.read_bytes() == replacement
    assert not old_owner.gate_path.exists()


@pytest.mark.parametrize("first_scope, second_scope", [
    ("colony", "session"),
    ("session", "colony"),
])
def test_expired_opposing_lease_no_longer_blocks(tmp_path, clock, first_scope, second_scope):
    service = short_coordinator(tmp_path / "AUTOMATION")
    expired = service.lock(first_scope, "old-resource")
    clock[0] = 1010.0

    service.lock(second_scope, "new-resource")
    assert not expired.path.exists()


@pytest.mark.parametrize("method", ["_renew_file", "release_file"])
def test_gate_protects_renewal_and_release(tmp_path, method):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    original = lease.path.read_bytes()
    service.gate_path.touch()

    with pytest.raises(FileExistsError):
        getattr(service, method)(lease)
    assert lease.path.read_bytes() == original
    assert service.gate_path.exists()


@pytest.mark.parametrize("content", ["", "not json", '{}',
    '{"token": "owner", "expires_at": NaN}'])
def test_malformed_record_is_not_reclaimed(tmp_path, content):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    broken = service.lock_dir / "session_broken.lock"
    broken.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        service.lock("colony", "analysis")
    assert broken.read_text(encoding="utf-8") == content
    assert not service.gate_path.exists()


def test_concurrent_expired_takeover_has_one_winner(tmp_path, clock):
    directory = tmp_path / "AUTOMATION"
    original_owner = short_coordinator(directory)
    expired = original_owner.lock("session", "session-1")
    contenders = [AutomationCoordinationService(directory) for _ in range(8)]
    start = Barrier(len(contenders))
    clock[0] = 1010.0

    def acquire(service):
        start.wait(timeout=5)
        try:
            return service.lock("session", "session-1")
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
        results = list(pool.map(acquire, contenders))
    winners = [lease for lease in results if lease is not None]

    assert len(winners) == 1
    assert json.loads(expired.path.read_text(encoding="utf-8"))["token"] == winners[0].token
    assert not original_owner.gate_path.exists()


def test_failed_renewal_preserves_original_record(tmp_path, monkeypatch, clock):
    service = short_coordinator(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    original = lease.path.read_bytes()
    clock[0] = 1005.0

    def fail_replace(*args, **kwargs):
        raise OSError("Cannot replace lease")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        service._renew_file(lease)
    assert lease.path.read_bytes() == original
    assert not service.gate_path.exists()
    assert not list(service.lock_dir.glob("*.tmp"))


def test_default_timing_and_single_worker(tmp_path, clock):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    first = service.lock("session", "first")
    thread = service._renewal_thread
    second = service.lock("session", "second")

    assert service.lease_seconds == 2400
    assert service.renew_interval == 600
    assert service.retry_range == (2.5, 7.5)
    assert first.expires_at == second.expires_at == 3400.0
    assert service._renewal_thread is thread
    assert thread.is_alive()


@pytest.mark.parametrize("interval", [0, -1, 10, 11, float("inf"), float("nan")])
def test_invalid_renewal_interval(tmp_path, interval):
    with pytest.raises(ValueError):
        AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=10, renew_interval=interval)


@pytest.mark.parametrize("retry_range", [
    (0, 5), (-1, 5), (7, 2), (1,), "ab", (1, float("nan")), (float("inf"), 5),
])
def test_invalid_retry_range(tmp_path, retry_range):
    with pytest.raises(ValueError):
        AutomationCoordinationService(tmp_path / "AUTOMATION", retry_range=retry_range)


def test_thread_automatically_renews_multiple_leases(tmp_path, monkeypatch):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=2, renew_interval=0.05)
    renewed = Event()
    seen = set()
    original_renew = service._renew_file

    def observe(lease):
        result = original_renew(lease)
        seen.add(lease.token)
        if len(seen) == 2:
            renewed.set()
        return result

    monkeypatch.setattr(service, "_renew_file", observe)
    first = service.lock("session", "first")
    second = service.lock("session", "second")
    initial = first.expires_at

    assert renewed.wait(timeout=3)
    assert first.expires_at > initial
    assert not first.lost and not second.lost
    assert json.loads(first.path.read_text(encoding="utf-8"))["expires_at"] == first.expires_at


def test_thread_retries_busy_gate(tmp_path, monkeypatch):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=2, renew_interval=0.05,
                        retry_range=(0.01, 0.01))
    busy, renewed = Event(), Event()
    original_renew = service._renew_file

    def observe(lease):
        try:
            result = original_renew(lease)
        except FileExistsError:
            busy.set()
            raise
        renewed.set()
        return result

    monkeypatch.setattr(service, "_renew_file", observe)
    lease = service.lock("session", "session-1")
    original = lease.path.read_bytes()
    service.gate_path.touch()

    assert busy.wait(timeout=3)
    assert not lease.lost
    assert lease.path.read_bytes() == original
    service.gate_path.unlink()
    assert renewed.wait(timeout=3)
    assert lease.renewal_error is None


def test_thread_flags_expiry_without_reviving_lease(tmp_path, clock):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=10, renew_interval=0.05)
    lease = service.lock("session", "session-1")
    original = lease.path.read_bytes()
    clock[0] = lease.expires_at

    assert lease._lost.wait(timeout=3)
    assert lease.lost
    assert isinstance(lease.renewal_error, TimeoutError)
    assert lease.token not in service._leases
    assert lease.path.read_bytes() == original


def test_thread_does_not_overwrite_new_owner(tmp_path):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=2, renew_interval=0.05)
    lease = service.lock("session", "session-1")
    with service.gate():
        record = json.loads(lease.path.read_text(encoding="utf-8"))
        record["token"] = "new-owner"
        lease.path.write_text(json.dumps(record), encoding="utf-8")

    assert lease._lost.wait(timeout=3)
    assert lease.lost
    assert isinstance(lease.renewal_error, PermissionError)
    assert json.loads(lease.path.read_text(encoding="utf-8"))["token"] == "new-owner"


def test_release_waits_for_inflight_renewal(tmp_path, monkeypatch):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION", lease_seconds=5, renew_interval=0.05)
    started, finish = Event(), Event()
    original_renew = service._renew_file

    def delayed_renew(lease):
        started.set()
        assert finish.wait(timeout=3)
        return original_renew(lease)

    monkeypatch.setattr(service, "_renew_file", delayed_renew)
    lease = service.lock("session", "session-1")
    assert started.wait(timeout=3)
    with ThreadPoolExecutor(max_workers=1) as pool:
        release = pool.submit(service.release_file, lease)
        try:
            assert not release.done()
        finally:
            finish.set()
        release.result(timeout=3)

    assert not lease.path.exists()
    assert lease.token not in service._leases
    assert lease.lost


def test_stop_joins_worker_releases_leases_and_allows_restart(tmp_path):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    thread = service._renewal_thread
    service.stop()

    assert not thread.is_alive()
    assert not lease.path.exists()
    assert lease.lost
    with pytest.raises(RuntimeError):
        service.lock("session", "session-2")
    service.stop()  # Idempotent shutdown.
    service.start()
    assert service.lock("session", "session-2").path.is_file()


def test_stop_does_not_delete_occupied_gate(tmp_path):
    service = AutomationCoordinationService(tmp_path / "AUTOMATION")
    lease = service.lock("session", "session-1")
    thread = service._renewal_thread
    service.gate_path.touch()
    service.stop()

    assert not thread.is_alive()
    assert service.gate_path.exists()
    assert lease.path.exists()  # Cannot release safely; it will expire normally.
    assert lease.lost


@pytest.mark.parametrize("shutdown", ["stop", "disconnect"])
def test_automation_rig_wires_coordination_lifecycle(tmp_path, shutdown):
    rig = AutomationRig(config={"lampyr.mice_directory": str(tmp_path)})
    assert rig.coordination.automation_dir == tmp_path / "AUTOMATION"
    assert rig.jobreservation.coordination is rig.coordination
    rig.start()
    lease = rig.jobreservation.acquire_session("session-1")
    thread = rig.coordination._renewal_thread
    getattr(rig, shutdown)()

    assert not thread.is_alive()
    assert not lease.path.exists()
    assert rig.dump() == ({"RIG_TYPE": "AutomationRig", "RIG_NAME": "AUTOMATION"}, {}, [])
    rig.start()
    rig.jobreservation.acquire_session("session-2")
    rig.stop()


def test_jobreservation_delegates_to_coordination_service(tmp_path):
    coordination = AutomationCoordinationService(tmp_path / "AUTOMATION")
    reservation = JobReservation(coordination)

    assert reservation.coordination is coordination
    lease = reservation.acquire_session("session-1")
    assert lease.path.is_file()
    assert list(coordination._leases) == [lease.token]

    reservation.release_file(lease)
    assert not lease.path.exists()
    assert coordination._leases == {}
