from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lampyr.segments.automation import (
    ArbitraryJob, AutomationSegment, ColonyJob, SessionJob,
)


class ColonyWork(ColonyJob):
    slug = "colony-work"
    version = 1

    def execute(self):
        raise AssertionError("Search must not execute jobs")


class SessionWork(SessionJob):
    slug = "session-work"
    version = 2

    def execute(self):
        raise AssertionError("Search must not execute jobs")


class OtherSessionWork(SessionWork):
    slug = None  # Exercise the class-name fallback.
    version = 1


class ArbitraryWork(ArbitraryJob):
    def execute(self):
        raise AssertionError("Arbitrary jobs are not supported yet")


class Reservations:
    def __init__(self, blocked=()):
        self.blocked = set(blocked)
        self.events = []

    def acquire(self, scope, identity):
        self.events.append(("acquire", scope, identity))
        if (scope, identity) in self.blocked:
            raise FileExistsError(identity)
        return SimpleNamespace(scope=scope, identity=identity, lost=False)

    def acquire_colony(self, identity):
        return self.acquire("colony", identity)

    def acquire_session(self, identity):
        return self.acquire("session", identity)

    def release_file(self, lease):
        self.events.append(("release", lease.scope, lease.identity))
        lease.lost = True


def make_search(joblist, blocked=(), candidates=(), pending=None):
    reservations = Reservations(blocked)
    tracker = Mock()
    tracker.candidate_sessions.return_value = candidates
    tracker.pending_jobs.side_effect = (
        (lambda jobs, sid: pending[sid]) if pending is not None
        else (lambda jobs, sid: jobs)
    )
    segment = AutomationSegment(
        joblist=joblist,
        rig=SimpleNamespace(jobreservation=reservations, sessionjobtracker=tracker),
    )
    return segment, reservations, tracker


def test_colony_priority_and_one_lease_for_remaining_session_jobs():
    segment, reservations, tracker = make_search(
        (SessionWork, ColonyWork, OtherSessionWork, ArbitraryWork),
        candidates=[("M1", "S1")],
    )
    search = segment.request_newjob()

    assert next(search) is ColonyWork
    assert segment._joblease.scope == "colony"
    tracker.candidate_sessions.assert_not_called()

    assert next(search) is SessionWork
    lease = segment._joblease
    assert (segment._mouseid, segment._sessionid) == ("M1", "S1")
    assert next(search) is OtherSessionWork
    assert segment._joblease is lease
    assert not lease.lost
    with pytest.raises(StopIteration):
        next(search)

    assert segment._joblease is None
    assert segment._mouseid is segment._sessionid is None
    assert reservations.events == [
        ("acquire", "colony", "colony-work"),
        ("release", "colony", "colony-work"),
        ("acquire", "session", "S1"),
        ("release", "session", "S1"),
    ]
    tracker.candidate_sessions.assert_called_once_with([
        ("session-work", 2), ("OtherSessionWork", 1),
    ])
    tracker.mark_completed.assert_not_called()


def test_busy_colony_and_session_locks_are_skipped():
    segment, reservations, _ = make_search(
        (ColonyWork, SessionWork),
        blocked=[("colony", "colony-work"), ("session", "S1")],
        candidates=[("M1", "S1"), ("M2", "S2")],
    )
    assert list(segment.request_newjob()) == [SessionWork]
    assert reservations.events[-2:] == [
        ("acquire", "session", "S2"), ("release", "session", "S2"),
    ]


def test_search_rechecks_pending_jobs_after_lock_and_skips_completed_jobs():
    segment, reservations, _ = make_search(
        (SessionWork, OtherSessionWork),
        candidates=[("M1", "S1"), ("M2", "S2")],
        pending={"S1": [], "S2": [("OtherSessionWork", 1)]},
    )
    assert list(segment.request_newjob()) == [OtherSessionWork]
    assert reservations.events == [
        ("acquire", "session", "S1"), ("release", "session", "S1"),
        ("acquire", "session", "S2"), ("release", "session", "S2"),
    ]


@pytest.mark.parametrize("scope", ["colony", "session"])
def test_closing_iterator_releases_current_lease(scope):
    job = ColonyWork if scope == "colony" else SessionWork
    segment, reservations, _ = make_search((job,), candidates=[("M1", "S1")])
    search = segment.request_newjob()
    assert next(search) is job
    lease = segment._joblease

    search.close()

    assert lease.lost
    assert segment._joblease is None
    assert segment._mouseid is segment._sessionid is None
    assert reservations.events[-1][0] == "release"


def test_throwing_error_into_iterator_releases_session_lease():
    segment, _, _ = make_search((SessionWork,), candidates=[("M1", "S1")])
    search = segment.request_newjob()
    next(search)
    lease = segment._joblease
    with pytest.raises(RuntimeError, match="execution failed"):
        search.throw(RuntimeError("execution failed"))
    assert lease.lost
    assert segment._joblease is None


def test_lost_session_lease_prevents_yielding_more_jobs():
    segment, _, _ = make_search(
        (SessionWork, OtherSessionWork), candidates=[("M1", "S1")],
    )
    search = segment.request_newjob()
    next(search)
    segment._joblease.lost = True
    with pytest.raises(RuntimeError, match="reservation was lost"):
        next(search)
    assert segment._joblease is None


@pytest.mark.parametrize("jobs", [None, (), (ArbitraryWork,)])
def test_empty_or_arbitrary_only_search_does_not_require_a_rig(jobs):
    segment = AutomationSegment(joblist=jobs)
    assert list(segment.request_newjob()) == []


def test_no_candidates_ends_search():
    segment, reservations, _ = make_search((SessionWork,))
    assert list(segment.request_newjob()) == []
    assert reservations.events == []


def test_non_contention_errors_are_not_silently_skipped():
    segment, reservations, _ = make_search((ColonyWork,))
    reservations.acquire_colony = Mock(side_effect=PermissionError("access denied"))
    with pytest.raises(PermissionError, match="access denied"):
        list(segment.request_newjob())
