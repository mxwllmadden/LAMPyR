# -*- coding: utf-8 -*-
"""
Created on Tue Jun 10 13:10:25 2025

@author: mm4114
"""
import time
import random
from typing import Literal, List, Tuple

from lampyr.segments import Trial, Task
from lampyr.segments.paradigm import Stage
from dataclasses import dataclass, field


def event_waterreward(self: Trial):
    self.log_debug('Sending give reward command to rig')
    self.rig.reward.give()
    self.log_reward()

def event_trialstart(self: Trial):
    self.log_debug('Sending play trial tone command to rig')
    self.rig.play.begintrialtone()


@dataclass
class HabituationTrial(Trial):
    iti1_dur: float = 1
    reward_consumption_period_s: Tuple[int] = 15
    reward_consumption_nolick_delay_s: float = 40
    iti2_dur: float = 0.5

    def setup(self):
        self.register_event('reward',
                            callback=event_waterreward,
                            description='Water reward given')

    def loop(self):
        # Start behavior
        time.sleep(self.iti1_dur)
        self.trigger_event('reward')
        self.loop_consumption()
        time.sleep(self.iti2_dur)
        self.finish()

    def loop_consumption(self):
        slick = time.time()
        licked = False
        while time.time() - slick < self.reward_consumption_period_s:
            if self.rig.licks.since(slick) and licked is False:
                licked = True
            time.sleep(0.01)
        if licked == False:
            while time.time() - slick < self.reward_consumption_nolick_delay_s:
                if self.rig.licks.since(slick) and licked is False:
                    licked = True
                time.sleep(0.01)
        self.create_report('reward_consumed', licked)
        self.log_notice(f'Detected {self.rig.licks.since(slick)} licks')
        if licked:
            self.log_merit()
        else:
            self.log_abstention()

@dataclass
class RewardedHabituationTask(Task):
    slug: str = 'RewHab'

    def setup(self):
        pass

    def loop(self):
        trial = HabituationTrial(parent=self,
                                 iti1_dur=1,
                                 reward_consumption_period_s=8,
                                 reward_consumption_nolick_delay_s = 40,
                                 iti2_dur=random.randint(4, 12))
        trial.run()
        del trial

@dataclass
class HabituationStage(Stage):
    slug: str = 'Stage0'

    def define_sessionparams(self):
        self.set_sessionparam('duration_limit', 60)
        self.set_sessionparam('serial_abstention_limit', 10)
        self.set_sessionparam('reward_limit', 200)

    def define_task(self):
        task = RewardedHabituationTask(parent=self)
        task.run()
        del task

    def define_shaping(self):
        pass
