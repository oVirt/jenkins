#!/bin/env python
"""test_automation_options.py - Tests module for automation_options.py"""

import pytest
from scripts.stdci_dsl.options.globals import _get_global_options
from scripts.stdci_dsl.options.parser_utils import get_merged_options
from scripts.stdci_dsl.options.defaults import apply_default_options
from scripts.stdci_dsl.options.defaults.values import DefaultValue
from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.options.normalize import (
    _render_template,
    _resolve_stdci_yaml_config,
    _resolve_stdci_list_config,
    _resolve_stdci_script,
)


@pytest.fixture(scope='function')
def stdci_project_dir(tmpdir):
    project_dir = tmpdir.mkdir('stdci-project')
    project_dir.mkdir('automation')
    project_dir.join(
        'automation/check-patch.environment.yaml'
    ).write('test: yaml cfg\n')
    project_dir.join('automation/check-patch.sh').write('script')
    project_dir.join('automation/check-patch.packages').write('p1\np2')
    project_dir.join('automation/check-patch.yumrepos').write('yumreposfile')
    return project_dir


@pytest.mark.parametrize(
    "thread,templates,expected",
    [
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64', {}),
            '{{ stage }}.{{ substage }}.{{ distro }}.{{ arch }}',
            'check-patch.default.el7.x86_64'
        )
    ]
)
def test_render_template(thread, templates, expected):
    out = _render_template(thread, templates)
    assert out == expected


@pytest.mark.parametrize(
    "options,expected",
    [
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'script':
                    {
                        'fromfile': 'automation/check-patch.sh'
                    },
                    'ignore_if_missing_script': False
                },
            ),
            'automation/check-patch.sh'
        ),
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'script':
                    {
                        'fromfile':
                        [
                            'no',
                            'no',
                            'check-patch.sh',
                            'no'
                        ]
                    },
                    'ignore_if_missing_script': False,
                    'scripts_directory': 'automation'
                },
            ),
            'automation/check-patch.sh'
        ),
    ]
)
def test_resolve_stdci_script(options, expected, stdci_project_dir):
    out = _resolve_stdci_script(stdci_project_dir, options)
    ex = stdci_project_dir / expected
    assert out == ex


@pytest.mark.parametrize(
    "options,expected",
    [
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'packages':
                    {
                        'fromlistfile': 'automation/check-patch.packages'
                    },
                },
            ),
            ['p1', 'p2']
        ),
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'packages':
                    {
                        'default_value': DefaultValue,
                        'fromlistfile': 'check-patch.packages'
                    },
                },
            ),
            ['p1', 'p2']
        ),
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'packages':
                    {
                        'fromlistfile': 'check-patch.packages'
                    },
                    'scripts_directory': 'automation'
                },
            ),
            ['p1', 'p2']
        )
    ]
)
def test_resolve_stdci_list_config(options, expected, stdci_project_dir):
    assert _resolve_stdci_list_config(
        stdci_project_dir, options, 'packages'
    ) == expected


@pytest.mark.parametrize(
    "options,expected",
    [
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'environment':
                    {
                        'fromfile': 'automation/check-patch.environment.yaml'
                    },
                },
            ),
            {'test': 'yaml cfg'}
        ),
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'environment':
                    {
                        'default_value': DefaultValue,
                        'fromfile': 'check-patch.environment.yaml'
                    },
                },
            ),
            {'test': 'yaml cfg'}
        ),
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64',
                {
                    'environment':
                    {
                        'fromfile': 'check-patch.environment.yaml'
                    },
                    'scripts_directory': 'automation'
                },
            ),
            {'test': 'yaml cfg'}
        )
    ]
)
def test_resolve_stdci_yaml_config(options, expected, stdci_project_dir):
    assert _resolve_stdci_yaml_config(
        stdci_project_dir, options, 'environment'
    ) == expected


