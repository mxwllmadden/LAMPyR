# -*- coding: utf-8 -*-
"""
Created on Tue Jun 10 13:10:25 2025

@author: mm4114
"""
import time
import random
from copy import deepcopy
from typing import ClassVar, Literal, List, Tuple

from lampyr.segments import Trial, Task
from lampyr.segments.paradigm import Stage, Paradigm
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
        if self._paradigmdata is None or not session_valid(self):
            return
        p = self._paradigmdata['params']
        shaping = self._paradigmdata['shaping']['habituation']
        if self.session.merit >= p['hab_merit_threshold']:
            shaping['consecutive_good'] = shaping.get('consecutive_good', 0) + 1
            self.log_notice(f"Hab good session ({self.session.merit} merit). {shaping['consecutive_good']}/2")
        else:
            shaping['consecutive_good'] = 0
            self.log_notice(f"Hab below threshold ({self.session.merit} merit). Resetting counter.")
        if shaping['consecutive_good'] >= 2:
            self.mouse.paradigm_stage[self.paradigm_tag] = 'AnyWheel'
            self.log_notice("Advancing: Habituation → AnyWheel")


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
    rescue_cooldown: int = 20
    rescue_threshold: int = 15
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


def session_valid(stage, min_duration_min: float = 20.0) -> bool:
    """Returns False (and logs) if session was too short to count for shaping."""
    dur = stage.session.duration
    if dur is None or dur < min_duration_min:
        stage.log_notice(f'Session too short ({round(dur, 1) if dur is not None else None} min < {min_duration_min} min). Shaping skipped.')
        return False
    return True


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
        self.set_sessionparam('duration_min', 20)
        self.set_sessionparam('serial_abstention_limit', 30)
        self.set_sessionparam('reward_limit', 200)

    def define_shaping(self):
        self.sessionsummary()

    def _compute_sb_metric(self):
        """Returns (Right - Left) / (Right + Left), or None if no directional responses."""
        trials = []
        for child_id in self.subdata:
            trials.extend(self.session.search(root=child_id, slug='BanditTrial', type='Trial'))
        counts = report_count(trials, self.session.segments, 'response')
        resp_r = counts.get('Right', 0)
        resp_l = counts.get('Left', 0)
        if resp_r + resp_l == 0:
            return None
        return (resp_r - resp_l) / (resp_l + resp_r)

    def sessionsummary(self):
        """Log response counts and side bias. Returns sb_metric (float) or None."""
        trials = []
        for child_id in self.subdata:
            trials.extend(self.session.search(root=child_id, slug='BanditTrial', type='Trial'))
        responsecounts = report_count(trials, self.session.segments, 'response')
        for resp, num in responsecounts.items():
            self.log_notice(f'Detected {num} {resp} responses.')
        sb_metric = self._compute_sb_metric()
        if sb_metric is None:
            self.log_notice('Sidebias could not be calculated due to no responses.')
        else:
            sb_perc = (sb_metric * 50) + 50
            self.log_notice(f'Sidebias was: {round(sb_metric, 2)} ({round(sb_perc)}% Right)')
        return sb_metric


@dataclass
class AnyWheelStage(ResponseAbstractStage):
    slug: str = 'AnyWheel'
    
    def define_sessionparams(self):
        super().define_sessionparams()
        self.set_sessionparam('duration_min', 40)

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

    def define_shaping(self):
        super().define_shaping()
        if self._paradigmdata is None or not session_valid(self):
            return
        p = self._paradigmdata['params']
        shaping = self._paradigmdata['shaping']['anywheel']
        if self.session.participation >= p['anywheel_participation_threshold']:
            shaping['consecutive_good'] = shaping.get('consecutive_good', 0) + 1
            self.log_notice(f"AnyWheel good session ({self.session.participation} participation). {shaping['consecutive_good']}/{p['anywheel_consecutive']}")
        else:
            shaping['consecutive_good'] = 0
            self.log_notice(f"AnyWheel below threshold ({self.session.participation} participation). Resetting counter.")
        if shaping['consecutive_good'] >= p['anywheel_consecutive']:
            self.mouse.paradigm_stage[self.paradigm_tag] = 'AltWheel'
            self.log_notice("Advancing: AnyWheel → AltWheel")


