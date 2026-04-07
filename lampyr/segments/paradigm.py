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
    """
    Base class for paradigm-level segments (Paradigm, Stage).

    Adds a ``paradigm_tag`` label and a ``_paradigmdata`` reference that is
    shared across the paradigm hierarchy.

    Attributes
    ----------
    paradigm_tag : str or None
        Label used to key into the mouse's ``paradigm_stage`` and
        ``properties`` dicts.  Defaults to ``slug`` if not set.
    _paradigmdata : dict or None
        Reference to the paradigm's persistent data dict from the mouse,
        populated by the root :class:`Paradigm`.
    """
    paradigm_tag : str = None
    _paradigmdata : dict = None
    
    def __post_init__(self):
        """
        Set ``paradigm_tag`` to ``slug`` if not explicitly provided.
        """
        super().__post_init__()
        if self.paradigm_tag is None:
            self.paradigm_tag = self.slug

    def _configure(self):
        """
        Add ``_paradigmdata`` and ``paradigm_tag`` to the parent-inherit list.
        """
        super()._configure()
        self._parent_inheritproperties += ['_paradigmdata',
                                           'paradigm_tag']

class Stage(ParadigmSegment):
    """
    Represents one stage within a Paradigm.

    A Stage runs a single task session and then applies shaping logic to
    determine whether the mouse should advance to the next stage.  Subclasses
    implement :meth:`define_sessionparams`, :meth:`define_task`, and
    :meth:`define_shaping`.
    """

    def execute(self):
        """
        Run the stage: set session parameters, run the task, then apply shaping.

        ``KeyboardInterrupt`` during :meth:`define_task` is caught and logged
        so that shaping logic in :meth:`define_shaping` still runs on forced
        exits.
        """
        self.define_sessionparams()
        try:
            self.define_task()
        except KeyboardInterrupt as e:
            self.log_error('Detected user initiated force quit.')
        self.define_shaping()
    
    @abstractmethod
    def define_sessionparams(self):
        """Set session limits and minimums via :meth:`set_sessionparam`."""
        pass

    @abstractmethod
    def define_task(self):
        """Instantiate and run the task(s) for this stage."""
        pass

    @abstractmethod
    def define_shaping(self):
        """Evaluate session outcome and update shaping state or advance stage."""
        pass
    
    def set_sessionparam(self, param, value):
        """
        Set a session parameter only if it has not already been overridden.

        If the session attribute is currently ``None``, it is set to
        ``value``.  If it already has a value, a warning is logged instead
        so the user is aware of the override.

        Parameters
        ----------
        param : str
            Session attribute name (e.g. ``'duration_limit'``).
        value : object
            Value to assign.
        """
        current_val = getattr(self.session, param)
        if current_val is not None:
            self.log_warning(f'Stage parameter {param} was overridden by user to be {current_val}. If this is not intentional, please quit and remove the override.')
        else:
            setattr(self.session, param, value)


@dataclass
class Paradigm(ParadigmSegment):
    """
    Root-level segment that orchestrates stage selection and session history.

    A Paradigm must always be the highest-ranked segment (rank 0) and must
    be run within a Lampyr instance.  It initialises per-mouse paradigm data
    from ``mouse.properties``, then delegates to the appropriate
    :class:`Stage` based on the mouse's current progress.

    Class Variables
    ---------------
    DEFAULT_PROPERTIES : dict
        Defines the initial structure of the per-mouse paradigm data dict.
        Subclasses must override this.
    STAGES : list of str
        Ordered list of stage name strings for this paradigm.

    Attributes
    ----------
    sessionhistory_sessionlimit : int
        Maximum number of past sessions to load when reviewing history.
    sessionhistory_dayslimit : int
        Maximum age (days) of past sessions to consider.
    _paradigmdata : dict or None
        Reference to ``mouse.properties[slug]``, populated during
        :meth:`execute`.
    """

    # default properites
    DEFAULT_PROPERTIES : ClassVar[dict] = None
    STAGES : ClassVar[list] = []
    
    # limits on history loading
    sessionhistory_sessionlimit : int = 2
    sessionhistory_dayslimit : int = 2
    
    _paradigmdata : dict = None
    
    def __post_init__(self):
        """
        Validate that a lampyr instance and DEFAULT_PROPERTIES are present.

        Raises
        ------
        RuntimeError
            If the paradigm is not at rank 0, if no lampyr instance is
            attached, or if ``DEFAULT_PROPERTIES`` has not been overridden.
        """
        super().__post_init__()
        if self.rank != 0:
            raise RuntimeError(f'Attempted to create paradigm {self.name} at a low rank. Paradigms must always be the highest ranked segment.')
        if self.lampyr is None:
            raise RuntimeError('Attempted to run paradigm outside of lampyr.')
        if not isinstance(self.DEFAULT_PROPERTIES, dict):
            raise RuntimeError('Failed to set DEFAULT_PROPERTIES class variable.')
    
    def execute(self):
        """
        Bind the mouse's paradigm data and load session history.

        Creates an empty property dict for this paradigm if one does not yet
        exist, then sets ``_paradigmdata`` to point at it and calls
        :meth:`_load_sessionhistory`.
        """
        if self.slug not in self.mouse.properties:
            self.mouse.properties[self.slug] = {}
        self._paradigmdata = self.mouse.properties[self.slug]
        self._load_sessionhistory()
    
    def _load_sessionhistory(self):
        """
        Load recent session history for this mouse.

        Base implementation is a no-op.  Subclasses may override to pull
        historical sessions and use them to inform shaping decisions.
        """
        pass
        
