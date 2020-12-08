#!/usr/bin/env python
"""test_git_utils.py - Tests for git_utils.py
"""
import os
from textwrap import dedent
from subprocess import CalledProcessError
import pytest
from six import string_types
import stdci_libs.git_utils
from stdci_libs.git_utils import (
    commit_files, staged_files, commit_message,
    commit_title, commit_headers, files_checksum,
    GitProcessError, git_rev_parse, InvalidGitRef, prep_git_repo,
    get_name_from_repo_url, CouldNotParseRepoURL, get_repo_root
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


@pytest.fixture
def repo(gitrepo, monkeypatch):
    r = gitrepo(
        'repo',
        {
            'msg': 'First commit',
            'files': {
                'file1': 'File 1 content\n',
                'file2': 'File 2 content\n',
                'dir1/file11': 'File 11 content\n',
                'dir1/file12': 'File 12 content\n',
            },
        },
    )
    monkeypatch.chdir(r)
    return r

@pytest.mark.parametrize('files,change,touch,changed,commits', [
    ('', 'file1', '', '', 1),
    ('file1', 'file1', '', 'file1', 2),
    ('file1', '', 'file1', '', 1),
    ('file1 file2', 'file1', '', 'file1', 2),
    ('file1 file2', 'file1', 'file2', 'file1', 2),
    ('file1 file2', 'file1 file2', '', 'file1 file2', 2),
    
    ('file1', 'file1 file2', '', 'file1', 2),
    
    ('file1 file3', 'file1 file3', '', 'file1 file3', 2),
    ('file1 file2', 'file1 file3', '', 'file1', 2),
    ('file3', 'file3', '', 'file3', 2),
    ('file1 file3', 'file3', '', 'file3', 2),
    ('dir1/file11 file2', 'dir1/file11', '', 'dir1/file11', 2),
    ('dir1', 'dir1/file11 dir1/file12', '', 'dir1/file11 dir1/file12', 2),
    ('dir1', 'dir1/file11', 'dir1/file12', 'dir1/file11', 2),
    ('file1', 'dir1/file11 dir1/file12', '', '', 1),
    ('file1 no_exist', 'file1', '', 'file1', 2),
    ('file1 no_exist', '', '', '', 1),
])
def test_commit_files(
    git, repo, files, change, touch, changed, commits
):
    files = files.split()
    change = change.split()
    touch = touch.split()
    changed = changed.split()

    for f in change:
        (repo / f).write('Changed {} content'.format(f), ensure=True)
    for f in touch:
        fp = (repo / f)
        fp.write(fp.read())

    out = commit_files(files)
    assert isinstance(out, list)
    assert out == changed
    assert len(git('log', '--oneline').splitlines()) == commits
    if changed:
        assert sorted((
            git('log', '-1', '--pretty=format:', '--name-only')
        ).strip().splitlines()) == sorted(changed)
        last_message = git('log', '-1', '--pretty=format:%s')
        if len(changed) == 1:
            assert last_message == 'Changed: {}'.format(changed[0])
        else:
            assert last_message == 'Changed {} files'.format(len(changed))

@pytest.mark.parametrize('files,add,change,changed,commits', [
    ('file1', 'file2', 'file1', 'file1', 2),
    ('file1', 'file1', 'file1', 'file1', 2),
    ('file1', 'file2', '', '', 1),
    ('file1', 'file3', 'file1', 'file1', 2),
])
def test_commit_files_pre_added(
    git, repo, files, add, change, changed, commits
):
    files = files.split()
    add = add.split()
    change = change.split()
    changed = changed.split()

    for f in add:
        (repo / f).write('Added {} content'.format(f), ensure=True)
        git('add', f)
    for f in change:
        (repo / f).write('Changed {} content'.format(f), ensure=True)

    out = commit_files(files)
    assert isinstance(out, list)
    assert out == changed
    assert len(git('log', '--oneline').splitlines()) == commits
    if changed:
        assert sorted((
            git('log', '-1', '--pretty=format:', '--name-only')
        ).strip().splitlines()) == sorted(changed)
        last_message = git('log', '-1', '--pretty=format:%s')
        if len(changed) == 1:
            assert last_message == 'Changed: {}'.format(changed[0])
        else:
            assert last_message == 'Changed {} files'.format(len(changed))

def test_commit_files_branch(repo, git, git_last_sha):
    commit_files(['file1'], 'tmp_branch')
    assert len(git('log', '--oneline').splitlines()) == 1
    assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/master'

    (repo / 'file1').write('Changed content')
    commit_files(['file1'], 'tmp_branch')
    assert len(git('log', '--oneline').splitlines()) == 2
    assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'
    tmp_branch_sha = git_last_sha(repo)

    git('checkout', 'master')
    assert len(git('log', '--oneline').splitlines()) == 1
    (repo / 'file1').write('Changed content again')
    commit_files(['file1'], 'tmp_branch')
    assert len(git('log', '--oneline').splitlines()) == 2
    assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'
    assert git_last_sha(repo) != tmp_branch_sha

    (repo / 'file1').write('Changed content once more')
    commit_files(['file1'], 'tmp_branch')
    assert len(git('log', '--oneline').splitlines()) == 3
    assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'

    git('checkout', 'master')
    assert len(git('log', '--oneline').splitlines()) == 1
    (repo / 'file1').write('Changed content')
    commit_files(['file1'])
    assert len(git('log', '--oneline').splitlines()) == 2
    assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/master'

@pytest.mark.parametrize('changed_files,commit_msg,expected', [
    (
        'file1', 'GIVEN_COMMIT_MESSGAE',
        'GIVEN_COMMIT_MESSGAE\nHEADERS_GO_HERE'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n',
        'GIVEN_COMMIT_MESSGAE\nHEADERS_GO_HERE'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n\nBODY',
        'GIVEN_COMMIT_MESSGAE\n\nBODY\nHEADERS_GO_HERE'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n\nBODY\n  \n\n',
        'GIVEN_COMMIT_MESSGAE\n\nBODY\nHEADERS_GO_HERE'
    ),
    (
        'file1', None,
        'TITLE_GOES_HERE\nHEADERS_GO_HERE'
    ),
    (
        'file1 file2', None,
        'TITLE_GOES_HERE\n\n'
        'Changed files:\n- file1\n- file2\n'
        'HEADERS_GO_HERE'
    ),
])
def test_commit_message(
    monkeypatch, changed_files, commit_msg, expected
):
    monkeypatch.setattr(
        stdci_libs.git_utils, 'commit_title', lambda *a: 'TITLE_GOES_HERE'
    )

    monkeypatch.setattr(
        stdci_libs.git_utils, 'commit_headers', lambda *a: 'HEADERS_GO_HERE'
    )
    out = commit_message(changed_files.split(), commit_msg)
    assert out == expected

@pytest.mark.parametrize('changed_files,commit_msg,expected', [
    (
        'file1', 'GIVEN_COMMIT_MESSGAE',
        'GIVEN_COMMIT_MESSGAE'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n',
        'GIVEN_COMMIT_MESSGAE'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n\nBODY',
        'GIVEN_COMMIT_MESSGAE\n\nBODY'
    ),
    (
        'file1', 'GIVEN_COMMIT_MESSGAE\n\nBODY\n  \n\n',
        'GIVEN_COMMIT_MESSGAE\n\nBODY'
    ),
    (
        'file1', None,
        'TITLE_GOES_HERE'
    ),
    (
        'file1 file2', None,
        'TITLE_GOES_HERE\n\n'
        'Changed files:\n- file1\n- file2'
    ),
])
def test_commit_message_no_headers(
    monkeypatch, changed_files, commit_msg, expected
):
    monkeypatch.setattr(
        stdci_libs.git_utils, 'commit_title', lambda *a: 'TITLE_GOES_HERE'
    )
    monkeypatch.setattr(stdci_libs.git_utils, 'commit_headers', lambda *a: '')
    out = commit_message(changed_files.split(), commit_msg)
    assert out == expected

@pytest.mark.parametrize(
    'changed_files,change_id_headers,extra_headers,expected',
    [
        ('file1', '', {}, ''),
        (
            'file1', 'Change-Id', {},
            '\nChange-Id: ICHECKSUM_GOES_HERE'
        ),
        (
            'file1', 'Change-Id x-md5', {},
            '\nx-md5: ICHECKSUM_GOES_HERE'
            '\nChange-Id: ICHECKSUM_GOES_HERE'
        ),
        (
            'file1', 'x-md5 Change-Id', {},
            '\nx-md5: ICHECKSUM_GOES_HERE'
            '\nChange-Id: ICHECKSUM_GOES_HERE'
        ),
        (
            'file1', 'x-md5 Change-Id x-md5', {},
            '\nx-md5: ICHECKSUM_GOES_HERE'
            '\nChange-Id: ICHECKSUM_GOES_HERE'
        ),
        (
            'file1', 'Change-Id', {'B_hdr': 'val1', 'A_hdr': 7},
            '\nA_hdr: 7'
            '\nB_hdr: val1'
            '\nChange-Id: ICHECKSUM_GOES_HERE'
        ),
        ('', '', {}, ''),
        ('', 'Change-Id', {}, ''),
        (
            '', 'Change-Id', {'B_hdr': 'val1', 'A_hdr': 7},
            '\nA_hdr: 7'
            '\nB_hdr: val1'
        ),
    ]
)
def test_commit_headers(
    monkeypatch, changed_files, change_id_headers,
    extra_headers, expected
):
    monkeypatch.setattr(
        stdci_libs.git_utils, 'files_checksum', lambda *a: 'CHECKSUM_GOES_HERE'
    )
    out = commit_headers(
        changed_files.split(), change_id_headers.split(), extra_headers
    )
    assert out == expected

def test_files_checksum(repo):
    checksum_1 = files_checksum(['file1'])
    assert isinstance(checksum_1, string_types)
    assert checksum_1.isalnum()

    checksum_2 = files_checksum(['file2'])
    assert checksum_2.isalnum()
    assert checksum_1 != checksum_2

    checksum_1_11 = files_checksum(['file1', 'dir1/file11'])
    assert checksum_1_11.isalnum()
    assert checksum_1_11 != checksum_1
    assert checksum_1_11 != checksum_2

    checksum_11_1 = files_checksum(['dir1/file11', 'file1'])
    assert checksum_1_11 == checksum_11_1

    checksum_1_11_1 = files_checksum(
        ['file1', 'dir1/file11', 'file1']
    )
    assert checksum_1_11 == checksum_1_11_1

    (repo / 'file1').write('New content')
    (repo / 'file2').write('New content')
    checksum_1_c = files_checksum(['file1'])
    checksum_2_c = files_checksum(['file2'])
    assert checksum_1_c != checksum_1
    assert checksum_2_c != checksum_2
    assert checksum_1_c != checksum_2_c

    (repo / 'file1').write('New content')
    checksum_1_c2 = files_checksum(['file1'])
    assert checksum_1_c2 == checksum_1_c

def test_get_repo_root(monkeypatch, repo_with_patches):
    monkeypatch.chdir(repo_with_patches)
    repo = get_repo_root()
    assert os.path.isdir(os.path.join(repo,".git")) == True

