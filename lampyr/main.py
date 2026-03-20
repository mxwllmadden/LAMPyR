# -*- coding: utf-8 -*-
"""
Created on Thu May 22 15:48:30 2025

@author: mxwll
"""

import os
import traceback
import json
import time

from lampyr.config import Config
from lampyr.primatives import Session

from lampyr.segments.abstract import Segment
from lampyr.managers import DataHandler, MouseManager, RigManager
from lampyr.managers.notification import NotificationManager


class Lampyr:
    def __init__(self, _input_func = input, _output_func=print):
        self._output_func = _output_func
        self._input_func = _input_func
        self.config = Config()
        self.session = None
        self.datamanager = DataHandler(self)
        
        self.rigmanager = RigManager(self)
        self.mousemanager = MouseManager(self)
        self.notificationmanager = NotificationManager(self)

        self.behaviors = {c.__name__: c for c in Segment.get_children()}
        self.paradigms = {}

    @property
    def rig(self):
        return self.rigmanager.rig

    @property
    def mouse(self):
        return self.mousemanager.mouse

    def run(self, segment_name: str, **kwargs):
        if segment_name not in self.behaviors:
            raise KeyError('Not a valid behavior')
        if segment_name in self.paradigms and self.mouse is None:
            raise RuntimeError(
                'Paradigms cannot be run without an active mouse')
        if self.rig is None:
            raise RuntimeError(
                'Segments cannot be run without an active rig')
            
        self._createsession(**kwargs)
        behav = self.behaviors[segment_name](lampyr=self,
                                             _verbose=True
                                             )
        stopcodes = []
        try:
            behav.run()
        except KeyboardInterrupt:
            self._output_func('\nAborted by user!\n')
            stopcodes.append('user intervention')
        except Exception as error:
            self._output_func(traceback.format_exc())
        finally:
            self._output_func(behav.session)
            stopcodes += behav.session.evaluatestopconditions()
            if getattr(self, '_user_aborted', False):
                stopcodes.append('user intervention')
                self._user_aborted = False
            if not stopcodes:
                stopcodes.append('finished task')
            rname = self.config.get('rig.name')
            mid = self.mouse.mouseid
            self.notificationmanager.send_notification(
                f'{mid} has ended behavior due to {" and ".join(stopcodes)}',
                title=f'Lampyr - {rname}'
                )
            
    
    def _createsession(self, **kwargs):
        if self.mouse is not None:
            kwargs['mouseid'] = self.mouse.mouseid
        self.session = Session(**kwargs)

    def close(self):
        if self.rig is not None:
            self.rigmanager.disconnect()
        if self.session is not None:
            self.datamanager.savesession()
        if self.mouse is not None:
            self.mousemanager.save() # Important that mouse is saved after session


if __name__ == '__main__':
    try:
        lamp = Lampyr()
        lamp.mousemanager.load('014-003')
    finally:
        lamp.close()
