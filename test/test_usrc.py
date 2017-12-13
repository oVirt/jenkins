#!/usr/bin/env python
"""test_usrc.py - Tests for usrc.py
"""
import pytest
from scripts.usrc import (
    get_upstream_sources, update_upstream_sources,
    commit_upstream_sources_update, GitProcessError, GitUpstreamSource
)
from textwrap import dedent
from hashlib import md5
from subprocess import CalledProcessError
from six import iteritems


class TestGitProcessError(object):
    def test_inheritance(self):
        assert issubclass(GitProcessError, CalledProcessError)


@pytest.fixture
def upstream(gitrepo):
    return gitrepo(
        'upstream',
        {
            'msg': dedent(
                '''
                First US commit

                Some detailed description about the first upstream commit
                '''
            ).lstrip(),
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


class TestGitUpstreamSource(object):
    @pytest.mark.parametrize('struct,expected', [
        (
            dict(url='some/url', branch='br1', commit='some_sha'),
            dict(url='some/url', branch='br1', commit='some_sha'),
        )
    ])
    def test_from_yaml_struct(self, struct, expected):
        out = GitUpstreamSource.from_yaml_struct(struct)
        for exp_attr, exp_val in iteritems(expected):
            assert getattr(out, exp_attr) == exp_val

    @pytest.mark.parametrize('init_args,expected', [
        (
            dict(url='some/url', branch='br1', commit='some_sha'),
            dict(url='some/url', branch='br1', commit='some_sha'),
        )
    ])
    def test_to_yaml_struct(self, init_args, expected):
        gus = GitUpstreamSource(**init_args)
        out = gus.to_yaml_struct()
        assert out == expected

    def test_get(self, upstream, downstream, git_last_sha):
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream)
        )
        assert not (downstream / 'upstream_file.txt').exists()
        gus.get(str(downstream))
        assert (downstream / 'upstream_file.txt').isfile()
        assert (downstream / 'upstream_file.txt').read() == 'Upstream content'
        assert (downstream / 'overriden_file.txt').isfile()
        assert (downstream / 'overriden_file.txt').read() == \
            'Overridden content'

    def test_update(self, gitrepo, upstream, git_last_sha):
        url, branch, commit = str(upstream), 'master', git_last_sha(upstream)
        gus = GitUpstreamSource(url, branch, commit)
        gus_id = id(gus)
        updated = gus.updated()
        assert id(gus) == gus_id
        assert gus.url == url
        assert gus.branch == branch
        assert gus.commit == commit
        assert updated == gus
        assert id(updated) == id(gus)
        gitrepo('upstream', {
            'msg': 'New US commit',
            'files': {
                'upstream_file.txt': 'Updated US content',
                'overriden_file.txt': 'Updated overridden content',
            }
        })
        new_commit = git_last_sha(upstream)
        updated = gus.updated()
        assert id(gus) == gus_id
        assert gus.url == url
        assert gus.branch == branch
        assert gus.commit == commit
        assert updated != gus
        assert id(updated) != id(gus)
        assert updated.url == url
        assert updated.branch == branch
        assert updated.commit == new_commit

    def test_commit_details(self, upstream, git_last_sha, git_at):
        url, branch, commit = str(upstream), 'master', git_last_sha(upstream)
        git = git_at(upstream)
        us_date = git('log', '-1', '--pretty=format:%ad', '--date=rfc').strip()
        us_author = git('log', '-1', '--pretty=format:%an').strip()
        expected = dedent(
            '''
            Project: {project}
            Branch:  {branch}
            Commit:  {sha}
            Author:  {author}
            Date:    {date}

                First US commit

                Some detailed description about the first upstream commit
            '''
        ).lstrip().format(
            project=str(upstream),
            branch='master',
            sha=commit,
            author=us_author,
            date=us_date,
        )
        gus = GitUpstreamSource(url, branch, commit)
        out = gus.commit_details
        assert out == expected

    def test_commit_title(self, upstream, git_last_sha, git_at):
        url, branch, commit = str(upstream), 'master', git_last_sha(upstream)
        expected = "First US commit"
        gus = GitUpstreamSource(url, branch, commit)
        out = gus.commit_title
        assert out == expected


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
        'msg': dedent(
            '''
            New US commit title

            New upstream commit message body with a couple of lines of detailed
            change description text.

            and_some: header
            '''
        ).lstrip(),
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
    mod_list = update_upstream_sources()
    assert len(list(mod_list)) == 1
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
    mod_list = update_upstream_sources()
    assert len(list(mod_list)) == 0
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
    monkeypatch.chdir(updated_upstream)
    us_sha = git('log', '-1', '--pretty=format:%H').strip()
    us_date = git('log', '-1', '--pretty=format:%ad', '--date=rfc').strip()
    us_author = git('log', '-1', '--pretty=format:%an').strip()
    monkeypatch.chdir(downstream)
    updates = update_upstream_sources()
    us_yaml = downstream / 'automation' / 'upstream_sources.yaml'
    us_yaml_md5 = md5(us_yaml.read().encode('utf-8')).hexdigest()
    commit_upstream_sources_update(updates)
    log = git('log', '--pretty=format:%s').splitlines()
    assert len(log) == 2
    assert log == [
        'Updated US source to: {0:.7} New US commit title'.format(us_sha),
        'First DS commit'
    ]
    log = git('log', '-1', '--pretty=format:%b')
    chid_hdr = next(
        (ln for ln in log.splitlines() if ln.startswith('Change-Id: ')), ''
    )
    _, chid = chid_hdr.split(': ', 1)
    assert log == dedent(
        '''
        Updated upstream source commit.
        Commit details follow:

        Project: {project}
        Branch:  {branch}
        Commit:  {sha}
        Author:  {author}
        Date:    {date}

            New US commit title

            New upstream commit message body with a couple of lines of detailed
            change description text.

            and_some: header

        x-md5: {xmd5}
        Change-Id: {chid}
        '''
    ).lstrip().format(
        project=str(updated_upstream),
        branch='master',
        sha=us_sha,
        author=us_author,
        date=us_date,
        xmd5=us_yaml_md5,
        chid=chid,
    )


def test_commit_us_src_no_update(monkeypatch, downstream, git):
    monkeypatch.chdir(downstream)
    commit_upstream_sources_update([])
    log = git('log', '--pretty=format:%s').splitlines()
    assert len(log) == 1
    assert log == ['First DS commit']
