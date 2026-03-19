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
    iti1_dur: float = 5
    reward_delay_s: float = 1
    reward_consumption_period_s: Tuple[int] = (10,20)
    reward_consumption_nolick_delay_s: float = 40
    iti2_dur: float = 0.5

    def setup(self):
        self.register_event('trialstart',
                            #callback=event_trialstart, #No callback for hab trial because trialstart is not signed
                            description='Beginning of trial')
        self.register_event('reward',
                            callback=event_waterreward,
                            description='Water reward given')

    def loop(self):
        # Start behavior
        time.sleep(self.iti_1_dur)
        self.trigger_event('trialstart')
        time.sleep(self.reward_delay_s)
        self.trigger_event('reward')
        self.loop_consumption()
        time.sleep(self.iti2_dur)
        self.finish()

    def loop_consumption(self):
        slick = time.time()
        licked = False
        consumption_period = random.randint(*self.reward_consumption_period_s)
        while time.time() - slick < consumption_period:
            if self.rig.licks.since(slick) and licked is False:
                licked = True
            if licked is True and time.time() - slick > consumption_period:
                break
            if time.time() - slick > self.reward_consumption_nolick_delay_s:
                break
            time.sleep(0.01)
        self.create_report('reward_consumed', licked)
        self.log_notice(f'Detected {self.rig.licks.since(slick)} licks')
        if licked:
            self.log_merit()
        else:
            self.log_abstention()

@dataclass
class HabituationStage(Stage):
    slug: str = 'Stage0'

    def define_sessionparams(self):
        self.set_sessionparam('duration_limit', 60)
        self.set_sessionparam('serial_abstention_limit', 15)
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
                                                                        'Right': 15}
                                               )
    trial_rewardprobs_perc: dict = field(default_factory=lambda: {'Left': 100,
                                                                  'Right': 100,
                                                                  'None': 0}
                                         )
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
            self.log_info('Animal movement detected. Waiting for cecassion.',
                          delay=4)

    def loop_trial(self):
        wheel_movement = self.rig.wheel.movement_since(self._tstagestart)
        response = False

        # Check for responses
        if wheel_movement < 0 and abs(wheel_movement) > self.trial_responsethresholds_deg['Left']:
            self.trigger_event('response', direction='Left')
            response = 'Left'
        elif wheel_movement > 0 and abs(wheel_movement) > self.trial_responsethresholds_deg['Right']:
            self.trigger_event('response', direction='Right')
            response = 'Right'
        elif response is False and time.time() - self._tstagestart > self.trial_responsewindow_s:
            response = 'None'
        else:
            return

        # Report the reponse
        self.create_report('response', response)
        self.log_info(f'Detected response: {response}')
        self.create_report('response_delay', time.time() - self._tstagestart)
        highestrewardprob = max(
            [prob for prob in self.trial_rewardprobs_perc.values()])
        if self.trial_rewardprobs_perc[response] == highestrewardprob:
            self.create_report('best_response', True)
            self.log_merit()
        else:
            if response == 'None':
                self.log_abstention()
            else:
                self.log_demerit()
            self.create_report('best_response', False)

        # Determine probability of reward and deliver reward
        probability = self.trial_rewardprobs_perc[response]/100
        rand = random.random()
        self.log_debug(f'RAND:{rand},THRESH:{probability}')
        if rand < probability:
            self.trigger_event('rewardtone')
            time.sleep(self.reward_delay_s)
            self.trigger_event('reward')
            self.create_report('rewarded', True)
        else:
            self.create_report('rewarded', False)

        self._trialstage = 'iti2'


