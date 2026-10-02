"""Hardware-free automation rig and automation-only components."""

from pathlib import Path

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


class ColonyAccess(Component):
    """Expose colony session discovery through the Colony API."""

    def setup(self, config=None):
        from lampyr.analysis.colony import Colony
        from lampyr.config import Config

        if isinstance(config, Config):
            config = config.readonly_copy()
        else:
            config = Config(sync=False)
        config.set("lampyr.enable_saveload_failsafe", False)
        self.colony = Colony(config=config)

    def candidate_sessions(self):
        """Return sorted ``(mouse_id, session_id)`` pairs from disk."""
        return sorted(
            (mid, sid)
            for mid in self.colony.mice.get_mice()
            for sid in self.colony.sessions.retrieve(mid)
        )


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
        self.register_component("colonyaccess", ColonyAccess(self.config))

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

    def is_calibrated(self):
        return True

    def is_configured(self):
        return True

    def calibrate(self):
        return True

    def configure(self):
        return True
