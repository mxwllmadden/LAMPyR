# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:40:27 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.rigs.rigcontrol import ArduinoBanditRig_0

import numpy as np
import time

class RigManager(AbstractManager):
    def start(self):
        self.rig = None
        self.connected = False

    def connect(self):
        self._output_func('Connecting to Arduino Rig...')
        self.rig = ArduinoBanditRig_0()
        self._output_func('Creating serial monitor thread...')
        self.rig.listen()
        self._output_func('Setting stored rig sipper calibration...')
        self.rig.reward.setsize(self.config.get('rig.sipper_calib'))
        self.connected = True

    def disconnect(self):
        self._output_func('Closing monitoring thread...')
        self.rig.abort()
        time.sleep(2)
        self._output_func('Disconnecting from Arduino Rig...')
        self.rig.close()
        self.connected = False

    def calibrate(self):
        if not self.connected:
            self.connect()

        def linreg(x, y):
            x = np.asarray(x)
            y = np.asarray(y)
            a, b = np.polyfit(x, y, 1)
            y_pred = a * x + b
            r2 = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)

            return a, b, r2

        def inputfloat(prompt):
            while True:
                val = input(prompt)
                try:
                    number = float(val)
                    break
                except ValueError:
                    self._output_func("Please enter a valid number.")
            return number

        def calib_disp(disp_size):
            disp_size = int(disp_size)
            self.rig.reward.setsize(disp_size)
            initial_value = inputfloat('INPUT WEIGHT (g): ')
            time.sleep(0.1)
            for i in range(200):
                self.rig.reward.give()
                time.sleep(0.4)
            dvol = (inputfloat('INPUT NEW WEIGHT (g):')-initial_value)/200
            self._output_func(f'Reward Size: {disp_size} produces {str(dvol)[:10]} ml reward')
            return dvol
        
        est_sipp = None
        while True:
            self._output_func('\nBEGINING CALIBRATION')
            if est_sipp is None:
                try:
                    est_sipp = int(self.config.get('rig.sipper_calib'))
                except:
                    est_sipp = 10000
            if est_sipp <= 10000:
                est_sipp = 10000
            dsizes = [int(est_sipp*(2/3)), est_sipp, int(est_sipp*1.5)]
            dvols = []
            for disp_size in dsizes:
                dvol = calib_disp(disp_size)
                dvols.append(dvol)
            slope, coeff, r2 = linreg(dsizes, dvols)
            if r2 < 0.9:
                self._output_func('Failed to produce linear regression. Repeating Calibration.')
                continue
            est_sipp = int((0.005 - coeff) / slope)
            self._output_func(f'Estimated correct reward size is {est_sipp}')
            self._output_func('Beginning dispenser test...')
            dvol = calib_disp(est_sipp)
            if abs(0.005 - dvol) < 0.0005:
                break
            else:
                self._output_func('Calibration failed. Repeating calibration.')
        self._output_func('Calibration success')
        self._output_func(f'Rig reward size is set to {est_sipp}')
        self.config.set('rig.sipper_calib', est_sipp)
        self.config.set('rig.calibrated', round(time.time()))

