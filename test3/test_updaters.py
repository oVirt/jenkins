import logging
import re
from click import command
from functools import partial
from unittest.mock import MagicMock, sentinel, create_autospec

import pytest

from stdci_libs.git_utils import git
import stdci_libs.actuators.updaters
from stdci_libs.actuators.updaters import updater_main, committing_updater
from stdci_libs.actuators.common import automerge_opt


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

    git('config', 'user.name', 'test user')
    git('config', 'user.email', 'test@example.com')
    git('add', filename)
    git('commit', '-m', f'added a line to {filename}')


def add_line_to_file_updater_no_commit(filename: str, content: str):
    with open(filename, mode='a', encoding='utf-8') as fd:
        fd.write('\n')
        fd.write(content)

    git('config', 'user.name', 'test user')
    git('config', 'user.email', 'test@example.com')


@pytest.mark.parametrize('updater_func, commit_files, automerge, expected_lines', [
        (
            partial(
                add_line_to_file_updater,
                filename='some_file',
                content='line2'
            ),
            False,
            True,
            ['line1', 'line2']
        ),
        (
            partial(
                add_line_to_file_updater_no_commit,
                filename='some_file',
                content='line2'
            ),
            True,
            True,
            ['line1', 'line2']
        ),
        (
            partial(
                add_line_to_file_updater_no_commit,
                filename='some_file',
                content='line2'
            ),
            True,
            False,
            ['line1', 'line2']
        )
    ]
)
def test_updater_main(
    tmpdir,
    midstream_repo,
    monkeypatch,
    gerrit_push_map,
    git_at,
    updater_func,
    commit_files,
    automerge,
    expected_lines
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
        updater_func=updater_func,
        execute_commit=commit_files,
        logger=logging.getLogger(),
        automerge=automerge,
    )
    midstream_git = git_at(midstream_repo)
    actual_lines = midstream_git(
        'show', 'refs/for/master:some_file'
    ).splitlines()

    assert expected_lines == actual_lines

    if commit_files:
        actual_message_lines = midstream_git(
            'log',  '-1', '--pretty=format:%b', 'refs/for/master'
        ).splitlines()
        headers = {}
        if automerge:
            headers["automerge"] = 'yes'

        for header, value in headers.items():
            pattern = f"^{header}: {value}"
            matched_lines = [line for line in actual_message_lines \
                  if re.match(pattern, line, flags=re.IGNORECASE)]
            assert matched_lines, f"Header '{pattern}' not found in commit message"


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
        logger=fake_looger,
    )


@pytest.mark.parametrize('call_with_env, automerge', [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ]
)
def test_automerge_opt(monkeypatch, run_click_command, call_with_env, automerge):
    # The automerge_opt is not used by updaters.py, as it is to be used by updaters.
    # This unit test covers it.
    cmd_opts = []
    if automerge:
        cmd_opts.append('--automerge')

    expected_kwargs = {
        'automerge': automerge,
    }

    def dummy_func(*args, **kwargs):
        pass

    mock_dummy_func = create_autospec(dummy_func)
   
    @command()
    @automerge_opt
    def dummy_updater_cli(*args, **kwargs):
        mock_dummy_func(*args, **kwargs)

    
    if call_with_env:
        monkeypatch.setenv('AUTOMERGE', str(automerge))
        run_click_command(dummy_updater_cli)
    else:
        run_click_command(
            dummy_updater_cli,
            *cmd_opts,
        )

    mock_dummy_func.assert_called_once_with(**expected_kwargs)

