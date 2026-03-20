# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 17:21:05 2025

@author: mm4114
"""

from dataclasses import dataclass, field
import time
from copy import deepcopy
from typing import Callable, List, Literal
from abc import ABC, abstractmethod

from lampyr.primatives import Mouse, Session, uniqueid


@dataclass
class Segment(ABC):
    # General identification
    name: str = None
    slug: str = None
    uniqueid: str = None
    starttime: float = None
    endtime: float = None

    # References to other segments and lampyr
    rank: int = 0
    subdata: list = field(default_factory=list)
    lampyr: object = None
    parent: object = None

    # Data and logs
    records: List = field(default_factory=list)  # General purpose log

    # Mouse, rig, session data
    rig: object = None
    mouse: Mouse = None
    session: Session = None

    # Input/Output functions
    _output_func: Callable = None  # inherited from lampyr; falls back to print if standalone
    _verbose: bool = False

    # Utilities
    _parent_inheritproperties: list = field(default_factory=list)
    _lampyr_inheritproperties: list = field(default_factory=list)
    _parent_inheritproperties_combine: list = field(default_factory=list)
    _dump_reducetorepresentations: list = field(default_factory=list)
    _dump_exclusions: list = field(default_factory=list)
    _frozen: bool = False
    
    # Logging nonsense
    _last_log_notice_t: float = field(default=0, init=False)
    _last_log_notice: str = field(default='', init=False)
    _last_log_info_t: float = field(default=0, init=False)
    _last_log_info: str = field(default='', init=False)

    def __post_init__(self):
        self._configure()
        if self.slug is None:
            self.slug = self.__class__.__name__
        if self.name is None:
            if self.parent is not None:
                self.name = f'{self.parent.name}_{self.slug}{len(self.parent.subdata)}'
            else:
                self.name = self.slug
        if self.uniqueid is None:
            self.uniqueid = uniqueid(
                'segment', self.__class__.__name__)
        self._inherit()
        self._inherit_from_lampyr()
        if self.session is None:
            self.log_warning('Not able to find a session. Creating new session (destructive).')
            self.session = Session()
        if self.parent is None:
            self.rank = 0
            self.log_debug('No parent detected, marking this segment as root')
            self.session.root = self.uniqueid

    @classmethod
    def get_children(cls, recursive=True):
        children = set()
        for subclass in cls.__subclasses__():
            children.add(subclass)
            if recursive:
                children.update(subclass.get_children())
        return children
    
    @classmethod
    def get_parents(cls, recursive=True):
        parents = set()
        for parent in cls.__bases__:
            if not issubclass(parent, Segment):
                continue
            parents.add(parent)
            if recursive and hasattr(parent, 'get_parents'):
                parents.update(parent.get_parents())
        return parents
    
    def run(self):
        if self._frozen:
            raise RuntimeError('Running a segment twice is forbidden')
        self.starttime = time.time()
        try:
            self.execute()
        except KeyboardInterrupt as error:
            self.log_error(f'User has initiated a force-quit. {self.name} closing...')
            raise
        finally:
            self.endtime = time.time()
            self._frozen = True
            self.dump()
    
    @abstractmethod
    def execute(self):
        pass

    def _log(self, prefix, message: str, output=True, style='\x1b[33m'):
        if output:
            out = self._output_func if self._output_func is not None else print
            out(f'{style}[{prefix}][{self.name}] {message}\033[0m')
        self.records.append((time.time(), prefix, message))
        return time.time()

    def log_info(self, message: str, delay = None):
        if delay is None:
            return self._log('INFO', message, output=True)
        if message != self._last_log_info or self._last_log_info_t + delay < time.time():
            self._last_log_info = message
            self._last_log_info_t = time.time()
            return self._log('INFO', message, output=True)
        return time.time()

    def log_debug(self, message: str):
        return self._log('DEBUG', message, output=self._verbose, style='\x1b[90m')
    
    def log_notice(self, message: str, delay=None):
        if delay is None:
            return self._log('NOTICE', message, output=True, style='\033[93m')
        if message != self._last_log_notice or self._last_log_notice_t + delay < time.time():
            self._last_log_notice = message
            self._last_log_notice_t = time.time()
            return self._log('NOTICE', message, output=True, style='\033[93m')
        return time.time()

    
    def log_warning(self, message: str):
        return self._log('WARNING', message, output=True, style='\033[38;5;208m')

    def log_error(self, message: str):
        return self._log('ERROR', message, output=True, style='\033[38;5;196m')

    def dump(self):
        all_data = {k: v for k, v in self.__dict__.items()
                    if k not in self._dump_reducetorepresentations
                    and k not in self._dump_exclusions
                    and not k.startswith('_')}
        for k in self._dump_reducetorepresentations:
            if k not in self.__dict__:
                continue
            v = self.__dict__[k]
            if hasattr(v, 'uniqueid'):
                all_data[k] = v.uniqueid
            elif v is None:
                all_data[k] = None
            else:
                all_data[k] = v.__repr__()
        all_data['segment_type'] = [cls.__name__ for cls in self.get_parents()]
        try:
            all_data = deepcopy(all_data)
        except:
            print([[k, type(v)] for k, v in all_data.items()])
        self.log_debug('Storing data in session...')
        self.session.segmentlist.append(self.uniqueid)
        self.session.segments[self.uniqueid] = all_data
        if self.rank == 0:
            self.log_notice('Detected that self is highest ranked segment')
            self.log_notice('Extracting rig data and saving to session')
            self.session.rigdata = self.rig.data.get_report_snippet(self.session.starttime,
                                                                    time.time())
            self.log_notice('Session data is now LOCKED')
            self.session.lock()
        else:
            self.log_debug('Storing reference to self in parent segment')
            self.parent.subdata.append(self.uniqueid)
        return all_data

    def _configure(self):
        self._parent_inheritproperties += ['lampyr',
                                           'rig', 'mouse', 'session', '_output_func',
                                           '_verbose']
        self._lampyr_inheritproperties += ['rig', 'mouse', 'session', '_output_func']
        self._dump_reducetorepresentations += ['lampyr', 'parent']
        self._dump_exclusions += ['rig', 'session', 'mouse']

    def _inherit(self):
        if self.parent is None:
            return
        self.rank = self.parent.rank + 1
        for prop in self._parent_inheritproperties:
            self.log_debug(f'Inheriting {prop} from parent (destructive)')
            self._inheritproperty(self.parent, prop, 'replace')
        for prop in self._parent_inheritproperties_combine:
            self.log_debug(f'Inheriting {prop} from parent (combinatorial)')
            self._inheritproperty(self.parent, prop, 'combine')
    
    def _inherit_from_lampyr(self):
        if self.lampyr is None:
            self.log_warning('You are running segments without a lampyr instance.')
            return
        for prop in self._lampyr_inheritproperties:
            if getattr(self, prop) is None:
                self.log_debug(f'Inheriting {prop} from parent (destructive)')
                self._inheritproperty(self.lampyr, prop, 'replace')
        

    def _inheritproperty(self, source, name: str, mode: Literal['replace', 'combine']):
        if not hasattr(source, name):
            return
        attr = getattr(source, name)
        if attr is None:
            return
        if mode == 'replace':
            setattr(self, name, attr)
            return
        myattr = getattr(self, name)
        hint = getattr(type(self), '__annotations__', {}).get(name, None)
        if myattr is None:
            setattr(self, name, attr)
            return
        if isinstance(attr, list) and isinstance(myattr, list):
            combined = attr + myattr
        elif isinstance(attr, dict) and isinstance(myattr, dict):
            combined = {**attr, **myattr}
        else:
            raise TypeError(f'{self.name} has attempted to inherit {name} from parent and has experienced a type mismatch.' +
                            f'Parent type was {type(attr)}, object type was {type(myattr)} and object annotation was for {hint}')
        setattr(self, name, combined)
