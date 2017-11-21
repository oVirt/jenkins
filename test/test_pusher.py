#!/usr/bin/env python
"""test_pusher.py - Tests for pusher.py
"""
import pytest
from textwrap import dedent
from functools import partial
from itertools import cycle
import py
from subprocess import CalledProcessError
try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call
import logging

from scripts.pusher import (
    push_to_scm, get_push_details, parse_push_details_struct, PushDetails,
    get_remote_url_from_ws, get_patch_header, add_key_to_known_hosts,
    PushMapError, PushMapMatchError, PushMapSyntaxError, PushMapIOError,
    GitProcessError
)


class TestGitProcessError(object):
    def test_inheritance(self):
        assert issubclass(GitProcessError, CalledProcessError)


class TestPushMapError(object):
    def test_inheritance(self):
        assert issubclass(PushMapError, Exception)


class TestPushMapMatchError(object):
    def test_inheritance(self):
        assert issubclass(PushMapMatchError, PushMapError)


class TestPushMapSyntaxError(object):
    def test_inheritance(self):
        assert issubclass(PushMapSyntaxError, PushMapError)


class TestPushMapIOError(object):
    def test_inheritance(self):
        assert issubclass(PushMapIOError, PushMapError)


@pytest.fixture
def remote_repo(tmpdir, git):
    remote_repo = tmpdir / 'remote'
    git('init', '--bare', str(remote_repo))
    return remote_repo


@pytest.fixture
def remote_git(remote_repo, git):
    return partial(git, '--git-dir=' + str(remote_repo))


@pytest.fixture
def local_repo(remote_repo, gitrepo, git_at):
    local_repo = gitrepo(
        'local',
        {
            'msg': 'Existing commit',
            'files': {'fil1.txt': 'Contents of fil1', }
        }
    )
    git = git_at(local_repo)
    git('remote', 'add', 'origin', str(remote_repo))
    git('push', '-u', 'origin', 'master')
    # Gerrit emulation - make remote have a refs/for/master ref
    git('push', 'origin', 'master:refs/for/master')
    return local_repo


@pytest.fixture
def remote_log(remote_git):
    def _remote_log(ref='refs/heads/master'):
        return remote_git('log', '--pretty=format:%H', ref, '--').splitlines()
    return _remote_log


@pytest.fixture
def local_log(local_repo, git_at):
    def _local_log(ref='refs/heads/master'):
        return git_at(local_repo)(
            'log', '--pretty=format:%H', ref, '--'
        ).splitlines()
    return _local_log


def test_local_remote_repo(local_log, remote_log, gitrepo, git_at):
    local_1_log = local_log()
    assert len(local_1_log) == 1
    assert remote_log() == local_1_log
    local_repo = gitrepo(
        'local',
        {
            'msg': 'New commit',
            'files': {'fil2.txt': 'Contents of fil2', }
        }
    )
    local_2_log = local_log()
    assert len(local_2_log) == 2
    assert remote_log() != local_2_log
    assert remote_log() == local_2_log[1:2]
    git = git_at(local_repo)
    git('push', 'origin', 'HEAD:refs/heads/branch1')
    assert remote_log() == local_2_log[1:2]
    assert remote_log('refs/heads/branch1') == local_2_log


@pytest.fixture
def local_repo_patch(gitrepo, local_repo):
    return gitrepo(
        'local',
        {
            'msg': 'New commit',
            'files': {'fil2.txt': 'Contents of fil2', }
        }
    )


@pytest.fixture
def gerrit_push_map(tmpdir):
    _push_map = tmpdir / 'git-push-url-map.yaml'
    _push_map.write(dedent(
        """
        ---
        - ^(/.*):
            push_url: \\1
        """
    ).lstrip().format())
    return str(_push_map)


@pytest.fixture
def mock_check_pushed(monkeypatch):
    _mock_check_pushed = MagicMock()

    def set_return(value):
        _mock_check_pushed.side_effect = cycle((value,))

    _mock_check_pushed.set_return = set_return
    _mock_check_pushed.set_return(False)
    monkeypatch.setattr(
        'scripts.pusher.check_if_similar_patch_pushed', _mock_check_pushed
    )
    return _mock_check_pushed


def test_push_gerrit(
    monkeypatch, gerrit_push_map, local_log, remote_log, local_repo_patch,
    mock_check_pushed
):
    remote_log_pre = remote_log()
    assert local_log() != remote_log_pre
    monkeypatch.chdir(str(local_repo_patch))
    push_to_scm('master', gerrit_push_map)
    assert remote_log() == remote_log_pre
    assert local_log() == remote_log('refs/for/master')
    push_to_scm('not_master', gerrit_push_map)
    assert remote_log() == remote_log_pre
    assert local_log() == remote_log('refs/for/not_master')