@dataclass
class BanditTask(Task):
    target_mode: Literal['Random', 'Any', 'Left', 'Right'] = 'Random'
    reward_prob_target: int = 80
    reward_prob_offtarget: int = 20

    rescue_trial_enabled: bool = False
    rescue_limit: int = 3
    rescue_cooldown: int = 2
    rescue_threshold: int = 12

    taskblocks_enabled: bool = True
    taskblocks_sizerange: tuple = (6, 15)
    taskblocks_blockcounttype: Literal['Reward', 'Merit', 'RewardedMerit'] = 'Reward'
    taskblocks_consecutivecounttype: Literal['Reward', 'Merit', 'RewardedMerit'] = 'Merit'
    taskblocks_minimumconsecutivecount: int = -1
    
    random_target_probs_enabled:bool = False
    random_target_probs_targets: List[int] = field(default_factory = lambda : [80,90,100])
    random_target_probs_offtargets: List[int] = field(default_factory = lambda: [0,10,20])
    random_target_probs_probability_of_nulltrialblock: int = 15

    def setup(self):
        match self.target_mode:
            case 'Random':
                self._target = random.choice(['Left', 'Right'])
            case _:
                self._target = self.target_mode
        # rescues
        self.rescue_count = 0
        self.rescue_sincelast = 999
        # taskblocks
        self.taskblock_reset()

    def taskblock_reset(self):
        if self.random_target_probs_enabled:
            self.randomize_target_probs()
        self._targetrewardprobabilityselection = {'Left': {'Left': self.reward_prob_target,
                                                           'Right': self.reward_prob_offtarget,
                                                           'None': 0},
                                                  'Right': {'Left': self.reward_prob_offtarget,
                                                            'Right': self.reward_prob_target,
                                                            'None': 0},
                                                  'Any': {'Left': self.reward_prob_target,
                                                          'Right': self.reward_prob_target,
                                                          'None': 0},
                                                  }
        self.taskblocks_count = 0
        self.taskblocks_countconsecutive = 0
        self.taskblocks_currentsize = random.randint(
            *self.taskblocks_sizerange)
        
        self.log_notice('Switching taskblocks')
        self.log_info(f'New target is {self._target}')
        self.log_info(f'Target reward is {self.reward_prob_target}%')
        self.log_info(f'Off-target reward is {self.reward_prob_offtarget}%')
    
    def randomize_target_probs(self):
        if random.random() < (self.random_target_probs_probability_of_nulltrialblock/100):
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
        

    def loop(self):
        trial_type = 'Bandit'

        # Check if a rescue trial is needed
        if self.rescue_trial_enabled:
            if (self.session.serial_abstention >= self.rescue_threshold and
                self.rescue_sincelast >= self.rescue_cooldown and
                    self.rescue_count < self.rescue_limit):
                trial_type = 'Rescue'

        # Check if taskblock needs to be progressed
        if self.taskblocks_enabled:
            if self.taskblocks_count >= self.taskblocks_currentsize and \
                self.taskblocks_countconsecutive >= self.taskblocks_minimumconsecutivecount:
                self.log_debug((f'{self.taskblocks_count} >= '
                                f'{self.taskblocks_currentsize} '
                                f'{self.taskblocks_blockcounttype}s'
                                ))
                self.log_debug((f'{self.taskblocks_countconsecutive} >= '
                               f'{self.taskblocks_minimumconsecutivecount} '
                               f'consecutive {self.taskblocks_consecutivecounttype}s'))
                self.taskblock_next()

        match trial_type:
            case 'Bandit':
                trial = BanditTrial(parent=self,
                                    trial_rewardprobs_perc=self._targetrewardprobabilityselection[self._target])
                self.rescue_sincelast += 1
            case 'Rescue':
                self.log_notice('Attempting to rescue participation with a rescue trial.')
                trial = HabituationTrial(parent=self,
                                         slug='Rescue',
                                         iti_1_dur=80,
                                         reward_delay_s=1,
                                         reward_consumption_delay_min=20,
                                         reward_consumption_delay_max=40,
                                         iti2_dur=0.5)
                self.rescue_sincelast = 0
                self.rescue_count += 1

        trial.run()
        
        def checkiftrialsatistfiescondition(counttype, trial):
            match counttype:
                case 'Reward':
                    return bool(trial.reports['rewarded'])
                case 'Merit':
                    return bool(trial.reports['best_response'])
                case 'RewardedMerit':
                    return bool(trial.reports['rewarded']) and bool(trial.reports['best_response'])
        
        def blockcountupdate(trial):
            if trial_type != 'Bandit':
                return
            if not set(['response', 'best_response', 'rewarded']).issubset(
                    trial.reports):
                return
            if trial.reports['response'] == 'None':
                return
            #check if increment block counter
            if checkiftrialsatistfiescondition(self.taskblocks_blockcounttype, trial):
                self.taskblocks_count += 1
            if checkiftrialsatistfiescondition(self.taskblocks_consecutivecounttype, trial):
                self.taskblocks_countconsecutive += 1
            else:
                self.taskblocks_countconsecutive = 0
                
        blockcountupdate(trial)
        del trial


@dataclass
class RewardedHabituationTask(Task):
    slug: str = 'RewHab'

    def setup(self):
        pass

    def loop(self):
        trial = HabituationTrial(parent=self,
                                 iti_1_dur=random.randint(3, 6),
                                 reward_consumption_delay_min=3,
                                 reward_consumption_delay_max=30,
                                 iti2_dur=2)
        trial.run()
        del trial


@dataclass
class HabituationStage(Stage):
    slug: str = 'Stage0'

    def define_sessionparams(self):
        self.set_sessionparam('duration_limit', 60)
        self.set_sessionparam('serial_abstention_limit', 15)
        self.set_sessionparam('reward_limit', 150)

    def define_task(self):
        task = RewardedHabituationTask(parent=self)
        task.run()
        del task

    def define_shaping(self):
        pass
