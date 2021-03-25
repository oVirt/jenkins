#!/bin/env python
"""project_dir_api.py - API for automation vectors"""

import pytest

from stdci_libs.stdci_dsl.job_thread import JobThread
from stdci_libs.stdci_dsl.api import (
    get_threads, RuntimeEnvDefinition,
    NoThreadForEnv, get_threads_with_globals
)
from stdci_libs.stdci_dsl.api.formatters.threads import (
    _pipeline_dict_formatter, _conf_checker_terse_formatter, format_table,
    _conf_checker_verbose_formatter, trim_zero, trim_str, trim_str_end,
    trim_path, TrimFunctionValueError
)
from stdci_libs.stdci_dsl.options.normalize import RepoConfig
from stdci_libs.nested_config import DepthLevel

@pytest.fixture(scope='function')
def project_dir(tmpdir):
    root = tmpdir
    root.join('secrets_file').write('a')
    automation = tmpdir.mkdir('automation')
    (automation/'check-patch.sh').write('code code code ...')
    (automation/'check-patch.repos').write('repo1\nrepo2\nrepo3')
    (root/'stdci.yaml').write(
        "STAGE: check-patch\n"
        "Packages: [pkg1, pkg2, pkg3]\n"
        "Environment:\n"
        "  - NAME: 'test'\n"
        "    value-From:\n"
        "      runtime-Env: 'PWD'\n"
    )
    return root


def test_RuntimeEnvDefinition(project_dir):
    obj = RuntimeEnvDefinition(
        str(project_dir), 'check-patch', 'default', 'el7', 'x86_64'
    )
    assert obj.script == 'automation/check-patch.sh'
    assert obj.yumrepos is None
    assert obj.environment == [
        {'name': 'test', 'valuefrom': {'runtimeenv': 'PWD'}}
    ]
    assert obj.repos == [
        RepoConfig('repo-734392d7a1ac9e3cfe63184b3e48eb0c', 'repo1'),
        RepoConfig('repo-1f02dddd81d2931b7c82f0a857dc2431', 'repo2'),
        RepoConfig('repo-1fb4cda750e4eac7714ee79c6bb4db28', 'repo3'),
    ]
    assert obj.packages == ['pkg1', 'pkg2', 'pkg3']
    assert obj.mounts == []


def test_RuntimeEnvDefinition_NoThreadForEnv_exception(project_dir):
    with pytest.raises(NoThreadForEnv) as exinfo:
        RuntimeEnvDefinition(
            str(project_dir), 'build', 'default', 'fc25', 'ppc64le'
        )
    assert 'Could not find thread for requested env: {0}'.format(
        ('build', 'default', 'fc25', 'ppc64le')) == str(exinfo.value)


def test_runner_yaml_dumper(project_dir, tmpdir):
    env = RuntimeEnvDefinition(
        str(project_dir), 'check-patch', 'default', 'el7', 'x86_64'
    )
    fmt = env.format('yaml_dumper')
    assert fmt == (
        "environment:\n"
        "- name: test\n"
        "  valuefrom:\n"
        "    runtimeenv: PWD\n"
        "hash: d0bf2d0c60a85aa61fa9ffd039e6198c\n"
        "mounts: {}\n"
        "packages:\n"
        "- pkg1\n"
        "- pkg2\n"
        "- pkg3\n"
        "repos:\n"
        "  repo-1f02dddd81d2931b7c82f0a857dc2431: repo2\n"
        "  repo-1fb4cda750e4eac7714ee79c6bb4db28: repo3\n"
        "  repo-734392d7a1ac9e3cfe63184b3e48eb0c: repo1\n"
        "script: %s\n"
        "yumrepos: ''\n"
    ) % ('automation/check-patch.sh')


def test_get_threads_with_globals(project_dir):
    threads, gopts = get_threads_with_globals(str(project_dir), 'check-patch')
    assert list(threads) == [
        JobThread(
            'check-patch', 'default', 'el7', 'x86_64',
            {
                'yumrepos': None,
                'script': 'automation/check-patch.sh',
                'upstreamsources': {},
                'repos': [
                    RepoConfig('repo-734392d7a1ac9e3cfe63184b3e48eb0c', 'repo1'), # noqa
                    RepoConfig('repo-1f02dddd81d2931b7c82f0a857dc2431', 'repo2'), # noqa
                    RepoConfig('repo-1fb4cda750e4eac7714ee79c6bb4db28', 'repo3'), # noqa
                ],
                'environment': [
                    {'name': 'test', 'valuefrom': {'runtimeenv': 'PWD'}}
                ],
                'runtimerequirements': {
                    'supportnestinglevel': 0,
                    'hostdistro': 'any',
                    'isolationlevel': 'virtual',
                    'sriovnic': False,
                    'jenkinsmaster': 'all',
                },
                'mounts': [],
                'releasebranches': {},
                'packages': ['pkg1', 'pkg2', 'pkg3'],
                'ignore_if_missing_script': True,
                'reporting': {'style': 'default', },
                'timeout': 10800,
                'containers': [],
                'podspecs': [],
                DepthLevel: 1
            }
        )
    ]
    assert gopts == {
        'releasebranches': {},
        'upstreamsources': {}
    }


