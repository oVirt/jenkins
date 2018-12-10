#!/usr/bin/env python
"""test_usrc.py - Tests for usrc.py
"""
import os
import pytest
from scripts.usrc import (
    get_upstream_sources, update_upstream_sources,
    commit_upstream_sources_update, GitProcessError, GitUpstreamSource,
    generate_update_commit_message, git_ls_files, git_read_file, ls_all_files,
    files_diff, get_modified_files, get_files_to_links_map, GitFile,
)
from textwrap import dedent
from hashlib import md5
from subprocess import CalledProcessError
from six import iteritems
from six.moves import map
try:
    from unittest.mock import MagicMock, call, sentinel
except ImportError:
    from mock import MagicMock, call, sentinel
from functools import cmp_to_key
from scripts.git_utils import git_rev_parse
from scripts import usrc

class TestGitProcessError(object):
    def test_inheritance(self):
        assert issubclass(GitProcessError, CalledProcessError)


@pytest.fixture
def upstream(gitrepo, symlinkto):
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
                'link_to_file': symlinkto('upstream_file.txt'),
                'file2': 'Just a file',
                'file3': 'Yet another file',
            },
        },
    )


@pytest.fixture
def downstream(gitrepo, upstream, git_last_sha, symlinkto):
    sha = git_last_sha(upstream)
    return gitrepo(
        'downstream',
        {
            'msg': 'First DS commit',
            'files': {
                'downstream_file.txt': 'Downstream content',
                'overriden_file.txt': 'Overriding content',
                'temp/downstream_file.txt': 'Downstream content',
                'temp/overriden_file.txt': 'Overriding content',
                'automation/upstream_sources.yaml': dedent(
                    """
                    ---
                    git:
                      - url: {upstream}
                        commit: {sha}
                        branch: master
                    """
                ).lstrip().format(upstream=str(upstream), sha=sha),
                'link_to_upstream_link': symlinkto('link_to_file'),
                'changing_link': symlinkto('link_to_file'),
            },
        },
    )


@pytest.fixture
def upstream_scenarios_for_tests(
        gitrepo, git_last_sha, git_tag, git_branch, git_at
    ):
    """
    This is a demonstration of the git repo commits:
    Both commit nodes E and D are childrens of commit node C.
    B commit points to sample_git_branch, A, C , E commits points to master,
    and D commit points to another_git_branch.
    A commit points to a_tag, B commit points to b_tag,
    C commits points to c_tag.

    a_tag <------A
               / |
    b_tag <---B  |
                 |
    c_tag <------C
                 | \
                 |  \
                 E   D---> d_tag

           E = HEAD = E^0         - master
           C = E^   = E~1 = c_tag - master
           A = E^^1 = A~2 = a_tag - master
           D = HEAD = D^0 = d_tag - another_git_branch
           B = HEAD = B^0 = b_tag - sample_git_branch
    """
    repo = gitrepo(
        'upstream',
        {
            'msg': 'First commit',
            'files': {
                'a.txt': 'A content'
            },
        },

    )
    with git_branch('upstream', 'sample_git_branch'):
        gitrepo(
            'upstream',
            {
                'msg': 'Second commit',
                'files': {
                    'b.txt': 'B content',
                    }
            },
        )
    with git_branch('upstream', 'master'):
        git_tag('upstream', 'a_tag', 'a tag')
        gitrepo('upstream', {
            'msg': 'Third commit',
            'files': {
                'c.txt': 'C content',
            }
        })
        git_tag('upstream', 'c_tag', 'newer annotated tag')

    with git_branch('upstream', 'sample_git_branch'):
        git_tag('upstream', 'b_tag', 'pointing to commit b')

    with git_branch('upstream', 'another_git_branch'):
        gitrepo(
            'upstream',
            {
                'msg': 'Fourth commit',
                'files': {
                    'd.txt': 'D content',
                }
            }
        )
        git_tag('upstream', 'd_tag', 'pointing to commit d')

    with git_branch('upstream', 'master'):
        gitrepo('upstream', {
            'msg': 'Fifth commit',
            'files': {
                'e.txt': 'E content',
            }
        })
    return repo

