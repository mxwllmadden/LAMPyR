# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:40:27 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.rigs.abstract import all_rig_definitions, AbstractHardwareRig
from lampyr.rigs.banditrig import BanditRig
from lampyr.rigs.automationrig import AutomationRig  # noqa: F401 — register for rig discovery



class RigManager(AbstractManager):
    """
    Manages connection to and calibration of the configured rig.

    Attributes
    ----------
    rig : AbstractHardwareRig or None
        The connected rig object; ``None`` until :meth:`connect` is called.
    connected : bool
        Whether a rig is currently connected.
    """

    def start(self):
        """Initialise rig and connection state to disconnected."""
        all_rigs = all_rig_definitions()
        rig_type = self.config.get('rig.rig_type')
        self.rig_cls = all_rigs.get(rig_type, BanditRig)
        self.rig = None
        self.connected = False

    def connect(self):
        """
        Connect to the configured rig.

        Instantiates the rig class and starts it. Calibration and any other
        rig-specific setup are the rig's responsibility.
        """
        self._output_func('Loading rig config')
        self._output_func('Connecting to rig...')
        self.rig = self.rig_cls(config = self.config)
        self._output_func('Starting rig...')
        self.rig.start()
        self.connected = True

    def disconnect(self):
        """
        Stop the serial monitor thread and close the rig serial port.
        """
        if self.rig is None:
            return
        if not self.connected:
            self._output_func('Rig is already shut down...')
            return
        self._output_func('Closing rig monitoring threads...')
        self.rig.stop()
        self.rig.disconnect()
        self.connected = False

    def calibrate(self):
        """
        Connect (if needed) and delegate calibration to the rig.

        The rig's ``calibrate`` method performs the interactive procedure using
        the input/output functions passed directly.
        """
        was_connected = self.connected
        if not self.connected:
            self.connect()
        try:
            self.rig.calibrate(self._input_func, self._output_func)
        finally:
            if not was_connected:
                self.disconnect()

