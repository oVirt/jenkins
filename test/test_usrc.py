#!/usr/bin/env python
"""test_usrc.py - Tests for usrc.py
"""
from six import iteritems
import pytest
from functools import partial
from scripts.usrc import (
    get_upstream_sources, update_upstream_sources,
    commit_upstream_sources_update, git
)
from textwrap import dedent
from hashlib import md5


def git_at(path):
    return partial(
        git,
        '--git-dir={0}'.format(path / '.git'),
        '--work-tree={0}'.format(str(path))
    )


@pytest.fixture
def gitrepo(tmpdir):
    def repo_maker(reponame, *commits):
        repodir = tmpdir / reponame
        repogit = git_at(repodir)
        git('init', str(repodir))
        for i, commit in enumerate(commits):
            for fname, fcontents in iteritems(commit.get('files', {})):
                (repodir / fname).write(fcontents, ensure=True)
                repogit('add', fname)
            repogit('commit', '-m', commit.get('msg', "Commit #{0}".format(i)))
        return repodir
    return repo_maker


def last_sha(repo_path):
    return git_at(repo_path)('log', '--format=format:%H', '-1').rstrip()


def test_gitrepo(gitrepo):
    repo = gitrepo(
        'tst_repo',
        {
            'msg': 'First commit',
            'files': {
                'fil1.txt': 'Text of fil1',
                'fil2.txt': 'Text of fil2',
            },
        },
        {
            'msg': 'Second commit',
            'files': {
                'fil2.txt': 'Modified text of fil2',
                'fil3.txt': 'Text of fil3',
            },
        },
    )
    assert (repo / '.git').isdir()
    assert (repo / 'fil1.txt').isfile()
    assert (repo / 'fil1.txt').read() == 'Text of fil1'
    assert (repo / 'fil2.txt').isfile()
    assert (repo / 'fil2.txt').read() == 'Modified text of fil2'
    assert (repo / 'fil3.txt').isfile()
    assert (repo / 'fil3.txt').read() == 'Text of fil3'
    repogit = git_at(repo)
    assert repogit('status', '--short') == ''
    assert repogit('status', '-v').splitlines()[0].endswith('On branch master')
    log = repogit('log', '--pretty=format:%s').splitlines()
    assert len(log) == 2
    assert log == ['Second commit', 'First commit']
    # Test adding commits to existing repo during test
    gitrepo(
        'tst_repo',
        {
            'msg': 'Third commit',
            'files': {
                'fil3.txt': 'Modified text of fil3',
                'fil4.txt': 'Text of fil4',
            },
        },
    )
    assert (repo / 'fil1.txt').isfile()
    assert (repo / 'fil1.txt').read() == 'Text of fil1'
    assert (repo / 'fil2.txt').isfile()
    assert (repo / 'fil2.txt').read() == 'Modified text of fil2'
    assert (repo / 'fil3.txt').isfile()
    assert (repo / 'fil3.txt').read() == 'Modified text of fil3'
    assert (repo / 'fil4.txt').isfile()
    assert (repo / 'fil4.txt').read() == 'Text of fil4'
    assert repogit('status', '--short') == ''
    log = repogit('log', '--pretty=format:%s').splitlines()
    assert len(log) == 3
    assert log == ['Third commit', 'Second commit', 'First commit']


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
def downstream(gitrepo, upstream):
    sha = last_sha(upstream)
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


def test_update_upstream_sources(monkeypatch, updated_upstream, downstream):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    gstatus = git('status', '--short', '--porcelain').rstrip()
    assert gstatus == ''
    update_upstream_sources()
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    gstatus = git('status', '--short', '--porcelain').rstrip()
    assert gstatus == ' M automation/upstream_sources.yaml'
    get_upstream_sources()
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Updated US content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


def test_no_update_upstream_sources(monkeypatch, upstream, downstream):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    gstatus = git('status', '--short', '--porcelain').rstrip()
    assert gstatus == ''
    update_upstream_sources()
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    gstatus = git('status', '--short', '--porcelain').rstrip()
    assert gstatus == ''
    get_upstream_sources()
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Upstream content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


def test_commit_us_src_update(monkeypatch, updated_upstream, downstream):
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


def test_commit_us_src_no_update(monkeypatch, downstream):
    monkeypatch.chdir(downstream)
    commit_upstream_sources_update()
    log = git('log', '--pretty=format:%s').splitlines()
    assert len(log) == 1
    assert log == ['First DS commit']
