#!/usr/bin/env python
"""test_git_utils.py - Tests for git_utils.py
"""
from textwrap import dedent
from subprocess import CalledProcessError
import pytest
from scripts.git_utils import GitProcessError, git_rev_parse, InvalidGitRef
try:
    from unittest.mock import MagicMock, call, sentinel
except ImportError:
    from mock import MagicMock, call, sentinel


class TestGitProcessError(object):
    def test_inheritance(self):
        assert issubclass(GitProcessError, CalledProcessError)


@pytest.fixture
def repo_with_patches(gitrepo, git_at):
    repo = gitrepo(
        'test_git_repo',
        {
            'msg': 'First commit',
            'files': {'file1.txt': 'F1 content'}
        },
        {
            'msg': 'Second commit',
            'files': {'file2.txt': 'F2 content'}
        }
    )
    git_at(repo)('tag', 'some-tag')
    git_at(repo)('tag', '-a', 'some-atag', '-m', 'some-tag')
    return repo


@pytest.fixture
def git_repo_log(repo_with_patches, git_at):
    def _git_repo_log(ref='refs/heads/master'):
        return git_at(repo_with_patches)(
            'log', '--pretty=format:%H', ref, '--'
        ).splitlines()
    return _git_repo_log


@pytest.mark.parametrize(('ref', 'exp_idx'), [
    ('HEAD', 0),
    ('HEAD^', 1),
    ('refs/heads/master', 0),
    ('master', 0),
    ('master~1', 1),
    ('no/such/ref', InvalidGitRef),
    ('some-tag', 0),
    ('some-atag', 0),
])
def test_git_rev_parse(
    repo_with_patches, git_repo_log, monkeypatch, ref, exp_idx
):
    monkeypatch.chdir(repo_with_patches)
    if isinstance(exp_idx, type) and issubclass(exp_idx, Exception):
        with pytest.raises(exp_idx) as e:
            git_rev_parse(ref)
        assert e.value.ref == ref
    else:
        out = git_rev_parse(ref)
        assert out == git_repo_log()[exp_idx]
