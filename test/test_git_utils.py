#!/usr/bin/env python
"""test_git_utils.py - Tests for git_utils.py
"""
import os
from textwrap import dedent
from subprocess import CalledProcessError
import pytest
from stdci_libs.git_utils import (
    GitProcessError, git_rev_parse, InvalidGitRef, prep_git_repo,
    get_name_from_repo_url, CouldNotParseRepoURL
)
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


def test_prep_git_repo(
        monkeypatch, tmpdir, git_at, repo_with_patches, git_last_sha):
    # we need this nested tmpdir because `repo_with_patches` exists in the
    # default tmpdir and the new git repo we initialize will have the same name
    tmpdir = tmpdir / 'tmpdir'
    tmpdir.mkdir()
    monkeypatch.chdir(tmpdir)
    repo_url = str(repo_with_patches)
    refspec = 'master'
    git_func, last_sha = prep_git_repo(
        tmpdir, repo_url, refspec, checkout=True)
    # we can't use get-url because on centos7 the git version is too old
    remote_url = git_func('remote', '-v').split()[1]
    assert remote_url == repo_url, \
        'expected git func to return the URL for repo_with_patches'
    assert last_sha == git_rev_parse('HEAD', git_func), (
        'expected to find the fetched sha at the HEAD'
        ' of the checked out branch'
    )


@pytest.mark.parametrize('repo_url,expected_name', [
    ('proto://some-scm.com/org/repo_name', 'repo_name'),
    ('proto://some-scm.com/repo_name', 'repo_name'),
    ('proto://some-scm.com/org/repo_name.git', 'repo_name'),
    ('proto://some-scm.com/repo_name.git', 'repo_name'),
])
def test_get_name_from_repo_url(repo_url, expected_name):
    assert get_name_from_repo_url(repo_url) == expected_name


@pytest.mark.parametrize('repo_url', [

    '', 'proto://', 'proto://scm-name.com/'

])
def test_get_name_from_repo_url_exception(repo_url):
    with pytest.raises(CouldNotParseRepoURL):
        get_name_from_repo_url(repo_url)