@pytest.mark.parametrize(
    "options1,options2,expected",
    [
        (
            {'packages': ['p1', 'p2', 'p3']},
            {'packages': ['p4']},
            {'packages': ['p4']},
        ),
        (
            {'packages': ['p1']},
            {'repos': ['r1']},
            {'packages': ['p1'], 'repos': ['r1']}
        ),
        (
            {'repos': ['r1'], 'release_branches': ['master', 'test']},
            {'repos': ['r2'], 'release_branches': ['4.1']},
            {'repos': ['r2'], 'release_branches': ['4.1']}
        ),
        (
            {'release_branches': 'br1', 'runtime_req': 'rq1'},
            {'repos': 'r1'},
            {'release_branches': 'br1', 'runtime_req': 'rq1', 'repos': 'r1'}
        ),
        (
            {'release_branches': 'br1', 'runtime_req': 'rq1'},
            {'release_branches': 'br2', 'runtime_req': 'rq2'},
            {'release_branches': 'br2', 'runtime_req': 'rq2'},
        )
    ]
)
def test_get_merged_options(options1, options2, expected):
    assert get_merged_options(options1, options2) == expected


@pytest.mark.parametrize(
    "threads,expected",
    [
        (
            [
                JobThread(
                    None, 'custom', None, None,
                    {
                        'mounts': {'fromfile': 'path_to_file'},
                        'scripts_directory': 'myCustomDir',
                        'packages': {'fromfile': ['f1', 'f2']},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                    }
                ),
            ],
            [
                JobThread(None, 'custom', None, None,
                    {
                        'scripts_directory': 'myCustomDir',
                        'yumrepos':
                        {
                            'default_value': DefaultValue,
                            'fromfile':
                            [
                                '{{ stage }}.{{ substage }}.yumrepos.{{ distro }}.{{ arch }}',
                                '{{ stage }}.{{ substage }}.yumrepos.{{ distro }}',
                                '{{ stage }}.{{ substage }}.yumrepos.{{ arch }}',
                                '{{ stage }}.{{ substage }}.yumrepos',
                            ]
                        },
                        'script':
                        {
                            'default_value': DefaultValue,
                            'fromfile':
                            [
                                '{{ stage }}.{{ substage }}.sh.{{ distro }}.{{ arch }}',
                                '{{ stage }}.{{ substage }}.sh.{{ distro }}',
                                '{{ stage }}.{{ substage }}.sh.{{ arch }}',
                                '{{ stage }}.{{ substage }}.sh',
                            ]
                        },
                        'upstream_sources': {},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                        'runtime_requirements':
                        {
                            'host_arch': 'x86_64',
                            'host_distro': 'el7',
                            'support_nesting_level': 0
                        },
                        'mounts': {'fromfile': 'path_to_file'},
                        'release_branches': {},
                        'packages': {'fromfile': ['f1', 'f2']},
                        'ignore_if_missing_script': False}
                    )
                ],
        ),
        (
            [
                JobThread(
                    None, 'default', None, None,
                    {
                        'mounts': {'fromfile': 'path_to_file'},
                        'scripts_directory': 'myCustomDir',
                        'packages': {'fromfile': ['f1', 'f2']},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                    }
                ),
            ],
            [
                JobThread(None, 'default', None, None,
                    {
                        'scripts_directory': 'myCustomDir',
                        'yumrepos':
                        {
                            'default_value': DefaultValue,
                            'fromfile':
                            [
                                '{{ stage }}.{{ substage }}.yumrepos.{{ distro }}.{{ arch }}',
                                '{{ stage }}.{{ substage }}.yumrepos.{{ distro }}',
                                '{{ stage }}.{{ substage }}.yumrepos.{{ arch }}',
                                '{{ stage }}.{{ substage }}.yumrepos',
                                '{{ stage }}.yumrepos.{{ distro }}.{{ arch }}',
                                '{{ stage }}.yumrepos.{{ distro }}',
                                '{{ stage }}.yumrepos.{{ arch }}',
                                '{{ stage }}.yumrepos'
                            ]
                        },
                        'script':
                        {
                            'default_value': DefaultValue,
                            'fromfile':
                            [
                                '{{ stage }}.{{ substage }}.sh.{{ distro }}.{{ arch }}',
                                '{{ stage }}.{{ substage }}.sh.{{ distro }}',
                                '{{ stage }}.{{ substage }}.sh.{{ arch }}',
                                '{{ stage }}.{{ substage }}.sh',
                                '{{ stage }}.sh.{{ distro }}.{{ arch }}',
                                '{{ stage }}.sh.{{ distro }}',
                                '{{ stage }}.sh.{{ arch }}',
                                '{{ stage }}.sh'
                            ]
                        },
                        'upstream_sources': {},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                        'runtime_requirements':
                        {
                            'host_arch': 'x86_64',
                            'host_distro': 'el7',
                            'support_nesting_level': 0
                        },
                        'mounts': {'fromfile': 'path_to_file'},
                        'release_branches': {},
                        'packages': {'fromfile': ['f1', 'f2']},
                        'ignore_if_missing_script': False
                    }
               )
            ],
        ),
        (
            [
                JobThread(
                    None, 'default', None, None,
                    {
                        'mounts': {'fromfile': 'path_to_file'},
                        'scripts_directory': 'myCustomDir',
                        'packages': {'fromfile': ['f1', 'f2']},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                        'script': 'specified inline',
                        'yumrepos': ['y1', 'y2'],
                    }
                ),
            ],
            [
                JobThread(
                    None, 'default', None, None,
                    {
                        'scripts_directory': 'myCustomDir',
                        'yumrepos': ['y1', 'y2'],
                        'script': 'specified inline',
                        'upstream_sources': {},
                        'repos': ['r1', 'r2'],
                        'environment': {'some env req': 123},
                        'runtime_requirements':
                        {
                            'host_arch': 'x86_64',
                            'host_distro': 'el7',
                            'support_nesting_level': 0
                        },
                        'mounts': {'fromfile': 'path_to_file'},
                        'release_branches': {},
                        'packages': {'fromfile': ['f1', 'f2']},
                        'ignore_if_missing_script': False
                    }
                )
            ]
        ),
    ]
)
def test_apply_default_options(threads, expected):
    assert list(apply_default_options(threads)) == expected