@pytest.mark.parametrize(
    ('patch_exists', 'if_not_exists', 'should_check', 'should_push'), [
        (False, False, False, True),
        (True,  False, False, True),
        (False, True,  True,  True),
        (True,  True,  True,  False),
    ]
)
def test_push_gerrit_if_not_exists(
    patch_exists, if_not_exists, should_check, should_push,
    monkeypatch, gerrit_push_map, local_log, remote_log, local_repo_patch,
    mock_check_pushed
):
    monkeypatch.chdir(str(local_repo_patch))
    assert local_log() != remote_log('refs/for/master')
    mock_check_pushed.set_return(patch_exists)
    push_to_scm('master', gerrit_push_map, if_not_exists=if_not_exists)
    assert mock_check_pushed.call_count <= 1
    assert mock_check_pushed.called == should_check
    assert (local_log() == remote_log('refs/for/master')) == should_push


def test_push_gerrit_unless_hash(
    monkeypatch, gerrit_push_map, local_log, remote_log, local_repo_patch,
    mock_check_pushed
):
    monkeypatch.chdir(str(local_repo_patch))
    assert remote_log('master') == remote_log('refs/for/master')
    head_hash, older_hash = local_log()[0:2]
    push_to_scm(
        'master', gerrit_push_map, unless_hash=head_hash, if_not_exists=True
    )
    assert remote_log('master') == remote_log('refs/for/master')
    assert not mock_check_pushed.called
    push_to_scm(
        'master', gerrit_push_map, unless_hash=older_hash, if_not_exists=True
    )
    assert local_log('master') == remote_log('refs/for/master')
    assert mock_check_pushed.called


def test_push_gerrit_set_ssh_key(
    monkeypatch, gerrit_push_map, local_log, remote_log, local_repo_patch,
    mock_check_pushed
):
    mock_add_pkey = MagicMock()
    monkeypatch.setattr(
        'scripts.pusher.add_key_to_known_hosts', mock_add_pkey
    )
    monkeypatch.chdir(str(local_repo_patch))
    push_to_scm('master', gerrit_push_map)
    assert not mock_add_pkey.called
    py.path.local(gerrit_push_map).write(dedent(
        """
        ---
        - ^(/.*):
            push_url: \\1
            host_key: some_host_key
        """
    ).lstrip().format())
    push_to_scm('master', gerrit_push_map)
    assert mock_add_pkey.called
    assert mock_add_pkey.call_count == 1
    assert mock_add_pkey.call_args == call('some_host_key')


@pytest.mark.parametrize(
    ('remote_url', 'expected'), [
        ('https://plain-remote/repo.git', 'ssh://plain-remote/repo.git'),
        ('https://plain-remote/repo2.git', PushMapMatchError),
        ('https://matched-remote/repo.git', 'ssh://matched-remote/repo.git'),
        ('https://matched-remote/repo2.git', 'ssh://matched-remote/repo2.git'),
        ('/local/path', '/local/path'),
        ('/moved/local/path', '/location_of/moved/local/path'),
    ]
)
def test_get_push_details(remote_url, expected):
    push_map_data = [
        {'^https://plain-remote/repo.git$': dict(
            push_url='ssh://plain-remote/repo.git',
        )},
        {'^https://matched-remote/(.*)$': dict(
            push_url='ssh://matched-remote/\\1',
        )},
        {'^(/moved.*)': dict(
            push_url='/location_of\\1',
        )},
        {'^(/.*)': dict(
            push_url='\\1',
        )},
    ]
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            get_push_details(push_map_data, remote_url)
    else:
        out = get_push_details(push_map_data, remote_url)
        assert isinstance(out, PushDetails)
        assert out.push_url == expected


@pytest.mark.parametrize(
    ('remote_url', 'expected'), [
        ('/local/path', '/local/path'),
        ('/moved/local/path', '/moved/local/path'),
    ]
)
def test_get_push_details_order(remote_url, expected):
    push_map_data = [
        {'^(/.*)': dict(
            push_url='\\1',
        )},
        {'^(/moved.*)': dict(
            push_url='/location_of\\1',
        )},
    ]
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            get_push_details(push_map_data, remote_url)
    else:
        out = get_push_details(push_map_data, remote_url)
        assert isinstance(out, PushDetails)
        assert out.push_url == expected


@pytest.mark.parametrize(
    ('push_map_data', 'expected'), [
        ([], PushMapMatchError),
        ([{}], PushMapSyntaxError),
        ([
            {'not_matching': dict()},
            {'not_matching_either': dict()},
        ], PushMapMatchError),
        ([
            {'remote_url': dict(push_url='push_url')},
        ], 'push_url'),
        ([
            {'remote_url': 'not-a-dict'},
        ], PushMapSyntaxError),
        ([
            {'remote_url': ['not-a-dict']},
        ], PushMapSyntaxError),
        ([
            {'remote_url': dict()},
        ], PushMapSyntaxError),
        ([
            {'remote_url': dict(push_url='push_url'), 'too': 'many keys'},
        ], PushMapSyntaxError),
        ({'not a': 'list of dicts'}, PushMapSyntaxError),
        (['not a', 'list of dicts', 'either'], PushMapSyntaxError),
        (['a', 'list with len(x) == 1 member'], PushMapSyntaxError),
        (7, PushMapSyntaxError),
    ]
)
def test_get_push_details_syntax(push_map_data, expected):
    remote_url = 'remote_url'
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            get_push_details(push_map_data, remote_url)
    else:
        out = get_push_details(push_map_data, remote_url)
        assert isinstance(out, PushDetails)
        assert out.push_url == expected


