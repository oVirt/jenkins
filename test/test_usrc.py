#!/usr/bin/env python
"""test_usrc.py - Tests for usrc.py
"""
import pytest
from textwrap import dedent
from types import GeneratorType
from hashlib import md5
import os
import inspect
from subprocess import CalledProcessError
from six import iteritems
from six.moves import map, builtins
import yaml
import re
try:
    from unittest.mock import MagicMock, call, sentinel, create_autospec
except ImportError:
    from mock import MagicMock, call, sentinel, create_autospec

from stdci_libs.git_utils import git_rev_parse
from stdci_tools import usrc
from stdci_tools.usrc import (
    get_upstream_sources, update_upstream_sources,
    commit_upstream_sources_update, GitProcessError, GitUpstreamSource,
    generate_update_commit_message, git_ls_files, git_read_file, ls_all_files,
    files_diff, get_modified_files, get_files_to_links_map, GitFile,
    UnkownDestFormatError, set_upstream_source_entries, modify_entries_main,
    only_if_imported_any, upstream_sources_config, UPSTREAM_SOURCES_FILE,
)


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
def downstream_remote(gitrepo):
    return gitrepo(
        'downstream_remote',
        {
            'msg': 'First DS remote commit',
        }
    )


@pytest.mark.parametrize('config_dir', [
    '',
    'automation',
])
def test_upstream_sources_config_filepath(monkeypatch, tmpdir, config_dir):
    tmp_config_dir = tmpdir
    if config_dir:
        tmp_config_dir = tmpdir / config_dir
        tmp_config_dir.mkdir()
    config_file = tmp_config_dir / UPSTREAM_SOURCES_FILE
    upstream_sources_text = 'bla bla bla'
    config_file.write(upstream_sources_text)
    monkeypatch.chdir(tmpdir)
    sanity_tests_upstream_sources_config(
        os.path.join(config_dir, UPSTREAM_SOURCES_FILE),
        upstream_sources_text
    )


def test_upstream_sources_config_custom_name(tmpdir):
    custom_config = tmpdir / 'custom_us_config.yaml'
    upstream_sources_text = 'bla bla bla'
    custom_config.write(upstream_sources_text)
    sanity_tests_upstream_sources_config(
        str(custom_config),
        upstream_sources_text,
        custom_configs=('file_which_does_not_exist', str(custom_config))
    )


@pytest.mark.parametrize('config_dir', [
    '',
    'automation',
])
def test_upstream_sources_config_git(
    monkeypatch, gitrepo, git_last_sha, config_dir
):
    upstream_sources_text = 'bla bla bla'
    expected_config_path = os.path.join(config_dir, UPSTREAM_SOURCES_FILE)
    repo = gitrepo(
        'myrepo',
        {
            'msg': 'First commit',
            'files': {expected_config_path: 'bla bla bla'}
        }
    )
    sha = git_last_sha(repo)
    monkeypatch.chdir(repo)
    sanity_tests_upstream_sources_config(
        expected_config_path, upstream_sources_text, commit=sha)


