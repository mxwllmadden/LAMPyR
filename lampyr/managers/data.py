# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:40:05 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.files import (savemousefile, loadmousefile, loadsessionfile,
                          savesessionfile, loadjson, savejson, savecsv)
import os
from pathlib import Path
import glob
from lampyr.primatives import Mouse, Session, SYSTEM_MOUSE_IDS
import shutil
import hashlib
import tempfile
from datetime import datetime

from typing import List


def hash_file(file_path, algo='sha256', block_size=65536):
    """
    Compute the hash digest of a file.

    Reads the file in fixed-size chunks to avoid loading large files into
    memory all at once.

    Parameters
    ----------
    file_path : str or os.PathLike
        Path to the file to hash.
    algo : str, optional
        Hash algorithm name accepted by :func:`hashlib.new`. Default is
        ``'sha256'``.
    block_size : int, optional
        Number of bytes to read per chunk. Default is 65536 (64 KiB).

    Returns
    -------
    str
        Hex-encoded digest string of the file contents.
    """
    hasher = hashlib.new(algo)
    with open(file_path, 'rb') as f:
        while chunk := f.read(block_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def hashcheck_copyoverwrite(sourcefile, targetfile):
    """
    Copy a source file to a target path only if the contents differ.

    If the target already exists and its hash matches the source, no copy is
    performed. This avoids unnecessary writes when the files are identical.

    Parameters
    ----------
    sourcefile : str or os.PathLike
        Path to the file to copy from. Must exist.
    targetfile : str or os.PathLike
        Path to copy the file to. Will be created or overwritten if the
        contents differ from the source.

    Returns
    -------
    bool
        ``True`` if the file was copied, ``False`` if it was skipped because
        the target already contained identical content.
    """
    if os.path.exists(targetfile):
        if hash_file(sourcefile) == hash_file(targetfile):
            return False
    shutil.copy(sourcefile, targetfile)
    return True


class DataHandler(AbstractManager):

    def start(self):
        """Configure backups and retry committed pending sessions."""
        if self.config is None:
            return

        self.enable_failsafe = bool(self.config.get(
            'lampyr.enable_saveload_failsafe'))
        self.enable_localbackup = bool(self.config.get(
            'lampyr.enable_local_mouse_backups')) and self.lampyr is not None
        self.local_save_dir = self.config._APP_DATA_DIR
        self.pending_sessions_dir = os.path.join(
            self.local_save_dir, 'pending_sessions')

        mice_directory = self.config.get('lampyr.mice_directory')
        if os.path.exists(mice_directory) and self.enable_localbackup:
            self._backupmice()

        if not self.enable_failsafe:
            return

        os.makedirs(self.pending_sessions_dir, exist_ok=True)
        self._publish_pending_sessions()

    def _publish_pending_sessions(self):
        """Attempt to publish every committed pending session on disk."""
        pending_root = Path(self.pending_sessions_dir)
        if not pending_root.is_dir():
            return
        for pending_dir in sorted(pending_root.iterdir()):
            if (not pending_dir.is_dir()
                    or pending_dir.name.startswith('.')
                    or not (pending_dir / 'manifest.json').is_file()):
                continue
            try:
                self._publish_pending_session(pending_dir)
                shutil.rmtree(pending_dir)
                self._output_func(
                    f'Recovered pending session {pending_dir.name}.')
            except Exception as error:
                self._output_func(
                    f'Could not publish pending session {pending_dir.name}: '
                    f'{error}')

    def _backupmice(self):
        """
        Copy all mouse data files from the shared directory to local app data.

        Iterates over every mouse returned by :meth:`mouselist` and uses
        :func:`hashcheck_copyoverwrite` to copy the metadata JSON and, where
        present, the history CSV to the local AppData backup directory. Files
        that are already up to date (matching hash) are skipped silently.

        System identities without history CSVs (``UNKNOWN_MOUSE`` and
        ``AUTOMATION``) are
        handled gracefully — only the JSON is backed up.

        Per-mouse errors are caught and reported via ``_output_func`` without
        interrupting the backup of remaining mice.

        Returns
        -------
        None
        """
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
                src_csv = f'{mfile_bname}_history.lampyr.csv'
                hfmove = (hashcheck_copyoverwrite(src_csv,
                          f'{bup_mfile_bname}_history.lampyr.csv')
                          if os.path.exists(src_csv) else False)
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

    def savesession(self, session: Session = None, register=True):
        """
        Save a session directly or through the local pending-session queue.

        With the failsafe disabled, this retains the existing direct-save
        behavior. With it enabled, a complete local copy is committed before
        network publication is attempted.

        Returns
        -------
        str
            ``'published'`` when the shared copy is complete, or ``'pending'``
            when a complete local copy remains queued. Local staging failures
            are raised.
        """
        if session is None:
            if self.lampyr is None:
                raise KeyError(
                    'Session must be specified if outside lampyr instance')
            session = self.lampyr.session

        should_register = bool(
            register and self.lampyr is not None and self.lampyr.mouse is not None)
        if not self.enable_failsafe:
            data_dir = self.config.get('lampyr.mice_directory')
            dir_fp = os.path.join(data_dir,
                                  session.mouseid,
                                  'lampyr_sessionhistory')
            savesessionfile(session, dir_fp)
            self.collect_extended_data(session)
            if should_register:
                self.register_session_to_mouse(self.lampyr.mouse, session)
            return 'published'

        pending_dir = self._stage_pending_session(session, should_register)
        try:
            published_history = self._publish_pending_session(pending_dir)
        except Exception as error:
            self._output_func(
                f'Session {session.uniquesessionid} saved locally and is '
                f'pending publication: {error}')
            return 'pending'

        try:
            shutil.rmtree(pending_dir)
        except Exception as error:
            # Publication is complete. Leaving an idempotent queue entry is
            # safer than treating the successfully saved session as failed.
            self._output_func(
                f'Session {session.uniquesessionid} was published, but its '
                f'local pending copy could not be removed: {error}')

        # Publication worked for this session, so opportunistically flush any
        # older pending sessions that failed on a previous attempt.
        self._publish_pending_sessions()

        if should_register:
            if (published_history is not None
                    and self.lampyr.mouse.mouseid == session.mouseid):
                self.lampyr.mouse.history = published_history
            else:
                self.register_session_to_mouse(self.lampyr.mouse, session)
        return 'published'

    def _stage_pending_session(self, session: Session, register: bool):
        """Build and atomically commit a complete local pending session."""
        os.makedirs(self.pending_sessions_dir, exist_ok=True)
        final_dir = Path(self.pending_sessions_dir) / session.uniquesessionid
        if final_dir.exists():
            manifest, _, _, _ = self._read_pending_session(final_dir)
            if manifest.get('register', True) != register:
                raise ValueError(
                    'Existing pending session has different registration behavior')
            return final_dir

        temp_dir = Path(tempfile.mkdtemp(
            dir=self.pending_sessions_dir,
            prefix=f'.{session.uniquesessionid}.'))
        source_files = []
        try:
            savesessionfile(session, temp_dir)
            json_path = temp_dir / f'{session.uniquesessionid}.lampyr.json'
            h5_path = temp_dir / f'{session.uniquesessionid}.lampyr.h5'
            if not json_path.is_file() or not h5_path.is_file():
                raise RuntimeError('Session JSON and HDF5 were not both staged')

            destinations = set()
            for entry in session._extendeddata or []:
                source = Path(entry['fp'])
                relative = Path(entry['type']) / source.name
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError(
                        f'Extended-data type must be relative: {entry["type"]}')
                if relative in destinations:
                    raise ValueError(
                        f'Duplicate extended-data destination: {relative}')
                destinations.add(relative)
                target = temp_dir / 'extended' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                source_files.append(source)

            staged_data = loadjson(json_path)
            expected_extended = {
                os.path.normpath(path)
                for path in staged_data.get('extendeddata') or []
            }
            if expected_extended != {
                    os.path.normpath(str(path)) for path in destinations}:
                raise RuntimeError(
                    'Staged extended data does not match session JSON')

            savejson(temp_dir / 'manifest.json', {
                'session_id': session.uniquesessionid,
                'mouse_id': session.mouseid,
                'register': register,
            })
            os.rename(temp_dir, final_dir)
            temp_dir = None
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

        for source in source_files:
            try:
                source.unlink()
            except FileNotFoundError:
                pass
            except Exception as error:
                self._output_func(
                    f'Could not remove staged extended-data source '
                    f'{source}: {error}')
        return final_dir

    def _read_pending_session(self, pending_dir):
        """Validate a committed pending session and return its metadata."""
        pending_dir = Path(pending_dir)
        manifest = loadjson(pending_dir / 'manifest.json')
        session_id = manifest.get('session_id')
        mouse_id = manifest.get('mouse_id')
        if session_id != pending_dir.name or not mouse_id:
            raise ValueError(
                'Pending-session manifest does not match its directory')

        json_path = pending_dir / f'{session_id}.lampyr.json'
        h5_path = pending_dir / f'{session_id}.lampyr.h5'
        if not json_path.is_file() or not h5_path.is_file():
            raise FileNotFoundError('Pending session is missing JSON or HDF5')

        session_data = loadjson(json_path)
        if (session_data.get('uniquesessionid') != session_id
                or session_data.get('mouseid') != mouse_id):
            raise ValueError('Pending session JSON does not match its manifest')
        for relative_name in session_data.get('extendeddata') or []:
            relative_path = Path(relative_name)
            if relative_path.is_absolute() or '..' in relative_path.parts:
                raise ValueError(
                    f'Extended-data path must be relative: {relative_name}')
            if not (pending_dir / 'extended' / relative_path).is_file():
                raise FileNotFoundError(
                    f'Pending extended-data file is missing: {relative_name}')
        return manifest, session_data, json_path, h5_path

    def _publish_pending_session(self, pending_dir):
        """Idempotently publish one committed pending session."""
        pending_dir = Path(pending_dir)
        manifest, session_data, json_path, h5_path = \
            self._read_pending_session(pending_dir)
        session_id = manifest['session_id']
        mouse_id = manifest['mouse_id']

        data_dir = Path(self.config.get('lampyr.mice_directory'))
        for relative_name in session_data.get('extendeddata') or []:
            relative_path = Path(relative_name)
            source = pending_dir / 'extended' / relative_path
            destination = (data_dir / mouse_id / 'lampyr_extendeddata'
                           / session_id / relative_path)
            self._publish_file(source, destination)

        session_history_dir = data_dir / mouse_id / 'lampyr_sessionhistory'
        self._publish_file(
            h5_path, session_history_dir / h5_path.name)
        self._publish_file(
            json_path, session_history_dir / json_path.name)

        published_history = None
        if manifest.get('register', True) and mouse_id != 'UNKNOWN_MOUSE':
            mouse = self.loadmouse(mouse_id)
            self.register_session_to_mouse(mouse, session_data)
            history_path = data_dir / mouse_id / f'{mouse_id}_history.lampyr.csv'
            savecsv(history_path, mouse.history)
            published_history = mouse.history
        return published_history

    def _publish_file(self, source, destination):
        """Publish one file atomically without overwriting a conflict."""
        source = Path(source)
        destination = Path(destination)
        source_hash = hash_file(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if hash_file(destination) == source_hash:
                return
            raise FileExistsError(
                f'Refusing to overwrite conflicting file {destination}')

        descriptor, temp_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f'.{destination.name}.',
            suffix='.tmp')
        os.close(descriptor)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(source, temp_path)
            if hash_file(temp_path) != source_hash:
                raise IOError(f'Hash mismatch while copying {destination}')
            if destination.exists():
                if hash_file(destination) == source_hash:
                    return
                raise FileExistsError(
                    f'Refusing to overwrite conflicting file {destination}')
            os.replace(temp_path, destination)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

    def loadsession(self, sessionid: str, mouseid: str = None):
        """
        Load a session from a mouse's session history directory.

        Looks up the session files under
        ``<mice_directory>/<mouseid>/lampyr_sessionhistory/`` via
        :func:`~lampyr.files.loadsessionfile`.

        Parameters
        ----------
        sessionid : str
            The unique session ID to load.
        mouseid : str, optional
            The mouse whose session history to search. If ``None``, uses the
            active mouse from the attached lampyr instance. Raises ``KeyError``
            if no lampyr instance is available.

        Raises
        ------
        KeyError
            If ``mouseid`` is ``None`` and no lampyr instance is attached.

        Returns
        -------
        Session
            The reconstructed Lampyr Session object.
        """
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
        """
        Check whether a mouse exists on disk.

        System identities exist when their directory exists; regular mice
        require a saved metadata file.

        Parameters
        ----------
        mouseid : str
            The mouse ID to look up.

        Returns
        -------
        bool
            ``True`` if the system identity directory or regular mouse
            metadata file exists, ``False`` otherwise.
        """
        mouse_dir = os.path.join(
            self.config.get('lampyr.mice_directory'), mouseid
        )
        if mouseid in SYSTEM_MOUSE_IDS:
            return os.path.isdir(mouse_dir)
        return os.path.exists(
            os.path.join(mouse_dir, f'{mouseid}_mouse.lampyr.json')
        )

    def mouselist(self) -> List[str]:
        """
        Return all mouse IDs and their metadata file paths found on disk.

        Scans the configured mice directory recursively for
        ``*.lampyr.json`` files and retains only those whose filename stem
        matches the pattern ``<parentdir>_mouse``, identifying them as mouse
        metadata files rather than session files.

        Returns
        -------
        mouseidlist : list of str
            List of mouse ID strings derived from the parent directory names.
        mousepaths : list of str
            Corresponding list of absolute paths to each mouse's
            ``_mouse.lampyr.json`` file.
        """
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
        """
        Save a Mouse object to the configured mice directory.

        Writes the mouse metadata JSON and, if the mouse has session history,
        the history CSV under ``<mice_directory>/<mouseid>/`` via
        :func:`~lampyr.files.savemousefile`.

        Parameters
        ----------
        mouse : Mouse, optional
            The Mouse object to save. If ``None``, uses the active mouse from
            the attached lampyr instance. Raises ``KeyError`` if no lampyr
            instance is available.

        Raises
        ------
        KeyError
            If ``mouse`` is ``None`` and no lampyr instance is attached.

        Returns
        -------
        None
        """
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
        """
        Load a Mouse object from the configured mice directory.

        Reconstructs the Mouse from the ``_mouse.lampyr.json`` and, if
        present, the ``_history.lampyr.csv`` files stored under
        ``<mice_directory>/<mouseid>/`` via
        :func:`~lampyr.files.loadmousefile`.

        Parameters
        ----------
        mouseid : str
            The ID of the mouse to load.

        Returns
        -------
        Mouse
            The reconstructed Lampyr Mouse object.
        """
        data_dir = os.path.join(self.config.get('lampyr.mice_directory'),
                                mouseid)
        return loadmousefile(mouseid, data_dir)

    def _session_history_entry(self, session):
        """Build a mouse-history row from a Session or staged JSON mapping."""
        def get_value(name):
            if isinstance(session, dict):
                return session.get(name)
            return getattr(session, name)

        starttime = get_value('starttime')
        dt = datetime.fromtimestamp(starttime).astimezone()
        segments = get_value('segments') or {}
        root = get_value('root')
        sessionentry = {
            'sessionid': get_value('uniquesessionid'),
            'starttime': starttime,
            'year': dt.year,
            'month': dt.month,
            'day': dt.day,
            'rootslug': segments.get(root, {}).get('slug', 'NA'),
        }
        for entry in ["merit", "demerit", "duration", "trial", "rewards",
                      "abstention", "participation"]:
            sessionentry[entry] = get_value(entry)
        return sessionentry

    def register_session_to_mouse(self, mouse: Mouse, session: Session):
        """Insert or replace a session row in a mouse's in-memory history."""
        sessionentry = self._session_history_entry(session)
        for index, existing in enumerate(mouse.history):
            if existing.get('sessionid') == sessionentry['sessionid']:
                mouse.history[index] = sessionentry
                break
        else:
            mouse.history.append(sessionentry)

    def collect_extended_data(self, session: Session):
        if session._extendeddata is None:
            return
        mouseid = session.mouseid
        data_dir = self.config.get('lampyr.mice_directory')
        for e in session._extendeddata:
            fname = os.path.basename(e['fp'])
            target_fp = os.path.join(data_dir,
                                     mouseid,
                                     'lampyr_extendeddata',
                                     session.uniquesessionid,
                                     e['type'],
                                     fname)
            os.makedirs(os.path.dirname(target_fp), exist_ok=True)
            shutil.move(e['fp'], target_fp)
            self._output_func('Collected {fname}')

    def _mouse_session_list_from_files(self, mouseid):
        data_dir = self.config.get('lampyr.mice_directory')
        dir_fp = os.path.join(data_dir,
                              mouseid,
                              'lampyr_sessionhistory',
                              '*.lampyr.json')
        all_sessions = glob.glob(dir_fp)
        all_sessions = [Path(p).name.removesuffix('.lampyr.json')
                        for p in all_sessions]
        return all_sessions

    def reconstruct_all_mouse_history_from_files(self):
        mouselist, _ = self.mouselist()
        for mouse in mouselist:
            print(f'Reconstructing {mouse} history')
            mouse_obj = self.loadmouse(mouse)
            mouse_obj.history = []
            if mouse in SYSTEM_MOUSE_IDS:
                continue
            sessionlist = self._mouse_session_list_from_files(mouse)
            print(f'Processing {len(sessionlist)} sessions')
            for session in sessionlist:
                try:
                    s = self.loadsession(session, mouse)
                    self.register_session_to_mouse(mouse_obj, s)
                except:
                    print(f'Failed to parse {mouse} - {session}')
            print('Successfully registered ' +
                  f'{len(mouse_obj.history)}/{len(sessionlist)} sessions')
            self.savemouse(mouse_obj)

    def heartbeat_filetouch(self):
        datadir = self.config.get('lampyr.mice_directory')
        hbeatfile = os.path.join(datadir, 'heartbeat.file')
        if not os.path.exists(hbeatfile):
            savejson(hbeatfile, {})
        loadjson(hbeatfile)


class MouseManager(AbstractManager):
    def start(self):
        """
        MouseManager startup.

        Ensures ``UNKNOWN_MOUSE`` exists on disk (creating it if necessary),
        then loads it as the initially active mouse. Raises ``RuntimeError``
        if no lampyr instance is attached, as this manager cannot function
        without one.

        Raises
        ------
        RuntimeError
            If no lampyr instance is attached to this manager.

        Returns
        -------
        None
        """
        if self.lampyr is None:
            raise RuntimeError(
                'MouseManager cannot operate without a lampyr instance')
        self.mouse = None
        if not self.exists('UNKNOWN_MOUSE'):
            self.create('UNKNOWN_MOUSE')
        self.load('UNKNOWN_MOUSE')

    def create(self, mouseid, **kwargs):
        """
        Create a new Mouse, set it as active, and save it to disk.

        Parameters
        ----------
        mouseid : str
            ID to assign to the new mouse.
        **kwargs
            Additional keyword arguments forwarded to the :class:`Mouse`
            constructor.

        Returns
        -------
        None
        """
        mouse = Mouse(mouseid=mouseid, **kwargs)
        self.mouse = mouse
        self.save()

    def retire(self):
        """
        Marks mouse as retired

        Parameters
        ----------
        mouseid : str
            DESCRIPTION.

        Returns
        -------
        None.

        """
        self.mouse.retired = True
        self.save()

    def deretire(self):
        self.mouse.retired = False
        self.save()

    def list(self):
        """
        Return a list of all mouse IDs found in the mice directory.

        Returns
        -------
        list of str
            Mouse IDs discovered on disk.
        """
        mlist, _ = self.lampyr.datamanager.mouselist()
        return mlist

    def exists(self, mouseid):
        """
        Check whether a mouse exists on disk.

        Parameters
        ----------
        mouseid : str
            The mouse ID to look up.

        Returns
        -------
        bool
            ``True`` if the mouse's metadata file is present, ``False``
            otherwise.
        """
        return self.lampyr.datamanager.mouseexists(mouseid)

    def load(self, mouseid):
        """
        Load a mouse from disk and set it as the active mouse.

        Parameters
        ----------
        mouseid : str
            The ID of the mouse to load.

        Returns
        -------
        None
        """
        self.mouse = self.lampyr.datamanager.loadmouse(mouseid)

    def save(self):
        """
        Save the currently active mouse to disk.

        Returns
        -------
        None
        """
        self.lampyr.datamanager.savemouse(self.mouse)


if __name__ == '__main__':
    dhandler = DataHandler()
    print(dhandler.loadmouse('014-000'))
