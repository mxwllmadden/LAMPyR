"""Hardware-free rig used by automation segments."""

import time

from lampyr.rigs.abstract import AbstractHardwareRig, Component


class SystemClock(Component):
    """Provide the current system time to automation segments."""

    def setup(self):
        pass

    def now(self):
        """Return the current Unix timestamp in seconds."""
        return time.time()


class AutomationRig(AbstractHardwareRig):
    """Provide the rig lifecycle expected by ``Segment`` without hardware.

    Automation segments can use this rig so root-segment finalization remains
    unchanged while avoiding serial, camera, and other physical interfaces.
    """

    def setup(self):
        self.register_component("clock", SystemClock())

    def start(self):
        """Start without initializing hardware."""
        pass

    def stop(self):
        """Stop safely without controlling hardware."""
        pass

    def disconnect(self):
        """Disconnect safely without controlling hardware."""
        pass

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
