import pytest

from lampyr.segments.automation import (
    ArbitraryJob,
    AutomationSegment,
    ColonyJob,
    SessionJob,
)


class TestColonyJob(ColonyJob):
    __test__ = False

    def execute(self):
        pass


class TestSessionJob(SessionJob):
    __test__ = False

    def execute(self):
        pass


class OtherSessionJob(TestSessionJob):
    pass


class TestArbitraryJob(ArbitraryJob):
    __test__ = False

    def execute(self):
        pass


class AmbiguousJob(ColonyJob, SessionJob):
    def execute(self):
        pass


def test_classification_stores_private_groups_in_declaration_order():
    segment = AutomationSegment(joblist=(
        TestSessionJob, TestArbitraryJob, TestColonyJob, OtherSessionJob,
    ))

    assert segment.classify_jobs() is None
    assert segment._colonyjobs == (TestColonyJob,)
    assert segment._sessionjobs == (TestSessionJob, OtherSessionJob)
    assert segment._arbitraryjobs == (TestArbitraryJob,)


def test_execute_classifies_jobs_and_reclassification_clears_old_groups():
    segment = AutomationSegment(joblist=(TestColonyJob,))
    segment.execute()
    assert segment._colonyjobs == (TestColonyJob,)

    segment.joblist = None
    segment.classify_jobs()
    assert segment._colonyjobs == ()
    assert segment._sessionjobs == ()
    assert segment._arbitraryjobs == ()


@pytest.mark.parametrize("job", [object, "not a class", AmbiguousJob])
def test_classification_rejects_invalid_or_ambiguous_jobs(job):
    segment = AutomationSegment(joblist=(job,))
    with pytest.raises(TypeError, match="exactly one job category"):
        segment.classify_jobs()
