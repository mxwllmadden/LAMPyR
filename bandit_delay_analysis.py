# -*- coding: utf-8 -*-
"""
Analysis: Accuracy, merit, and side bias over reward_delay for all animals
in the bandit delay stage (Stage4AltWheelDelay).
"""

import sys
import warnings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from collections import defaultdict

sys.path.insert(0, 'N:/Maxwell/Lampyr')

from lampyr.analysis.colony import Colony


STAGE_SLUG = 'Stage4AltWheelDelay'


def get_session_reward_delay(session):
    """Extract reward_delay_s from BanditTrial segments."""
    trials = session.search(slug='BanditTrial')
    for tid in trials:
        seg = session.segments[tid]
        if 'reward_delay_s' in seg:
            return seg['reward_delay_s']
    # Fallback: try BanditTask
    tasks = session.search(slug='BanditTask')
    for tid in tasks:
        seg = session.segments[tid]
        if 'reward_delay_s' in seg:
            return seg['reward_delay_s']
    return None


def compute_side_bias(session):
    """Compute (Right - Left) / (Right + Left) from BanditTrial response reports."""
    trials = session.search(slug='BanditTrial', type='Trial')
    resp_r = 0
    resp_l = 0
    for tid in trials:
        seg = session.segments[tid]
        response = seg.get('reports', {}).get('response', None)
        if response == 'Right':
            resp_r += 1
        elif response == 'Left':
            resp_l += 1
    total = resp_r + resp_l
    if total == 0:
        return None
    return (resp_r - resp_l) / total


def session_has_stage(session, stage_slug):
    """Return True if the session contains a segment with the given slug."""
    return any(
        seg.get('slug') == stage_slug
        for seg in session.segments.values()
    )


def main():
    colony = Colony()
    mouseids, _ = colony.data.mouselist()
    mouseids = [m for m in mouseids if m != 'UNKNOWN_MOUSE']
    print(f'Found {len(mouseids)} mice: {mouseids}')

    # Collect per-animal data
    animal_data = defaultdict(list)

    for mouseid in mouseids:
        mouse = colony.data.loadmouse(mouseid)
        session_ids = [
            entry.get('sessionid') or entry.get('uniquesessionid')
            for entry in mouse.history
            if entry.get('sessionid') or entry.get('uniquesessionid')
        ]
        print(f'\n{mouseid}: {len(session_ids)} sessions in history')

        for sid in session_ids:
            try:
                session = colony.data.loadsession(sid, mouseid)
            except Exception as e:
                print(f'  Failed to load {sid}: {e}')
                continue

            if not session_has_stage(session, STAGE_SLUG):
                continue

            merit = session.merit
            participation = session.participation
            accuracy = merit / participation if participation > 0 else None
            side_bias = compute_side_bias(session)
            reward_delay = get_session_reward_delay(session)

            if reward_delay is None:
                print(f'  {sid}: no reward_delay found, skipping')
                continue

            animal_data[mouseid].append({
                'reward_delay': reward_delay,
                'merit': merit,
                'accuracy': accuracy,
                'side_bias': side_bias,
                'starttime': session.starttime,
            })
            acc_str = f'{accuracy:.3f}' if accuracy is not None else 'N/A'
            sb_str = f'{side_bias:.3f}' if side_bias is not None else 'N/A'
            print(f'  {sid}: delay={reward_delay}s  merit={merit}  '
                  f'acc={acc_str}  sb={sb_str}')

    if not animal_data:
        print('\nNo Stage4AltWheelDelay sessions found.')
        return

    # --- Plotting ---
    metrics = [
        ('accuracy', 'Accuracy (merit/participation)', (0, 1)),
        ('merit',    'Merit (correct responses)',       None),
        ('side_bias','Side Bias ((R-L)/(R+L))',         (-1, 1)),
    ]

    delay_ticks = [0.1, 0.25, 0.5, 1.0]
    animals = sorted(animal_data.keys())
    colors = cm.tab10(np.linspace(0, 0.9, len(animals)))

    fig, axes = plt.subplots(len(animals), 3,
                             figsize=(14, 4 * len(animals)),
                             squeeze=False)
    fig.suptitle('Bandit Delay Stage: Metrics over Reward Delay',
                 fontsize=14, fontweight='bold', y=1.01)

    for row, (mouseid, color) in enumerate(zip(animals, colors)):
        records = sorted(animal_data[mouseid], key=lambda r: r['starttime'])

        for col, (metric_key, metric_label, ylim) in enumerate(metrics):
            ax = axes[row][col]

            xs = [r['reward_delay'] for r in records if r[metric_key] is not None]
            ys = [r[metric_key]     for r in records if r[metric_key] is not None]

            if xs:
                ax.scatter(xs, ys, color=color, alpha=0.8, s=60, zorder=3,
                           label=mouseid)
                # connect dots in session order
                ax.plot(xs, ys, color=color, alpha=0.3, linewidth=1, zorder=2)

            ax.set_xticks(delay_ticks)
            ax.set_xticklabels([str(d) for d in delay_ticks])
            ax.set_xlabel('Reward Delay (s)')
            ax.set_xlim(0, 1.15)

            if ylim is not None:
                ax.set_ylim(ylim)

            if col == 0:
                ax.set_ylabel(mouseid, fontsize=10, fontweight='bold')
            if row == 0:
                ax.set_title(metric_label, fontsize=10)

            if metric_key == 'side_bias':
                ax.axhline(0, color='gray', linestyle='--', linewidth=0.8, zorder=1)

            ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = 'N:/Maxwell/Lampyr/bandit_delay_analysis.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f'\nFigure saved to {out_path}')
    plt.close()


if __name__ == '__main__':
    main()
