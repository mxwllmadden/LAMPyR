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
    count_merits: bool = False
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
            if self.count_merits:
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
                                 iti2_dur=random.randint(4, 12),
                                 count_merits=True)
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


@dataclass
class BanditTrial(Trial):
    iti_1_dur: float = 1
    pretrial_hold_dur: float = 2
    pretrial_movement_threshold: float = 5
    trial_responsewindow_s: float = 3
    trial_responsethresholds_deg: dict = field(default_factory=lambda: {'Left': 15,
                                                                        'Right': 15})
    trial_rewardprobs_perc: dict = field(default_factory=lambda: {'Left': 100,
                                                                   'Right': 100,
                                                                   'None': 0})
    reward_delay_s: float = 1
    iti2_dur: float = 2.5

    def setup(self):
        self.register_event('reward',
                            callback=event_waterreward,
                            description='Water reward given')
        self.register_event('trialstart',
                            callback=event_trialstart,
                            description='Trial begins. Start tone played.')
        self.register_event('pretrialstart',
                            description='beginning of pretrial period')
        self.register_event('response',
                            description='Wheel response registered')
        self._trialstage = 'iti1'
        self.log_debug(self.trial_rewardprobs_perc)

    def loop(self):
        time.sleep(0.1)
        match self._trialstage:
            case 'iti1':
                time.sleep(self.iti_1_dur)
                self._tstagestart = self.trigger_event('pretrialstart')
                self._trialstage = 'pretrial'
            case 'pretrial':
                self.loop_pretrial()
            case 'trial':
                self.loop_trial()
            case 'iti2':
                time.sleep(self.iti2_dur)
                self.finish()

    def loop_pretrial(self):
        if time.time() - self._tstagestart < self.pretrial_hold_dur:
            return
        last2seconds = time.time() - self.pretrial_hold_dur
        movement = self.rig.wheel.movement_components_since(last2seconds)
        dist = sum([abs(x) for x in movement])
        if dist < self.pretrial_movement_threshold:
            self._tstagestart = self.trigger_event('trialstart')
            self._trialstage = 'trial'
            self.log_info('Beginning bandit trial!')
        else:
            self.log_info('Animal movement detected. Waiting for cessation.', delay=4)

    def loop_trial(self):
        wheel_movement = self.rig.wheel.movement_since(self._tstagestart)
        response = None

        if wheel_movement < 0 and abs(wheel_movement) > self.trial_responsethresholds_deg['Left']:
            self.trigger_event('response', direction='Left')
            response = 'Left'
        elif wheel_movement > 0 and abs(wheel_movement) > self.trial_responsethresholds_deg['Right']:
            self.trigger_event('response', direction='Right')
            response = 'Right'
        elif response is None and time.time() - self._tstagestart > self.trial_responsewindow_s:
            response = 'None'
        else:
            return

        self.create_report('response', response)
        self.log_info(f'Detected response: {response}')
        self.create_report('response_delay', time.time() - self._tstagestart)

        highestrewardprob = max(self.trial_rewardprobs_perc.values())
        if self.trial_rewardprobs_perc[response] == highestrewardprob:
            self.create_report('best_response', True)
            self.log_merit()
        else:
            if response == 'None':
                self.log_abstention()
            else:
                self.log_demerit()
            self.create_report('best_response', False)

        probability = self.trial_rewardprobs_perc[response] / 100
        rand = random.random()
        self.log_debug(f'RAND:{rand},THRESH:{probability}')
        if rand < probability:
            self.trigger_event('reward')
            time.sleep(self.reward_delay_s)
            self.create_report('rewarded', True)
        else:
            self.create_report('rewarded', False)

        self._trialstage = 'iti2'

    def satisfies_condition(self, counttype: str) -> bool:
        match counttype:
            case 'Reward':
                return bool(self.reports['rewarded'])
            case 'Merit':
                return bool(self.reports['best_response'])
            case 'RewardedMerit':
                return bool(self.reports['rewarded']) and bool(self.reports['best_response'])


