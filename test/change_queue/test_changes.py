#!/usr/bin/env python
"""change_queue/test_changes.py - Tests for change_queue.changes
"""
try:
    import pytest
    from unittest.mock import MagicMock, sentinel
except ImportError:
    from mock import MagicMock, sentinel

from scripts.change_queue.changes import DisplayableChange, \
    DisplayableChangeWrapper, ChangeInStream, ChangeInStreamWrapper, \
    GerritMergedChange, GitMergedChange


class TestDisplayableChange(object):
    def test_presentable_id(self):
        chg = DisplayableChange()
        assert chg.id == chg
        assert chg.presentable_id == str(chg)
        chg.id = sentinel.change_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.change_id)
        chg.presentable_id = sentinel.presentable_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.presentable_id)

    def test_url(self):
        chg = DisplayableChange()
        assert chg.url is None
        chg.url = sentinel.url
        assert chg.url == sentinel.url


class TestDisplayableChangeWrapper(object):
    class SomeObject(object):
        pass

    def test_presentable_id(self):
        obj = self.SomeObject()
        chg = DisplayableChangeWrapper(obj)
        assert chg.id == obj
        assert chg.presentable_id == str(obj)
        obj.id = sentinel.change_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.change_id)
        obj.presentable_id = sentinel.presentable_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.presentable_id)

    def test_url(self):
        obj = self.SomeObject()
        chg = DisplayableChangeWrapper(obj)
        assert chg.url is None
        obj.url = sentinel.url
        assert chg.url == sentinel.url

    def test_presentable_id_on_displayable(self):
        obj = DisplayableChange()
        chg = DisplayableChangeWrapper(obj)
        assert chg.id == obj
        assert chg.presentable_id == str(obj)
        obj.id = sentinel.change_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.change_id)
        obj.presentable_id = sentinel.presentable_id
        assert chg.id == sentinel.change_id
        assert chg.presentable_id == str(sentinel.presentable_id)

    def test_url_on_displayable(self):
        obj = DisplayableChange()
        chg = DisplayableChangeWrapper(obj)
        assert chg.url is None
        obj.url = sentinel.url
        assert chg.url == sentinel.url


class TestChangeInStream(object):
    def test_stream_id(self):
        chg = ChangeInStream()
        assert chg.stream_id is None
        chg.stream_id = sentinel.stream_id
        assert chg.stream_id == sentinel.stream_id


class TestChangeInStreamWrapper(object):
    class SomeObject(object):
        pass

    def test_stream_id(self):
        obj = self.SomeObject()
        chg = ChangeInStreamWrapper(obj)
        assert chg.stream_id is None
        obj.stream_id = sentinel.stream_id
        assert chg.stream_id == sentinel.stream_id

    def test_stream_id_on_in_stream(self):
        obj = ChangeInStream()
        chg = ChangeInStreamWrapper(obj)
        assert chg.stream_id is None
        obj.stream_id = sentinel.stream_id
        assert chg.stream_id == sentinel.stream_id


class TestGerritMergedChange(object):
    @pytest.fixture
    def a_gerrit_patchset(self):
        return MagicMock(**{
            'change.url': 'http://some.gerrit/1234567',
            'change.number': 1234567,
            'patchset_number': 8,
            'project.name': 'some_project',
            'branch.name': 'some_branch',
            'server.host': 'some.gerrit',
            'server.port': 29418,
        })

    @pytest.fixture
    def a_gerrit_merged_change(self, a_gerrit_patchset):
        return GerritMergedChange(a_gerrit_patchset)

    def test_id(self, a_gerrit_merged_change):
        assert a_gerrit_merged_change.id == ('some.gerrit', 29418, 1234567)

    def test_presentable_id(self, a_gerrit_merged_change):
        assert a_gerrit_merged_change.presentable_id == \
            '1234567,8 (some_project)'

    def test_url(self, a_gerrit_merged_change):
        assert a_gerrit_merged_change.url == 'http://some.gerrit/#/c/1234567/8'

    def test_stream_id(self, a_gerrit_merged_change):
        assert a_gerrit_merged_change.stream_id == \
            ('some.gerrit', 29418, 'some_project', 'some_branch')

    def test_mail_recipents(self, a_gerrit_merged_change):
        infra = ('infra@ovirt.org',)
        assert not a_gerrit_merged_change.added_recipients
        assert a_gerrit_merged_change.rejected_recipients == infra
        assert not a_gerrit_merged_change.successful_recipients
        assert a_gerrit_merged_change.failed_recipients == infra


class TestGitMergedChange(object):
    @pytest.fixture
    def a_git_merged_change(self):
        return GitMergedChange(
            project='project1',
            branch='master',
            sha='1234567890abcdef1234567890abcdef1234567',
            url='http://example.com/patch/1234567',
        )

    def test_id(self, a_git_merged_change):
        assert a_git_merged_change.id == \
            ('project1', '1234567890abcdef1234567890abcdef1234567')

    def test_presentable_id(self, a_git_merged_change):
        assert a_git_merged_change.presentable_id == \
            '1234567 (project1)'

    def test_stream_id(self, a_git_merged_change):
        assert a_git_merged_change.stream_id == ('project1', 'master')
