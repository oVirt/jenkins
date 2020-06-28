import logging
from functools import partial
from unittest.mock import MagicMock, sentinel, create_autospec

import pytest

from stdci_libs.git_utils import git
import stdci_libs.actuators.updaters
from stdci_libs.actuators.updaters import updater_main, committing_updater


@pytest.fixture
def midstream_repo(gitrepo):
    return gitrepo(
        'midstream',
        {
            'msg': 'First upstream commit',
            'files': {
                'some_file': 'line1'
            },
        },
    )


def add_line_to_file_updater(filename: str, content: str):
    with open(filename, mode='a', encoding='utf-8') as fd:
        fd.write('\n')
        fd.write(content)

    git('add', filename)
    git('commit', '-m', f'added a line to {filename}')


def test_updater_main(
    tmpdir,
    midstream_repo,
    monkeypatch,
    gerrit_push_map,
    git_at
):
    # A different directory is needed since the "midstream_repo"
    # "Which represents the remote repo is cloned into "tmpdir"
    workdir = tmpdir / 'workdir'
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    # we need to mock this because the tool is actually designed to work with
    # Gerrit but in the test we don't have an actual Gerrit server
    mock_check_if_similar_patch_pushed = MagicMock(return_value=False)
    monkeypatch.setattr(
        'stdci_tools.pusher.check_if_similar_patch_pushed',
        mock_check_if_similar_patch_pushed
    )
    updater_main(
        repo_url=str(midstream_repo),
        refspec='refs/heads/master',
        target_branch='master',
        push_map=str(gerrit_push_map),
        updater_func=partial(
            add_line_to_file_updater,
            filename='some_file',
            content='line2'
        ),
        logger=logging.getLogger(),
    )
    expected_lines = ['line1', 'line2']
    midstream_git = git_at(midstream_repo)
    actual_lines = midstream_git(
        'show', 'refs/for/master:some_file'
    ).splitlines()

    assert expected_lines == actual_lines


def test_committing_updater(monkeypatch):
    fake_kwarg = {'some_key': sentinel.fake_value}
    fake_repo_url = sentinel.repo_url
    fake_refspec = sentinel.refspec
    fake_target_branch = sentinel.target_branch
    fake_push_map = sentinel.push_map
    fake_updater = sentinel.updater
    fake_looger = sentinel.logger

    updater_main_mock = create_autospec(updater_main)
    monkeypatch.setattr(
        stdci_libs.actuators.updaters,
        'updater_main',
        updater_main_mock
    )

    @committing_updater
    def fake_updater_cli(committing_updater_func, **kwargs):
        committing_updater_func(
            updater_func=fake_updater,
            logger=fake_looger
        )
        assert kwargs == fake_kwarg

    fake_updater_cli(
        repo_url=fake_repo_url,
        refspec=fake_refspec,
        target_branch=fake_target_branch,
        push_map=fake_push_map,
        **fake_kwarg
    )

    updater_main_mock.assert_called_once_with(
        repo_url=fake_repo_url,
        refspec=fake_refspec,
        target_branch=fake_target_branch,
        push_map=fake_push_map,
        updater_func=fake_updater,
        logger=fake_looger
    )