@pytest.mark.parametrize(
    "threads,expected",
    [
        (
            [
                JobThread('a', 'b', 'c', 'd', {'p': 'p'}),
                JobThread('c', 'd', 'c', 'd', {'release_branches': 'master'})
            ],
            {'release_branches': 'master'}
        ),
        (
            [
                JobThread('a', 'b', 'c', 'd', {'p': 'p'}),
                JobThread('c', 'd', 'c', 'd', {'upstream_sources': 'usrc'})
            ],
            {'upstream_sources': 'usrc'}
        ),
        (
            [
                JobThread('a', 'b', 'c', 'd', {'p': 'p'}),
                JobThread('c', 'd', 'c', 'd', {'runtime_requirements': 'rtr'})
            ],
            {'runtime_requirements': 'rtr'}
        ),
        (
            [
                JobThread('a', 'b', 'c', 'd', {'p': 'p'}),
                JobThread('c', 'd', 'c', 'd', {'e': 'e'})
            ],
            {}
        ),
        (
            [
                JobThread(
                    'a', 'b', 'c', 'd',
                    {'runtime_requirements': 'rtr', 'upstream_sources': 'usrc'},
                ),
                JobThread('c', 'd', 'c', 'd', {'release_branches': 'rbrnch'})
            ],
            {
                'release_branches': 'rbrnch',
                'runtime_requirements': 'rtr',
                'upstream_sources': 'usrc'
            }
        ),
    ]
)
def test_get_global_options_cfg(threads, expected):
    assert _get_global_options(threads) == expected