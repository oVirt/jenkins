#!/usr/bin/env python
"""conftest.py - Common pytest fixtures
"""
from __future__ import absolute_import, print_function
import pytest
from six import iteritems
from collections import namedtuple


@pytest.fixture
def jenkins_env(monkeypatch, tmpdir):
    env_spec = dict(
        job_base_name='some_job',
        worspace=tmpdir,
    )
    for var, value in iteritems(env_spec):
        monkeypatch.setenv(var.upper(), value)
    monkeypatch.chdir(env_spec['worspace'])
    return namedtuple('jenkins_env_spec', env_spec.keys())(*env_spec.values())


@pytest.fixture
def not_jenkins_env(monkeypatch):
    monkeypatch.delenv('JOB_BASE_NAME', False)