def sanity_tests_upstream_sources_config(
    expected_config_path, expected_content, custom_configs=tuple(), **params
):
    # verify that the content of the file is indeed what we wrote there
    with upstream_sources_config(*custom_configs, **params) as config_path:
        assert config_path.path == expected_config_path
        assert config_path.stream.read() == expected_content
    assert config_path.stream.closed


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
                automerge='no', dest_formats={'files': None}, files_dest_dir='',
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
                annotated_tag_only=True
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
                annotated_tag_only=True
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged', 'latest'),
                annotated_tag_only=False
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('tagged', 'latest'),
                annotated_tag_only=False
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
                annotated_tag_only=False
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
                annotated_tag_only=True
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=False,
                annotated_tag_only=None
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                update_policy=('latest'),
                annotated_tag_only=False
            ),
        ),

        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'files': None, 'branch': None},
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'files': None, 'branch': None},
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'branch': None},
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'branch': None},
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
                annotated_tag_only=False
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                annotated_tag_only=False
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha'
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'files': None, 'branch': None},
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'files': None, 'branch': None},
            ),
        ),
        (
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'branch': None},
            ),
            dict(
                url='some/url', branch='br1', commit='some_sha',
                dest_formats={'branch': None},
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
    ])
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

    def test_get_dest_dir(
            self, upstream, downstream, git_last_sha, gerrit_push_map):
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream), 'no',
            {'files': None}, 'temp'
        )
        assert not (downstream / 'temp' / 'upstream_file.txt').exists()
        gus.get(str(downstream), gerrit_push_map)
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

    def test_files_format_handler(
        self, upstream, downstream, git_last_sha, gerrit_push_map
    ):
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream),
            dest_formats={'files': None}
        )
        assert not (downstream / 'upstream_file.txt').exists()
        gus.get(str(downstream), gerrit_push_map)
        assert (downstream / 'upstream_file.txt').isfile()
        assert (downstream / 'upstream_file.txt').read() == 'Upstream content'
        assert (downstream / 'overriden_file.txt').isfile()
        assert (downstream / 'overriden_file.txt').read() == \
            'Overridden content'

    def test_branch_format_handler(
        self, monkeypatch, upstream, downstream, downstream_remote,
        git_at, git_last_sha, gerrit_push_map
    ):
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream), 'no',
            {'branch': None}
        )
        dst_branch = '_upstream_' + gus.branch + '_' + gus.commit[0:7]
        gus._fetch()
        git = git_at(downstream)
        git('remote', 'add', 'origin', str(downstream_remote))
        git('remote', 'add', 'upstream', str(upstream))
        upstream_head = \
            git('ls-remote', '--heads', 'upstream', 'master').split()[0]
        origin_pre = git('ls-remote', '--heads', 'origin', dst_branch)
        # Check dst_branch does not exist on downstream_remote pre push
        assert origin_pre == ''
        monkeypatch.chdir(str(downstream))
        mock_src_repos_handler = MagicMock()
        gus._branch_format_handler(gerrit_push_map)
        origin_post = git('ls-remote', '--heads', 'origin', dst_branch)
        assert origin_post != ''
        origin_post_commit = origin_post.split()[0]
        # Check dst_branch on downstream_remote points to the same commit
        # as upstream branch
        assert upstream_head == origin_post_commit
        mock_src_repos_handler.assert_not_called
        monkeypatch.setattr(
            gus, '_source_repos_format_handler', mock_src_repos_handler
        )
        gus._branch_format_handler(
            gerrit_push_map, gen_source_repos=True, dst_path='path')
        mock_src_repos_handler.assert_called_once_with(
            gerrit_push_map, dst_path='path', gen_source_repos=True
        )

    @pytest.mark.parametrize(
        'src_repos_file,files_dest_dir,expected_file_name',
        [
            ('custom-source-repos', None, 'custom-source-repos'),
            ('path/custom-source-repos', None, 'path/custom-source-repos'),
            (None, None, 'source-repos'),
            (None, 'base', 'base/source-repos'),
        ]
    )
    def test_source_repos_format_handler(
        self, src_repos_file, expected_file_name, files_dest_dir, tmpdir,
        monkeypatch
    ):
        tmp_dir = tmpdir.mkdir('tmp_dir')
        gus = GitUpstreamSource(
            'str(upstream)', 'master', 'some-commit',
            files_dest_dir=str(tmp_dir)
        )
        mock_push_details = MagicMock(
            side_effect=(MagicMock(anonymous_clone_url='some-url'),)
        )
        monkeypatch.setattr(usrc, 'read_push_details', mock_push_details)
        gus._source_repos_format_handler(
            dst_path=str(tmp_dir), push_map={}, src_repos_file=src_repos_file,
            files_dest_dir=files_dest_dir
        )

        mock_push_details.assert_called_once_with({}, None)
        f = tmp_dir.join(expected_file_name)
        assert f.exists()
        assert f.read_text(encoding='utf-8') == 'some-url some-commit\n'

    @pytest.mark.parametrize(
        'dest_formats,get_as_files_expected,push_to_branch_expected',
        [
            ({'files': None}, True, False),
            ({'files': None, 'branch': None}, True, True),
            ({'branch': None}, False, True)
        ]
    )
    def test_get(
        self, upstream, git_last_sha, gerrit_push_map, dest_formats,
        get_as_files_expected, push_to_branch_expected
    ):
        get_as_files = MagicMock()
        push_to_branch = MagicMock()
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream),
            dest_formats=dest_formats
        )
        gus._files_format_handler = get_as_files
        gus._branch_format_handler = push_to_branch
        gus.get(str(upstream), gerrit_push_map)
        assert get_as_files.called == get_as_files_expected
        assert push_to_branch.called == push_to_branch_expected

    def test_get_unknown_dest_exception(
        self, upstream, git_last_sha, gerrit_push_map
    ):
        with pytest.raises(UnkownDestFormatError):
            GitUpstreamSource(
                str(upstream), 'master', git_last_sha(upstream),
                dest_formats={'unknown_dest': None}
            )

    def test_call_format_handlers(self, git_last_sha, upstream, monkeypatch):
        mock_formatter = MagicMock()
        monkeypatch.setattr(
            GitUpstreamSource,
            '_validate_dst_fmt_exists',
            lambda this: True
        )
        gus = GitUpstreamSource(
            str(upstream), 'master', git_last_sha(upstream),
            dest_formats={'mock': {'mock_param': 'mock_value'}}
        )
        setattr(gus, '_mock_format_handler', mock_formatter)
        gus._call_format_handlers('dst_path', 'push_map')
        mock_formatter.assert_called_once_with(
            mock_param='mock_value', dst_path='dst_path', push_map='push_map'
        )

    def test_update(self, gitrepo, upstream, git_last_sha):
        url, branch, commit = str(upstream), 'master', git_last_sha(upstream)
        dest_formats = {'files': None}
        files_dest_dir = 'temp'
        gus = GitUpstreamSource(
            url, branch, commit, 'no', dest_formats, files_dest_dir
        )
        gus_id = id(gus)
        updated = gus.updated()
        assert id(gus) == gus_id
        assert gus.url == url
        assert gus.branch == branch
        assert gus.commit == commit
        assert gus.dest_formats == dest_formats
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
        assert gus.dest_formats == dest_formats
        assert gus.files_dest_dir == files_dest_dir
        assert updated != gus
        assert id(updated) != id(gus)
        assert updated.url == url
        assert updated.branch == branch
        assert updated.commit == new_commit
        assert gus.dest_formats == dest_formats
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
        monkeypatch.setattr('stdci_tools.usrc.git_ls_files', git_ls_files)
        gus = GitUpstreamSource('git://url.of/repo', 'a_branch', 'a_commit')
        gus._fetch = fetch
        out = gus.ls_files()
        assert git_ls_files.called
        assert git_ls_files.call_args == \
            call('a_commit', git_func=gus._cache_git)
        assert fetch.called
        assert out == sentinel.some_files

    @pytest.mark.parametrize(
        'root_path,file_path',
        (
            ('/some/path', '/not/some/path'),
            ('/some/path', '/some/path/../here'),
        )
    )
    def test_assert_path_under_root_raises(self, root_path, file_path):
        with pytest.raises(usrc.ConfigError):
            GitUpstreamSource._assert_path_under_root(root_path, file_path)

    @pytest.mark.parametrize(
        'root_path,file_path',
        (
            ('/some/path', '/some/path/here/is/ok'),
        )
    )
    def test_assert_path_under_root_ok(self, root_path, file_path):
        GitUpstreamSource._assert_path_under_root(root_path, file_path)

    @pytest.mark.parametrize('tag_filter,expected', [
        (
            None,
            [
                {'annotated': 'tag', 'name': 'a_tag'},
                {'annotated': 'tag', 'name': 'b_tag'},
                {'annotated': 'tag', 'name': 'c_tag'},
                {'annotated': 'tag', 'name': 'd_tag'},
            ]
        ),
        (
            'a*',
            [{'annotated': 'tag', 'name': 'a_tag'}]
        )
    ])
    def test_get_raw_tags(
        self, tag_filter, expected,
        upstream_scenarios_for_tests, tmpdir, monkeypatch
    ):
        monkeypatch.setattr(usrc, 'xdg_cache_home', str(tmpdir))
        gus = GitUpstreamSource(
            url=str(upstream_scenarios_for_tests),
            branch='master',
            commit='master',
            tag_filter=tag_filter
        )
        gus._fetch()
        tags = gus._get_raw_tags()
        assert isinstance(tags, str)
        yaml_struct = yaml.safe_load(tags)

        git_sha_pattern = re.compile(r'[a-f0-9]{40}')
        for r, e in zip(yaml_struct, expected):
            for attr in ('annotated', 'name'):
                assert r[attr] == e[attr]

            assert git_sha_pattern.match(r['commit'])

    def test_get_raw_tags_should_return_empty_str(
        self, upstream_scenarios_for_tests, tmpdir,
        monkeypatch
    ):
        monkeypatch.setattr(usrc, 'xdg_cache_home', str(tmpdir))
        gus = GitUpstreamSource(
            url=str(upstream_scenarios_for_tests),
            branch='master',
            commit='master',
            tag_filter='blabla'
        )
        gus._fetch()
        tags = gus._get_raw_tags()
        assert isinstance(tags, str)
        assert tags == ''

    @pytest.mark.parametrize('tags_yaml_struct,expected', [
        ([], []),
        (
            [
                {'commit': 'abc', 'annotated': 'tag', 'name': 'a_tag'},
                {'commit': 'efg', 'annotated': 'commit', 'name': 'b_tag'},
            ],
            [
                usrc.TagObject(commit='abc', annotated='tag', name='a_tag'),
                usrc.TagObject(commit='efg', annotated='commit', name='b_tag'),
            ]
        )
    ])
    def test_get_tags_gen(self, tags_yaml_struct, expected, monkeypatch):
        gus = GitUpstreamSource(
            url='https://gerrit.ovirt.org/some-project',
            branch='master',
            commit='master',
        )
        rev_parse_mock = MagicMock(side_effect=lambda x: x)
        monkeypatch.setattr(gus, '_rev_parse', rev_parse_mock)
        tag_gen = gus._get_tags_gen(tags_yaml_struct)
        assert isinstance(tag_gen, GeneratorType)
        tag_list = list(tag_gen)
        assert rev_parse_mock.call_count == len(expected)
        assert tag_list == expected

    def test_get_tags(self, monkeypatch):
        gus = GitUpstreamSource(
            url='https://gerrit.ovirt.org/some-project',
            branch='master',
            commit='master',
        )
        yaml_safe_load_ret = sentinel.yaml_struct
        safe_load_mock = MagicMock(return_value=yaml_safe_load_ret)
        _get_raw_tags_mock_ret = ''
        _get_raw_tags_mock = MagicMock(return_value=_get_raw_tags_mock_ret)
        _get_tags_gen_mock_ret = sentinel.generator
        _get_tags_gen_mock = MagicMock(return_value=_get_tags_gen_mock_ret)
        monkeypatch.setattr(yaml, 'safe_load', safe_load_mock)
        monkeypatch.setattr(gus, '_get_raw_tags', _get_raw_tags_mock)
        monkeypatch.setattr(gus, '_get_tags_gen', _get_tags_gen_mock)

        _get_tags_ret = gus._get_tags()
        assert safe_load_mock.call_count == 0
        assert _get_tags_ret == []
        safe_load_mock.reset_mock()

        _get_raw_tags_mock_ret = sentinel.string_with_tags
        _get_raw_tags_mock.return_value = _get_raw_tags_mock_ret
        _get_tags_ret = gus._get_tags()
        safe_load_mock.assert_called_with(_get_raw_tags_mock_ret)
        assert _get_tags_ret is _get_tags_gen_mock_ret

    def test_update_policy_tagged_not_calling_max_if_tag_list_is_empty(
        self, monkeypatch
    ):
        commit = 'best_commit_ever'
        gus = GitUpstreamSource(
            url='https://gerrit.ovirt.org/some-project',
            branch='master',
            commit=commit
        )
        max_mock = MagicMock()
        _get_tags_mock = MagicMock(return_value=[])
        monkeypatch.setattr(builtins, 'max', max_mock)
        monkeypatch.setattr(gus, '_get_tags', _get_tags_mock)
        _get_tags_ret = gus._update_policy_tagged()
        assert _get_tags_mock.call_count == 1
        assert max_mock.call_count == 0
        assert _get_tags_ret == commit

    def test_update_policy_static(self):
        gus = GitUpstreamSource(
            url='https://gerrit.ovirt.org/some-project',
            branch='master',
            commit='commit',
            update_policy='static'
        )
        ret = gus._update_policy_static()
        assert ret == 'commit'

    def test_rev_parse_returns_an_str(
        self, upstream_scenarios_for_tests, tmpdir, monkeypatch
    ):
        monkeypatch.setattr(usrc, 'xdg_cache_home', str(tmpdir))
        gus = GitUpstreamSource(
            url=str(upstream_scenarios_for_tests),
            branch='master',
            commit='master',
        )
        gus._fetch()
        out = gus._rev_parse('refs/remotes/origin/master')
        assert isinstance(out, str)


