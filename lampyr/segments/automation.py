# -*- coding: utf-8 -*-
"""
Created on Thu Oct 1 17:31:16 2026

@author: mm4114
"""
from dataclasses import dataclass, field
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
    joblist : tuple = None
    _colonyjobs: tuple = field(default=(), init=False, repr=False)
    _sessionjobs: tuple = field(default=(), init=False, repr=False)
    _arbitraryjobs: tuple = field(default=(), init=False, repr=False)
    _joblease: object = field(default=None, init=False, repr=False)
    _mouseid: str = field(default=None, init=False, repr=False)
    _sessionid: str = field(default=None, init=False, repr=False)

    def execute(self):
        self.classify_jobs()

    def request_newjob(self):
        """Yield available job classes, holding their reservation while paused.

        Colony jobs are attempted once per pass; colony completion tracking
        and arbitrary jobs are not implemented yet. Session jobs are filtered
        by recorded version and share one lease for the whole session.
        Close the iterator explicitly if stopping early to release its lease.
        Execution, completion marking, and query handoff belong to the caller.
        """
        self.classify_jobs()
        if not self._colonyjobs and not self._sessionjobs:
            return
        reservations = self.rig.jobreservation

        for job in self._colonyjobs:
            try:
                lease = reservations.acquire_colony(job.slug or job.__name__)
            except FileExistsError:
                continue
            self._joblease = lease
            try:
                if lease.lost:
                    raise RuntimeError("Automation job reservation was lost")
                yield job
            finally:
                self._joblease = None
                reservations.release_file(lease)

        if not self._sessionjobs:
            return
        tracker = self.rig.sessionjobtracker
        jobs = [(job.slug or job.__name__, job.version) for job in self._sessionjobs]
        for mouse_id, session_id in tracker.candidate_sessions(jobs):
            try:
                lease = reservations.acquire_session(session_id)
            except FileExistsError:
                continue
            self._joblease = lease
            self._mouseid, self._sessionid = mouse_id, session_id
            try:
                # Recheck after locking: another worker may have finished
                # these jobs since candidate discovery.
                pending = tracker.pending_jobs(jobs, session_id)
                for job, identity in zip(self._sessionjobs, jobs):
                    if lease.lost:
                        raise RuntimeError("Automation job reservation was lost")
                    if identity in pending:
                        yield job
            finally:
                self._joblease = None
                self._mouseid = self._sessionid = None
                reservations.release_file(lease)

    def classify_jobs(self):
        """Store job classes by scope, preserving order within each category."""
        groups = {scope: [] for scope in (ColonyJob, SessionJob, ArbitraryJob)}
        for job in self.joblist or ():
            matches = [scope for scope in groups
                       if isinstance(job, type) and issubclass(job, scope)]
            if len(matches) != 1:
                raise TypeError(f"{job!r} must belong to exactly one job category")
            groups[matches[0]].append(job)

        self._colonyjobs, self._sessionjobs, self._arbitraryjobs = (
            tuple(jobs) for jobs in groups.values()
        )

@dataclass
class Job(Segment):
    """
    Base class for Jobs
    """
    slug : str = None
    version : str = None
    
@dataclass
class ColonyJob(Job):
    """
    Base class for colony-wide jobs
    """
    pass

@dataclass
class SessionJob(Job):
    """
    Base class for session-wide jobs
    """
    pass

@dataclass
class ArbitraryJob(Job):
    """
    Base class for session-wide jobs
    
    NOT YET IMPLEMENTED
    """
    pass