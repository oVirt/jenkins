from typing import Callable
from unittest.mock import MagicMock

import pytest
import yaml

from stdci_tools.usrc_updater import updater_main_cli
from stdci_libs.git_utils import git_rev_parse


@pytest.fixture
def upstream_repo(gitrepo):
    return gitrepo(
        'upstream',
        {
            'msg': 'First upstream commit',
            'files': {
                'upstream_file': 'upstream file content'
            },
        },
    )


@pytest.fixture
def midstream_repo(gitrepo, upstream_repo):
    return gitrepo(
        'midstream',
        {
            'msg': 'First commit',
            'files': {
                'upstream_sources.yaml': yaml.safe_dump({
                    'git': [
                        {
                            'url': f'{str(upstream_repo)}',
                            'commit': 'this-should-be-updated-by-usrc',
                            'branch': 'master'
                        },
                    ],
                })
            },
        }
    )


@pytest.mark.parametrize('call_with_env', [True, False])
def test_updater_main(
        tmpdir, upstream_repo, midstream_repo, git_at, monkeypatch,
        gerrit_push_map, run_click_command, call_with_env):
    monkeypatch.chdir(tmpdir)
    # we need to mock this because the tool is actually designed to work with
    # Gerrit but in the test we don't have an actual Gerrit server
    mock_check_if_similar_patch_pushed = MagicMock(return_value=False)
    monkeypatch.setattr(
        'stdci_tools.pusher.check_if_similar_patch_pushed',
        mock_check_if_similar_patch_pushed
    )
    midstream_git = git_at(midstream_repo)

    if call_with_env:
        monkeypatch.setenv('REPO_URL', str(midstream_repo))
        monkeypatch.setenv('REPO_REF', 'refs/heads/master')
        monkeypatch.setenv('REPO_PUSH_BRANCH', 'other_branch')
        monkeypatch.setenv('PUSHER_PUSH_MAP', str(gerrit_push_map))
        run_click_command(updater_main_cli, '-d', '-v')
    else:
        run_click_command(
            updater_main_cli, '-d', '-v',
            str(midstream_repo),
            'refs/heads/master',
            'other_branch',
            str(gerrit_push_map))

    assert mock_check_if_similar_patch_pushed.called, \
        'expected check if similar patch pushed to be called'
    other_branch_sha = git_rev_parse('refs/for/other_branch', midstream_git)
    head_sha = git_rev_parse('HEAD', midstream_git)
    assert head_sha == other_branch_sha, \
        'expected push to occur to other_branch and sha to be the same as HEAD'
