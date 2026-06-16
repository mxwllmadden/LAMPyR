# -*- coding: utf-8 -*-
"""
Session plotting helpers.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import lru_cache

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


class AbstractPlot(ABC):
    extractor_name = None

    def __init__(self, query, record_store, **settings):
        self.query = query
        self.record_store = record_store
        self.settings = settings

    def sessions(self):
        return self.query.objects()

    def records(self):
        if self.extractor_name is None:
            raise ValueError("Plot subclasses must define extractor_name.")

        return [
            self.record_store.get(self.extractor_name, session)
            for session in self.sessions()
        ]

    def groupby(self, key):
        groups = {}

        for record in self.records():
            group_key = key(record) if callable(key) else record[key]
            groups.setdefault(group_key, []).append(record)

        return groups

    @abstractmethod
    def plot(self, ax=None):
        if ax is None:
            _, ax = plt.subplots()
        return ax


class RecordExtractor(ABC):
    name = None

    @abstractmethod
    def build(self, session):
        pass


class RecordStore:
    def __init__(self):
        self.extractors = {}
        self.cache = {}

    def register(self, extractor):
        if extractor.name is None:
            raise ValueError("Extractor must define a name.")
        self.extractors[extractor.name] = extractor

    def get(self, extractor_name, session):
        if extractor_name not in self.extractors:
            raise KeyError(f"Unknown extractor: {extractor_name}")

        sessionid = self._sessionid(session)
        key = (extractor_name, sessionid)

        if key not in self.cache:
            self.cache[key] = self.extractors[extractor_name].build(session)

        return self.cache[key]

    @staticmethod
    def _sessionid(session):
        for attr in ("sessionid", "uniquesessionid", "id"):
            value = getattr(session, attr, None)
            if value not in (None, ""):
                return value
        raise AttributeError("Could not determine session id for cache key.")


class BasicSessionRecord(RecordExtractor):
    name = "basic_session"

    def build(self, session):
        return {
            "mouseid": getattr(session, "mouseid", None),
            "sessionid": RecordStore._sessionid(session),
            "starttime": getattr(session, "starttime", None),
            "duration": getattr(session, "duration", None),
            "participation": getattr(session, "participation", None),
            "rewards": getattr(session, "rewards", None),
        }


class ParticipationByMousePlot(AbstractPlot):
    extractor_name = "basic_session"

    def plot(self, ax=None):
        ax = super().plot(ax=ax)
        groups = self.groupby("mouseid")
        labels = []
        means = []

        for mouseid, records in groups.items():
            labels.append(mouseid)
            means.append(
                sum(record["participation"] for record in records) / len(records)
            )

        ax.bar(labels, means)
        ax.set_ylabel("Mean participation")
        ax.set_xlabel("Mouse")
        ax.set_title("Participation by Mouse")
        ax.tick_params(axis="x", rotation=45)
        return ax


BANDIT_STAGE_ORDER = [
    "Stage0Hab",
    "Stage1AnyWheel",
    "Stage2Correction",
    "Stage3Return",
    "Stage4AltWheelDelay",
    "Stage5BanditTraining",
    "Stage6Bandit",
]

STAGE_LABELS = {
    "Stage0Hab": "Habituation",
    "Stage1AnyWheel": "Any Wheel",
    "Stage2Correction": "Bias Correction",
    "Stage3Return": "Bias Return",
    "Stage4AltWheelDelay": "Delay Intro",
    "Stage5BanditTraining": "Bandit Training",
    "Stage6Bandit": "Bandit",
    "Unknown": "Unknown",
}

STAGE_COLORS = {
    "Stage0Hab": "#E74C3C",
    "Stage1AnyWheel": "#FF8C00",
    "Stage2Correction": "#A89A2E",
    "Stage3Return": "#F4E01A",
    "Stage4AltWheelDelay": "#27AE60",
    "Stage5BanditTraining": "#2980B9",
    "Stage6Bandit": "#8E44AD",
    "Unknown": "#95A5A6",
}

ALL_STAGE_KEYS = BANDIT_STAGE_ORDER + ["Unknown"]

WEIGHT_LOG_PATH = r"N:\SHARED\Maxwell_Lampyr_MouseData\WaterRestrictionLogs.xlsx"


@lru_cache(maxsize=1)
def load_weight_lookup():
    """
    Load weight data once and store it in a dict keyed by (date, mouseid).
    """
    df = pd.read_excel(
        WEIGHT_LOG_PATH,
        sheet_name="DataEntry",
        header=0,
        usecols=[0, 2, 3],
    )
    df.columns = ["date", "animal", "weight"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["animal"] = df["animal"].astype(str).str.strip()
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df = df.dropna(subset=["date", "animal", "weight"])
    df = df[df["animal"].str.len() > 0]
    df["date"] = df["date"].dt.normalize()

    return {
        (row["date"], row["animal"]): float(row["weight"])
        for _, row in df.iterrows()
    }


@lru_cache(maxsize=1)
def load_baseline_weight_lookup():
    """
    Load baseline (free-feeding) weights once and store them by mouseid.
    """
    df = pd.read_excel(
        WEIGHT_LOG_PATH,
        sheet_name="80% Weights",
        header=0,
        usecols=[0, 1],
    )
    df.columns = ["animal", "weight_80pct"]
    df["animal"] = df["animal"].astype(str).str.strip()
    df["weight_80pct"] = pd.to_numeric(df["weight_80pct"], errors="coerce")
    df = df.dropna()

    return {
        row["animal"]: float(row["weight_80pct"]) / 0.80
        for _, row in df.iterrows()
    }


def get_weight(mouseid, date):
    if mouseid in (None, "") or date is None:
        return None
    return load_weight_lookup().get((pd.Timestamp(date), str(mouseid).strip()))


def get_baseline_weight(mouseid):
    if mouseid in (None, ""):
        return None
    return load_baseline_weight_lookup().get(str(mouseid).strip())


def missing_weight(mouseid, date):
    """
    Placeholder weight lookup.

    Replace this with a function that returns the weight for the supplied mouse
    and date.
    """
    return None


def missing_baseline_weight(mouseid):
    """
    Placeholder baseline-weight lookup.
    """
    return None


class ReportCardRecord(RecordExtractor):
    name = "report_card"

    def __init__(self,
                 weight_provider=None,
                 baseline_weight_provider=None):
        self.weight_provider = weight_provider or get_weight
        self.baseline_weight_provider = (
            baseline_weight_provider or get_baseline_weight
        )

    def build(self, session):
        mouseid = getattr(session, "mouseid", None)
        starttime = getattr(session, "starttime", None)
        date = self._date_from_starttime(starttime)
        weight = self.weight_provider(mouseid, date)
        baseline_weight = self.baseline_weight_provider(mouseid)

        return {
            "mouseid": mouseid,
            "sessionid": RecordStore._sessionid(session),
            "starttime": starttime,
            "date": date,
            "stage": self._stage(session),
            "duration": getattr(session, "duration", None),
            "trials": getattr(session, "trial", None),
            "participation": getattr(session, "participation", None),
            "weight": weight,
            "baseline_weight": baseline_weight,
        }

    @staticmethod
    def _date_from_starttime(starttime):
        if starttime in (None, ""):
            return None

        try:
            return datetime.fromtimestamp(float(starttime)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _stage(session):
        try:
            root = session.root
            first_subsegment = session.segments[session.root]["subdata"][0]
            stage = session.segments[first_subsegment]["slug"]
            if isinstance(stage, str) and stage:
                return stage
        except (AttributeError, KeyError, IndexError, TypeError):
            pass
        return "Unknown"


class ColonyReportCardPlot(AbstractPlot):
    extractor_name = "report_card"

    def plot(self, ax=None):
        records = [
            record for record in self.records()
            if record["date"] is not None
        ]

        if not records:
            fig, axes = plt.subplots(2, 2, figsize=(16, 9), sharex=True)
            fig.suptitle("No sessions found")
            return fig, axes

        records.sort(key=lambda record: record["date"])
        mice = sorted({record["mouseid"] for record in records})
        dates = sorted({record["date"] for record in records})

        start_date = dates[0]
        end_date = dates[-1]
        n_days = (end_date - start_date).days + 1
        all_dates = [start_date + timedelta(days=i) for i in range(n_days)]

        fig, axes = plt.subplots(2, 2, figsize=(16, 9), sharex=True)

        self._plot_stage_progression(axes[0, 0], mice, all_dates, records)
        self._plot_engagement(axes[0, 1], mice, records)
        self._plot_weight(axes[1, 0], mice, records)
        self._plot_percentile_weight(axes[1, 1], mice, records)

        for subplot in axes.flat:
            subplot.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
            subplot.tick_params(axis="x", rotation=45, labelbottom=True)

        fig.tight_layout()
        return fig, axes

    def _plot_stage_progression(self, ax, mice, all_dates, records):
        latest_stage = {}

        for record in records:
            latest_stage[(record["mouseid"], record["date"])] = record["stage"]

        color_matrix = np.zeros((len(mice), len(all_dates), 4))
        color_matrix[:, :, 3] = 1.0

        for i, mouseid in enumerate(mice):
            for j, date in enumerate(all_dates):
                stage = latest_stage.get((mouseid, date))
                if isinstance(stage, str):
                    color_matrix[i, j] = mcolors.to_rgba(
                        STAGE_COLORS.get(stage, STAGE_COLORS["Unknown"])
                    )

        date_nums = mdates.date2num(all_dates)
        extent = [date_nums[0] - 0.5, date_nums[-1] + 0.5, len(mice) - 0.5, -0.5]
        ax.imshow(color_matrix, aspect="auto", interpolation="none", extent=extent)
        ax.set_yticks(range(len(mice)))
        ax.set_yticklabels(mice, fontsize=10)
        ax.set_title("Stage Progression", fontsize=12)

        present = [stage for stage in ALL_STAGE_KEYS if any(
            record["stage"] == stage for record in records
        )]
        ax.legend(
            handles=[
                Patch(facecolor=STAGE_COLORS[stage], label=STAGE_LABELS[stage])
                for stage in present
            ],
            loc="upper left",
            bbox_to_anchor=(1.01, 1),
            fontsize=9,
            borderaxespad=0,
        )

    def _plot_engagement(self, ax, mice, records):
        grouped = self._group_records_by_mouse_and_date(records)

        for mouseid in mice:
            rows = []

            for date, day_records in grouped.get(mouseid, {}).items():
                participation = sum(
                    record["participation"] or 0 for record in day_records
                )
                trials = sum(record["trials"] or 0 for record in day_records)

                if trials > 0:
                    rows.append((date, participation / trials))

            if not rows:
                continue

            rows.sort(key=lambda item: item[0])
            xs = [item[0] for item in rows]
            ys = [item[1] for item in rows]
            line, = ax.plot(xs, ys, marker="o", markersize=4, linewidth=1)
            ax.text(xs[-1], ys[-1], f"  {mouseid}", fontsize=10,
                    va="center", color=line.get_color())

        ax.set_title("Engagement", fontsize=12)
        ax.set_ylabel("Participation / Trials", fontsize=10)
        ax.set_ylim(0, 1.05)

    def _plot_weight(self, ax, mice, records):
        grouped = self._group_records_by_mouse(records)

        for mouseid in mice:
            rows = [
                (record["date"], record["weight"])
                for record in grouped.get(mouseid, [])
                if record["weight"] is not None
            ]

            if not rows:
                continue

            rows.sort(key=lambda item: item[0])
            xs = [item[0] for item in rows]
            ys = [item[1] for item in rows]
            line, = ax.plot(xs, ys, marker="o", markersize=4, linewidth=1)
            ax.text(xs[-1], ys[-1], f"  {mouseid}", fontsize=10,
                    va="center", color=line.get_color())

        ax.set_title("Weight", fontsize=12)
        ax.set_ylabel("Weight (g)", fontsize=10)
        ax.set_xlabel("Date", fontsize=10)

    def _plot_percentile_weight(self, ax, mice, records):
        grouped = self._group_records_by_mouse(records)

        for mouseid in mice:
            rows = []

            for record in grouped.get(mouseid, []):
                weight = record["weight"]
                baseline_weight = record["baseline_weight"]

                if weight is None or baseline_weight in (None, 0):
                    continue

                rows.append((record["date"], (weight / baseline_weight) * 100))

            if not rows:
                continue

            rows.sort(key=lambda item: item[0])
            xs = [item[0] for item in rows]
            ys = [item[1] for item in rows]
            line, = ax.plot(xs, ys, marker="o", markersize=4, linewidth=1)
            ax.text(xs[-1], ys[-1], f"  {mouseid}", fontsize=10,
                    va="center", color=line.get_color())

        ax.axhline(80, color="red", linestyle="--", linewidth=1, alpha=0.7)
        ax.set_title("Percentile Weight", fontsize=12)
        ax.set_ylabel("% of Baseline Weight", fontsize=10)
        ax.set_xlabel("Date", fontsize=10)

    @staticmethod
    def _group_records_by_mouse(records):
        groups = {}

        for record in records:
            groups.setdefault(record["mouseid"], []).append(record)

        return groups

    @staticmethod
    def _group_records_by_mouse_and_date(records):
        groups = {}

        for record in records:
            groups.setdefault(record["mouseid"], {})
            groups[record["mouseid"]].setdefault(record["date"], [])
            groups[record["mouseid"]][record["date"]].append(record)

        return groups
