# -*- coding: utf-8 -*-
"""
Created on Wed May 14 15:02:02 2025

@author: mm4114
"""

import click
import time
import os
import numpy as np
from lampyr import config, Lampyr
from lampyr.version import __version__
from lampyr.segments import Task, Trial, Stage, Paradigm
from lampyr.behaviors import bandit
from lampyr.rigs.rigcontrol import ArduinoBanditRig_0, SerialMonitor
from lampyr import actions

@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = Lampyr()
    @ctx.call_on_close
    def cleanup():
        ctx.obj.close()

@cli.command()
@click.pass_obj
def list(lampyr : Lampyr):
    actions.printtitle('LOADED BEHAVIORS')
    actions.printheader('PARADIGMS')
    for behav in Paradigm.get_children():
        click.echo(behav.__name__)
    actions.printheader('STAGES')
    for behav in Stage.get_children():
        click.echo(behav.__name__)
    actions.printheader('TASKS')
    for behav in Task.get_children():
        click.echo(behav.__name__)
    actions.printheader('TRIALS')
    for behav in Trial.get_children():
        click.echo(behav.__name__)

@cli.command()
@click.pass_obj
def reset(lampyr):
    passw = click.prompt("Type YES to confirm")
    if passw != 'YES':
        click.echo('Denied')
    else:
        lampyr.config.reset_to_default()
        click.echo("Configuration reset to default.")

@cli.command()
@click.pass_obj
def developer(lampyr):
    passw = click.prompt("Input Password")
    if passw != 'photuris':
        click.echo('Denied')
    else:
        lampyr.config.set('rig.calibrated', 100000000000)
        lampyr.config.set('rig.name', 'Photuris')
        lampyr.config.set('rig.configured', True)
        click.echo("Configuration set to developer mode.")
    
@cli.command()
@click.pass_obj
def info(lampyr):
    actions.printtitle(f'LAMPYR BEHAVIOR SOFTWARE v{__version__}')
    actions.printheader('CONFIG')
    info = lampyr.config._config
    actions.printinfo(info)

@cli.group()
@click.pass_obj
def rig(ctx):
    pass

@rig.command(name = 'info')
@click.pass_obj
def rig_info(lampyr):
    info = lampyr.config.get('rig')
    actions.printinfo(info)

@rig.command()
@click.pass_obj
def configure(lampyr):
    actions.configure_rig(lampyr)
        
@rig.command()
@click.pass_obj
def calibrate(ctx):
    ctx.rigmanager.calibrate()

@cli.group()
def mouse():
    pass

@mouse.command(name = 'create')
@click.argument('mouseid')
@click.option('--paradigm','-p', type = str, required = False)
@click.option('--force', is_flag = True, help='overwrite existing mouse')
@click.pass_obj
def mouse_create(lampyr : Lampyr, mouseid, force, **kwargs):
    if not force:
        if lampyr.mousemanager.exists(mouseid):
            click.echo(f'\nFailed to create mouse: Mouse name {mouseid} already exists.')
            return
        mousedir = os.path.join(lampyr.config.get('lampyr.mice_directory'),mouseid)
        if not os.path.exists(mousedir):
            click.echo(f'\nFailed to create mouse: No folder exists at {lampyr.config.get("lampyr.mice_directory")} for that mouseid.')
            return
    if kwargs['paradigm'] is not None:
        if kwargs['paradigm'] not in lampyr.paradigms:
            click.echo(f'\nFailed to create mouse: {kwargs["paradigm"]} Paradigm does not exist.')
            return
    lampyr.mousemanager.create(mouseid, **kwargs)

@mouse.command(name = 'list')
@click.pass_obj
def mouse_list(lampyr):
    actions.printheader('MICE')
    l, _ = lampyr.mousemanager.list()
    for m in l:
        click.echo(m)

@mouse.command(name = 'info')
@click.argument('mouseid')
@click.pass_obj
def mouse_info(lampyr, mouseid):
    lampyr.mousemanager.load(mouseid)
    info = lampyr.mouse
    click.echo(info)

@mouse.command(name = 'run')
@click.argument('mouseid')
@click.argument('behavior', required = False)
@click.option('--merit_limit', '-ml', type=int, required=False)
@click.option('--merit_min', '-mm', type=int, required=False)
@click.option('--demerit_limit', '-dml', type=int, required=False)
@click.option('--demerit_min', '-dmm', type=int, required=False)
@click.option('--duration_limit', '-dl', type=int, required=False)
@click.option('--duration_min', '-dm', type=int, required=False)
@click.option('--trial_limit', '-tl', type=int, required=False)
@click.option('--trial_min', '-tm', type=int, required=False)
@click.option('--reward_limit', '-rl', type=int, required=False)
@click.option('--reward_min', '-rm', type=int, required=False)
@click.option('--abstention_limit', '-al', type=int, required=False)
@click.option('--abstention_min', '-am', type=int, required=False)
@click.option('--participation_limit', '-pl', type=int, required=False)
@click.option('--participation_min', '-pm', type=int, required=False)
@click.option('--serial_abstention_limit', '-sal', type=int, required=False)
@click.option('--serial_abstention_min', '-sam', type=int, required=False)
@click.pass_obj
def mouse_run(lampyr, mouseid, behavior, **kwargs):
    try:
        lampyr.mousemanager.load(mouseid)
    except KeyError as e:
        click.echo(f'Error loading mouse: {e}')
        return
    if behavior is None:
        behavior = lampyr.mouse.paradigm
    try:
        actions.start_rig(lampyr)
    except actions.Abort as e:
        click.echo(f'Error starting rig: {e}')
        return
    lampyr.run(behavior, **kwargs)

