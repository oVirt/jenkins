#!/usr/bin/env python
"""change_queue/test_changes.py - Tests for change_queue.changes
"""
try:
    from unittest.mock import sentinel
except ImportError:
    from mock import sentinel

from scripts.change_queue.changes import DisplayableChange, \
    DisplayableChangeWrapper, ChangeInStream, ChangeInStreamWrapper


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
