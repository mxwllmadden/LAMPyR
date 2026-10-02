# -*- coding: utf-8 -*-
"""
Created on Wed May 14 15:02:37 2025

@author: mm4114

NOT YET IMPLEMENTED

"""

import threading
from serial.tools import list_ports
import serial
from dataclasses import dataclass, field
from collections import defaultdict
import time
import numpy as np
from lampyr.rigs.abstract import AbstractHardwareRig, Component
from lampyr.rigs.interfaces import SerialInterface_ArduinoTRV, CameraInterface_Arducam


class Wheel(Component):
    def setup(self, serialinterface):
        self.serial = serialinterface
        self.home()

    def movement_total_since(self, time):
        components = self.movement_components_since(time)
        return components[1] - components[0]

    def movement_since(self, time):
        def condition(report): return report['unix_time'] > time
        values = self.serial.data.scanback_values(
            'R', 'report_value', condition)
        return sum(values)/4096*360

    def movement_components_since(self, time):
        def condition(report): return report['unix_time'] > time
        values = self.serial.data.scanback_values(
            'R', 'report_value', condition)
        sum_positive = sum(x for x in values if x > 0)/4096*360
        sum_negative = sum(x for x in values if x < 0)/4096*360
        return sum_negative, sum_positive

    def angle(self):
        return self.movement_since(self.home_t)

    def home(self):
        self.home_t = time.time()


class Lick(Component):
    def setup(self, serialinterface):
        self.serial = serialinterface

    def since(self, time):
        """
        Count the number of lick onset events since ``time``.

        Detects lick onsets as low-to-high threshold crossings (threshold
        512) in the raw lick signal.

        Parameters
        ----------
        time : float
            Unix timestamp; only events after this time are counted.

        Returns
        -------
        int
            Number of detected lick onsets.
        """
        def condition(report): return report['unix_time'] > time
        lickdat = self.serial.data.scanback_values(
            'L', 'report_value', condition)
        lcount = 0
        for l1, l2 in zip(lickdat, lickdat[1:]):
            if l1 < 512 and l2 > 512:
                lcount += 1
        return lcount


class Speaker(Component):
    """Speaker interface for playing tones via the rig Arduino."""

    def setup(self, serialinterface):
        self.serial = serialinterface

    def begintrialtone(self):
        """Play the trial-start tone (serial command ``'b'``)."""
        self.serial.send_command('b')

    def responsetone(self):
        """Play the response tone (serial command ``'r'``)."""
        self.serial.send_command('r')

    def punishtone(self):
        """Play the punishment tone (serial command ``'p'``)."""
        self.serial.send_command('p')


class Sipper(Component):
    """Water sipper interface for delivering liquid rewards."""

    def setup(self, serialinterface):
        self.serial = serialinterface

    def give(self):
        """Dispense one reward (serial command ``'g'``)."""
        self.serial.send_command('g')

    def setsize(self, size: int):
        """
        Set the sipper reward size on the Arduino.

        Parameters
        ----------
        size : int
            Dispense size value (arbitrary Arduino units, calibrated to
            ~5 µl per reward).
        """
        self.serial.send_command(f'w{size}')


class WheelLock(Component):
    def setup(self, serialinterface, handedness = 1):
        self.serial = serialinterface
        self.handedness = handedness

    def lock(self):
        self.serial.send_command('l')

    def unlock(self):
        self.serial.send_command('u')

    def to_angle(self, angle):
        if self.handedness == -1:
            angle = 180-angle
        self.serial.send_command(f'a{angle}')
        
    def stop(self):
        self.unlock()


class LaserControl(Component):
    def setup(self, serialinterface):
        self.serial = serialinterface

    def begin(self):
        self.serial.send_command('z')

    def stop(self):
        self.serial.send_command('x')

    def rampdown(self, ramp_ms=500, delay_ms=0):
        """Ramp the laser down, optionally after a delay in milliseconds."""
        if delay_ms:
            self.serial.send_command(f'c{ramp_ms},{delay_ms}')
        else:
            self.serial.send_command(f'c{ramp_ms}')


class Camera(Component):
    def setup(self, serialinterface, camerainterface):
        self.serial = serialinterface
        self.cam = camerainterface

    def begin(self):
        self.serial.send_command('o')

    def stop(self):
        self.serial.send_command('k')

    def get_framecount_inlast(self, seconds):
        cutoff = time.time() - seconds
        return len(
            self.cam.data._scanback('cam_frame_times',
                                    lambda r: r['unix_time'] > cutoff)
        )
    
    def get_total_frames(self):
        idx = 0
        with self.cam.lock:
            idx = self.cam.idx
        return idx

