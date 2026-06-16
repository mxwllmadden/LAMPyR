# -*- coding: utf-8 -*-
"""
Created on Mon Jun 15 16:42:30 2026

@author: mm4114
"""
from datetime import date, datetime, timedelta
from time import time

from typing import Callable, List, Tuple

from lampyr.managers.data import DataHandler


class MouseQuery:
    def __init__(self, colony, predicates: Tuple[Callable, ...] = ()):
        self.colony = colony
        self.predicates = predicates

    def _clone(self, predicate: Callable):
        return MouseQuery(self.colony, self.predicates + (predicate,))

    def where(self, predicate: Callable):
        return self._clone(predicate)

    def paradigm(self, paradigm: str):
        return self.where(lambda mouse: mouse.paradigm == paradigm)

    def stage(self, slug: str, stage: str):
        return self.where(
            lambda mouse: mouse.properties.get(slug, {}).get("stage") == stage
        )

    def retired(self, retired: bool = True):
        return self.where(lambda mouse: mouse.retired == retired)

    def active(self):
        return self.retired(False)

    def property(self, key: str, value):
        return self.where(lambda mouse: mouse.properties.get(key) == value)

    def properties(self, **properties):
        query = self
        for key, value in properties.items():
            query = query.property(key, value)
        return query

    def ids(self) -> List[str]:
        mouseids, _ = self.colony.data.mouselist()
        result = []

        for mouseid in mouseids:
            if mouseid == "UNKNOWN_MOUSE":
                continue

            mouse = self.colony.load_mouse(mouseid)
            if all(predicate(mouse) for predicate in self.predicates):
                result.append(mouseid)

        return result

    def count(self) -> int:
        return len(self.ids())

    def objects(self) -> list:
        return [self.colony.load_mouse(mouseid) for mouseid in self.ids()]

    def sessions(self, **filters):
        return self.colony.sessions(mouseids=self.ids(), **filters)


