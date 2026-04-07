# -*- coding: utf-8 -*-
"""
Created on Wed Dec  3 18:26:06 2025

@author: mm4114
"""

from lampyr.primatives import Session
from lampyr import files
from typing import List, Union
from random import randint
from scipy.interpolate import interp1d
from dataclasses import asdict
from collections import namedtuple
import numpy as np
import os
import shutil

SegmentReference = namedtuple('SegmentReference', ['animal',
                                                   'session',
                                                   'segment'])
TraceReference = namedtuple('ExtractionToken', ['session',
                                                'timearray',
                                                'time_type'])
TraceExtractionProfile = namedtuple('ExtractionProfile', ['profile_name',
                                                          'mode',
                                                          'signal',
                                                          'samplerate',
                                                          'time_type',
                                                          'fill'])


def trace_extractor_factory(session, profile: TraceExtractionProfile):
    """
    Build a callable that extracts trace values from a session's rig data.

    For ``'nearest'`` and ``'linear'`` modes, returns a
    :func:`~scipy.interpolate.interp1d` object.  For windowed modes
    (``'mean'``, ``'sum'``, ``'count'``, ``'rate'``), returns a custom
    function that averages/sums/counts samples within each time window.

    Parameters
    ----------
    session : Session
        The session containing the rig data to extract from.
    profile : TraceExtractionProfile
        Specifies the signal channel, interpolation mode, sample rate, time
        type, and fill value.

    Returns
    -------
    callable
        A function ``f(time_array: np.ndarray) -> np.ndarray`` that returns
        extracted trace values at the requested times.
    """
    t_data = session.rigdata[profile.signal][profile.time_type]
    v_data = session.rigdata[profile.signal]['report_value']
    if profile.mode in ['nearest', 'linear']:
        return interp1d(t_data, v_data,
                        kind=profile.mode,
                        bounds_error=False,
                        fill_value=profile.fill)

    def windowed_extraction(time_array: np.ndarray):
        n = len(time_array)
        left_window = np.empty(n)
        right_window = np.empty(n)

        # edges
        left_window[0] = (time_array[1] - time_array[0]) / 2
        right_window[0] = left_window[0]
        left_window[-1] = (time_array[-1] - time_array[-2]) / 2
        right_window[-1] = left_window[-1]

        # interior points
        left_window[1:-1] = (time_array[1:-1] - time_array[:-2]) / 2
        right_window[1:-1] = (time_array[2:] - time_array[1:-1]) / 2

        out = np.full(n, profile.fill)
        for i, ti in enumerate(time_array):
            mask = (t_data >= ti - left_window[i]
                    ) & (t_data <= ti + right_window[i])
            if not mask.any():
                continue

            if profile.mode == "mean":
                out[i] = np.nanmean(v_data[mask])
            elif profile.mode == "sum":
                out[i] = np.nansum(v_data[mask])
            elif profile.mode == "count":
                out[i] = np.sum(~np.isnan(v_data[mask]))
            elif profile.mode == "rate":
                out[i] = np.sum(~np.isnan(v_data[mask])) / \
                    (left_window[i] + right_window[i])
            else:
                raise ValueError(f"Unknown mode: {profile.mode}")
        return out
    return windowed_extraction