@dataclass
class BanditTask(Task):
    target_mode: Literal['Random', 'Any', 'Left', 'Right'] = 'Random'
    reward_prob_target: int = 80
    reward_prob_offtarget: int = 20
    reward_delay_s: float = 1
    rescue_trial_enabled: bool = False
    rescue_limit: int = 3
    rescue_cooldown: int = 2
    rescue_threshold: int = 12
    taskblocks_enabled: bool = True
    taskblocks_sizerange: tuple = (6, 15)
    taskblocks_blockcounttype: Literal['Reward', 'Merit', 'RewardedMerit'] = 'Reward'
    taskblocks_consecutivecounttype: Literal['Reward', 'Merit', 'RewardedMerit'] = 'Merit'
    taskblocks_minimumconsecutivecount: int = -1

    random_target_probs_enabled: bool = False
    random_target_probs_targets: List[int] = field(default_factory=lambda: [80, 90, 100])
    random_target_probs_offtargets: List[int] = field(default_factory=lambda: [0, 10, 20])
    random_target_probs_probability_of_nulltrialblock: int = 15

    def setup(self):
        match self.target_mode:
            case 'Random':
                self._target = random.choice(['Left', 'Right'])
            case _:
                self._target = self.target_mode
        self.rescue_count = 0
        self.rescue_sincelast = 999
        self.taskblock_reset()

    def taskblock_reset(self):
        if self.random_target_probs_enabled:
            self.randomize_target_probs()
        self._reward_probs = {
            'Left':  {'Left': self.reward_prob_target,   'Right': self.reward_prob_offtarget, 'None': 0},
            'Right': {'Left': self.reward_prob_offtarget, 'Right': self.reward_prob_target,   'None': 0},
            'Any':   {'Left': self.reward_prob_target,   'Right': self.reward_prob_target,    'None': 0},
        }
        self.taskblocks_count = 0
        self.taskblocks_countconsecutive = 0
        self.taskblocks_currentsize = random.randint(*self.taskblocks_sizerange)
        self.log_notice('Switching taskblocks')
        self.log_info(f'New target is {self._target}')
        self.log_info(f'Target reward is {self.reward_prob_target}%')
        self.log_info(f'Off-target reward is {self.reward_prob_offtarget}%')

    def randomize_target_probs(self):
        if random.random() < (self.random_target_probs_probability_of_nulltrialblock / 100):
            self.log_notice('Starting null taskblock')
            self.reward_prob_offtarget = 50
            self.reward_prob_target = 50
        else:
            self.reward_prob_offtarget = random.choice(self.random_target_probs_offtargets)
            self.reward_prob_target = random.choice(self.random_target_probs_targets)

    def taskblock_next(self):
        match self._target:
            case 'Left':
                self._target = 'Right'
            case 'Right':
                self._target = 'Left'
            case 'Any':
                self._target = 'Any'
        self.taskblock_reset()

    def _update_block_count(self, trial: BanditTrial, trial_type: str) -> None:
        if trial_type != 'Bandit':
            return
        if not {'response', 'best_response', 'rewarded'}.issubset(trial.reports):
            return
        if trial.reports['response'] == 'None':
            return
        if trial.satisfies_condition(self.taskblocks_blockcounttype):
            self.taskblocks_count += 1
        if trial.satisfies_condition(self.taskblocks_consecutivecounttype):
            self.taskblocks_countconsecutive += 1
        else:
            self.taskblocks_countconsecutive = 0

    def loop(self):
        trial_type = 'Bandit'
        if self.rescue_trial_enabled:
            if (self.session.serial_abstention >= self.rescue_threshold and
                    self.rescue_sincelast >= self.rescue_cooldown and
                    self.rescue_count < self.rescue_limit):
                trial_type = 'Rescue'

        if self.taskblocks_enabled:
            if (self.taskblocks_count >= self.taskblocks_currentsize and
                    self.taskblocks_countconsecutive >= self.taskblocks_minimumconsecutivecount):
                self.taskblock_next()

        match trial_type:
            case 'Bandit':
                trial = BanditTrial(parent=self,
                                    reward_delay_s=self.reward_delay_s,
                                    trial_rewardprobs_perc=self._reward_probs[self._target])
                self.rescue_sincelast += 1
            case 'Rescue':
                self.log_notice('Attempting to rescue participation with a rescue trial.')
                trial = HabituationTrial(parent=self,
                                         slug='Rescue',
                                         iti1_dur=80,
                                         reward_consumption_period_s=40,
                                         reward_consumption_nolick_delay_s=40,
                                         iti2_dur=0.5)
                self.rescue_sincelast = 0
                self.rescue_count += 1

        trial.run()
        self._update_block_count(trial, trial_type)
        del trial