def test_get_upstream_sources(monkeypatch, gerrit_push_map, downstream):
    monkeypatch.chdir(downstream)
    assert not (downstream / 'upstream_file.txt').exists()
    get_upstream_sources(gerrit_push_map)
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
    monkeypatch, gerrit_push_map, updated_upstream, downstream, git_status
):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    mod_list, config_path = update_upstream_sources()
    assert config_path == 'automation/upstream_sources.yaml'
    assert len(list(mod_list)) == 1
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ' M automation/upstream_sources.yaml'
    get_upstream_sources(gerrit_push_map)
    assert (downstream / 'upstream_file.txt').isfile()
    assert (downstream / 'upstream_file.txt').read() == 'Updated US content'
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert (downstream / 'overriden_file.txt').isfile()
    assert (downstream / 'overriden_file.txt').read() == 'Overriding content'


def test_no_update_upstream_sources(
    monkeypatch, gerrit_push_map, upstream, downstream, git_status
):
    monkeypatch.chdir(downstream)
    # Verify that downstream in unmodified
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    mod_list, config_path = update_upstream_sources()
    assert len(list(mod_list)) == 0
    assert config_path == 'automation/upstream_sources.yaml'
    assert not (downstream / 'upstream_file.txt').exists()
    assert (downstream / 'downstream_file.txt').isfile()
    assert (downstream / 'downstream_file.txt').read() == 'Downstream content'
    assert git_status(downstream) == ''
    get_upstream_sources(gerrit_push_map)
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
    updates, used_config_path = update_upstream_sources()
    us_yaml = downstream / 'automation' / 'upstream_sources.yaml'
    us_yaml_md5 = md5(us_yaml.read().encode('utf-8')).hexdigest()
    commit_upstream_sources_update(updates, used_config_path)
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
    commit_upstream_sources_update([], '')
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
    load_usrc = MagicMock(return_value=(upstream_sources, 'dummy_path'))
    git_ls_files = MagicMock(side_effect=({
        'file3.txt': (1234, 'file3_hash'),
        'overriden2.txt': (1234, 'overriding_hash2'),
    },))
    monkeypatch.setattr('stdci_tools.usrc.load_upstream_sources', load_usrc)
    monkeypatch.setattr('stdci_tools.usrc.git_ls_files', git_ls_files)
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
    monkeypatch.setattr('stdci_tools.usrc.ls_all_files', ls_all_files)
    monkeypatch.setattr('stdci_tools.usrc.files_diff', files_diff)
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
def test_get_modified_files_resolve_links(
    links_map, diff, expected, monkeypatch
):
    ls_all_files = MagicMock(side_effect=lambda x: getattr(sentinel, x))
    files_diff = MagicMock(side_effect=lambda x, y: diff)
    get_files_to_links_map = MagicMock(side_effect=lambda x, y: links_map)
    monkeypatch.setattr('stdci_tools.usrc.ls_all_files', ls_all_files)
    monkeypatch.setattr('stdci_tools.usrc.files_diff', files_diff)
    monkeypatch.setattr(
        'stdci_tools.usrc.get_files_to_links_map', get_files_to_links_map
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
        read_file=MagicMock(side_effect=lambda: 'linked_by'),
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


@pytest.mark.parametrize('usrc,usrc_to_set,expected', (
    (
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
        ),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1u'),
        ),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1u'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
        ),
    ),
    (
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
        ),
        (
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
    ),
    (
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
        (
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
            GitUpstreamSource(url='u1', branch='b1', commit='c1u'),
        ),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1u'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
    ),
    (
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
        ),

        (
            GitUpstreamSource(url='u1', branch='b2', commit='c2'),
        ),

        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u1', branch='b2', commit='c2'),
        ),
    ),
    (
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
        tuple(),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
            GitUpstreamSource(url='u2', branch='b2', commit='c2'),
            GitUpstreamSource(url='u3', branch='b3', commit='c3'),
        ),
    ),
    (
        tuple(),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
        ),
        (
            GitUpstreamSource(url='u1', branch='b1', commit='c1'),
        ),
    ),
))
def test_set_upstream_source_entries(usrc, usrc_to_set, expected):
    ret = tuple(set_upstream_source_entries(usrc, usrc_to_set))
    assert len(ret) == len(expected)
    for usrc_expected, usrc_returned in zip(expected, ret):
        assert usrc_expected.url == usrc_returned.url
        assert usrc_expected.branch == usrc_returned.branch
        assert usrc_expected.commit == usrc_returned.commit


