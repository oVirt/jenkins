#!/usr/bin/env python3
"""minishift_fixture.py - A PyTest fixture that uses MiniShift
"""
import re
import pytest
import sh
import os

from scripts.object_utils import object_proxy


class MiniShift(object_proxy):
    def __init__(
        self, profile='minishift', logdest=None, loglevel=None,
        showlibmachinelogs=False, truncate_exc=True
    ):
        minishift = sh.minishift.bake('--profile', profile)
        minishift = minishift.bake(_truncate_exc=truncate_exc)
        if logdest:
            os.makedirs(logdest, exist_ok=True)
            minishift = minishift.bake('--log_dir', logdest)
        if loglevel:
            minishift = minishift.bake('-v', loglevel)
        if showlibmachinelogs:
            minishift = minishift.bake('--show-libmachine-logs')
        super().__init__(minishift)

    def status(self):
        return self._status_split(self('status'))

    @staticmethod
    def _status_split(ms_stdout):
        sep = re.compile(':\s+')
        kv_pairs = (sep.split(l, 1) for l in ms_stdout.splitlines())
        return {k: v for k, v in kv_pairs}


@pytest.fixture(scope='session')
def minishift():
    loglevel = getattr(minishift, 'loglevel')
    logdest = getattr(minishift, 'logdest')
    showlibmachinelogs = getattr(minishift, 'showlibmachinelogs')
    truncate_exc = getattr(minishift, 'truncate_exc')
    ms = MiniShift(
        'minishiftfixture', logdest, loglevel, showlibmachinelogs, truncate_exc
    )
    try:
        ms.start()
    except sh.ErrorReturnCode_1:
        ms.delete('-f')
        ms.start()
    yield ms
    ms.stop()
    ms.delete('-f')