class TestGitUpstreamSource(object):
    @pytest.mark.parametrize('struct,expected', [
        (
            dict(url='some/url', branch='br1', commit='some_sha'),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='never',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='never',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='True',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='False',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge=True,
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge=False,
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('latest'), tag_filter='tag*',
                annotated_tag_only='yes'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('latest'), tag_filter='tag*',
                annotated_tag_only='yes'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged'), tag_filter=None,
                annotated_tag_only='yes'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged'), tag_filter=None,
                annotated_tag_only='yes'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged', 'latest'),
                annotated_tag_only=None
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged', 'latest'),
                annotated_tag_only='no'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=False,
                annotated_tag_only='no'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('latest'),
                annotated_tag_only='no'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=False,
                annotated_tag_only='yes'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('latest'),
                annotated_tag_only='yes'
            ),
        ),
    ])
    def test_from_yaml_struct(self, struct, expected):
        out = GitUpstreamSource.from_yaml_struct(struct)
        for exp_attr, exp_val in iteritems(expected):
            assert getattr(out, exp_attr) == exp_val

    @pytest.mark.parametrize('init_args,expected', [
        (
            dict(url='some/url', branch='br1', commit='some_sha'),
            dict(url='some/url', branch='br1', commit='some_sha'),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='never',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='never',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='no',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='True',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='False',
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge=True,
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge='yes',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                automerge=False,
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=False
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=['latest', 'tagged']
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=['latest', 'tagged']
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=['tagged']
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=['tagged']
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                tag_filter=None
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                tag_filter='some_tag'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                tag_filter='some_tag'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                annotated_tag_only='yes'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                annotated_tag_only='yes'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                annotated_tag_only=None
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                annotated_tag_only='no'
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha'
            ),
        ),
    ])
    def test_to_yaml_struct(self, init_args, expected):
        gus = GitUpstreamSource(**init_args)
        out = gus.to_yaml_struct()
        assert out == expected

    @pytest.mark.parametrize('struct,expected', [
            (
                ('master', 'master~2', ('tagged')),
                ('master~1')
            ),
            (
                ('master', 'master~2', ('tagged', 'latest')),
                ('master~1')
            ),
            (
                ('master', 'master~2', ('latest')),
                ('master')
            ),
            (
                ('sample_git_branch', 'sample_git_branch^1', ('tagged')),
                ('sample_git_branch')
            ),
            (
                ('another_git_branch', 'another_git_branch~2', ('tagged')),
                ('another_git_branch')
            ),
            (
                ('another_git_branch', 'another_git_branch~1',
                    ('tagged', 'latest')),
                ('another_git_branch')
            ),
        ]
    )
    def test_tag_updated(
        self, struct, expected,
        upstream_scenarios_for_tests, git_branch, monkeypatch
    ):
        monkeypatch.setattr(usrc, 'xdg_cache_home', '/tmp/test_tag_updated/')
        monkeypatch.chdir(upstream_scenarios_for_tests)
        url = str(upstream_scenarios_for_tests)
        branch, commit, update_policy = struct
        commit = git_rev_parse(commit)
        gus = GitUpstreamSource(
            url=url, branch=branch, commit=commit,
            update_policy=update_policy
        )
        out = gus.updated().commit
        assert out == git_rev_parse(expected)

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

    def test_get_dest_dir(self, upstream, downstream, git_last_sha):
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream), 'no', 'temp'
        )
        assert not (downstream / 'temp' / 'upstream_file.txt').exists()
        gus.get(str(downstream))
        assert not (downstream / 'upstream_file.txt').isfile()
        assert (downstream / 'downstream_file.txt').isfile()
        assert (downstream / 'downstream_file.txt').read() == \
            'Downstream content'
        assert (downstream / 'overriden_file.txt').isfile()
        assert (downstream / 'overriden_file.txt').read() == \
            'Overriding content'
        assert (downstream / 'temp' / 'upstream_file.txt').isfile()
        assert (downstream / 'temp' / 'upstream_file.txt').read() == \
            'Upstream content'
        assert (downstream / 'temp' / 'overriden_file.txt').isfile()
        assert (downstream / 'temp' / 'overriden_file.txt').read() == \
            'Overridden content'

    def test_update(self, gitrepo, upstream, git_last_sha):
        url, branch, commit = str(upstream), 'master', git_last_sha(upstream)
        files_dest_dir = 'temp'
        gus = GitUpstreamSource(url, branch, commit, 'no', files_dest_dir)
        gus_id = id(gus)
        updated = gus.updated()
        assert id(gus) == gus_id
        assert gus.url == url
        assert gus.branch == branch
        assert gus.commit == commit
        assert gus.files_dest_dir == files_dest_dir
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
        assert gus.files_dest_dir == files_dest_dir
        assert updated != gus
        assert id(updated) != id(gus)
        assert updated.url == url
        assert updated.branch == branch
        assert updated.commit == new_commit
        assert updated.files_dest_dir == files_dest_dir

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

    def test_ls_files(self, monkeypatch):
        git_ls_files = MagicMock(side_effect=(sentinel.some_files,))
        fetch = MagicMock()
        monkeypatch.setattr('scripts.usrc.git_ls_files', git_ls_files)
        gus = GitUpstreamSource('git://url.of/repo', 'a_branch', 'a_commit')
        gus._fetch = fetch
        out = gus.ls_files()
        assert git_ls_files.called
        assert git_ls_files.call_args == \
            call('a_commit', git_func=gus._cache_git)
        assert fetch.called
        assert out == sentinel.some_files


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