def test_get_threads(project_dir):
    threads = get_threads(str(project_dir), 'check-patch')
    assert list(threads) == [
        JobThread(
            'check-patch', 'default', 'el7', 'x86_64',
            {
                'yumrepos': None,
                'script': 'automation/check-patch.sh',
                'upstreamsources': {},
                'repos': [
                    RepoConfig('repo-734392d7a1ac9e3cfe63184b3e48eb0c', 'repo1'), # noqa
                    RepoConfig('repo-1f02dddd81d2931b7c82f0a857dc2431', 'repo2'), # noqa
                    RepoConfig('repo-1fb4cda750e4eac7714ee79c6bb4db28', 'repo3'), # noqa
                ],
                'environment': [
                    {'name': 'test', 'valuefrom': {'runtimeenv': 'PWD'}}
                ],
                'runtimerequirements': {
                    'supportnestinglevel': 0,
                    'hostdistro': 'any',
                    'isolationlevel': 'virtual',
                    'sriovnic': False,
                    'jenkinsmaster': 'all',
                },
                'mounts': [],
                'releasebranches': {},
                'packages': ['pkg1', 'pkg2', 'pkg3'],
                'ignore_if_missing_script': True,
                'reporting': {'style': 'default', },
                'timeout': 10800,
                'containers': [],
                'podspecs': [],
                DepthLevel: 1
            }
        )
    ]


@pytest.mark.parametrize(
    "threads,global_cfg,expected",
    [
        (
            [],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                'global_config:\n'
                '  release_branches:\n'
                '    r: b\n'
                '  upstream_sources:\n'
                '    u: s\n'
                'jobs: []\n'
            )
        ),
        (
            [
                JobThread(
                    'check-patch', 'default', 'fc25', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                        'reporting': {'style': 'default'},
                        'timeout': '3h',
                        'containers': [],
                        'podspecs': [],
                    }
                ),
                JobThread(
                    'build-artifacts', 'default', 'fc26', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                        'reporting': {'style': 'default'},
                        'timeout': '3h',
                        'containers': [],
                        'podspecs': [],
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'reporting': {'style': 'default'},
                        'timeout': '4h',
                        'containers': [],
                        'podspecs': [],
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el8', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'reporting': {'style': 'classic'},
                        'timeout': '3h',
                        'containers': [{
                            'image': 'docker.io/centos:8',
                            'args': ['s'],
                        }],
                        'decorate': True,
                        'podspecs': [
                            'apiVersion: v1\n'
                            'kind: Pod\n'
                            'spec:\n'
                            '  foo\n',
                        ]
                    }
                ),
            ],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                'global_config:\n'
                '  release_branches:\n'
                '    r: b\n'
                '  upstream_sources:\n'
                '    u: s\n'
                'jobs:\n'
                '- arch: x86_64\n'
                '  containers: []\n'
                '  decorate: false\n'
                '  distro: fc25\n'
                '  podspecs: []\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '  timeout: 3h\n'
                '- arch: x86_64\n'
                '  containers: []\n'
                '  decorate: false\n'
                '  distro: fc26\n'
                '  podspecs: []\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: build-artifacts\n'
                '  substage: default\n'
                '  timeout: 3h\n'
                '- arch: x86_64\n'
                '  containers: []\n'
                '  decorate: false\n'
                '  distro: el7\n'
                '  podspecs: []\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '  timeout: 4h\n'
                '- arch: x86_64\n'
                '  containers:\n'
                '  - args:\n'
                '    - s\n'
                '    image: docker.io/centos:8\n'
                '  decorate: true\n'
                '  distro: el8\n'
                '  podspecs:\n'
                '  - "apiVersion: v1\\nkind: Pod\\nspec:\\n  foo\\n"\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: classic\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '  timeout: 3h\n'
            )
        ),
    ]
)
def test_pipeline_formatter(threads, global_cfg, expected):
    threads_it = iter(threads)
    out = _pipeline_dict_formatter(threads_it, global_cfg)
    assert out == expected


@pytest.mark.parametrize(
    "threads,global_cfg,expected",
    [
        (
            [],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                '\n'
            )
        ),
        (
            [
                JobThread(
                    'check-patch', 'default', 'fc25', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'fc26', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                    }
                )
            ],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                'Stage: check-patch\n'
                'Substag  Dist  Arch    S  If\n'
                '----------------------------\n'
                'default  fc25  x86_64  s    \n'
                'default  fc26  x86_64  s    \n'
                'default  el7   x86_64  s    \n'
            )
        ),
        (
            [
                JobThread(
                    'check-patch', 'default', 'fc25', 'x86_64',
                    {
                        'script': 'sabcdefghijklmnopqrstuvwxyzabcdefghijk',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'check-patch', 'ssabcdefghijklmnopqrstuvwxyzabcdefghijk',
                    'fc26', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                    }
                )
            ],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                'Stage: check-patch\n'
                'Substage                           Dist  Arch    Script      '
                '                If\n'
                '-------------------------------------------------------------'
                '------------------\n'
                'default                            fc25  x86_64  sabcdefghijk'
                'lmnopqrstuv...    \n'
                'ssabcdefghijklmnopqrstuvwxyzab...  fc26  x86_64  s           '
                '                  \n'
                'default                            el7   x86_64  s           '
                '                  \n'
            )
        ),
    ]
)
def test_conf_checker_terse_formatter_output(
        capsys, threads, global_cfg, expected):
    threads_it = iter(threads)
    template = 80
    print(_conf_checker_terse_formatter(threads_it, global_cfg, template))
    out, _ = capsys.readouterr()
    assert out == expected

