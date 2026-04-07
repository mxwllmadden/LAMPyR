# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 17:32:31 2025

@author: mm4114
"""

from dataclasses import dataclass
from lampyr.segments.abstract import Segment

@dataclass
class ControlSegment(Segment):
    """
    Base class for non-behavioral control segments.

    Control segments are used for infrastructure-level operations (e.g.
    shaping adjustments, scoped wrappers) that do not represent discrete
    behavioural epochs.
    """
    pass

@dataclass
class Shaper(ControlSegment):
    """
    A control segment that applies shaping logic without running a behaviour.
    """

    def execute(self):
        """No-op execute; subclasses override to implement shaping logic."""
        pass

@dataclass
class ScopedSegment(ControlSegment):
    """
    A control segment scoped to a limited context or sub-operation.
    """
    pass