class SessionQuery:
    RANGE_KEYS = {
        "duration",
        "merit",
        "demerit",
        "trial",
        "rewards",
        "abstention",
        "participation",
        "starttime",
        "age"
    }

    def __init__(self,
                 colony,
                 mouseids: Tuple[str, ...],
                 predicates: Tuple[Callable, ...] = ()):
        self.colony = colony
        self.mouseids = mouseids
        self.predicates = predicates

    def _clone(self, predicate: Callable):
        return SessionQuery(self.colony, self.mouseids, self.predicates + (predicate,))

    def session(self, sessionid):
        for mouseid, entry in self._matched_entries():
            if self.colony._sessionid(entry) == sessionid:
                return self.colony.load_session(
                    sessionid,
                    mouseid,
                )
    
        raise KeyError(
            f"Session '{sessionid}' not found in query."
        )

    def where(self, predicate: Callable):
        return self._clone(predicate)

    def range(self, key: str, minimum=None, maximum=None):
        if key not in self.RANGE_KEYS:
            raise ValueError(f"Unknown session filter: {key}")

        def predicate(entry):
            value = entry.get(key)

            if value in (None, ""):
                return False

            try:
                value = float(value)
            except (TypeError, ValueError):
                return False

            if minimum is not None and value < minimum:
                return False

            if maximum is not None and value > maximum:
                return False

            return True

        return self._clone(predicate)

    def duration(self, minimum=None, maximum=None):
        return self.range("duration", minimum, maximum)

    def merit(self, minimum=None, maximum=None):
        return self.range("merit", minimum, maximum)

    def demerit(self, minimum=None, maximum=None):
        return self.range("demerit", minimum, maximum)

    def trial(self, minimum=None, maximum=None):
        return self.range("trial", minimum, maximum)

    def rewards(self, minimum=None, maximum=None):
        return self.range("rewards", minimum, maximum)

    def abstention(self, minimum=None, maximum=None):
        return self.range("abstention", minimum, maximum)

    def participation(self, minimum=None, maximum=None):
        return self.range("participation", minimum, maximum)

    def starttime(self, minimum=None, maximum=None):
        return self.range("starttime", minimum, maximum)

    @staticmethod
    def _timestamp_bound(value, *, is_end: bool):
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, datetime):
            return value.timestamp()

        if isinstance(value, date):
            dt = datetime.combine(value, datetime.min.time())
            if is_end:
                dt += timedelta(days=1)
            return dt.timestamp()

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

            for parser in (datetime.fromisoformat, date.fromisoformat):
                try:
                    parsed = parser(value)
                except ValueError:
                    continue

                if isinstance(parsed, datetime):
                    return parsed.timestamp()

                dt = datetime.combine(parsed, datetime.min.time())
                if is_end:
                    dt += timedelta(days=1)
                return dt.timestamp()

        raise ValueError(
            "Date bounds must be date, datetime, timestamp, or ISO-format string."
        )

    def date_range(self, start=None, end=None):
        """
        Filter sessions by calendar date or datetime range.

        `start` is inclusive. `end` is inclusive for date-only values and
        exclusive for datetime/timestamp values.
        """
        minimum = self._timestamp_bound(start, is_end=False)
        maximum = self._timestamp_bound(end, is_end=True)

        def predicate(entry):
            starttime = self.colony._starttime(entry)

            if starttime is None:
                return False

            if minimum is not None and starttime < minimum:
                return False

            if maximum is not None and starttime >= maximum:
                return False

            return True

        return self._clone(predicate)
    
    def age(self, minimum=None, maximum=None):
        """
        Session age in days.
        age(0, 30) => last 30 days
        age(30, None) => older than 30 days
        """
        now = time()
    
        def predicate(entry):
            starttime = self.colony._starttime(entry)
    
            if starttime is None:
                return False
    
            age_days = (now - starttime) / 86400
    
            if minimum is not None and age_days < minimum:
                return False
    
            if maximum is not None and age_days > maximum:
                return False
    
            return True
    
        return self._clone(predicate)
    
    def younger_than(self, days: float):
        """
        Include only sessions that occurred within the last N days.
        """
        cutoff = time() - days * 24 * 60 * 60
    
        return self.where(
            lambda entry: (
                self.colony._starttime(entry) is not None
                and self.colony._starttime(entry) >= cutoff
            )
        )
    
    def older_than(self, days: float):
        """
        Include only sessions older than N days.
        """
        cutoff = time() - days * 24 * 60 * 60
    
        return self.where(
            lambda entry: (
                self.colony._starttime(entry) is not None
                and self.colony._starttime(entry) < cutoff
            )
        )

    def filters(self, **filters):
        query = self

        for key, bounds in filters.items():
            if bounds is None:
                continue

            try:
                minimum, maximum = bounds
            except (TypeError, ValueError):
                raise ValueError(
                    f"Filter '{key}' must be a (minimum, maximum) tuple."
                ) from None

            query = query.range(key, minimum, maximum)

        return query

    def _matched_entries(self) -> list:
        result = []

        for mouseid in self.mouseids:
            mouse = self.colony.load_mouse(mouseid)

            for entry in mouse.history:
                if self.colony._sessionid(entry) is None:
                    continue

                if all(predicate(entry) for predicate in self.predicates):
                    result.append((mouseid, entry))

        return result

    def ids(self) -> List[str]:
        return [
            self.colony._sessionid(entry)
            for _, entry in self._matched_entries()
        ]

    def count(self) -> int:
        return len(self._matched_entries())

    def objects(self) -> list:
        return [
            self.colony.load_session(self.colony._sessionid(entry), mouseid)
            for mouseid, entry in self._matched_entries()
        ]

    def last_ids(self, n: int = 1) -> List[str]:
        entries = [
            (mouseid, entry)
            for mouseid, entry in self._matched_entries()
            if self.colony._starttime(entry) is not None
        ]
        entries.sort(key=lambda pair: self.colony._starttime(pair[1]), reverse=True)

        return [
            self.colony._sessionid(entry)
            for _, entry in entries[:n]
        ]

    def last(self, n: int = 1) -> list:
        entries = [
            (mouseid, entry)
            for mouseid, entry in self._matched_entries()
            if self.colony._starttime(entry) is not None
        ]
        entries.sort(key=lambda pair: self.colony._starttime(pair[1]), reverse=True)

        return [
            self.colony.load_session(self.colony._sessionid(entry), mouseid)
            for mouseid, entry in entries[:n]
        ]

    def bymouse(self) -> dict:
        return {
            mouseid: SessionQuery(self.colony, (mouseid,), self.predicates)
            for mouseid in self.mouseids
        }