class BanditRig(AbstractHardwareRig):
    CONFIGURATION = {
        'handedness': {
            'prompt': 'Rig handedness (1 = right-handed, -1 = left-handed)',
            'type': int,
            'choices': [1, -1],
            'default': 1,
        },
    }
    CALIBRATION = {
        'sipper_calib': {'type': dict, 'default': {'size': 10000, 'calibrated_at': 0}},
    }
    CALIBRATION_VALIDITY = 5 * 24 * 60 * 60  # seconds

    @classmethod
    def is_calibrated(cls, config):
        if not super().is_calibrated(config):
            return False
        entry = config.rigconfig.get('sipper_calib')
        if not isinstance(entry, dict):
            return False
        size = entry.get('size')
        calibrated_at = entry.get('calibrated_at')
        if size is None or calibrated_at is None:
            return False
        return calibrated_at > time.time() - cls.CALIBRATION_VALIDITY

    def setup(self):
        serialinterface = SerialInterface_ArduinoTRV(baud=115200, timeout=1)
        self.register_interface('HudaHub', serialinterface)
        self.register_component('wheel', Wheel(serialinterface))
        self.register_component('licks', Lick(serialinterface))
        self.register_component('play', Speaker(serialinterface))
        self.register_component('reward', Sipper(serialinterface))
        handedness = self.config_value('handedness', 1)
        self.register_component('wheellock', WheelLock(serialinterface, handedness = handedness))
        self.register_component('laser', LaserControl(serialinterface))
        
        

    def start(self):
        """Start interfaces, then apply the stored calibration."""
        super().start()
        calib = self.config_value('sipper_calib') or {}
        self.reward.setsize(calib.get('size', 10000))

    def initialize_mousecam(self):
        try:
            apdir = self.config._APP_DATA_DIR
        except:
            apdir = None
    
        camerainterface = CameraInterface_Arducam()
        self.register_interface('Arducam', camerainterface)
        # This will require manually starting the camera interface, as the
        # Rig wide start command has already occurred
        camerainterface.start()
        camerainterface.ready.wait(timeout = 5)
        # This is not advisable as general practice but this hack allows
        # The same rig to run camera and non-camera sessions wihout reconfig
        time.sleep(1)
        serialinterface = self.interfaces['HudaHub']
        cam = Camera(serialinterface, camerainterface)
        self.register_component('camera', cam)
        self.camera.begin()

    def calibrate(self, _input_func, _output_func):
        """Interactively calibrate the sipper dispenser to ~5 µl per reward."""
        def linreg(x, y):
            x = np.asarray(x)
            y = np.asarray(y)
            a, b = np.polyfit(x, y, 1)
            y_pred = a * x + b
            r2 = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
            return a, b, r2

        def inputfloat(prompt):
            while True:
                val = _input_func(prompt)
                try:
                    number = float(val)
                    break
                except ValueError:
                    _output_func("Please enter a valid number.")
            return number

        def calib_disp(disp_size, initial_value=None):
            disp_size = int(disp_size)
            self.reward.setsize(disp_size)
            if initial_value is None:
                initial_value = inputfloat('INPUT WEIGHT (g): ')
                if initial_value == 0.0:
                    _output_func("Zero entered — restarting calibration cycle.")
                    return None
            time.sleep(0.1)
            for i in range(200):
                self.reward.give()
                time.sleep(0.3)
            new_value = inputfloat('INPUT NEW WEIGHT (g):')
            if new_value == 0.0:
                _output_func("Zero entered — restarting calibration cycle.")
                return None
            dvol = (new_value - initial_value) / 200
            _output_func(f'Reward Size: {disp_size} produces {str(dvol)[:10]} ml reward')
            return dvol, new_value

        est_sipp = None
        while True:
            _output_func('\nBEGINING CALIBRATION')
            if est_sipp is None:
                try:
                    est_sipp = int((self.config.rigconfig.get('sipper_calib') or {}).get('size', 10000))
                except Exception:
                    est_sipp = 10000
            if est_sipp <= 6000:
                est_sipp = 10000
            dsizes = [int(est_sipp*(2/3)), est_sipp, int(est_sipp*1.5)]
            dvols = []
            next_initial = None
            restart = False
            for disp_size in dsizes:
                result = calib_disp(disp_size, initial_value=next_initial)
                if result is None:
                    restart = True
                    break
                dvol, next_initial = result
                dvols.append(dvol)
            if restart:
                continue
            slope, coeff, r2 = linreg(dsizes, dvols)
            if r2 < 0.9:
                _output_func('Failed to produce linear regression. Repeating Calibration.')
                continue
            est_sipp = int((0.005 - coeff) / slope)
            _output_func(f'Estimated correct reward size is {est_sipp}')
            _output_func('Beginning dispenser test...')
            result = calib_disp(est_sipp, initial_value=next_initial)
            if result is None:
                continue
            dvol, _ = result
            if abs(0.005 - dvol) < 0.0005:
                break
            else:
                _output_func('Calibration failed. Repeating calibration.')

        _output_func('Calibration success')
        _output_func(f'Rig reward size is set to {est_sipp}')
        self.config.rigconfig['sipper_calib'] = {
            'size': est_sipp,
            'calibrated_at': time.time(),
        }
        self.config.save()

    def configure(self, _input_func, _output_func):
        pass
