# -*- coding: utf-8 -*-
"""
Created on Thu Jun 12 15:21:44 2025

@author: mm4114
"""

import click
import time
from lampyr import Lampyr

class Abort(Exception):
    pass

def printtitle(msg, char = '='):
    printheader('',char)
    printheader(f' {msg} ', char)
    printheader('',char)

def printheader(msg, char = '-'):
    prefix = char * (40 - len(msg)//2)
    if len(msg) % 2 == 1:
        suffix = prefix[:-1]
    else:
        suffix = prefix
    click.echo(prefix+msg+suffix)

def printinfo(info, indent = 0):
    prefix = '\t'*indent
    for k, v in info.items():
        if isinstance(v, dict):
            click.echo(f'{prefix}{k}')
            printinfo(v, indent+1)
        elif isinstance(v, list):
            click.echo(f'{prefix}{k}')
            for vind in v:
                if isinstance(vind, dict):
                    printinfo(vind, indent+1)
                else:
                    click.echo(f'\t{prefix}{vind}')
        else:
            click.echo(f'{prefix}{k} : {v}')

def start_rig(lampyr : Lampyr):
    if lampyr.config.get('rig.configured') < 1:
        click.echo('Command aborted because rig is not configured')
        click.echo('\nUse "lampyr rig configure" to configure rig')
        raise Abort()
    if lampyr.config.get('rig.calibrated') < time.time() - 43200:
        click.echo('Command aborted because rig is not calibrated')
        click.echo('\nUse "lampyr rig calibrate" to calibrate rig')
        raise Abort()
    lampyr.rigmanager.connect()
    return True

def configure_rig(lampyr : Lampyr):
    name = input('Rig Name: ')
    lampyr.config.set('rig.name', name)
    lampyr.config.set('rig.configured', 1)