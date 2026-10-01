# -*- coding: utf-8 -*-
"""
Created on Thu Oct 1 17:31:16 2026

@author: mm4114
"""
from dataclasses import dataclass
from lampyr.segments.abstract import Segment
from abc import abstractmethod

@dataclass
class AutomationSegment(Segment):
    """
    Base class for Automation segments.

    Used to execute arbitrary code in an automated fashion. Intended to be 
    used with the lampyr go GUI and for processing intensive post-facto 
    session analysis.
    """
    
    def execute(self):
        self.rig.stop()

