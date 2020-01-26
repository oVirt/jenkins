#!/usr/bin/env python
"""test_gerrit.py - Tests for gerrit.py
"""
from __future__ import absolute_import, print_function
import pytest
import random
from base64 import b64encode
from six import iteritems
try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call

from stdci_libs.gerrit import GerritPatchset


class TestGerritPatchset(object):
    def test_from_jenkins_env(self, monkeypatch):
        msg = 'This is a commit message'
        env = {
            'GERRIT_BRANCH': 'master',
            'GERRIT_CHANGE_COMMIT_MESSAGE': b64encode(msg.encode()).decode(),
            'GERRIT_CHANGE_ID': 'I5b35b72af9a40b1564792dbfcf30a82cf3f5ccb5',
            'GERRIT_CHANGE_NUMBER': '4',
            'GERRIT_CHANGE_OWNER_EMAIL': 'bkorren@redhat.com',
            'GERRIT_CHANGE_OWNER_NAME': 'Barak Korren',
            'GERRIT_CHANGE_SUBJECT': 'Just a dummy change for testing',
            'GERRIT_CHANGE_URL': 'https://gerrit-staging.phx.ovirt.org/4',
            'GERRIT_HOST': 'gerrit-staging.phx.ovirt.org',
            'GERRIT_PATCHSET_NUMBER': '2',
            'GERRIT_PATCHSET_REVISION': 'some-revision',
            'GERRIT_PATCHSET_UPLOADER_EMAIL': 'bkorren@redhat.com',
            'GERRIT_PATCHSET_UPLOADER_NAME': 'Barak Korren',
            'GERRIT_PORT': '29418',
            'GERRIT_PROJECT': 'barak-test',
            'GERRIT_REFSPEC': 'refs/changes/04/4/2',
            'GERRIT_SCHEME': 'ssh',
            'GERRIT_TOPIC': 'Dummy change for testing',
        }
        for var, val in iteritems(env):
            monkeypatch.setenv(var, val)
        ps = GerritPatchset.from_jenkins_env()
        assert ps.refspec == env['GERRIT_REFSPEC']
        assert ps.change.branch.project.server.host == env['GERRIT_HOST']
        assert ps.change.branch.project.server.port == int(env['GERRIT_PORT'])
        assert ps.change.branch.project.name == env['GERRIT_PROJECT']
        assert ps.change.branch.name == env['GERRIT_BRANCH']
        assert ps.change.change_id == env['GERRIT_CHANGE_ID']
        assert ps.change.number == int(env['GERRIT_CHANGE_NUMBER'])
        assert ps.refspec == env['GERRIT_REFSPEC']
        assert ps.patchset_number == int(env['GERRIT_PATCHSET_NUMBER'])
        assert ps.commit_message == msg

    @pytest.mark.parametrize(
        ('args', 'kwargs', 'exp_args'),
        [
            ([], dict(abandon=True), '--abandon'),
            (
                [], dict(label={'verify': 1, 'code-review': -1}),
                '--label code-review=-1 --label verify=1',
            ),
            (
                [], dict(verify=1, code_review=-1),
                '--label code-review=-1 --label verify=1',
            ),
            (
                [], dict(label={'verify': -1}, verify=1, code_review=-1),
                '--label code-review=-1 --label verify=-1',
            ),
            ([], dict(message="foo mc'foo"), "--message 'foo mc'\"'\"'foo'"),
            (
                ['bar', "mc'bar"], dict(message="foo"),
                "--message 'foo bar mc'\"'\"'bar'",
            ),
            (['foo', 7], dict(), "--message 'foo 7'"),
            ([], dict(publish=True), '--publish'),
            ([], dict(rebase=True), '--rebase'),
            ([], dict(restore=True), '--restore'),
            ([], dict(submit=True), '--submit'),
        ]
    )
    def test_review(self, args, kwargs, exp_args):
        cnum = random.randint(1000, 100000)
        psnum = random.randint(0, 100)
        # Fake a change object that has the methods we need
        change = MagicMock(
            spec_set=('number', 'server'), number=cnum,
            **{'server.run_ssh_command.return_value': None}
        )
        ps = GerritPatchset(change, None, psnum, None, None, None, None)
        exp_cmd = 'review {0},{1} {2}'.format(cnum, psnum, exp_args)
        ps.review(*args, **kwargs)
        assert change.server.run_ssh_command.called
        assert change.server.run_ssh_command.call_args == call(exp_cmd)