class MultiSessionDataset:
    """
    A collection of sessions with disk persistence and cross-session search.

    Sessions are stored in a directory as pairs of ``.lampyr.h5`` (rig data)
    and ``.lampyr.json`` (metadata) files, indexed by
    ``msd_INDEX.lampyr.json``.

    Attributes
    ----------
    fp : str
        Path to the directory used for saving/loading session files.
    sessions : list of Session
        All sessions currently in the dataset.
    sessionsbyid : dict
        Maps ``uniquesessionid`` to Session objects.
    animals : list of str
        Sorted list of unique mouse IDs present in the dataset.
    sessionids : list of str
        List of session IDs in insertion order.
    animal_sessions : dict
        Maps mouse ID to a list of its sessions.
    """

    def __init__(self, fp: str, sessions: List[Session] = None,
                 destructive_overwrite=False):
        """
        Initialise the dataset, loading existing sessions from disk.

        Parameters
        ----------
        fp : str
            Directory path for session file storage.  Created if it does not
            exist.
        sessions : list of Session, optional
            Sessions to add after loading from disk.
        destructive_overwrite : bool, optional
            If ``True``, delete all existing files in ``fp`` before adding
            new sessions.  Default is ``False``.
        """
        if sessions is None:
            sessions = []
        # Basic attributes
        self.sessions = []
        self.sessionsbyid = {}

        # File attributes
        self.fp = fp
        os.makedirs(fp, exist_ok=True)
        self.update()

        if destructive_overwrite:
            self.clear_files()
        else:
            self._load()
        self.addsession(sessions)

        # Secondary attributes
        self._extractor_objects = {}

    def clear(self):
        """Remove all sessions from the in-memory list and update derived attributes."""
        self.sessions = []
        self.update()

    def clear_files(self):
        """
        Remove all in-memory sessions and delete all files in the dataset directory.

        Also saves an empty index file after clearing.
        """
        self.clear()
        for item in os.listdir(self.fp):
            path = os.path.join(self.fp, item)
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        self.save()
        self.update()

    def addsession(self, session: Union[Session, List[Session]], _suppressupdate = False):
        """
        Add one or more sessions to the dataset, replacing duplicates by ID.

        Parameters
        ----------
        session : Session or list of Session
            Session(s) to add.
        _suppressupdate : bool, optional
            If ``True``, skip calling :meth:`update` (used internally for
            batch adds).  Default is ``False``.
        """
        if isinstance(session, list):
            for s in session:
                self.addsession(s, _suppressupdate=True)
            return
        if session.uniquesessionid in self.sessionids:
            self.sessions = [s for s in self.sessions
                             if s.uniquesessionid != session.uniquesessionid]
        self.sessions.append(session)
        if not _suppressupdate:
            self.update()

    def update(self):
        """
        Rebuild all derived lookup attributes from the current session list.

        Should be called after any modification to :attr:`sessions`.
        """
        self.animals = sorted(list(set([s.mouseid for s in self.sessions])))
        self.sessionids = [s.uniquesessionid for s in self.sessions]
        self.sessionsbyid = {s.uniquesessionid : s for s in self.sessions}
        self.animal_sessions = {a: [s for s in self.sessions
                                    if s.mouseid == a]
                                for a in self.animals}
        self._extractor_objects = {}

    def search(self,
               *args,
               mouseid: str = None,
               return_objects : bool = False,
               **kwargs):
        """
        Search segments across all sessions.

        Parameters
        ----------
        *args
            Positional arguments forwarded to :meth:`Session.search`.
        mouseid : str, optional
            Restrict search to sessions from this mouse.
        return_objects : bool, optional
            If ``True``, return segment dicts instead of
            :class:`SegmentReference` named tuples.
        **kwargs
            Keyword arguments forwarded to :meth:`Session.search`.

        Returns
        -------
        list of SegmentReference or list of dict
            Matching segments across all sessions.
        """
        seglist = []
        for session in self.sessions:
            if mouseid is not None and mouseid != session.mouseid:
                continue
            segments = session.search(*args,
                                      return_objects=return_objects,
                                      **kwargs)
            if not return_objects:
                for seg in segments:
                    seglist.append(
                        SegmentReference(animal=session.mouseid,
                                         session=session.uniquesessionid,
                                         segment=seg)
                    )
            else:
                seglist += segments
        return seglist

    def get_segment(self, reference: SegmentReference):
        """
        Retrieve a segment dict by reference.

        Parameters
        ----------
        reference : SegmentReference
            Named tuple identifying the animal, session, and segment.

        Returns
        -------
        dict
            The serialised segment data dict from the session.
        """
        return self.sessionsbyid[reference.session].segments[reference.segment]

    def get_trace(self, reference: TraceReference,
                  profile: TraceExtractionProfile):
        """
        Extract and return a trace array for the given reference and profile.

        Caches the extractor object per ``(session, profile)`` pair.

        Parameters
        ----------
        reference : TraceReference
            Identifies the session and the time array to evaluate.
        profile : TraceExtractionProfile
            Specifies signal, mode, sample rate, time type, and fill value.

        Returns
        -------
        np.ndarray
            Extracted trace values at ``reference.timearray`` times.
        """
        if (reference.session, profile) not in self._extractor_objects:
            extractor = trace_extractor_factory(
                self.sessionsbyid[reference.session],
                profile)
            self._extractor_objects[(reference.session, profile)] = extractor
        else:
            extractor = self._extractor_objects[(reference.session, profile)]
        return extractor(reference.timearray)

    # File management

    def save(self):
        """
        Save all sessions to disk and update the index file.
        """
        session_names = [session.uniquesessionid for session in self.sessions]
        for session in self.sessions:
            files.savesessionfile(session, self.fp)
        files.savejson(os.path.join(self.fp,
                                    'msd_INDEX.lampyr.json'),
                       session_names)

    def _load(self):
        """
        Load all sessions listed in the index file into memory.

        Silently returns if the index file does not exist.
        """
        print('Loading dataset...')
        try:
            session_names = files.loadjson(os.path.join(self.fp,
                                                        'msd_INDEX.lampyr.json'))
        except FileNotFoundError:
            return
        for sname in session_names:
            print(f'Loading sessionfile {sname}')
            session = files.loadsessionfile(sname, self.fp)
            self.addsession(session, _suppressupdate=True)
        self.update()
