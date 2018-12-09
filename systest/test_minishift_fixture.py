#!/usr/bin/env python3
"""test_minishift_fixture.py - Tests from minishift_fixture.py
"""
from textwrap import dedent

from sysscripts.minishift_fixture import minishift
from sysscripts.minishift_fixture import MiniShift


class TestMinishif(object):
    def test_call(self):
        ms = MiniShift('someprofile')
        out = ms('version')
        assert out.startswith('minishift v')

    def test_sub_call(self):
        ms = MiniShift('someprofile')
        out = ms.version()
        assert out.startswith('minishift v')

    def test__status_split(self):
        inp = dedent(
            '''
            Minishift:  Running
            Profile:    minishift
            OpenShift:  Running (openshift v3.11.0+8de5c34-71)
            DiskUsage:  14% of 19G (Mounted On: /mnt/sda1)
            CacheUsage: 1.661 GB (used by oc binary, ISO or cached images)
            '''
        ).lstrip()
        expected = {
            'Minishift':  'Running',
            'Profile':    'minishift',
            'OpenShift':  'Running (openshift v3.11.0+8de5c34-71)',
            'DiskUsage':  '14% of 19G (Mounted On: /mnt/sda1)',
            'CacheUsage': '1.661 GB (used by oc binary, ISO or cached images)',
        }
        out = MiniShift._status_split(inp)
        assert out == expected


minishift.logdest = 'exported-artifacts/minishift_logs'
minishift.loglevel = 5
minishift.showlibmachinelogs = True
minishift.truncate_exc = False


def test_minishift(minishift):
    stt = minishift.status()
    assert stt['Minishift'] == 'Running'
    assert stt['Profile'] == 'minishiftfixture'
    assert stt['OpenShift'].startswith('Running')
