import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import lampyr.managers.data as data_module
from lampyr.files import loadmousefile, savemousefile
from lampyr.main import Lampyr
from lampyr.managers.data import DataHandler
from lampyr.primatives import Mouse, Session


class FakeConfig:
    def __init__(self, app_dir, mice_dir, failsafe=True):
        self._APP_DATA_DIR = str(app_dir)
        self.values = {
            'lampyr.enable_saveload_failsafe': failsafe,
            'lampyr.enable_local_mouse_backups': False,
            'lampyr.mice_directory': str(mice_dir),
        }

    def get(self, key):
        return self.values[key]


def make_handler(tmp_path, failsafe=True, output=None):
    app_dir = tmp_path / 'app'
    mice_dir = tmp_path / 'mice'
    app_dir.mkdir(exist_ok=True)
    mice_dir.mkdir(exist_ok=True)
    mouse = Mouse(mouseid='014-003')
    mouse_dir = mice_dir / mouse.mouseid
    if not (mouse_dir / f'{mouse.mouseid}_mouse.lampyr.json').exists():
        savemousefile(mouse, mouse_dir)
    lampyr = SimpleNamespace(
        config=FakeConfig(app_dir, mice_dir, failsafe),
        mouse=mouse,
        session=None,
        _input_func=input,
        _output_func=output or (lambda _message: None),
    )
    return DataHandler(lampyr), lampyr, app_dir, mice_dir


def make_session(tmp_path, session_id='session_test'):
    source = tmp_path / f'{session_id}.avi'
    source.write_bytes(b'extended-data')
    session = Session(
        mouseid='014-003',
        uniquesessionid=session_id,
        rigdata={'events': {'value': [1, 2, 3]}},
    )
    session.root = 'root'
    session.segments = {'root': {'slug': 'test'}}
    session._extendeddata = [{'fp': str(source), 'type': 'face_cam'}]
    # Deliberately use a bad public value: serialization must derive it from
    # the registered private source rather than persist a temporary path.
    session.extendeddata = [str(source)]
    session.lock()
    return session, source


def pending_dir(app_dir, session):
    return app_dir / 'pending_sessions' / session.uniquesessionid


def test_failsafe_success_publishes_complete_session(tmp_path):
    handler, lampyr, app_dir, mice_dir = make_handler(tmp_path)
    session, source = make_session(tmp_path)
    lampyr.session = session

    assert handler.savesession() == 'published'

    session_dir = mice_dir / session.mouseid / 'lampyr_sessionhistory'
    extended = (mice_dir / session.mouseid / 'lampyr_extendeddata'
                / session.uniquesessionid / 'face_cam' / source.name)
    assert (session_dir / f'{session.uniquesessionid}.lampyr.h5').is_file()
    json_path = session_dir / f'{session.uniquesessionid}.lampyr.json'
    assert json_path.is_file()
    assert extended.read_bytes() == b'extended-data'
    assert not source.exists()
    assert not pending_dir(app_dir, session).exists()

    saved = json.loads(json_path.read_text())
    assert '_extendeddata' not in saved
    assert saved['extendeddata'] == [str(Path('face_cam') / source.name)]
    assert str(tmp_path) not in json_path.read_text()

    saved_mouse = loadmousefile(session.mouseid, mice_dir / session.mouseid)
    assert [row['sessionid'] for row in saved_mouse.history] == [
        session.uniquesessionid
    ]


def test_publication_failure_leaves_complete_pending_copy(tmp_path, monkeypatch):
    handler, lampyr, app_dir, _ = make_handler(tmp_path)
    session, source = make_session(tmp_path)
    lampyr.session = session
    monkeypatch.setattr(
        handler, '_publish_pending_session',
        lambda _pending: (_ for _ in ()).throw(OSError('network unavailable')),
    )

    assert handler.savesession() == 'pending'

    pending = pending_dir(app_dir, session)
    assert (pending / 'manifest.json').is_file()
    assert (pending / f'{session.uniquesessionid}.lampyr.json').is_file()
    assert (pending / f'{session.uniquesessionid}.lampyr.h5').is_file()
    assert (pending / 'extended' / 'face_cam' / source.name).is_file()
    assert not source.exists()


