"""Hardware-free automation rig and automation-only components."""

import json
from pathlib import Path
from urllib.parse import quote

from lampyr.rigs.abstract import AbstractHardwareRig, Component
from lampyr.rigs.services import AutomationCoordinationService


class JobReservation(Component):
    """Reserve jobs, sessions, and resources through the coordination service."""

    def setup(self, coordination):
        self.coordination = coordination

    def acquire_colony(self, jobid):
        return self.coordination.lock("colony", jobid)

    def acquire_session(self, sessionid):
        return self.coordination.lock("session", sessionid)

    def acquire_arbitrary(self, resource_id):
        return self.coordination.lock("arbitrary", resource_id)

    def release_file(self, lease):
        return self.coordination.release_file(lease)


class SessionJobTracker(Component):
    """Find candidate sessions and record completed automation job runs."""

    def setup(self, config, coordination):
        from lampyr.analysis.colony import Colony
        from lampyr.config import Config

        if isinstance(config, Config):
            config = config.readonly_copy()
        else:
            config = Config(sync=False)
        config.set("lampyr.enable_saveload_failsafe", False)
        self.colony = Colony(config=config)
        self.coordination = coordination
        self.runs_dir = coordination.automation_dir / ".runs"

    def candidate_sessions(self, jobs):
        """Return ``(mouse_id, session_id)`` pairs still needing a job run.

        ``jobs`` is a sequence of ``(jobid, version)`` tuples. A session is
        excluded only when it has a valid run marker for every job. A marker
        is invalid when its recorded version is older than the requested one
        (i.e. the job's version has since been incremented).
        """
        all_sessions = sorted(
            (mid, sid)
            for mid in self.colony.mice.get_mice()
            for sid in self.colony.sessions.retrieve(mid)
        )
        return [
            (mid, sid)
            for mid, sid in all_sessions
            if not self._is_run_through(sid, jobs)
        ]

    def mark_completed(self, jobid, version, session_id):
        """Write a session/job completion marker under the coordination guard."""
        marker = self.runs_dir / session_id / f"{quote(str(jobid), safe='')}.json"
        with self.coordination.gate():
            marker.parent.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps({"version": version}), encoding="utf-8")
                temporary.replace(marker)
            finally:
                temporary.unlink(missing_ok=True)

    def _is_run_through(self, session_id, jobs):
        return all(self._is_processed(jobid, version, session_id)
                   for jobid, version in jobs)

    def _is_processed(self, jobid, version, session_id):
        marker = self.runs_dir / session_id / f"{quote(str(jobid), safe='')}.json"
        if not marker.is_file():
            return False
        try:
            record = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(record, dict) and record.get("version", -1) >= version


class AutomationRig(AbstractHardwareRig):
    """Provide the rig lifecycle expected by ``Segment`` without hardware."""

    def setup(self, automation_dir=None):
        if automation_dir is None:
            shared_dir = self.config.get("lampyr.mice_directory")
            if shared_dir is None:
                raise ValueError("Provide automation_dir or configure lampyr.mice_directory")
            automation_dir = Path(shared_dir) / "AUTOMATION"
        coordination = AutomationCoordinationService(automation_dir)
        self.register_service("coordination", coordination)
        self.register_component("jobreservation", JobReservation(coordination))
        self.register_component("sessionjobtracker", SessionJobTracker(self.config, coordination))

    def start(self):
        """Enable automation coordination without initializing hardware."""
        self.coordination.start()

    def stop(self):
        """Stop lease renewal and release automation reservations."""
        self.coordination.stop()

    def disconnect(self):
        """Shut down automation coordination safely without controlling hardware."""
        self.coordination.disconnect()

    def dump(self):
        """Return empty rig data in the format expected by ``Segment.dump``."""
        properties = {
            "RIG_TYPE": self.__class__.__name__,
            "RIG_NAME": "AUTOMATION",
        }
        return properties, {}, []

    def calibrate(self):
        return True

    def configure(self):
        return True