@pytest.mark.parametrize('updates,expected', [
    (
        [dict(commit_title='commit 1')],
        dedent(
            '''
            Updated US source to: 1234567 commit 1

            Updated upstream source commit.
            Commit details follow:

            COMMIT 1 DETAILS

            '''
        ).lstrip(),
    ),
    (
        [dict(commit_title='commit 1'), dict(commit_title='commit 2')],
        dedent(
            '''
            Updated 2 upstream sources

            Updated upstream source commits.
            Updated commit details follow:

            COMMIT 1 DETAILS

            COMMIT 2 DETAILS

            '''
        ).lstrip(),
    ),
    (
        [dict(commit_title='commit 1', automerge='yes')],
        dedent(
            '''
            Updated US source to: 1234567 commit 1

            Updated upstream source commit.
            Commit details follow:

            COMMIT 1 DETAILS

            automerge: yes
            '''
        ).lstrip(),
    ),
    (
        [dict(commit_title='commit 1', automerge='no')],
        dedent(
            '''
            Updated US source to: 1234567 commit 1

            Updated upstream source commit.
            Commit details follow:

            COMMIT 1 DETAILS

            '''
        ).lstrip(),
    ),
    (
        [dict(commit_title='commit 1', automerge='never')],
        dedent(
            '''
            Updated US source to: 1234567 commit 1

            Updated upstream source commit.
            Commit details follow:

            COMMIT 1 DETAILS

            '''
        ).lstrip(),
    ),
    (
        [
            dict(commit_title='commit 1', automerge='yes'),
            dict(commit_title='commit 2', automerge='no'),
        ],
        dedent(
            '''
            Updated 2 upstream sources

            Updated upstream source commits.
            Updated commit details follow:

            COMMIT 1 DETAILS

            COMMIT 2 DETAILS

            automerge: yes
            '''
        ).lstrip(),
    ),
    (
        [
            dict(commit_title='commit 1', automerge='never'),
            dict(commit_title='commit 2', automerge='yes'),
        ],
        dedent(
            '''
            Updated 2 upstream sources

            Updated upstream source commits.
            Updated commit details follow:

            COMMIT 1 DETAILS

            COMMIT 2 DETAILS

            '''
        ).lstrip(),
    ),
])
def test_generate_update_commit_message(updates, expected):
    def mock_update_object(update_dict):
        commit_title = update_dict['commit_title']
        return MagicMock(
            commit_title=commit_title,
            commit=update_dict.get(
                'commit', '1234567890abcdef1234567890abcdef12345678'
            ),
            commit_details=update_dict.get(
                'commit_details', (commit_title + ' details').upper()
            ),
            automerge=update_dict.get('automerge', 'no')
        )
    out = generate_update_commit_message(map(mock_update_object, updates))
    assert out == expected