@dataclass
class AltWheelStage(ResponseAbstractStage):
    slug: str = 'AltWheel'

    def define_task(self):
        task = BanditTask(parent=self,
                          reward_prob_target=100,
                          reward_prob_offtarget=0,
                          rescue_trial_enabled=True,
                          reward_delay_s=0)
        task.run()
        del task

    def define_shaping(self):
        sb = self.sessionsummary()
        if self._paradigmdata is None or not session_valid(self):
            return
        if sb is None:
            self.log_notice('Cannot shape thresholds: no responses.')
            return

        p = self._paradigmdata['params']
        aw = self._paradigmdata['shaping']['altwheel']
        phase = aw['phase']
        score = aw.get('adjustment_score', 0)

        if phase == 'complete':
            return  # NEVER adjust once complete

        N = p['threshold_normal']
        max_adj = p['max_adjustment']

        if phase == 'correction':
            prevailing = 1 if score > 0 else (-1 if score < 0 else 0)
            against_prevailing = prevailing != 0 and (
                (prevailing > 0 and sb < 0) or (prevailing < 0 and sb > 0)
            )
            is_equalized = abs(sb) < p['equalize_threshold'] or against_prevailing

            if is_equalized:
                aw['consecutive_equalized'] = aw.get('consecutive_equalized', 0) + 1
                self.log_notice(
                    f"Equalized ({aw['consecutive_equalized']}/{p['equalize_consecutive']})"
                )
                if aw['consecutive_equalized'] >= p['equalize_consecutive']:
                    aw['phase'] = 'return'
                    self.log_notice('Threshold correction complete → entering return phase.')
            else:
                aw['consecutive_equalized'] = 0
                if sb > 0:  # right-biased: increase score (makes right harder)
                    new_score = min(max_adj, score + p['correction_rate'])
                else:       # left-biased: decrease score (makes left harder)
                    new_score = max(-max_adj, score - p['correction_rate'])
                aw['adjustment_score'] = new_score
                lt = max(5, min(40, N - new_score))
                rt = max(5, min(40, N + new_score))
                self.log_notice(f"Adjusted score → {new_score} (L:{lt}° R:{rt}°)")

        elif phase == 'return':
            if score > 0:
                score = max(0, score - p['return_rate'])
            elif score < 0:
                score = min(0, score + p['return_rate'])
            aw['adjustment_score'] = score
            lt = max(5, min(40, N - score))
            rt = max(5, min(40, N + score))
            self.log_notice(f"Returning score → {score} (L:{lt}° R:{rt}°)")
            if score == 0:
                aw['phase'] = 'complete'
                self.log_notice('Score fully normalized. AltWheel shaping complete.')


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
class BanditEndStage(ResponseAbstractStage):
    slug: str = 'Bandit'

    def define_task(self):
        task = BanditTask(parent=self,
                          rescue_trial_enabled=False)
        task.run()
        del task


@dataclass
class AltWheelDelayStage(ResponseAbstractStage):
    slug: str = 'AltWheelDelay'

    def define_task(self):
        task = BanditTask(parent=self,
                          reward_prob_target=100,
                          reward_prob_offtarget=0,
                          rescue_trial_enabled=True,
                          reward_delay_s=0)  # overridden by BanditParadigm at runtime
        task.run()
        del task

    def define_shaping(self):
        self.sessionsummary()
        if self._paradigmdata is None or not session_valid(self):
            return
        p = self._paradigmdata['params']
        shaping = self._paradigmdata['shaping']['reward_delay']
        delay_steps = p['delay_steps']
        step = shaping['current_step']
        if self.session.merit >= p['delay_merit_threshold'] and step < len(delay_steps) - 1:
            shaping['current_step'] += 1
            new_delay = delay_steps[shaping['current_step']]
            self.log_notice(f"Merit {self.session.merit} >= {p['delay_merit_threshold']}. Advancing delay → {new_delay}s")
            if shaping['current_step'] == len(delay_steps) - 1:
                self.mouse.paradigm_stage[self.paradigm_tag] = 'BanditTraining'
                self.log_notice('Delay training complete. Advancing → BanditTraining.')
        else:
            self.log_notice(f"Merit {self.session.merit}. Delay stays at {delay_steps[step]}s")


