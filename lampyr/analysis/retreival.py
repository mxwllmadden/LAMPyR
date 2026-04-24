# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 11:40:43 2026

@author: mm4114
"""

import os
import re
from typing import Union, List, Tuple, Dict, Optional

from lampyr.managers.data import DataHandler


_TS_RE = re.compile(r'created(\d+)_')


def _resolve_sessionid(entry: dict, session_dir: str) -> Optional[str]:
    """
    Return the sessionid for a history entry.

    Uses the stored ``sessionid`` key if present.  Otherwise scans
    ``session_dir`` for a session file whose embedded timestamp matches
    ``entry['starttime']``.
    """
    sessionid = entry.get('sessionid')
    if sessionid is not None:
        return sessionid

    starttime = entry.get('starttime')
    if starttime is None or not os.path.isdir(session_dir):
        return None

    target_ts = round(starttime)
    for fname in os.listdir(session_dir):
        if not fname.endswith('.lampyr.json'):
            continue
        m = _TS_RE.search(fname)
        if m and int(m.group(1)) == target_ts:
            return fname[:-len('.lampyr.json')]

    return None


def find_sessions(
    data_handler: DataHandler,
    mice: Union[str, List[str], Dict[str, dict], None] = None,
    date_range: Union[Tuple[Optional[Tuple[int, int, int]],
                            Optional[Tuple[int, int, int]]], None] = None,
    **filters: Tuple[Optional[float], Optional[float]]
) -> List[Tuple[str, str]]:
    """
    Search mouse history for sessions matching date and metric criteria.

    Filters are applied against the lightweight history entries stored in each
    mouse's CSV, so full session files are not loaded.  Use
    ``data_handler.loadsession(sessionid, mouseid)`` on the results to get
    full Session objects.

    Parameters
    ----------
    data_handler : DataHandler
        Configured DataHandler used to load mouse objects.
    mice : str, list of str, dict, or None
        Mouse ID(s) to search.  ``None`` searches all mice on disk.

        Pass a ``dict`` to specify per-mouse criteria that override the global
        ``date_range`` and ``filters`` for individual mice::

            mice={
                'mouseA': {'date_range': ((2026, 1, 1), (2026, 1, 1))},
                'mouseB': {'date_range': ((2026, 1, 15), None),
                           'merit': (5, None)},
            }

        Any key accepted by ``date_range`` or ``**filters`` may appear in
        each per-mouse dict.  Omitted keys fall back to the global values.

    date_range : tuple of two (year, month, day) tuples, or None
        ``(start, end)`` bounds, both inclusive.  Either bound may be ``None``
        for open-ended.  Example: ``((2026, 1, 1), (2026, 4, 23))``.
    **filters : (min, max) tuples
        Numeric range filters keyed by history field name.  Either bound may
        be ``None`` for unbounded.  Recognised fields: ``merit``, ``demerit``,
        ``duration``, ``trial``, ``rewards``, ``abstention``,
        ``participation``, ``serial_abstention``.
        Example: ``merit=(5, None), duration=(300, 3600)``.

    Returns
    -------
    list of (mouseid, sessionid) tuples
        Matching sessions in the order they appear in each mouse's history.
    """
    if isinstance(mice, dict):
        per_mouse_criteria = mice
        mouseids = list(mice.keys())
    else:
        per_mouse_criteria = {}
        if isinstance(mice, str):
            mouseids = [mice]
        elif mice is None:
            mouseids, _ = data_handler.mouselist()
        else:
            mouseids = list(mice)

    mice_directory = data_handler.config.get('lampyr.mice_directory')

    results = []
    for mouseid in mouseids:
        overrides = per_mouse_criteria.get(mouseid, {})
        mouse_date_range = overrides.get('date_range', date_range)
        mouse_filters = {**filters,
                         **{k: v for k, v in overrides.items()
                            if k != 'date_range'}}

        date_start, date_end = ((None, None) if mouse_date_range is None
                                else mouse_date_range)

        session_dir = os.path.join(mice_directory, mouseid,
                                   'lampyr_sessionhistory')

        mouse = data_handler.loadmouse(mouseid)
        for entry in mouse.history:
            if date_start is not None:
                if (entry['year'], entry['month'], entry['day']) < date_start:
                    continue
            if date_end is not None:
                if (entry['year'], entry['month'], entry['day']) > date_end:
                    continue

            match = True
            for field, bounds in mouse_filters.items():
                value = entry.get(field)
                if value is None:
                    match = False
                    break
                lo, hi = bounds
                if lo is not None and value < lo:
                    match = False
                    break
                if hi is not None and value > hi:
                    match = False
                    break

            if not match:
                continue

            sessionid = _resolve_sessionid(entry, session_dir)
            if sessionid is not None:
                results.append((mouseid, sessionid))

    return results
