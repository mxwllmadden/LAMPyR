# -*- coding: utf-8 -*-
"""
Created on Tue Jun 24 11:33:55 2025

@author: mm4114
"""

from dataclasses import dataclass, field
import time
from copy import deepcopy
from typing import List
import random


def uniqueid(type, name=None):
    uid = f'{type}_'
    if name is not None:
        uid += f'{name}_'
    uid += f'created{round(time.time())}_{random.randint(0, 999999):06d}'
    return uid


@dataclass
class Mouse:
    mouseid: str = '014-000'
    mouse_behav_param_overrides: dict = field(default_factory=dict)
    paradigm: str = None
    paradigm_stage: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)
    history: List = field(default_factory=list)


@dataclass
class Session:
    # Session limits and minimums
    merit_limit: int = None
    merit_min: int = None
    merit: int = 0
    demerit_limit: int = None
    demerit_min: int = None
    demerit: int = 0
    duration_limit: int = None
    duration_min: int = None
    duration: float = None
    trial_limit: int = None
    trial_min: int = None
    trial: int = 0
    reward_limit: int = None
    reward_min: int = None
    rewards: int = 0
    abstention_limit: int = None
    abstention_min: int = None
    abstention: int = 0
    participation_limit: int = None
    participation_min: int = None
    participation: int = 0
    serial_abstention_limit: int = None
    serial_abstention_min: int = None
    serial_abstention: int = 0

    # General information
    starttime: float = field(default_factory=time.time)
    endtime: float = None
    uniquesessionid: str = field(default_factory=lambda: uniqueid('session'))

    # Mouseid
    mouseid: str = None
    mouseid_unique: str = None

    # Segment records
    root: str = None
    segmentlist: list = field(default_factory=list)
    segments: dict = field(default_factory=dict)

    # Session Events and rig data
    eventlist: List = field(default_factory=list)
    rigdata: dict = None

    def __setattr__(self, key, value):
        if hasattr(self, "endtime") and self.endtime is not None:
            raise RuntimeError(f"Cannot modify '{key}'; session is finalized.")
        super().__setattr__(key, value)

    def lock(self):
        self.endtime = time.time()

    def __repr__(self):
        fields = [
            ("merit", self.merit_min, self.merit_limit, self.merit),
            ("demerit", self.demerit_min, self.demerit_limit, self.demerit),
            ("duration", self.duration_min, self.duration_limit,
             0 if self.duration is None else round(self.duration, 2)),
            ("trial", self.trial_min, self.trial_limit, self.trial),
            ("reward", self.reward_min, self.reward_limit, self.rewards),
            ("abstention", self.abstention_min,
             self.abstention_limit, self.abstention),
            ("participation", self.participation_min,
             self.participation_limit, self.participation),
            ("serial_abstention", self.serial_abstention_min,
             self.serial_abstention_limit, self.serial_abstention),
        ]
        msg = ''
        for name, min_val, max_val, val in fields:
            msg += f"{name:22}: {str(val):6} (Min: {str(min_val):6} Max: {str(max_val):6})\n"
        msg += f"{'starttime':22}: {self.starttime}\n"
        msg += f"{'endtime':22}: {self.endtime}\n"
        msg += f"{'uniquesessionid':22}: {self.uniquesessionid}\n"
        msg += f"{'mouseid':22}: {self.mouseid}\n"
        msg += f"{'mouseid_unique':22}: {self.mouseid_unique}\n"
        return msg

    def search(self, root=None,
               type=None, types=None,
               slug=None, slugs=None,
               custom_checks_permissive=None,
               custom_checks_strict=None,
               sort=None, return_objects=False,
               filt = None,
               _seglist=None):
        if _seglist is None:
            _seglist = []
        if root is None:
            root = self.root
        segment = self.segments[root]

        custom_checks_permissive = custom_checks_permissive or {}
        custom_checks_strict = custom_checks_strict or {}

        def search_filter(singleton, multioption, target, strict=False):
            if singleton is None and multioption is None:
                return True
            if not isinstance(target, (list, tuple, set, dict)):
                target = [target]
            if singleton is not None:
                if singleton not in target:
                    return False
            if multioption is not None:
                for option in multioption:
                    if strict:
                        if option not in target:
                            return False
                    else:
                        if option in target:
                            return True
                if strict:
                    return True
                else:
                    return False
            return True

        valid = search_filter(type, types, segment['segment_type'])
        valid = valid and search_filter(slug, slugs, segment['slug'])
        for check, vals in custom_checks_permissive.items():
            if check not in segment:
                valid = False
                break
            valid = valid and search_filter(None, vals, segment[check],
                                            strict=False)
        for check, vals in custom_checks_strict.items():
            if check not in segment:
                valid = False
                break
            valid = valid and search_filter(None, vals, segment[check],
                                            strict=True)

        if valid:
            _seglist.append(root)
        for subseg in segment['subdata']:
            self.search(root = subseg,
                        type = type,
                        types = types,
                        slug = slug,
                        slugs = slugs,
                        custom_checks_permissive=custom_checks_permissive,
                        custom_checks_strict=custom_checks_strict,
                        _seglist=_seglist)
        if sort is not None:
            _seglist = sorted(_seglist, key=lambda x: self.segments[x][sort])
        if filt is not None:
            _seglist = [seg for seg in _seglist
                        if filt(self.segments[seg])]
        if return_objects:
            return [self.segments[seg] for seg in _seglist]
        return _seglist

    @property
    def segment_types(self):
        typs = set()
        for seg in self.segments.values():
            for typ in seg['segment_type']:
                typs.add(typ)
        return list(typs)

    def evaluatestopconditions(self):
        stops = []
        if self.endtime is None:
            self.duration = (time.time() - self.starttime) / 60
        duration = self.duration

        # Reward limits are privileged to avoid senarios where water restriction is broken
        if self.reward_limit is not None:
            if self.rewards >= self.reward_limit:
                stops.append('reward')

        # All minimum requirements must be met before limits are tested
        if self.trial_min is not None:
            if self.trial < self.trial_min:
                return stops
        if self.duration_min is not None:
            if duration < self.duration_min:
                return stops
        if self.participation_min is not None:
            if self.participation < self.participation_min:
                return stops
        if self.merit_min is not None:
            if self.merit < self.merit_min:
                return stops
        if self.demerit_min is not None:
            if self.demerit < self.demerit_min:
                return stops
        if self.abstention_min is not None:
            if self.abstention < self.abstention_min:
                return stops
        if self.serial_abstention_min is not None:
            if self.serial_abstention < self.serial_abstention_min:
                return stops

        # Test all limits and report reasons for stop
        if self.trial_limit is not None:
            if self.trial >= self.trial_limit:
                stops.append('trial')
        if self.duration_limit is not None:
            if duration >= self.duration_limit:
                stops.append('duration')
        if self.merit_limit is not None:
            if self.merit >= self.merit_limit:
                stops.append('merit')
        if self.demerit_limit is not None:
            if self.demerit >= self.demerit_limit:
                stops.append('demerit')
        if self.participation_limit is not None:
            if self.participation >= self.participation_limit:
                stops.append('participation')
        if self.abstention_limit is not None:
            if self.abstention >= self.abstention_limit:
                stops.append('abstention')
        if self.serial_abstention_limit is not None:
            if self.serial_abstention >= self.serial_abstention_limit:
                stops.append('serialabstention')
        return stops