@dataclass
class BanditParadigm(Paradigm):
    slug: str = 'bandit'
    paradigm_tag: str = 'BanditParadigm'
    DEFAULT_PROPERTIES: ClassVar[dict] = {
        'shaping': {
            'habituation': {'consecutive_good': 0},
            'anywheel':    {'consecutive_good': 0},
            'altwheel': {
                'phase': 'correction',
                'adjustment_score': 0,
                'consecutive_equalized': 0,
            },
            'reward_delay': {'current_step': 0},
        }
    }
    STAGES: ClassVar[list] = ['Habituation', 'AnyWheel', 'AltWheel', 'BanditTraining']
    DELAY_STEPS: ClassVar[list] = [0, 0.1, 0.25, 0.5, 0.75, 1.0]

    # Shaping rate parameters — dataclass fields, overridable per-instance
    threshold_normal: int = 15
    correction_rate: int = 5
    return_rate: int = 2
    equalize_threshold: float = 0.1
    equalize_consecutive: int = 2
    max_adjustment: int = 25
    hab_merit_threshold: int = 140
    anywheel_participation_threshold: int = 150
    anywheel_consecutive: int = 2
    delay_merit_threshold: int = 150

    def execute(self):
        super().execute()
        self._init_defaults()
        self._apply_shaping_overrides()
        self._run_stage()

    def _init_defaults(self):
        self._migrate_altwheel()
        self._deep_setdefaults(self._paradigmdata, self.DEFAULT_PROPERTIES)

    def _migrate_altwheel(self):
        aw = self._paradigmdata.get('shaping', {}).get('altwheel', {})
        if 'right_threshold' in aw and 'adjustment_score' not in aw:
            score = aw['right_threshold'] - self.threshold_normal
            aw['adjustment_score'] = score
            self.log_notice(f"Migrated altwheel thresholds → adjustment_score={score}")

    def _deep_setdefaults(self, target, defaults):
        for k, v in defaults.items():
            if k not in target:
                target[k] = deepcopy(v)
            elif isinstance(v, dict) and isinstance(target[k], dict):
                self._deep_setdefaults(target[k], v)

    def _apply_shaping_overrides(self):
        aw = self._paradigmdata['shaping']['altwheel']
        step = self._paradigmdata['shaping']['reward_delay']['current_step']
        delay = self.DELAY_STEPS[step]
        score = aw.get('adjustment_score', 0)
        N = self.threshold_normal
        lt = max(5, min(40, N - score))
        rt = max(5, min(40, N + score))
        overrides = {
            'trial_responsethresholds_deg': {
                'Left':  lt,
                'Right': rt,
            },
            'reward_delay_s': delay,
        }
        self.mouse.mouse_behav_param_overrides['BanditTrial'] = overrides
        self.log_notice(f"BanditTrial overrides: thresholds L:{lt}° R:{rt}° (score={score}), delay {delay}s")

    def _run_stage(self):
        stage_map = {
            'Habituation':    HabituationStage,
            'AnyWheel':       AnyWheelStage,
            'BanditTraining': BanditTrainingStage,
        }
        current = self.mouse.paradigm_stage.setdefault(self.paradigm_tag, 'Habituation')
        if current == 'AltWheel':
            aw_phase = self._paradigmdata['shaping']['altwheel']['phase']
            stage_cls = AltWheelStage if aw_phase != 'complete' else AltWheelDelayStage
        else:
            stage_cls = stage_map[current]
        self.log_notice(f"Running stage: {stage_cls.__name__} (current_stage='{current}')")
        stage = stage_cls(parent=self)
        stage.run()


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
