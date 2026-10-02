"""Rig services that coordinate automation state without producing session data."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import logging
import math
import random
import threading
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from lampyr.rigs.abstract import AbstractService


@dataclass
class Lease:
    """A claim whose lost property signals release, expiry, or lost ownership."""

    path: Path
    token: str
    expires_at: float
    renewal_error: Exception | None = field(default=None, repr=False)
    _lost: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def lost(self):
        return self._lost.is_set() or time.time() >= self.expires_at


class AutomationCoordinationService(AbstractService):
    """Coordinate automation leases (jobs, sessions, resources) on disk.

    Leases last 40 minutes and renew every 10 minutes by default. Clocks on
    participating machines must be synchronized. Workers must stop using a
    resource when lease.lost is true; renewal cannot stop their code for them.

    When the shared gate is busy, renewal retries after a delay drawn uniformly
    from retry_range. Colony jobs with different IDs may coexist but exclude
    session locks. Session locks are blocked while a colony job is active.
    Arbitrary locks are fully independent and conflict only with their own
    resource ID.
    """

    _LOCK_SCOPES = ("colony", "session", "arbitrary")

    def setup(self, automation_dir, lease_seconds=2400, renew_interval=600,
              retry_range=(2.5, 7.5)):
        """Store paths and configure automatic renewal and retry in seconds."""
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Lease duration must be finite and positive")
        if not math.isfinite(renew_interval) or not 0 < renew_interval < lease_seconds:
            raise ValueError("Renewal interval must be positive and shorter than the lease")
        try:
            retry_low, retry_high = retry_range
        except (TypeError, ValueError) as error:
            raise ValueError("retry_range must be a (low, high) pair") from error
        if (not isinstance(retry_low, (int, float))
                or not isinstance(retry_high, (int, float))
                or not math.isfinite(retry_low)
                or not math.isfinite(retry_high)
                or not 0 < retry_low <= retry_high):
            raise ValueError("retry_range must be (low, high) with 0 < low <= high")
        self.lease_seconds = lease_seconds
        self.renew_interval = renew_interval
        self.retry_range = (float(retry_low), float(retry_high))
        self.automation_dir = Path(automation_dir)
        self.lock_dir = self.automation_dir / ".locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.gate_path = self.lock_dir / "automation.lock"
        self._leases = {}
        self._state_lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._renewal_thread = None
        self._stopped = False

    def start(self):
        """Allow acquisitions after shutdown; renewal starts on acquisition."""
        with self._lifecycle_lock, self._state_lock:
            self._stopped = False
            self._stop_event.clear()

    def _renew_loop(self):
        delay = self.renew_interval
        while not self._stop_event.wait(delay):
            retry = False
            with self._state_lock:
                for lease in list(self._leases.values()):
                    if self._stop_event.is_set():
                        return
                    try:
                        self._renew_file(lease)
                    except (FileNotFoundError, PermissionError, TimeoutError, ValueError) as error:
                        self._lose_lease(lease, error)
                    except OSError as error:
                        lease.renewal_error = error
                        if lease.lost:
                            self._lose_lease(lease, error)
                        else:
                            retry = True
                    except Exception as error:
                        self._lose_lease(lease, error)
            delay = random.uniform(*self.retry_range) if retry else self.renew_interval

    def _lose_lease(self, lease, error):
        lease.renewal_error = error
        lease._lost.set()
        self._leases.pop(lease.token, None)
        logging.getLogger(__name__).warning("Lease lost for %s: %s", lease.path, error)

    def stop(self):
        """Stop renewal and release owned leases; blocked releases expire normally."""
        with self._lifecycle_lock:
            with self._state_lock:
                self._stopped = True
                self._stop_event.set()
                thread = self._renewal_thread
            if thread is not None:
                thread.join()
            with self._state_lock:
                for lease in list(self._leases.values()):
                    try:
                        self.release_file(lease)
                    except (OSError, ValueError) as error:
                        self._lose_lease(lease, error)
                self._renewal_thread = None

    def disconnect(self):
        """Alias for stop; there is no separate connection to tear down."""
        self.stop()

    @contextmanager
    def gate(self):
        """Serialize changes; a crash may leave a gate for manual removal."""
        with self.gate_path.open("x", encoding="utf-8"):
            pass
        try:
            yield
        finally:
            self.gate_path.unlink()

    def _read_lease(self, path):
        """Fail closed on unreadable or malformed records, never reclaim them."""
        with path.open(encoding="utf-8") as file:
            record = json.load(file)
        if (not isinstance(record, dict)
                or not isinstance(record.get("token"), str)
                or not record["token"]
                or type(record.get("expires_at")) not in (int, float)
                or not math.isfinite(record["expires_at"])):
            raise ValueError(f"Invalid lease record: {path}")
        return record

    def lock(self, scope, resource_id):
        """Check conflicts and atomically claim a resource under the gate."""
        filename = f"{scope}_{quote(str(resource_id), safe='')}.lock"
        with self._state_lock:
            if self._stopped:
                raise RuntimeError("Automation coordination is stopped; call start before acquiring")
            with self.gate():
                now = time.time()
                active = {scope_name: [] for scope_name in self._LOCK_SCOPES}
                for scope_name in self._LOCK_SCOPES:
                    for path in self.lock_dir.glob(f"{scope_name}_*.lock"):
                        if self._read_lease(path)["expires_at"] <= now:
                            path.unlink()
                        else:
                            active[scope_name].append(path)

                lock_path = self.lock_dir / filename
                if lock_path in active[scope]:
                    raise FileExistsError(f"Resource already locked: {filename}")
                if scope == "colony":
                    if active["session"]:
                        raise FileExistsError(
                            "A colony job cannot overlap with session locks")
                elif scope == "session" and active["colony"]:
                    raise FileExistsError(
                        "Session locks cannot overlap with a colony job")

                lease = Lease(lock_path, uuid4().hex, time.time() + self.lease_seconds)
                record = {"token": lease.token, "expires_at": lease.expires_at}
                with lock_path.open("x", encoding="utf-8") as file:
                    json.dump(record, file)
            self._leases[lease.token] = lease
            if self._renewal_thread is None:
                self._renewal_thread = threading.Thread(
                    target=self._renew_loop, name="AutomationCoordination-renewal", daemon=True)
                self._renewal_thread.start()
            return lease

    def _owned_record(self, lease):
        """Verify this claim still owns its resource. Caller must hold gate."""
        if lease.path.parent != self.lock_dir:
            raise ValueError("Lease belongs to a different lock directory")
        record = self._read_lease(lease.path)
        if record["token"] != lease.token:
            raise PermissionError("Lease ownership has been lost")
        return record

    def _renew_file(self, lease):
        """Extend an unexpired owned lease; return its new expiry timestamp."""
        with self._state_lock, self.gate():
            record = self._owned_record(lease)
            now = time.time()
            if lease._lost.is_set() or record["expires_at"] <= now:
                raise TimeoutError("Expired or lost leases cannot be renewed")
            record["expires_at"] = now + self.lease_seconds
            temporary = lease.path.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps(record), encoding="utf-8")
                temporary.replace(lease.path)
            finally:
                temporary.unlink(missing_ok=True)
            lease.expires_at = record["expires_at"]
            lease.renewal_error = None
            return lease.expires_at

    def release_file(self, lease):
        """Release only the claim represented by this lease handle."""
        with self._state_lock, self.gate():
            self._owned_record(lease)
            lease.path.unlink()
            self._leases.pop(lease.token, None)
            lease._lost.set()