@pytest.fixture
def some_commits(gitrepo, git_at):
    gr = gitrepo(
        'some_commits',
        {
            'msg': 'Initial commit',
        },
        {
            'msg': 'First commit',
            'files': {
                'unmodified.txt': 'Unmodified content',
                'modified_in_2nd_commit.txt': 'abcdef',
                'modified_in_3rd_commit.txt': 'ghijkl',
                'removed_in_2nd_commit.txt': 'mnopqr',
                'removed_in_3rd_commit.txt': 'stuvwx',
            },
        },
        {
            'msg': 'Second commit',
            'files': {
                'modified_in_2nd_commit.txt': 'yz1234',
                'removed_in_2nd_commit.txt': None,
                'added_in_2nd_commit.txt': '567890',
                'removed_in_3rd_commit_too.txt': 'ABCDEF',
            },
        },
        {
            'msg': 'Third commit',
            'files': {
                'modified_in_3rd_commit.txt': 'GHIJKL',
                'removed_in_3rd_commit.txt': None,
                'removed_in_3rd_commit_too.txt': None,
            },
        },
    )
    git = git_at(gr)
    git('branch', 'first-commit', 'HEAD^^')
    git('branch', 'second-commit', 'HEAD^')
    git('branch', 'third-commit', 'HEAD')
    return gr


@pytest.mark.parametrize('commit, expected', [
    ('HEAD', [
        u'unmodified.txt',
        u'modified_in_2nd_commit.txt',
        u'modified_in_3rd_commit.txt',
        u'added_in_2nd_commit.txt',
    ]),
    ('HEAD^', [
        u'unmodified.txt',
        u'modified_in_2nd_commit.txt',
        u'modified_in_3rd_commit.txt',
        u'added_in_2nd_commit.txt',
        u'removed_in_3rd_commit.txt',
        u'removed_in_3rd_commit_too.txt',
    ]),
    ('first-commit', [
        u'unmodified.txt',
        u'modified_in_2nd_commit.txt',
        u'modified_in_3rd_commit.txt',
        u'removed_in_2nd_commit.txt',
        u'removed_in_3rd_commit.txt',
    ]),
])
def test_git_ls_files(monkeypatch, some_commits, commit, expected):
    monkeypatch.chdir(some_commits)
    out = git_ls_files(commit)
    assert sorted(out) == sorted(expected)


def test_git_ls_files_git_func():
    files = dedent(
        u'''
        100644 blob d96dc95707c20a371b14928ee42071f00e00b645\tfile1.txt
        100644 blob 08cf76c72911f5f336ec71e1c9045dfd3107b92e\tfile2.txt
        '''
    ).lstrip()
    git_func = MagicMock(side_effect=(files,))
    out = git_ls_files('some_commit', git_func=git_func)
    assert git_func.called
    assert git_func.call_args == \
        call('ls-tree', '--full-tree', '-r', 'some_commit')
    assert out == {
        'file1.txt': (0o100644, 'd96dc95707c20a371b14928ee42071f00e00b645'),
        'file2.txt': (0o100644, '08cf76c72911f5f336ec71e1c9045dfd3107b92e'),
    }


@pytest.mark.parametrize('path, commit, expected', [
    ('modified_in_3rd_commit.txt', 'HEAD', u'GHIJKL'),
    ('modified_in_3rd_commit.txt', None, u'GHIJKL'),
    ('modified_in_3rd_commit.txt', 'HEAD^', u'ghijkl'),
    ('modified_in_3rd_commit.txt', 'HEAD^^', u'ghijkl'),
    ('modified_in_2nd_commit.txt', 'HEAD', u'yz1234'),
    ('modified_in_2nd_commit.txt', 'HEAD^', u'yz1234'),
    ('modified_in_2nd_commit.txt', 'HEAD^^', u'abcdef'),
    ('added_in_2nd_commit.txt', 'second-commit', u'567890'),
    ('added_in_2nd_commit.txt', 'second-commit^', GitProcessError),
    ('no_such_file.txt', 'HEAD', GitProcessError),
])
def test_git_read_file(monkeypatch, some_commits, path, commit, expected):
    monkeypatch.chdir(some_commits)
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            git_read_file(path, commit)
    else:
        out = git_read_file(path, commit)
        assert out == expected


