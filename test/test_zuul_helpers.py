#!/usr/bin/env python
# test_zuul_helpers.py - Tests for zuul_helpers.py
#
import pytest
from six import string_types, iteritems
import yaml
try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from scripts.zuul_helpers import (
    is_gated_project, merge_project_yaml, is_gated_project_entry
)
from scripts import zuul_helpers


@pytest.fixture
def projects(gitrepo):
    prj_defs = {
        'onefile': {
            'zuul.yaml': [
                {'project': {'name': 'onefile', 'id': 'p1', 'gated': True}},
            ],
        },
        'onedotfile': {
            '.zuul.yaml': [
                {'project': {'name': 'onedotfile', 'id': 'p1', 'gated': True}},
            ],
        },
        'unnamed': {
            'zuul.yaml': [{'project': {'id': 'p1', 'gated': True}}],
        },
        'dir': {
            'zuul.d/base-project.yaml': [{'project': {'id': 'p1'}}],
            'zuul.d/jobs.yaml': [
                {'job': {'name': 'j1'}},
                {'job': {'name': 'j2'}},
            ],
            'zuul.d/project.yaml': [
                {'project': {'id': 'p2', 'gated': True}},
                {'project': {'name': 'p3', 'id': 'p3'}},
            ],
        },
        'file+': {
            'zuul.yaml': [{'project': {'id': 'p1'}}],
            'zuul.d/a.yaml': [{'project': {'id': 'p2'}}],
            '.zuul.yaml': [{'project': {'id': 'p3'}}],
            '.zuul.d/b.yaml': [{'project': {'id': 'p4'}}],
        },
        'dir+': {
            'zuul.d/a.yaml': [{'project': {'id': 'p2'}}],
            '.zuul.yaml': [{'project': {'id': 'p3'}}],
            '.zuul.d/b.yaml': [{'project': {'id': 'p4'}}],
        },
        'dotfile+': {
            '.zuul.yaml': [{'project': {'id': 'p3'}}],
            '.zuul.d/b.yaml': [{'project': {'id': 'p4'}}],
        },
        'dotdir+': {
            '.zuul.d/b.yaml': [{'project': {'id': 'p4'}}],
        },
    }
    prj_defs = {
        name: {
            fn:
                fc if isinstance(fc, string_types) else
                yaml.safe_dump(fc, default_flow_style=False)
            for fn, fc in iteritems(content)
        }
        for name, content in iteritems(prj_defs)
    }
    prj_defs = {
        name: gitrepo(name, {'files': content})
        for name, content in iteritems(prj_defs)
    }
    return prj_defs


@pytest.mark.parametrize('prj,prj_name,exp_prj,exp_out', [
    ('onefile', None, 'p1', True),
    ('onefile', 'other-project', None, False),
    ('onedotfile', None, 'p1', True),
    ('unnamed', None, 'p1', True),
    ('unnamed', 'foo', 'p1', True),
    ('unnamed', 'bar', 'p1', True),
    ('dir', None, 'p1+p2', True),
    ('dir', 'foo', 'p1+p2', True),
    ('dir', 'p3', 'p1+p2+p3', True),
    ('file+', None, 'p1', False),
    ('dir+', None, 'p2', False),
    ('dotfile+', None, 'p3', False),
    ('dotdir+', None, 'p4', False),
])
def test_is_gated_project(
    monkeypatch, projects, prj, prj_name, exp_prj, exp_out
):

    def is_gated_project_entry(entry, *args, **kwargs):
        return entry.get('gated', False)
    is_gated_project_entry = MagicMock(side_effect=is_gated_project_entry)

    def merge_project_yaml(entries, *args, **kwargs):
        return {
            'id': '+'.join(e['id'] for e in entries),
            'gated': any(e.get('gated', False) for e in entries),
        }
    merge_project_yaml = MagicMock(side_effect=merge_project_yaml)

    monkeypatch.setattr(
        zuul_helpers, 'is_gated_project_entry', is_gated_project_entry
    )
    monkeypatch.setattr(
        zuul_helpers, 'merge_project_yaml', merge_project_yaml
    )

    out = is_gated_project(projects[prj], prj_name)
    if exp_prj is None:
        assert not is_gated_project_entry.called
    else:
        assert is_gated_project_entry.call_args[0][0]['id'] == exp_prj
    assert out == exp_out


@pytest.mark.parametrize('entries,gate_pipelines,expected', [
    (
        ({'name': 'prj'}, {'templates': ['t1', 't2']}),
        '^gt$',
        {'templates': ['t1', 't2']}
    ),
    (
        ({'templates': ['t1', 't2']}, {'templates': ['t3']}),
        '^gt$',
        {'templates': ['t1', 't2', 't3']}
    ),
    (
        ({'gt': {'jobs': ['j1']}}, {'gt': {'jobs': ['j2']}}),
        '^gt$',
        {'gt': {'jobs': ['j1', 'j2']}},
    ),
    (
        ({'gt': {'jobs': ['j1']}}, {'gt': {'jobs': ['j2', 'j1']}}),
        '^gt$',
        {'gt': {'jobs': ['j1', 'j2', 'j1']}},
    ),
    (
        ({'gt1': {'jobs': ['j1']}}, {'gt2': {'jobs': ['j2', 'j1']}}),
        '^gt$',
        {},
    ),
    (
        ({'gt1': {'jobs': ['j1']}}, {'gt2': {'jobs': ['j2', 'j1']}}),
        '^gt.$',
        {'gt1': {'jobs': ['j1']}, 'gt2': {'jobs': ['j2', 'j1']}},
    ),
    (
        (
            {'templates': ['t1', 't2'], 'gt': {'jobs': ['1', '2']}},
            {'templates': ['t3'], 'gt': {'jobs': ['3']}, 'p': {'jobs': ['4']}},
            {'gt': {'jobs': ['5']}, 'p': {'jobs': ['6', '7']}},
        ),
        '^gt$',
        {'templates': ['t1', 't2', 't3'], 'gt': {'jobs': ['1', '2', '3', '5']}}
    )

])
def test_merge_project_yaml(entries, gate_pipelines, expected):
    out = merge_project_yaml(entries, gate_pipelines)
    assert out == expected


@pytest.mark.parametrize('input,expected', [
    ({
        'entry': {'templates': ['the-gated-project']},
    }, True),
    ({
        'entry': {'templates': ['some-template', 'the-gated-project']},
    }, True),
    ({
        'entry': {'templates': ['some-template', 'the-gated-project']},
        'gate_templates': '^really-gated$',
    }, False),
    ({
        'entry': {'gate-patch': {'jobs': ['run-gate-job']}},
    }, True),
    ({
        'entry': {'gate-patch': {'jobs': [{'run-gate-job': {}}]}},
    }, True),
    ({
        'entry': {'gate-patch': {'jobs': ['job1', {'job2': {}}]}},
    }, False),
    ({
        'entry': {'gate-patch': {'jobs': ['run-gate-job']}},
        'gate_jobs': '2$',
    }, False),
    ({
        'entry': {'gate-patch': {'jobs': ['run-gate-job']}},
        'gate_pipelines': '^gate$',
    }, False),
    ({
        'entry': {'gate-patch': {'jobs': ['job1', {'job2': {}}]}},
        'gate_jobs': '2$',
    }, True),
])
def test_is_gated_project_entry(input, expected):
    out = is_gated_project_entry(**input)
    assert out == expected
