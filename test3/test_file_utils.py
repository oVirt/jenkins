import pytest

from stdci_libs import file_utils
import os


def test_workdir(monkeypatch, tmpdir):
    newdir = tmpdir / 'newdir'
    newdir.mkdir()
    monkeypatch.chdir(tmpdir)
    with file_utils.workdir(str(newdir)) as cwd:
        assert cwd == str(newdir), 'expected cwd to be newdir'
        assert os.getcwd() == cwd, 'expected to be in newdir'
    assert os.getcwd() == str(tmpdir), 'expected to be in tmpdir'


def test_workdir_exception(monkeypatch, tmpdir):
    newdir = tmpdir / 'newdir'
    monkeypatch.chdir(tmpdir)
    with pytest.raises(OSError) as excinfo:
        with file_utils.workdir(str(newdir)) as cwd:
            pass  # should failed here
    assert excinfo.value.errno == 2, 'expected errno to be 2 (no such file)'
