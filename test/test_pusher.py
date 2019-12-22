#!/usr/bin/env python
"""test_pusher.py - Tests for pusher.py
"""
import pytest
from textwrap import dedent
from functools import partial
from itertools import cycle
import py
try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call
import logging

from scripts.pusher import (
    push_to_scm, get_push_details, parse_push_details_struct, PushDetails,
    get_remote_url_from_ws, get_patch_header, add_key_to_known_hosts,
    PushMapError, PushMapMatchError, PushMapSyntaxError, PushMapIOError,
    merge_to_scm, patch_header_is_true, check_if_similar_patch_pushed,
    get_patch_owner, gerrit_user_in_group, can_merge_to_scm, PatchInfoError,
    parse_yaml_to_list, read_push_details
)


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


class TestPatchInfoError(object):
    def test_inheritance(self):
        assert issubclass(PatchInfoError, Exception)


class TestPushDetails(object):
    def test_init(self):
        pd = PushDetails('a_push_url')
        assert pd.push_url == 'a_push_url'
        assert pd.host_key is None
        assert pd.merge_flags == []
        assert pd.maintainer_groups == []
        assert pd.maintainers == []
        assert pd.anonymous_clone_url == 'a_push_url'
        pd = PushDetails('a_push_url', 'a_host_key')
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == []
        assert pd.maintainer_groups == []
        assert pd.maintainers == []
        assert pd.anonymous_clone_url == 'a_push_url'
        pd = PushDetails('a_push_url', 'a_host_key', ['merge', 'flags'])
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == []
        assert pd.maintainers == []
        assert pd.anonymous_clone_url == 'a_push_url'
        pd = PushDetails(
            'a_push_url', 'a_host_key', ['merge', 'flags'],
            ['gr1', 'gr2'], ['mnt1', 'mnt2'],
        )
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == ['gr1', 'gr2']
        assert pd.maintainers == ['mnt1', 'mnt2']
        assert pd.anonymous_clone_url == 'a_push_url'
        pd = PushDetails(
            'a_push_url', 'a_host_key', ['merge', 'flags'],
            ['gr1', 'gr2'], ['mnt1', 'mnt2'], 'anon_url'
        )
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == ['gr1', 'gr2']
        assert pd.maintainers == ['mnt1', 'mnt2']
        assert pd.anonymous_clone_url == 'anon_url'

    def test_named_init(self):
        pd = PushDetails(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
            host_key='a_host_key',
            maintainer_groups=['gr1', 'gr2'],
            maintainers=['mnt1', 'mnt2'],
            anonymous_clone_url='anon_url',
        )
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == ['gr1', 'gr2']
        assert pd.maintainers == ['mnt1', 'mnt2']
        assert pd.anonymous_clone_url == 'anon_url'
        pd = PushDetails(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
            host_key='a_host_key',
        )
        assert pd.push_url == 'a_push_url'
        assert pd.host_key == 'a_host_key'
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == []
        assert pd.maintainers == []
        assert pd.anonymous_clone_url == 'a_push_url'
        pd = PushDetails(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
        )
        assert pd.push_url == 'a_push_url'
        assert pd.host_key is None
        assert pd.merge_flags == ['merge', 'flags']
        assert pd.maintainer_groups == []
        assert pd.maintainers == []
        assert pd.anonymous_clone_url == 'a_push_url'

    def test_eq(self):
        pd1 = PushDetails(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
            host_key='a_host_key',
            maintainer_groups=['gr1', 'gr2'],
            maintainers=['mnt1', 'mnt2'],
            anonymous_clone_url='anon_url',
        )
        pd2 = PushDetails(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
            host_key='a_host_key',
            maintainer_groups=['gr1', 'gr2'],
            maintainers=['mnt1', 'mnt2'],
            anonymous_clone_url='anon_url',
        )
        assert id(pd1) != id(pd2)
        assert pd1 == pd2

    @pytest.mark.parametrize('unset_attrs', [
        ('merge_flags',),
        ('host_key',),
        ('maintainer_groups',),
        ('maintainers',),
        ('merge_flags', 'host_key', 'maintainer_groups', 'maintainers',),
        ('anonymous_clone_url',),
    ])
    def test_neq(self, unset_attrs):
        pd1_attrs = dict(
            push_url='a_push_url',
            merge_flags=['merge', 'flags'],
            host_key='a_host_key',
            maintainer_groups=['gr1', 'gr2'],
            maintainers=['mnt1', 'mnt2'],
            anonymous_clone_url='anon_url',
        )
        pd2_attrs = dict()
        pd2_attrs.update(pd1_attrs)
        for attr in unset_attrs:
            pd2_attrs.pop(attr)
        pd1 = PushDetails(**pd1_attrs)
        pd2 = PushDetails(**pd2_attrs)
        all_attrs = (
            'push_url', 'merge_flags', 'host_key', 'maintainer_groups',
            'maintainers', 'anonymous_clone_url',
        )
        print(unset_attrs)
        for attr in all_attrs:
            if attr in unset_attrs:
                print('{0} != {0}'.format(attr))
                assert getattr(pd1, attr) != getattr(pd2, attr)
                continue
            print('{0} == {0}'.format(attr))
            assert getattr(pd1, attr) == getattr(pd2, attr)
        assert id(pd1) != id(pd2)
        assert pd1 != pd2
        assert not (pd1 == pd2)


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


