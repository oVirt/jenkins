#!/usr/bin/env python
"""test_usrc.py - Tests for usrc.py
"""
import pytest
from scripts.usrc import (
    get_upstream_sources, update_upstream_sources,
    commit_upstream_sources_update, GitProcessError
)
from textwrap import dedent
from hashlib import md5
from subprocess import CalledProcessError


class TestGitProcessError(object):
    def test_inheritance(self):
        assert issubclass(GitProcessError, CalledProcessError)


@pytest.fixture
def upstream(gitrepo):
    return gitrepo(
        'upstream',
        {
            'msg': 'First US commit',
            'files': {
                'upstream_file.txt': 'Upstream content',
                'overriden_file.txt': 'Overridden content',
            },
        },
    )


@pytest.fixture
def downstream(gitrepo, upstream, git_last_sha):
    sha = git_last_sha(upstream)
    return gitrepo(
        'downstream',
        {
            'msg': 'First DS commit',
            'files': {
                'downstream_file.txt': 'Downstream content',
                'overriden_file.txt': 'Overriding content',
                'automation/upstream_sources.yaml': dedent(
                    """
                    ---
                    git:
                      - url: {upstream}
                        commit: {sha}
                        branch: master
                    """
                ).lstrip().format(upstream=str(upstream), sha=sha)
            },
        },
    )


def test_get_upstream_sources(monkeypatch, downstream):
    monkeypatch.chdir(downstream)
    assert not (downstream / 'upstream_file.txt').exists()
    get_upstream_sources()
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Upstream content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


@pytest.fixture
def updated_upstream(gitrepo, upstream, downstream):
    # We include the upstream and downstream fixtures as parameters to ensure
    # they get created before this fixture
    # Add an upstream commit
    return gitrepo('upstream', {
        'msg': 'New US commit',
        'files': {
            'upstream_file.txt': 'Updated US content',
            'overriden_file.txt': 'Updated overridden content',
        }
    })


def test_update_upstream_sources(
    monkeypatch, updated_upstream, downstream, git_status
):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    update_upstream_sources()
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ' M automation/upstream_sources.yaml'
    get_upstream_sources()
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Updated US content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


def test_no_update_upstream_sources(
    monkeypatch, upstream, downstream, git_status
):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    update_upstream_sources()
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    get_upstream_sources()
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Upstream content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


def test_commit_us_src_update(monkeypatch, updated_upstream, downstream, git):
    monkeypatch.chdir(downstream)
    update_upstream_sources()
    us_yaml = downstream / 'automation' / 'upstream_sources.yaml'
    us_yaml_md5 = md5(us_yaml.read().encode('utf-8')).hexdigest()
    commit_upstream_sources_update()
    log = git('log', '--pretty=format:%s').splitlines()
    assert len(log) == 2
    assert log == ['Changed commit SHA1', 'First DS commit']
    log = git('log', '-1', '--pretty=format:%b').splitlines()
    md5_header = next((line for line in log if line.startswith('x-md5: ')), '')
    assert md5_header == 'x-md5: ' + us_yaml_md5


def test_commit_us_src_no_update(monkeypatch, downstream, git):
    monkeypatch.chdir(downstream)
    commit_upstream_sources_update()
    log = git('log', '--pretty=format:%s').splitlines()
    assert len(log) == 1
    assert log == ['First DS commit']