def test_git_read_file_git_func():
    git_func = MagicMock(side_effect=(u'some_output',))
    out = git_read_file('some/path', 'some_commit', git_func)
    assert git_func.called
    assert git_func.call_args == \
        call('cat-file', '-p', 'some_commit:some/path')
    assert out == u'some_output'


def test_ls_all_files(monkeypatch):
    upstream_sources = (
        MagicMock(
            spec=GitUpstreamSource,
            ls_files=MagicMock(side_effect=({
                'file1.txt': (1234, 'file1_hash'),
                'overriden1.txt': (1234, 'overridden_hash1'),
                'overriden2.txt': (1234, 'overridden_hash2'),
            },))
        ),
        MagicMock(
            spec=GitUpstreamSource,
            ls_files=MagicMock(side_effect=({
                'file2.txt': (1234, 'file2_hash'),
                'overriden1.txt': (1234, 'overriding_hash1'),
            },))
        ),
    )
    load_usrc = MagicMock(side_effect=(upstream_sources,))
    git_ls_files = MagicMock(side_effect=({
        'file3.txt': (1234, 'file3_hash'),
        'overriden2.txt': (1234, 'overriding_hash2'),
    },))
    monkeypatch.setattr('scripts.usrc.load_upstream_sources', load_usrc)
    monkeypatch.setattr('scripts.usrc.git_ls_files', git_ls_files)
    out = ls_all_files('some_commit')
    assert load_usrc.called
    assert load_usrc.call_args == call('some_commit')
    assert git_ls_files.called
    assert git_ls_files.call_args == call('some_commit')
    assert out == {
        'file1.txt': (1234, 'file1_hash'),
        'file2.txt': (1234, 'file2_hash'),
        'overriden1.txt': (1234, 'overriding_hash1'),
        'file3.txt': (1234, 'file3_hash'),
        'overriden2.txt': (1234, 'overriding_hash2'),
    }


def test_files_diff():
    old_files = {
        'unchanged.txt': (1234, 'unchanged_hash'),
        'changed.txt': (1234, 'original_hash'),
        'changed_mode.txt': (1234, 'some_hash'),
        'removed.txt': (1234, 'removed_hash'),
    }
    new_files = {
        'unchanged.txt': (1234, 'unchanged_hash'),
        'changed.txt': (1234, 'changed_hash'),
        'changed_mode.txt': (5678, 'some_hash'),
        'added.txt': (1234, 'added_hash'),
    }
    expected = set((
        'changed.txt',
        'changed_mode.txt',
        'removed.txt',
        'added.txt',
    ))
    out = files_diff(old_files, new_files)
    assert set(out) == expected


def test_get_modified_files(monkeypatch):
    ls_all_files = MagicMock(side_effect=lambda x: getattr(sentinel, x))
    files_diff = MagicMock(side_effect=(sentinel.a_diff,))
    monkeypatch.setattr('scripts.usrc.ls_all_files', ls_all_files)
    monkeypatch.setattr('scripts.usrc.files_diff', files_diff)
    out = get_modified_files('new_commit', 'old_commit')
    assert ls_all_files.call_count == 2
    assert call('new_commit') in ls_all_files.call_args_list
    assert call('old_commit') in ls_all_files.call_args_list
    assert files_diff.called
    assert files_diff.call_args == \
        call(sentinel.old_commit, sentinel.new_commit)
    assert out == sentinel.a_diff


def test_git_file_object(monkeypatch):
    git_func = MagicMock(side_effect=lambda x, y, z: getattr(sentinel, x))
    git_file = GitFile.construct('some-path', 0o12345, 'hash', git_func, 'com')
    assert git_file == (0o12345, 'hash')
    assert git_file.git_func == git_func
    assert git_file.path == 'some-path'
    assert git_file.commit == 'com'
    git_file.read_file()
    assert git_func.called
    assert call('cat-file', '-p', 'com:some-path') in git_func.call_args_list


