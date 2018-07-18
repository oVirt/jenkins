#!/bin/env python
"""project_dir_api.py - API for autoamtion vectors"""

import pytest

from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.api import (
    get_threads, RuntimeEnvDefinition,
    NoThreadForEnv, get_threads_with_globals
)
from scripts.stdci_dsl.api.formatters.threads import (
    _pipeline_dict_formatter
)
from scripts.stdci_dsl.options.normalize import RepoConfig
from scripts.nested_config import DepthLevel


@pytest.fixture(scope='function')
def project_dir(tmpdir):
    root = tmpdir
    root.join('secrets_file').write('a')
    automation = tmpdir.mkdir('automation')
    (automation/'check-patch.sh').write('code code code ...')
    (automation/'check-patch.repos').write('repo1\nrepo2\nrepo3')
    (root/'stdci.yaml').write(
        "STAGE: check-patch\n"
        "runtimer-equire_ments: dummy_req\n"
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
                'runtimerequirements': 'dummy_req',
                'mounts': [],
                'releasebranches': {},
                'packages': ['pkg1', 'pkg2', 'pkg3'],
                'ignore_if_missing_script': True,
                'reporting': {'style': 'default', },
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
                'runtimerequirements': 'dummy_req',
                'mounts': [],
                'releasebranches': {},
                'packages': ['pkg1', 'pkg2', 'pkg3'],
                'ignore_if_missing_script': True,
                'reporting': {'style': 'default', },
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
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtimerequirements': {'r': 'r'},
                        'releasebranches': {'r': 'b'},
                        'upstreamsources': {'u': 's'},
                        'reporting': {'style': 'classic'},
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
                '  distro: fc25\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '- arch: x86_64\n'
                '  distro: fc26\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: build-artifacts\n'
                '  substage: default\n'
                '- arch: x86_64\n'
                '  distro: el7\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: default\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '- arch: x86_64\n'
                '  distro: el7\n'
                '  release_branches:\n'
                '    r: b\n'
                '  reporting:\n'
                '    style: classic\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
            )
        ),
    ]
)
def test_pipeline_formatter(threads, global_cfg, expected):
    threads_it = iter(threads)
    out = _pipeline_dict_formatter(threads_it, global_cfg)
    assert out == expected
