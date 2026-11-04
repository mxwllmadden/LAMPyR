from types import SimpleNamespace
from unittest.mock import Mock

from click.testing import CliRunner
import lampyr.ui.click_cli.app as cli_app


def test_open_folder_uses_linux_default_file_explorer(monkeypatch, tmp_path):
    popen = Mock()
    monkeypatch.setattr(cli_app.sys, "platform", "linux")
    monkeypatch.setattr(cli_app.subprocess, "Popen", popen)

    cli_app._open_folder_in_file_explorer(tmp_path)

    popen.assert_called_once_with(["xdg-open", str(tmp_path)])


def test_open_folder_uses_windows_file_explorer(monkeypatch, tmp_path):
    startfile = Mock()
    monkeypatch.setattr(cli_app.sys, "platform", "win32")
    monkeypatch.setattr(cli_app.os, "startfile", startfile, raising=False)

    cli_app._open_folder_in_file_explorer(tmp_path)

    startfile.assert_called_once_with(str(tmp_path))


def test_open_config_command_opens_config_directory(monkeypatch, tmp_path):
    config_dir = tmp_path / "lampyr"
    config_dir.mkdir()
    open_folder = Mock()

    class FakeLampyr:
        def __init__(self):
            self.config = SimpleNamespace(
                _APP_DATA_DIR=str(config_dir),
                get=lambda key: False,
            )

        def close(self):
            pass

    monkeypatch.setattr(cli_app, "Lampyr", FakeLampyr)
    monkeypatch.setattr(cli_app, "_open_folder_in_file_explorer", open_folder)

    result = CliRunner().invoke(cli_app.cli, ["open-config"])

    assert result.exit_code == 0
    assert f"Opened configuration folder: {config_dir}" in result.output
    open_folder.assert_called_once_with(str(config_dir))


def test_open_config_reports_missing_directory(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing"

    class FakeLampyr:
        def __init__(self):
            self.config = SimpleNamespace(
                _APP_DATA_DIR=str(missing_dir),
                get=lambda key: False,
            )

        def close(self):
            pass

    monkeypatch.setattr(cli_app, "Lampyr", FakeLampyr)

    result = CliRunner().invoke(cli_app.cli, ["open-config"])

    assert result.exit_code != 0
    assert f"Configuration folder does not exist: {missing_dir}" in result.output