@pytest.mark.parametrize(
    "links_map,diff,expected",
    [
        (
            {
                u'file1': set([u'link1', u'link2']),
            },
            [u'file1', u'abc', u'efg'],
            set([u'file1', u'link1', u'link2', u'abc', u'efg'])
        ),
        (
            {
                u'file1': set([u'link1', u'link2']),
                u'file2': set([u'link3']),
                u'file3': set([u'link4']),
            },
            [u'file1', u'file3'],
            set([u'file1', u'file3', u'link1', u'link2', u'link4'])
        ),
        (
            {},
            [u'file1', u'abc', u'efg'],
            set([u'file1', u'abc', u'efg'])
        ),
        (
            {
                u'file1': set([u'link1', u'link2']),
                u'file2': set([u'link3']),
                u'file3': set([u'link4']),
            },
            [],
            set()
        ),
        (
            {},
            [],
            set()
        ),
    ]
)
def test_get_modified_files_resolve_links(links_map, diff, expected, monkeypatch):
    ls_all_files = MagicMock(side_effect=lambda x: getattr(sentinel, x))
    files_diff = MagicMock(side_effect=lambda x, y: diff)
    get_files_to_links_map = MagicMock(side_effect=lambda x, y: links_map)
    monkeypatch.setattr('scripts.usrc.ls_all_files', ls_all_files)
    monkeypatch.setattr('scripts.usrc.files_diff', files_diff)
    monkeypatch.setattr(
        'scripts.usrc.get_files_to_links_map', get_files_to_links_map
    )
    out = get_modified_files('new_commit', 'old_commit', resolve_links=True)
    assert set(out) == expected
    assert ls_all_files.call_count == 2
    assert call('new_commit') in ls_all_files.call_args_list
    assert call('old_commit') in ls_all_files.call_args_list
    assert files_diff.called
    assert files_diff.call_args == \
        call(sentinel.old_commit, sentinel.new_commit)
    assert get_files_to_links_map.called
    assert call(sentinel.new_commit, 'new_commit') in \
        get_files_to_links_map.call_args_list
    assert get_files_to_links_map.call_args == \
        call(sentinel.new_commit, 'new_commit')


def test_get_files_to_links_map(monkeypatch):
    git_file = MagicMock(
        path='dummy_link_path',
        file_type=0o120000,
        read_file=MagicMock(side_effect=lambda : 'linked_by'),
    )
    out = get_files_to_links_map({'filename': git_file})
    assert git_file.read_file.called
    assert call() in git_file.read_file.call_args_list
    assert out == {'linked_by': set(['dummy_link_path'])}


def test_get_modified_files_links(
    downstream, upstream, git_last_sha, gitrepo, symlinkto, monkeypatch
):
    gitrepo(
        'upstream',
        {
            'msg': 'updated file',
            'files': {
                'upstream_file.txt': 'Updated upstream file',
                'link2': symlinkto('file2'),
                'link4': symlinkto('upstream_file.txt')
            }
        }
    )
    sha = git_last_sha(upstream)
    gitrepo(
        'downstream',
        {
            'msg': 'updated usrc',
            'files': {
                'automation/upstream_sources.yaml': dedent(
                    """
                    ---
                    git:
                      - url: {upstream}
                        commit: {sha}
                        branch: master
                    """
                ).lstrip().format(upstream=str(upstream), sha=sha),
                'link3': symlinkto('file3'),
                'new_ds_file': 'just a changed file',
                'changing_link': symlinkto('file3'),
                'link4': symlinkto('nowhere'),
                'broken_link': symlinkto('nowhere')

            }
        }
    )
    monkeypatch.chdir(downstream)
    out = get_modified_files(resolve_links=True)
    assert sorted(out) == sorted([
        u'link4', u'link_to_upstream_link', u'upstream_file.txt', u'link3',
        u'link2', u'new_ds_file', u'broken_link',
        u'automation/upstream_sources.yaml', u'changing_link', u'link_to_file'
    ])