def report_count(triallist, segmentlist, report):
    reportcounts = {}
    for trial_id in triallist:
        trial = segmentlist[trial_id]
        val = trial['reports'].get(report)
        if val not in reportcounts:
            reportcounts[val] = 0
        reportcounts[val] += 1
    return reportcounts


@dataclass
class ResponseAbstractStage(Stage):
    slug: str = 'ResponseAbstractStage'

    def define_sessionparams(self):
        self.set_sessionparam('duration_limit', 60)
        self.set_sessionparam('serial_abstention_limit', 15)
        self.set_sessionparam('reward_limit', 200)

    def define_shaping(self):
        self.sessionsummary()

    def sessionsummary(self):
        trials = self.session.search(slug='BanditTrial', type='Trial')
        responsecounts = report_count(trials, self.session.segments, 'response')
        for resp, num in responsecounts.items():
            self.log_notice(f'Detected {num} {resp} responses.')
        resp_r = responsecounts.get('Right', 0)
        resp_l = responsecounts.get('Left', 0)
        if resp_r + resp_l == 0:
            self.log_notice('Sidebias could not be calculated due to no responses.')
        else:
            sb_metric = (resp_r - resp_l) / (resp_l + resp_r)
            sb_perc = (sb_metric * 50) + 50
            self.log_notice(f'Sidebias was: {round(sb_metric, 2)} ({round(sb_perc)}% Right)')


@dataclass
class AnyWheelStage(ResponseAbstractStage):
    slug: str = 'AnyWheel'

    def define_task(self):
        task = BanditTask(parent=self,
                          target_mode='Any',
                          reward_prob_target=100,
                          reward_prob_offtarget=0,
                          reward_delay_s=0,
                          rescue_trial_enabled=True,
                          taskblocks_enabled=False)
        task.run()
        del task


@dataclass
class AltWheelStage(ResponseAbstractStage):
    slug: str = 'AltWheel'

    def define_task(self):
        task = BanditTask(parent=self,
                          reward_prob_target=100,
                          reward_prob_offtarget=0,
                          rescue_trial_enabled=True)
        task.run()
        del task


@dataclass
class BanditTrainingStage(ResponseAbstractStage):
    slug: str = 'BanditTraining'
    _task: object = None

    def define_task(self):
        task = BanditTask(parent=self,
                          rescue_trial_enabled=True)
        task.run()
        self._task = task


@dataclass
class RandomBanditStage(ResponseAbstractStage):
    slug: str = 'RandomBandit'
    _task: object = None

    def define_task(self):
        task = BanditTask(parent=self,
                          rescue_trial_enabled=False,
                          taskblocks_blockcounttype='RewardedMerit',
                          taskblocks_consecutivecounttype='Merit',
                          taskblocks_minimumconsecutivecount=3,
                          random_target_probs_enabled=True)
        task.run()
        self._task = task


@dataclass
class BanditEndStage(ResponseAbstractStage):
    slug: str = 'Bandit'

    def define_task(self):
        task = BanditTask(parent=self,
                          rescue_trial_enabled=False)
        task.run()
        del task


if __name__ == '__main__':
    from lampyr.rigcontrol import ArduinoBanditRig_0
    from lampyr.primatives import Session
    rig = ArduinoBanditRig_0()
    session = Session(trial_limit=2)
    try:
        rig.listen()
        t = AltWheelStage(session=session,
                          rig=rig,
                          _verbose=True)
        t.run()
    finally:
        rig.abort()
        rig.close()
