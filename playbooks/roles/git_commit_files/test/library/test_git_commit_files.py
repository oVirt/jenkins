"""test_git_commit_files.py - Tests for the git_commit_files Ansible module
"""
from __future__ import absolute_import, division, print_function
import pytest
from collections import Mapping
from six import string_types

import ansible.module_utils.basic
from git_commit_files import GitCommitFilesModule


class TestGitCommitFileModule(object):
    @pytest.fixture
    def repo(self, gitrepo, monkeypatch):
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

    @pytest.fixture
    def instance(self, monkeypatch):
        def _load_params():
            return {'files': []}

        monkeypatch.setattr(
            ansible.module_utils.basic, '_load_params', _load_params
        )
        return GitCommitFilesModule()

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
    def test__commit_files(
        self, git, repo, instance, files, change, touch, changed, commits
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

        out = instance._commit_files(files)
        assert isinstance(out, Mapping)
        assert out['changed_files'] == changed
        assert len(git('log', '--oneline').splitlines()) == commits
        if changed:
            assert sorted((
                git('log', '-1', '--pretty=format:', '--name-only')
            ).strip().splitlines()) == sorted(changed)
            last_messgae = git('log', '-1', '--pretty=format:%s')
            if len(changed) == 1:
                assert last_messgae == 'Changed: {}'.format(changed[0])
            else:
                assert last_messgae == 'Changed {} files'.format(len(changed))

    @pytest.mark.parametrize('files,add,change,changed,commits', [
        ('file1', 'file2', 'file1', 'file1', 2),
        ('file1', 'file1', 'file1', 'file1', 2),
        ('file1', 'file2', '', '', 1),
        ('file1', 'file3', 'file1', 'file1', 2),
    ])
    def test__commit_files_pre_added(
        self, git, repo, instance, files, add, change, changed, commits
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

        out = instance._commit_files(files)
        assert isinstance(out, Mapping)
        assert out['changed_files'] == changed
        assert len(git('log', '--oneline').splitlines()) == commits
        if changed:
            assert sorted((
                git('log', '-1', '--pretty=format:', '--name-only')
            ).strip().splitlines()) == sorted(changed)
            last_messgae = git('log', '-1', '--pretty=format:%s')
            if len(changed) == 1:
                assert last_messgae == 'Changed: {}'.format(changed[0])
            else:
                assert last_messgae == 'Changed {} files'.format(len(changed))

    @pytest.mark.parametrize('changed_files,expected', [
        ('a_file.txt', 'Changed: a_file.txt'),
        ('fil1 fil2 fil3', 'Changed 3 files'),
        ('a_dir/a_file.txt', 'Changed: a_dir/a_file.txt'),
        (
            'a_really/rediculesly/insanely/extremely/very/long/file_path.txt',
            'Changed: file_path.txt'
        ),
        (
            'a_really_rediculesly_insanely_extremely_very_long_file_name.txt',
            'Changed one file'
        ),
    ])
    def test__commit_title(self, instance, changed_files, expected):
        out = instance._commit_title(changed_files.split())
        assert out == expected

    def test__commit_files_branch(self, repo, instance, git, git_last_sha):
        instance._commit_files(['file1'], 'tmp_branch')
        assert len(git('log', '--oneline').splitlines()) == 1
        assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/master'

        (repo / 'file1').write('Changed content')
        instance._commit_files(['file1'], 'tmp_branch')
        assert len(git('log', '--oneline').splitlines()) == 2
        assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'
        tmp_branch_sha = git_last_sha(repo)

        git('checkout', 'master')
        assert len(git('log', '--oneline').splitlines()) == 1
        (repo / 'file1').write('Changed content again')
        instance._commit_files(['file1'], 'tmp_branch')
        assert len(git('log', '--oneline').splitlines()) == 2
        assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'
        assert git_last_sha(repo) != tmp_branch_sha

        (repo / 'file1').write('Changed content once more')
        instance._commit_files(['file1'], 'tmp_branch')
        assert len(git('log', '--oneline').splitlines()) == 3
        assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/tmp_branch'

        git('checkout', 'master')
        assert len(git('log', '--oneline').splitlines()) == 1
        (repo / 'file1').write('Changed content')
        instance._commit_files(['file1'])
        assert len(git('log', '--oneline').splitlines()) == 2
        assert git('symbolic-ref', 'HEAD').strip() == 'refs/heads/master'

    @pytest.mark.parametrize('changed_files,commit_message,expected', [
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
    def test__commit_message(
        self, monkeypatch, instance, changed_files, commit_message, expected
    ):
        monkeypatch.setattr(
            instance, '_commit_title', lambda *a: 'TITLE_GOES_HERE'
        )
        monkeypatch.setattr(
            instance, '_commit_headers', lambda *a: 'HEADERS_GO_HERE'
        )
        out = instance._commit_message(changed_files.split(), commit_message)
        assert out == expected

    @pytest.mark.parametrize('changed_files,commit_message,expected', [
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
    def test__commit_message_no_headers(
        self, monkeypatch, instance, changed_files, commit_message, expected
    ):
        monkeypatch.setattr(
            instance, '_commit_title', lambda *a: 'TITLE_GOES_HERE'
        )
        monkeypatch.setattr(instance, '_commit_headers', lambda *a: '')
        out = instance._commit_message(changed_files.split(), commit_message)
        assert out == expected

    @pytest.mark.parametrize(
        'changed_files,change_id_headers,extra_headers,expected',
        [
            ('file1', '', {}, ''),
            (
                'file1', 'Change-Id', {},
                '\nChange-Id: CHECKSUM_GOES_HERE'
            ),
            (
                'file1', 'Change-Id x-md5', {},
                '\nx-md5: CHECKSUM_GOES_HERE'
                '\nChange-Id: CHECKSUM_GOES_HERE'
            ),
            (
                'file1', 'x-md5 Change-Id', {},
                '\nx-md5: CHECKSUM_GOES_HERE'
                '\nChange-Id: CHECKSUM_GOES_HERE'
            ),
            (
                'file1', 'x-md5 Change-Id x-md5', {},
                '\nx-md5: CHECKSUM_GOES_HERE'
                '\nChange-Id: CHECKSUM_GOES_HERE'
            ),
            (
                'file1', 'Change-Id', {'B_hdr': 'val1', 'A_hdr': 7},
                '\nA_hdr: 7'
                '\nB_hdr: val1'
                '\nChange-Id: CHECKSUM_GOES_HERE'
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
    def test__commit_headers(
        self, monkeypatch, instance, changed_files, change_id_headers,
        extra_headers, expected
    ):
        monkeypatch.setattr(
            instance, '_files_checksum', lambda *a: 'CHECKSUM_GOES_HERE'
        )
        out = instance._commit_headers(
            changed_files.split(), change_id_headers.split(), extra_headers
        )
        assert out == expected

    def test__files_checksum(self, repo, instance):
        checksum_1 = instance._files_checksum(['file1'])
        assert isinstance(checksum_1, string_types)
        assert checksum_1.isalnum()

        checksum_2 = instance._files_checksum(['file2'])
        assert checksum_2.isalnum()
        assert checksum_1 != checksum_2

        checksum_1_11 = instance._files_checksum(['file1', 'dir1/file11'])
        assert checksum_1_11.isalnum()
        assert checksum_1_11 != checksum_1
        assert checksum_1_11 != checksum_2

        checksum_11_1 = instance._files_checksum(['dir1/file11', 'file1'])
        assert checksum_1_11 == checksum_11_1

        checksum_1_11_1 = instance._files_checksum(
            ['file1', 'dir1/file11', 'file1']
        )
        assert checksum_1_11 == checksum_1_11_1

        (repo / 'file1').write('New content')
        (repo / 'file2').write('New content')
        checksum_1_c = instance._files_checksum(['file1'])
        checksum_2_c = instance._files_checksum(['file2'])
        assert checksum_1_c != checksum_1
        assert checksum_2_c != checksum_2
        assert checksum_1_c != checksum_2_c

        (repo / 'file1').write('New content')
        checksum_1_c2 = instance._files_checksum(['file1'])
        assert checksum_1_c2 == checksum_1_c