@pytest.mark.parametrize(
    "threads,global_cfg,expected",
    [
        (
            [],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                '\n'
            )
        ),
        (
            [
                JobThread(
                    'check-patch', 'default', 'fc25', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'build-artifacts', 'default', 'fc26', 'x86_64',
                    {
                        'script': 's',
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'runtimerequirements': {'r': 'r'},
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                    }
                )
            ],
            {
                'releasebranches': {'r': 'b'},
                'upstreamsources': {'u': 's'},
            },
            (
                '-------------------------------------------------------------'
                '-------------------\n'
                'stage: check-patch\n'
                'substage: default\n'
                'distro: fc25\n'
                'arch: x86_64\n'
                'script: s\n'
                '-------------------------------------------------------------'
                '-------------------\n'
                'stage: build-artifacts\n'
                'substage: default\n'
                'distro: fc26\n'
                'arch: x86_64\n'
                'script: s\n'
                '-------------------------------------------------------------'
                '-------------------\n'
                'stage: check-patch\n'
                'substage: default\n'
                'distro: el7\n'
                'arch: x86_64\n'
                'script: s\n'
                '-------------------------------------------------------------'
                '-------------------\n'
                '\n'
            )
        ),
    ]
)
def test_conf_checker_verbose_formatter_output(
        capsys, threads, global_cfg, expected):
    threads_it = iter(threads)
    template = 80
    print(_conf_checker_verbose_formatter(threads_it, global_cfg, template))
    out, _ = capsys.readouterr()
    assert out == expected

def test_trim_zero():
    assert trim_zero('') == ''
    assert trim_zero('foo') == 'foo'
    assert trim_zero('foo', 1) == 'foo'

def test_trim_str():
    assert trim_str('') == ''
    assert trim_str('foo', 5) == 'foo'
    assert trim_str('foo', 1) == 'f'
    assert trim_str('foobar', 5) == 'fo...'
    assert trim_str('foobar', 5, '++') == 'foo++'
    with pytest.raises(TrimFunctionValueError): trim_str('foo', -1)

def test_trim_str_end():
    assert trim_str_end('') == ''
    assert trim_str_end('foo', 5) == 'foo'
    assert trim_str_end('foo', 1) == 'o'
    assert trim_str_end('foobar', 5) == '...ar'
    assert trim_str_end('foobar', 5, '++') == '++bar'
    with pytest.raises(TrimFunctionValueError): trim_str_end('foo', -1)

def test_trim_path():
    assert trim_path('') == ''
    assert trim_path('check_patch.sh') == 'c...'
    assert trim_path('automation/check_patch.sh') == '...n/c...'
    assert trim_path('automation/check_patch.sh', 10) == 'check_p...'
    assert trim_path('automation/check_patch.sh', 15) == 'check_patch.sh'
    assert trim_path('automation/check_patch.sh', 20) == '...on/check_patch.sh'
    assert trim_path('automation/check_patch.sh', 25) == 'automation/check_patch.sh'
    with pytest.raises(TrimFunctionValueError): trim_path('foo', -1)

@pytest.mark.parametrize(
    "all_jobs, trim_functions, table_headers, expected",
    [
        (
            [],
            [],
            [],
            (
                ''
            )
        ),
        (
            [['default', 'el7', 'x86_64', 'automation/check-patch.sh', '* '],
             ['default', 'verylongdistroel7', 'x86_64',
                 'automation/check-patch.sh', '  '],
             ['abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 'fc27',
                 'x86_64', '/usr/local/automation/check-patch.sh', '  '],
             ['default', 'fc26', 'x86_64',
                 '/opt/automation/long-script-name-check-patch.sh', '  ']],
            [trim_str, trim_zero, trim_zero, trim_path, trim_zero],
            ['Substage', 'Distro', 'Arch', 'Script', 'If'],
            (
                'Substage          Distro             Arch    Script          '
                '                If\n'
                '-------------------------------------------------------------'
                '------------------\n'
                'default           el7                x86_64  automation/check'
                '-patch.sh       * \n'
                'default           verylongdistroel7  x86_64  automation/check'
                '-patch.sh         \n'
                'abcdefghijklm...  fc27               x86_64  ...l/automation/'
                'check-patch.sh    \n'
                'default           fc26               x86_64  long-script-name'
                '-check-patc...    '
            )
        ),
    ]
)
def test_format_table(all_jobs, trim_functions, table_headers, expected):
    term_width = 80
    out = format_table(all_jobs, trim_functions, table_headers, term_width)
    assert out == expected
