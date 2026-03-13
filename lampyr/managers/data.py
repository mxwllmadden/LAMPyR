# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:40:05 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.files import savemousefile, loadmousefile, loadsessionfile, savesessionfile
import os
import json
import glob
from lampyr.primatives import Session, Mouse
import shutil
import csv
import hashlib
from datetime import datetime

from typing import List


def hash_file(file_path, algo='sha256', block_size=65536):
    hasher = hashlib.new(algo)
    with open(file_path, 'rb') as f:
        while chunk := f.read(block_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def hashcheck_copyoverwrite(sourcefile, targetfile):
    if os.path.exists(targetfile):
        if hash_file(sourcefile) == hash_file(targetfile):
            return False
    shutil.copy(sourcefile, targetfile)
    return True


class DataHandler(AbstractManager):
    CONFIG_FAILSAFE_DEFAULT = {'sessions': []}

    def start(self):
        """
        DataHandler startup. If this object is instantiated with a config file,
        determine if backups and failsafes are enabled, then execute those methods.


        Returns
        -------
        None.

        """
        configured = self.config is not None
        haslampyr = self.lampyr is not None
        if not configured:
            return
        self.enable_failsafe = self.config.get(
            'lampyr.enable_saveload_failsafe') and haslampyr
        self.enable_localbackup = self.config.get(
            'lampyr.enable_local_mouse_backups') and haslampyr

        # Create required information for backups and cleanup
        self.local_save_dir = self.config._APP_DATA_DIR
        self.config_failsafe_data = self.config.load_extended_config('data_failsafe',
                                                                     default=self.CONFIG_FAILSAFE_DEFAULT)
        # Check if
        m_dir_present = os.path.exists(
            self.config.get('lampyr.mice_directory'))
        if m_dir_present and self.enable_localbackup:
            self._backupmice()
        if m_dir_present and self.enable_failsafe:
            self._runfailsafecleanup()

    def _backupmice(self):
        if not self.enable_localbackup:
            return
        miceids, _ = self.mouselist()
        apdir = self.config._APP_DATA_DIR
        data_dir = self.config.get('lampyr.mice_directory')
        for mid in miceids:
            try:
                mfile_bname = os.path.join(data_dir,
                                         mid,
                                         mid)
                bup_mfile_bname = os.path.join(apdir,
                                               mid)
                mfmove = hashcheck_copyoverwrite(
                    f'{mfile_bname}_mouse.lampyr.json',
                    f'{bup_mfile_bname}_mouse.lampyr.json')
                hfmove = hashcheck_copyoverwrite(
                    f'{mfile_bname}_history.lampyr.csv',
                    f'{bup_mfile_bname}_history.lampyr.csv')
                if mfmove or hfmove:
                    self._output_func(f'Updated local backup of {mid}.')
            except FileNotFoundError:
                self._output_func(
                    f'FAILED TO BACK UP {mid} due to FILE NOT FOUND')
            except PermissionError:
                self._output_func(
                    f'FAILED TO BACK UP {mid} due to PERMISSION DENIED')
            except Exception as e:
                self._output_func(
                    f'FAILED TO BACK UP {mid} due to UNEXPECTED ERROR')
                self._output_func(str(e))

    def _runfailsafecleanup(self):
        if not self.enable_failsafe:
            return
        failsafe = self.config.load_extended_config('data_failsafe',
                                                    default=self.CONFIG_FAILSAFE_DEFAULT)
        failed_sessions = failsafe.get('sessions')
        for session in failed_sessions:
            if not isinstance(session, dict):
                self._output_func(
                    'DataHandler found an invalid session failsafe entry!!!')
                continue
            if not {'fps', 'target'} <= session:
                self._output_func(
                    'DataHandler found an invalid session failsafe entry!!!')
                self._output_func(
                    'You must manually inspect and register any remaining failed files.')
                continue
            for fp in session['fps']:
                shutil.copy(fp, session['target'])

    def _logfailure(self, failure_type: str, fps: list, target: str):
        failures = self.config_failsafe_data.get(failure_type)
        failures.append({'fps': fps,
                         'target': target})
        self.config_failsafe_data.set(failure_type, failures)

    def savesession(self, session: Session = None, register=True):
        if session is None:
            if self.lampyr is None:
                raise KeyError(
                    'Mouse must be specified if outside lampyr instance')
            session = self.lampyr.session
        mouseid = session.mouseid
        data_dir = self.config.get('lampyr.mice_directory')
        dir_fp = os.path.join(data_dir,
                              mouseid,
                              'lampyr_sessionhistory')
        savesessionfile(session, dir_fp)
        if register is True and self.lampyr is not None:
            self.register_session_to_mouse(self.lampyr.mouse,
                                           session)

    def loadsession(self, sessionid: str, mouseid: str = None):
        data_dir = self.config.get('lampyr.mice_directory')
        if mouseid is None:
            if self.lampyr is not None:
                mouseid = self.lampyr.mouse.mouseid
            else:
                raise KeyError(
                    'Mouseid must be specified if outside lampyr instance')
        data_dir = os.path.join(data_dir,
                                mouseid,
                                'lampyr_sessionhistory')
        return loadsessionfile(sessionid, data_dir)

    def mouseexists(self, mouseid):
        return os.path.exists(os.path.join(self.config.get('lampyr.mice_directory'),
                                           mouseid,
                                           f'{mouseid}_mouse.lampyr.json'))

    def mouselist(self) -> List[str]:
        data_dir = self.config.get('lampyr.mice_directory')
        candidate_mice = glob.glob(os.path.join(data_dir,
                                                '**',
                                                '*.lampyr.json'))
        mousepaths = [mpath for mpath in candidate_mice
                      if os.path.basename(mpath).split('.')[0] ==
                      os.path.basename(os.path.dirname(mpath)) + '_mouse']
        mouseidlist = [os.path.basename(os.path.dirname(m))
                       for m in mousepaths]
        return mouseidlist, mousepaths

    def savemouse(self, mouse: Mouse = None):
        if mouse is None:
            if self.lampyr is None:
                raise KeyError(
                    'Mouse must be specified if outside lampyr instance')
            mouse = self.lampyr.mouse
        data_dir = self.config.get('lampyr.mice_directory')
        data_dir = os.path.join(data_dir,
                                mouse.mouseid)
        savemousefile(mouse, data_dir)

    def loadmouse(self, mouseid: str):
        data_dir = os.path.join(self.config.get('lampyr.mice_directory'),
                                mouseid)
        return loadmousefile(mouseid, data_dir)

    def register_session_to_mouse(self, mouse: Mouse, session: Session):
        sessionentry = {}
        dt = datetime.fromtimestamp(session.starttime).astimezone()
        sessionentry['starttime'] = session.starttime
        sessionentry['year'] = dt.year
        sessionentry['month'] = dt.month
        sessionentry['day'] = dt.day
        for entry in ["merit", "demerit", "duration", "trial", "rewards",
                      "abstention", "participation", "serial_abstention"]:
            sessionentry[entry] = getattr(session, entry)
        mouse.history.append(sessionentry)


class MouseManager(AbstractManager):
    def start(self):
        if self.lampyr is None:
            raise RuntimeError(
                'MouseManager cannot operate without a lampyr instance')
        self.mouse = None
        if not self.exists('UNKNOWN_MOUSE'):
            self.create('UNKNOWN_MOUSE')
        self.load('UNKNOWN_MOUSE')

    def create(self, mouseid, **kwargs):
        mouse = Mouse(mouseid=mouseid, **kwargs)
        self.mouse = mouse
        self.save()

    def list(self):
        mlist, _ = self.lampyr.datamanager.mouselist()
        return mlist

    def exists(self, mouseid):
        return self.lampyr.datamanager.mouseexists(mouseid)

    def load(self, mouseid):
        self.mouse = self.lampyr.datamanager.loadmouse(mouseid)

    def save(self):
        self.lampyr.datamanager.savemouse(self.mouse)


if __name__ == '__main__':
    dhandler = DataHandler()
    print(dhandler.loadmouse('014-000'))