@pytest.mark.parametrize(
    ('struct', 'expected'), [
        (dict(), PushMapSyntaxError),
        (dict(push_url='some_url'), PushDetails('some_url', '')),
        (
            dict(push_url='some_url', host_key='some_key'),
            PushDetails('some_url', 'some_key')
        ),
        ('not-a-dict', PushMapSyntaxError),
        (['still', 'not', 'a', 'dict'], PushMapSyntaxError),
        (7, PushMapSyntaxError),
    ]
)
def test_parse_push_details_struct(struct, expected):
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            parse_push_details_struct(struct)
    else:
        out = parse_push_details_struct(struct)
        assert out == expected


def test_get_remote_url_from_ws(gitrepo, git, monkeypatch):
    repo = gitrepo('a-repo')
    monkeypatch.chdir(repo)
    with pytest.raises(ValueError):
        get_remote_url_from_ws()
    git('remote', 'add', 'not_origin', 'not_origin_url')
    with pytest.raises(ValueError):
        get_remote_url_from_ws()
    git('remote', 'add', 'origin', 'origin_url')
    out = get_remote_url_from_ws()
    assert out == 'origin_url'
    git('remote', 'set-url', 'origin', 'crazy  origin_url ')
    out = get_remote_url_from_ws()
    assert out == 'crazy  origin_url '


@pytest.mark.xfail
def test_check_if_similar_patch_pushed():
    # TODO
    assert False


@pytest.mark.xfail
def test_add_private_key_to_known_hosts():
    # TODO
    assert False


@pytest.mark.parametrize(
    ('header', 'default', 'expected'), [
        ('header-at-top', None, 'Header at top value'),
        ('header-in-middle', None, 'Header in middle value'),
        ('spaced_out_header', None, 'Spaced out value'),
        ('bottom-header1', None, 'Value 1'),
        ('bottom-header1', 'given default', 'Value 1'),
        ('bottom-header2', None, 'Value 2'),
        ('numeric-header', None, '17'),
        ('none-existant-header', None, KeyError),
        ('none-existant-header', 'given default', 'given default'),
    ]
)
def test_get_patch_header(monkeypatch, gitrepo, header, default, expected):
    repo = gitrepo(
        'repo',
        {
            'msg': dedent(
                """
                Commit message title, up to 60 chars

                header-at-top: Header at top value

                Human readable text in the commit message that can be quite
                long and span multiple lines.

                header-in-middle: Header in middle value

                Another human readable paragraph that: may look like a header.

                spaced_out_header: Spaced out value

                bottom-header1: Value 1
                bottom-header2: Value 2
                numeric-header: 17
                """
            ).lstrip(),
            'files': {'dummy.txt': 'dummy'},
        }
    )
    monkeypatch.chdir(repo)
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            get_patch_header(header, default)
    else:
        out = get_patch_header(header, default)
        assert out == expected


@pytest.mark.parametrize(('existing', 'key', 'expected'), [
    (
        None,
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE',
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n',
    ),
    (
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n',
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE',
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n',
    ),
    (
        '[other-server.ovirt.org]:29418 ssh-rsa OTHER_LONG_B64_HERE\n',
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE',
        (
            '[other-server.ovirt.org]:29418 ssh-rsa OTHER_LONG_B64_HERE\n'
            '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n'
        ),
    ),
    (
        (
            '[other-server.ovirt.org]:29418 ssh-rsa OTHER_LONG_B64_HERE\n'
            '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n'
            '[more-server.ovirt.org]:29418 ssh-rsa MORE_LONG_B64_HERE\n'
        ),
        '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE',
        (
            '[other-server.ovirt.org]:29418 ssh-rsa OTHER_LONG_B64_HERE\n'
            '[gerrit-staging.phx.ovirt.org]:29418 ssh-rsa BIG_LONG_B64_HERE\n'
            '[more-server.ovirt.org]:29418 ssh-rsa MORE_LONG_B64_HERE\n'
        ),
    ),
])
def test_add_key_to_known_hosts(tmpdir, monkeypatch, existing, key, expected):
    logging.basicConfig(level=logging.DEBUG)
    known_hosts = tmpdir / '.ssh' / 'known_hosts'
    if existing is not None:
        known_hosts.write(existing, ensure=True)
    monkeypatch.setenv('HOME', str(tmpdir))
    add_key_to_known_hosts(key)
    assert expected == known_hosts.read()
