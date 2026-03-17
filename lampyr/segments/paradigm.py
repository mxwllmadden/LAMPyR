# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 17:31:16 2025

@author: mm4114
"""
from dataclasses import dataclass
from typing import ClassVar
from lampyr.segments.abstract import Segment
from abc import abstractmethod

@dataclass
class ParadigmSegment(Segment):
    paradigm_tag : str = None
    _paradigmdata : dict = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.paradigm_tag is None:
            self.paradigm_tag = self.slug
    
    def _configure(self):
        super()._configure()
        self._parent_inheritproperties += ['_paradigmdata',
                                           'paradigm_tag']

class Stage(ParadigmSegment):
    def execute(self):
        self.define_sessionparams()
        try:
            self.define_task()
        except KeyboardInterrupt as e:
            self.log_error('Detected user initiated force quit.')
        self.define_shaping()
    
    @abstractmethod
    def define_sessionparams(self):
        pass
    
    @abstractmethod
    def define_task(self):
        pass
    
    @abstractmethod
    def define_shaping(self):
        pass
    
    def set_sessionparam(self, param, value):
        current_val = getattr(self.session, param)
        if current_val is not None:
            self.log_warning(f'Stage parameter {param} was overridden by user to be {current_val}. If this is not intentional, please quit and remove the override.')
        else:
            setattr(self.session, param, value)


@dataclass
class Paradigm(ParadigmSegment):
    # default properites
    DEFAULT_PROPERTIES : ClassVar[dict] = None
    
    # limits on history loading
    sessionhistory_sessionlimit : int = 2
    sessionhistory_dayslimit : int = 2
    
    _paradigmdata : dict = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.rank != 0:
            raise RuntimeError(f'Attempted to create paradigm {self.name} at a low rank. Paradigms must always be the highest ranked segment.')
        if self.lampyr is None:
            raise RuntimeError('Attempted to run paradigm outside of lampyr.')
        if not isinstance(self.DEFAULT_PROPERTIES, dict):
            raise RuntimeError('Failed to set DEFAULT_PROPERTIES class variable.')
    
    def execute(self):
        if self.slug not in self.mouse.properties:
            self.mouse.properties[self.slug] = {}
        self._paradigmdata = self.mouse.properties[self.slug]
        self._load_sessionhistory()
    
    def _load_sessionhistory(self):
        pass
        