@pytest.mark.parametrize(
    'usrc_orig,usrc_modify,should_commit',
(
    (  # update one, append one
        (
            GitUpstreamSource('u', 'b', 'commit'),
            GitUpstreamSource('u1', 'b1', 'commit'),
        ),
        (
            '{"url": "u1", "branch": "b1", "commit": "updated_commit"}',
            '{"url": "u3", "branch": "b3", "commit": "new_commit"}',
        ),
        False
    ),
    (  # append two
        (GitUpstreamSource('u', 'b', 'commit'),),
        (
            '{"url": "u1", "branch": "b1", "commit": "updated_commit"}',
            '{"url": "u3", "branch": "b3", "commit": "new_commit"}',
        ),
        False
    ),
    (  # update one, append one, commit
        (
            GitUpstreamSource('u', 'b', 'commit'),
            GitUpstreamSource('u1', 'b1', 'commit')
        ),
        (
            '{"url": "u1", "branch": "b1", "commit": "updated_commit"}',
            '{"url": "u3", "branch": "b3", "commit": "new_commit"}',
        ),
        True
    ),
    (  # append two, commit
        tuple(),
        (
            '{"url": "u1", "branch": "b1", "commit": "updated_commit"}',
            '{"url": "u3", "branch": "b3", "commit": "new_commit"}',
        ),
        True
    ),
))
def test_modify_entries(monkeypatch, usrc_orig, usrc_modify, should_commit):
    config_path = 'dummy-path'
    entry_property = MagicMock()
    entry_property.__iter__ = MagicMock(return_value=iter(usrc_modify))
    mock_args = MagicMock(
        entries=entry_property, commit=should_commit
    )
    mock_load_usrc = MagicMock(return_value=(usrc_orig, config_path))
    monkeypatch.setattr('stdci_tools.usrc.load_upstream_sources', mock_load_usrc)
    mock_save_usrc = create_autospec(usrc.save_upstream_sources)
    monkeypatch.setattr('stdci_tools.usrc.save_upstream_sources', mock_save_usrc)
    mock_commit_usrc = MagicMock()
    monkeypatch.setattr(
        'stdci_tools.usrc.commit_upstream_sources_update', mock_commit_usrc
    )
    mock_set_upstream_source_entries = MagicMock(
        return_value=sentinel.some_entries
    )
    monkeypatch.setattr(
        'stdci_tools.usrc.set_upstream_source_entries',
        mock_set_upstream_source_entries
    )
    modify_entries_main(mock_args)
    assert mock_load_usrc.call_count == 1
    assert mock_args.entries.__iter__.call_count == 1
    mock_save_usrc.assert_called_with(sentinel.some_entries, config_path)
    if should_commit:
        mock_commit_usrc.assert_called_once_with(
            sentinel.some_entries, config_path
        )
    else:
        mock_commit_usrc.assert_not_called


def test_modify_entries_parser_error():
    mock_args = MagicMock(entries=['{{}'])
    base_exception_msg = \
        'Exception while trying parse one of the upstream sources:\n'
    with pytest.raises(yaml.parser.ParserError) as excinfo:
        modify_entries_main(mock_args)
    assert base_exception_msg in str(excinfo.value)


@pytest.mark.parametrize('modules,should_raise', (
    (
        ('some-module', 'pytest'), False
    ),
    (
        ('no-such-module', 'no-such-module-2'), True
    ),
    (
        tuple(), False
    )
))
def test_only_if_imported_any(modules, should_raise):
    @only_if_imported_any(*modules)
    def test_function(arg1, arg2, arg3): return 'test-result'
    assert test_function.__name__ == 'test_function'
    if should_raise:
            with pytest.raises(RuntimeError) as excinfo:
                test_function(1, 2, 3)
            assert str(excinfo.value) == (
                'test_function is disabled because none of {0}'
                ' were imported.'
                .format(modules)
            )
    else:
        assert test_function(1, 2, 3) == 'test-result'