def test_staging_failure_preserves_extended_source(tmp_path, monkeypatch):
    handler, lampyr, app_dir, _ = make_handler(tmp_path)
    session, source = make_session(tmp_path)
    lampyr.session = session

    def fail_copy(_source, _destination):
        raise OSError('local copy failed')

    monkeypatch.setattr(data_module.shutil, 'copy2', fail_copy)

    with pytest.raises(OSError, match='local copy failed'):
        handler.savesession()

    assert source.is_file()
    assert not pending_dir(app_dir, session).exists()
    assert not list((app_dir / 'pending_sessions').glob('.*'))


def test_startup_recovery_is_idempotent_and_upserts_history(tmp_path, monkeypatch):
    handler, lampyr, app_dir, mice_dir = make_handler(tmp_path)
    session, source = make_session(tmp_path)
    lampyr.session = session
    monkeypatch.setattr(
        handler, '_publish_pending_session',
        lambda _pending: (_ for _ in ()).throw(OSError('offline')),
    )
    assert handler.savesession() == 'pending'

    pending = pending_dir(app_dir, session)
    remote_h5 = (mice_dir / session.mouseid / 'lampyr_sessionhistory'
                  / f'{session.uniquesessionid}.lampyr.h5')
    remote_h5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pending / remote_h5.name, remote_h5)

    mouse = loadmousefile(session.mouseid, mice_dir / session.mouseid)
    mouse.history = [{'sessionid': session.uniquesessionid, 'trial': 'old'}]
    savemousefile(mouse, mice_dir / session.mouseid)

    recovered = DataHandler(SimpleNamespace(
        config=lampyr.config,
        mouse=mouse,
        session=None,
        _input_func=input,
        _output_func=lambda _message: None,
    ))

    assert recovered.enable_failsafe
    assert not pending.exists()
    saved_mouse = loadmousefile(session.mouseid, mice_dir / session.mouseid)
    matching = [row for row in saved_mouse.history
                if row['sessionid'] == session.uniquesessionid]
    assert len(matching) == 1
    assert matching[0]['trial'] == '0'


def test_conflicting_remote_file_is_not_overwritten(tmp_path, monkeypatch):
    handler, lampyr, app_dir, mice_dir = make_handler(tmp_path)
    session, _ = make_session(tmp_path)
    lampyr.session = session
    monkeypatch.setattr(
        handler, '_publish_pending_session',
        lambda _pending: (_ for _ in ()).throw(OSError('offline')),
    )
    assert handler.savesession() == 'pending'

    conflict = (mice_dir / session.mouseid / 'lampyr_sessionhistory'
                / f'{session.uniquesessionid}.lampyr.json')
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_bytes(b'conflicting contents')

    DataHandler(SimpleNamespace(
        config=lampyr.config,
        mouse=lampyr.mouse,
        session=None,
        _input_func=input,
        _output_func=lambda _message: None,
    ))

    assert conflict.read_bytes() == b'conflicting contents'
    assert pending_dir(app_dir, session).is_dir()


def test_disabled_failsafe_uses_direct_save(tmp_path):
    handler, lampyr, app_dir, mice_dir = make_handler(tmp_path, failsafe=False)
    session, source = make_session(tmp_path)
    lampyr.session = session

    assert handler.savesession() == 'published'

    assert not (app_dir / 'pending_sessions').exists()
    assert not source.exists()
    assert (mice_dir / session.mouseid / 'lampyr_sessionhistory'
            / f'{session.uniquesessionid}.lampyr.json').is_file()


def test_close_attempts_all_shutdown_steps_after_failures():
    calls = []
    lampyr = object.__new__(Lampyr)
    lampyr._output_func = lambda _message: None
    lampyr.rigmanager = SimpleNamespace(
        rig=object(),
        disconnect=lambda: (
            calls.append('disconnect'),
            (_ for _ in ()).throw(RuntimeError('disconnect failed')),
        )[-1],
    )
    lampyr.datamanager = SimpleNamespace(
        savesession=lambda: (
            calls.append('session'),
            (_ for _ in ()).throw(RuntimeError('save failed')),
        )[-1],
        _backupmice=lambda: calls.append('backup'),
    )
    lampyr.mousemanager = SimpleNamespace(
        mouse=Mouse(),
        save=lambda: calls.append('mouse'),
    )
    lampyr.session = object()

    with pytest.raises(RuntimeError, match='disconnect failed'):
        lampyr.close()

    assert calls == ['disconnect', 'session', 'mouse', 'backup']