def test_push_gerrit_direct(
    monkeypatch, gerrit_push_map, local_log, remote_log, local_repo_patch,
    mock_check_pushed
):
    assert local_log() != remote_log()
    monkeypatch.chdir(str(local_repo_patch))
    push_to_scm('master', gerrit_push_map, direct=True)
    assert local_log() == remote_log()
    push_to_scm('not_master', gerrit_push_map, direct=True)
    assert local_log() == remote_log('not_master')


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
        'master', gerrit_push_map, unless_hash='HEAD', if_not_exists=True
    )
    assert remote_log('master') == remote_log('refs/for/master')
    assert not mock_check_pushed.called
    push_to_scm(
        'master', gerrit_push_map, unless_hash='master', if_not_exists=True
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


@pytest.mark.parametrize('push_map_data, remote_url, expected', [
    (
        [{'^(https|(git+)?ssh)://((.*)@)?server\\.com(:29418)?/(.*)$': {
            'push_url': 'ssh://jenkins@server.com:29418/\\6',
            'host_key': 'some_host_key',
            'merge_flags': '--code-review=2 --verified=1',
            'maintainer_groups': ['\\6', '\\6-maintainers'],
            'maintainers': '\\4',
            'anonymous_clone_url': 'http://server.com/\\6'
        }}],
        'ssh://jenkins@server.com:29418/project_name',
        PushDetails(
            push_url='ssh://jenkins@server.com:29418/project_name',
            host_key='some_host_key',
            merge_flags=['--code-review=2', '--verified=1'],
            maintainer_groups=['project_name', 'project_name-maintainers'],
            maintainers=['jenkins'],
            anonymous_clone_url='http://server.com/project_name',
        )
    )
])
def test_get_push_details_expansion(push_map_data, remote_url, expected):
    out = get_push_details(push_map_data, remote_url)
    assert isinstance(out, PushDetails)
    assert out.push_url == expected.push_url
    assert out.host_key == expected.host_key
    assert out.merge_flags == expected.merge_flags
    assert out.maintainer_groups == expected.maintainer_groups
    assert out.maintainers == expected.maintainers
    assert out.anonymous_clone_url == expected.anonymous_clone_url
    assert out == expected


@pytest.mark.parametrize('yaml_object, expected', [
    (['val1', 'val2', 'val3'], ['val1', 'val2', 'val3']),
    (['val1 val2 val3'], ['val1', 'val2', 'val3']),
    (['val1', 'val2 val3'], ['val1', 'val2', 'val3']),
    (['val1  \n val2 val3'], ['val1', 'val2', 'val3']),
    ({'k1': 'v1', 'k2': 'v2'}, ['k1', 'k2']),
    ({'k1 k2': 'v2'}, ['k1', 'k2']),
    ({'k2 k1': 'v2'}, ['k2', 'k1']),
    ('      ', []),
])
def test_parse_yaml_to_list(yaml_object, expected):
    out = parse_yaml_to_list(yaml_object)
    assert out == expected


@pytest.mark.parametrize(
    ('struct', 'expected'), [
        (dict(), PushMapSyntaxError),
        (dict(push_url='some_url'), PushDetails('some_url')),
        (
            dict(push_url='some_url', host_key='some_key'),
            PushDetails('some_url', 'some_key', [])
        ),
        ('not-a-dict', PushMapSyntaxError),
        (['still', 'not', 'a', 'dict'], PushMapSyntaxError),
        (7, PushMapSyntaxError),
        (
            dict(push_url='some_url', merge_flags=['op1', 'op2', 'op3']),
            PushDetails('some_url', merge_flags=['op1', 'op2', 'op3'])
        ),
        (
            dict(push_url='some_url', merge_flags=['op1', 'op2 op3']),
            PushDetails('some_url', merge_flags=['op1', 'op2', 'op3'])
        ),
        (
            dict(push_url='some_url', merge_flags='op1 op2 op3'),
            PushDetails('some_url', merge_flags=['op1', 'op2', 'op3'])
        ),
        (
            dict(push_url='a_url', merge_flags={'o1': 1, 'o2': 2, 'o3': 3}),
            PushDetails('a_url', merge_flags=['o1=1', 'o2=2', 'o3=3'])
        ),
        (
            dict(push_url='a_url', maintainer_groups='gr1 gr2 gr3'),
            PushDetails('a_url', maintainer_groups=['gr1', 'gr2', 'gr3'])
        ),
        (
            dict(push_url='a_url', maintainers='mr1 mr2 mr3'),
            PushDetails('a_url', maintainers=['mr1', 'mr2', 'mr3'])
        ),
        (
            dict(push_url='a_url', anonymous_clone_url='anon_url'),
            PushDetails('a_url', anonymous_clone_url='anon_url')
        ),
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


@pytest.fixture
def push_details():
    return PushDetails(
        push_url='ssh://user@gerrit.server:29418/some_project.git',
        host_key='a_host_key',
        merge_flags=[
            '--code-review', '+2', '--verified', '+1', '--label', 'custom=+1',
        ],
    )


def test_check_if_similar_patch_pushed(monkeypatch, push_details):
    communicate = MagicMock(side_effect=[(
        '{"rowCount": 1}'.encode('utf-8'), 'STDERR'.encode('utf-8')
    )])
    poll = MagicMock(side_effect=(0,))
    process = MagicMock(communicate=communicate, poll=poll)
    popen = MagicMock(side_effect=(process,))
    monkeypatch.setattr('scripts.pusher.Popen', popen)
    get_patch_header = MagicMock(side_effect=('some-md5-checksum',))
    monkeypatch.setattr('scripts.pusher.get_patch_header', get_patch_header)
    branch = 'master'
    out = check_if_similar_patch_pushed(push_details, branch)
    assert popen.called
    assert list(popen.call_args[0][0]) == [
        'ssh', '-p', '29418', 'user@gerrit.server',
        'gerrit', 'query', '--format=JSON',
        'project:some_project', 'message:some-md5-checksum',
        'branch:{}'.format(branch)
    ]
    assert get_patch_header.called
    assert get_patch_header.call_args == call('x-md5')
    assert out


@pytest.mark.parametrize(
    ('header', 'default', 'commit', 'expected'), [
        ('header-at-top', None, 'HEAD', 'Header at top value'),
        ('header-in-middle', None, 'HEAD', 'Header in middle value'),
        ('spaced_out_header', None, 'HEAD', 'Spaced out value'),
        ('bottom-header1', None, 'HEAD', 'Value 1'),
        ('bottom-header1', 'given default', 'HEAD', 'Value 1'),
        ('bottom-header2', None, 'HEAD', 'Value 2'),
        ('numeric-header', None, 'HEAD', '17'),
        ('none-existant-header', None, 'HEAD', KeyError),
        ('none-existant-header', 'given default', 'HEAD', 'given default'),
        ('header-at-top', None, 'HEAD^', 'Header at top first commit value'),
        ('header-in-middle', None, 'HEAD^', KeyError),
    ]
)
def test_get_patch_header(
    monkeypatch, gitrepo, header, default, commit, expected
):
    repo = gitrepo(
        'repo',
        {
            'msg': dedent(
                """
                First commit message title

                header-at-top: Header at top first commit value
                """
            ).lstrip(),
            'files': {'dummy.txt': 'dummy1'},
        },
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
            'files': {'dummy.txt': 'dummy2'},
        }
    )
    monkeypatch.chdir(repo)
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            get_patch_header(header, default, commit)
    else:
        out = get_patch_header(header, default, commit)
        assert out == expected


@pytest.mark.parametrize('header_value,expected', [
    ('yes', True),
    ('Yes', True),
    ('true', True),
    ('TRUE', True),
    ('no', False),
    ('NO', False),
    ('false', False),
])
def test_patch_header_is_true(monkeypatch, header_value, expected):
    get_patch_header = MagicMock(side_effect=cycle((header_value,)))
    monkeypatch.setattr('scripts.pusher.get_patch_header', get_patch_header)
    out = patch_header_is_true('a_patch_header', 'a_commit_ref')
    assert get_patch_header.called
    assert get_patch_header.call_args == \
        call('a_patch_header', 'no', 'a_commit_ref')
    assert out == expected
    out = patch_header_is_true('another_patch_header')
    assert get_patch_header.called
    assert get_patch_header.call_args == \
        call('another_patch_header', 'no', 'HEAD')
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


@pytest.fixture
def local_repo_tag(local_repo_patch, git_at):
    git_at(local_repo_patch)('tag', 'some-tag')
    git_at(local_repo_patch)('tag', '-a', 'some-atag', '-m', 'some-tag')
    return local_repo_patch


@pytest.mark.parametrize('can_merge', [True, False])
def test_merge_to_scm(monkeypatch, can_merge, push_details):
    git_rev_parse = MagicMock(side_effect=('some_git_hash',))
    can_merge_to_scm = MagicMock(side_effect=(can_merge,))
    read_push_details = MagicMock(side_effect=(push_details,))
    gerrit_cli = MagicMock()
    monkeypatch.setattr('scripts.pusher.git_rev_parse', git_rev_parse)
    monkeypatch.setattr('scripts.pusher.can_merge_to_scm', can_merge_to_scm)
    monkeypatch.setattr('scripts.pusher.read_push_details', read_push_details)
    monkeypatch.setattr('scripts.pusher.gerrit_cli', gerrit_cli)
    merge_to_scm('/push/map/path', 'a_commit_ref', 'a_header')
    assert can_merge_to_scm.called
    assert can_merge_to_scm.call_args == \
        call('/push/map/path', 'a_commit_ref', 'a_header')
    if can_merge:
        assert git_rev_parse.called
        assert git_rev_parse.call_args == call('a_commit_ref')
        assert read_push_details.called
        assert read_push_details.call_args == call('/push/map/path')
        assert gerrit_cli.called
        assert gerrit_cli.call_args == call(
            push_details,
            'review', 'some_git_hash',
            '--submit',
            '--code-review', '+2',
            '--verified', '+1',
            '--label', 'custom=+1',
        )
    else:
        assert not git_rev_parse.called
        assert not read_push_details.called
        assert not gerrit_cli.called


def test_get_patch_owner(monkeypatch, push_details):
    git_rev_parse = MagicMock(side_effect=('some_git_hash',))
    gerrit_cli = MagicMock(side_effect=(dedent(
        '''
        {"owner":{"username":"some_user"}}
        {"rowCount":1}
        '''
    ).lstrip(),))
    monkeypatch.setattr('scripts.pusher.git_rev_parse', git_rev_parse)
    monkeypatch.setattr('scripts.pusher.gerrit_cli', gerrit_cli)
    out = get_patch_owner(push_details, 'some_git_ref')
    assert git_rev_parse.called
    assert git_rev_parse.call_args == call('some_git_ref')
    assert gerrit_cli.called
    assert gerrit_cli.call_args == call(
        push_details, 'query', '--format=json', 'commit:some_git_hash'
    )
    assert out == 'some_user'


def test_get_no_patch_owner(monkeypatch, push_details):
    git_rev_parse = MagicMock(side_effect=('some_git_hash',))
    gerrit_cli = MagicMock(side_effect=(dedent(
        '''
        {"rowCount":0}
        '''
    ).lstrip(),))
    monkeypatch.setattr('scripts.pusher.git_rev_parse', git_rev_parse)
    monkeypatch.setattr('scripts.pusher.gerrit_cli', gerrit_cli)
    out = get_patch_owner(push_details, 'some_git_ref')
    assert git_rev_parse.called
    assert git_rev_parse.call_args == call('some_git_ref')
    assert gerrit_cli.called
    assert gerrit_cli.call_args == call(
        push_details, 'query', '--format=json', 'commit:some_git_hash'
    )
    assert out is None


@pytest.mark.parametrize('lsm_out, expected', [
    (dedent(
        '''
        id\tusername\tfull name\temail
        1000001\tuser1\tFirst User\tuser1@domain.com
        1000002\tuser2\tSecond User\tuser2@domain.com
        1000003\tuser3\tThird User\tuser3@domain.com
        '''
    ).lstrip(), True),
    (dedent(
        '''
        id\tusername\tfull name\temail
        1000003\tuser3\tThird User\tuser3@domain.com
        '''
    ).lstrip(), False),
    (dedent(
        '''
        Group not found or not visible
        '''
    ).lstrip(), False),
])
def test_gerrit_user_in_group(monkeypatch, push_details, lsm_out, expected):
    gerrit_cli = MagicMock(side_effect=(lsm_out,))
    monkeypatch.setattr('scripts.pusher.gerrit_cli', gerrit_cli)
    out = gerrit_user_in_group(push_details, 'user2', 'a_group')
    assert gerrit_cli.called
    assert gerrit_cli.call_args == call(
        push_details, 'ls-members', '--recursive', 'a_group'
    )
    assert out == expected


@pytest.mark.parametrize('has_hdr, u_in_group, u_in_file, exp', [
    (True,  True,  True,  True),
    (True,  True,  False, True),
    (True,  False, True,  True),
    (True,  False, False, False),
    (False, True,  True,  False),
    (False, True,  False, False),
    (False, False, True,  False),
    (False, False, False, False),
    (None,  True,  True,  True),
    (None,  True,  False, True),
    (None,  False, True,  True),
    (None,  False, False, False),
])
def test_can_merge_to_scm(has_hdr, u_in_group, u_in_file, exp, monkeypatch):
    add_key_to_known_hosts = MagicMock()
    patch_header_is_true = MagicMock(side_effect=(has_hdr,))
    gerrit_user_in_group = MagicMock(side_effect=(False, u_in_group))
    get_patch_owner = MagicMock(side_effect=('a_user',))
    push_details = PushDetails(
        push_url='a_push_url',
        host_key='some_host_key',
        maintainer_groups=['gr1', 'gr2'],
        maintainers=u_in_file and ['a_user'] or [],
    )
    read_push_details = MagicMock(side_effect=(push_details,))
    monkeypatch.setattr(
        'scripts.pusher.add_key_to_known_hosts', add_key_to_known_hosts
    )
    monkeypatch.setattr(
        'scripts.pusher.patch_header_is_true', patch_header_is_true
    )
    monkeypatch.setattr(
        'scripts.pusher.gerrit_user_in_group', gerrit_user_in_group
    )
    monkeypatch.setattr('scripts.pusher.get_patch_owner', get_patch_owner)
    monkeypatch.setattr('scripts.pusher.read_push_details', read_push_details)
    if has_hdr is None:
        check_header = None
    else:
        check_header = 'a_header'
    out = can_merge_to_scm('/push/map/path', 'a_commit', check_header)
    assert out == exp
    if has_hdr is None:
        assert not patch_header_is_true.called
    else:
        assert patch_header_is_true.called
        assert patch_header_is_true.call_args == call('a_header', 'a_commit')
    if has_hdr or has_hdr is None:
        assert read_push_details.called
        assert read_push_details.call_args == call('/push/map/path')
        assert add_key_to_known_hosts.called
        assert add_key_to_known_hosts.call_args == call('some_host_key')
        assert get_patch_owner.called
        assert get_patch_owner.call_args == call(push_details, 'a_commit')
        if u_in_file:
            assert not gerrit_user_in_group.called
        else:
            assert gerrit_user_in_group.called
            assert gerrit_user_in_group.call_count == 2
            assert gerrit_user_in_group.call_args_list == [
                call(push_details, 'a_user', 'gr1'),
                call(push_details, 'a_user', 'gr2'),
            ]
    else:
        assert not read_push_details.called
        assert not add_key_to_known_hosts.called
        assert not get_patch_owner.called
        assert not gerrit_user_in_group.called


def test_read_push_details_ws(gerrit_push_map, local_repo, monkeypatch):
    monkeypatch.chdir(str(local_repo))
    push_details = read_push_details(gerrit_push_map)
    expected_push_url = local_repo.dirname + '/remote'
    assert push_details.push_url == str(expected_push_url)


def test_read_push_details(gerrit_push_map, local_repo, monkeypatch):
    monkeypatch.chdir(str(local_repo))
    push_details = read_push_details(gerrit_push_map, '/my-url')
    expected_push_url = '/my-url'
    assert push_details.push_url == expected_push_url