class Colony:
    def __init__(self, config=None, keep="sessions", verbose: bool = False):
        self.data = DataHandler(config=config)
        self.keep_mice, self.keep_sessions = self._resolve_keep(keep)
        self.verbose = verbose
        self._mouse_cache = {}
        self._session_cache = {}

    def mice(self,
             paradigm=None,
             slug=None,
             stage=None,
             retired=None,
             properties=None,
             where=None) -> MouseQuery:
        query = MouseQuery(self)

        if paradigm is not None:
            query = query.paradigm(paradigm)

        if stage is not None:
            query = query.stage(slug, stage)

        if retired is not None:
            query = query.retired(retired)

        if properties is not None:
            query = query.properties(**properties)

        if where is not None:
            query = query.where(where)

        return query

    def sessions(self,
                 mouseid=None,
                 mouseids=None,
                 paradigm=None,
                 slug=None,
                 stage=None,
                 retired=None,
                 properties=None,
                 where_mouse=None,
                 duration=None,
                 merit=None,
                 demerit=None,
                 trial=None,
                 rewards=None,
                 abstention=None,
                 participation=None,
                 starttime=None,
                 date_range=None,
                 where=None) -> SessionQuery:
        if mouseid is not None and mouseids is not None:
            raise ValueError("Pass only one of mouseid or mouseids.")

        if mouseid is not None:
            selected_mouseids = (mouseid,)
        elif mouseids is not None:
            selected_mouseids = tuple(mouseids)
        else:
            selected_mouseids = tuple(
                self.mice(
                    paradigm=paradigm,
                    slug=slug,
                    stage=stage,
                    retired=retired,
                    properties=properties,
                    where=where_mouse,
                ).ids()
            )

        query = SessionQuery(self, selected_mouseids).filters(
            duration=duration,
            merit=merit,
            demerit=demerit,
            trial=trial,
            rewards=rewards,
            abstention=abstention,
            participation=participation,
            starttime=starttime,
        )

        if where is not None:
            query = query.where(where)

        if date_range is not None:
            try:
                start, end = date_range
            except (TypeError, ValueError):
                raise ValueError(
                    "date_range must be a (start, end) tuple."
                ) from None

            query = query.date_range(start, end)

        return query

    def load_mouse(self, mouseid: str):
        if not self.keep_mice:
            self._log(f"Loading mouse {mouseid}")
            return self.data.loadmouse(mouseid)

        if mouseid not in self._mouse_cache:
            self._log(f"Loading mouse {mouseid}")
            self._mouse_cache[mouseid] = self.data.loadmouse(mouseid)

        return self._mouse_cache[mouseid]

    def load_session(self, sessionid: str, mouseid: str):
        if not self.keep_sessions:
            self._log(f"Loading session {sessionid} for mouse {mouseid}")
            return self.data.loadsession(sessionid, mouseid)

        key = (mouseid, sessionid)
        if key not in self._session_cache:
            self._log(f"Loading session {sessionid} for mouse {mouseid}")
            self._session_cache[key] = self.data.loadsession(sessionid, mouseid)

        return self._session_cache[key]

    def clear_cache(self, mice: bool = True, sessions: bool = True):
        if mice:
            self._mouse_cache.clear()
        if sessions:
            self._session_cache.clear()

    @staticmethod
    def _resolve_keep(keep):
        modes = {
            None: (False, False),
            "none": (False, False),
            "mice": (True, False),
            "sessions": (False, True),
            "all": (True, True),
        }

        if keep not in modes:
            raise ValueError("keep must be one of: None, 'none', 'mice', 'sessions', 'all'")

        return modes[keep]

    def _log(self, message: str):
        if self.verbose:
            print(message)

    @staticmethod
    def _sessionid(entry: dict):
        for key in ("sessionid", "uniquesessionid", "session_id", "id"):
            if key in entry and entry[key] not in (None, ""):
                return entry[key]

        return None

    @staticmethod
    def _starttime(entry: dict):
        value = entry.get("starttime")

        if value in (None, ""):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None