@cli.group()
def user():
    pass

@user.command(name='create')
@click.argument('name')
@click.option('-super', 'is_super', is_flag=True, default=False, help='Make user a supervisor')
@click.option('--pushover_user_key', type=str, default=None, help='Pushover user key')
@click.option('--pushover_app_token', type=str, default=None, help='Pushover app token')
@click.pass_obj
def user_create(lampyr, name, is_super, pushover_user_key, pushover_app_token):
    nm = lampyr.notificationmanager
    if name in nm.userdata._config:
        click.echo(f"User '{name}' already exists. Use 'user edit' to modify.")
        return
    nm.add_user(name, pushover_user_key or '', pushover_app_token or '', supervisor=is_super)
    click.echo(f"User '{name}' created.")

@user.command(name='edit')
@click.argument('name')
@click.option('--pushover_user_key', type=str, default=None, help='Pushover user key')
@click.option('--pushover_app_token', type=str, default=None, help='Pushover app token')
@click.option('--supervisor', type=click.BOOL, default=None, help='Set supervisor status (true/false)')
@click.pass_obj
def user_edit(lampyr, name, pushover_user_key, pushover_app_token, supervisor):
    nm = lampyr.notificationmanager
    if name not in nm.userdata._config:
        click.echo(f"User '{name}' not found.")
        return
    existing = nm.userdata._config[name]
    puk = pushover_user_key if pushover_user_key is not None else existing.get('pushover_user_key', '')
    pat = pushover_app_token if pushover_app_token is not None else existing.get('pushover_app_token', '')
    sup = supervisor if supervisor is not None else existing.get('supervisor', False)
    nm.add_user(name, puk, pat, supervisor=sup)
    click.echo(f"User '{name}' updated.")

@user.command(name='inspect')
@click.argument('name')
@click.pass_obj
def user_inspect(lampyr, name):
    users = lampyr.notificationmanager.userdata._config
    if name not in users:
        click.echo(f"User '{name}' not found.")
        return
    actions.printheader(name.upper())
    actions.printinfo(users[name])

@user.command(name='list')
@click.pass_obj
def user_list(lampyr):
    users = lampyr.notificationmanager.userdata._config
    if not users:
        click.echo('No users configured.')
        return
    actions.printheader('USERS')
    for name, data in users.items():
        supervisor = ' [supervisor]' if data.get('supervisor') else ''
        click.echo(f'{name}{supervisor}')

@user.command(name='remove')
@click.argument('name')
@click.pass_obj
def user_remove(lampyr, name):
    nm = lampyr.notificationmanager
    try:
        nm.delete_user(name)
        click.echo(f"User '{name}' removed.")
    except KeyError as e:
        click.echo(f"Error: {e}")

@cli.command()
@click.argument('behavior')
@click.option('--merit_limit', '-ml', type=int, required=False)
@click.option('--merit_min', '-mm', type=int, required=False)
@click.option('--demerit_limit', '-dml', type=int, required=False)
@click.option('--demerit_min', '-dmm', type=int, required=False)
@click.option('--duration_limit', '-dl', type=int, required=False)
@click.option('--duration_min', '-dm', type=int, required=False)
@click.option('--trial_limit', '-tl', type=int, required=False)
@click.option('--trial_min', '-tm', type=int, required=False)
@click.option('--reward_limit', '-rl', type=int, required=False)
@click.option('--reward_min', '-rm', type=int, required=False)
@click.option('--abstention_limit', '-al', type=int, required=False)
@click.option('--abstention_min', '-am', type=int, required=False)
@click.option('--participation_limit', '-pl', type=int, required=False)
@click.option('--participation_min', '-pm', type=int, required=False)
@click.option('--serial_abstention_limit', '-sal', type=int, required=False)
@click.option('--serial_abstention_min', '-sam', type=int, required=False)
@click.pass_obj
def run(lampyr : Lampyr, behavior, **kwargs):
    try:
        actions.start_rig(lampyr)
    except actions.Abort:
        return
    lampyr.run(behavior, **kwargs)

@cli.command()
def go():
    """Launch the Lampyr TUI."""
    import sys
    if sys.platform == "win32":
        import ctypes
        KEYEVENTF_KEYUP = 0x0002
        VK_F11 = 0x7A
        ctypes.windll.user32.keybd_event(VK_F11, 0, 0, 0)           # F11 down
        ctypes.windll.user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)  # F11 up
    from lampyr.interfaces.textual_tui.app import LampyrApp
    LampyrApp().run()