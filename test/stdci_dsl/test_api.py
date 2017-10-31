#!/bin/env python
"""project_dir_api.py - API for autoamtion vectors"""

import pytest

from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.api import _pipeline_dict_formatter, get_threads


@pytest.fixture(scope='function')
def project_dir(tmpdir):
    root = tmpdir
    automation = tmpdir.mkdir('automation')
    automation.join('check-patch.sh').write('code code code ...')
    automation.join('check-patch.repos').write('repo1\nrepo2\nrepo3')
    root.join('automation.yaml').write(
        "stage: check-patch\n"
        "runtime_requirements: dummy_req\n"
        "packages: [pkg1, pkg2, pkg3]\n"
    )
    return root


def test_get_threads(project_dir):
    threads = get_threads(str(project_dir), 'check-patch')
    assert list(threads) == [
        JobThread('check-patch', 'default', 'el7', 'x86_64',
            {
                'yumrepos': None,
                'script': project_dir/'automation/check-patch.sh',
                'upstream_sources': {},
                'repos': ['repo1', 'repo2', 'repo3'],
                'environment': {},
                'runtime_requirements': 'dummy_req',
                'mounts': [],
                'release_branches': {},
                'packages': ['pkg1', 'pkg2', 'pkg3'],
                'ignore_if_missing_script': False
            }
        )
    ]


@pytest.mark.parametrize(
    "threads,expected",
    [
        (
            [
                JobThread(
                    'check-patch', 'default', 'fc25', 'x86_64',
                    {
                        'script': 's',
                        'runtime_requirements': {'r': 'r'},
                        'release_branches': {'r': 'b'},
                        'upstream_sources': {'u': 's'},
                    }
                ),
                JobThread(
                    'build-artifacts', 'default', 'fc26', 'x86_64',
                    {
                        'script': 's',
                        'runtime_requirements': {'r': 'r'},
                        'release_branches': {'r': 'b'},
                        'upstream_sources': {'u': 's'},
                    }
                ),
                JobThread(
                    'check-patch', 'default', 'el7', 'x86_64',
                    {
                        'script': 's',
                        'runtime_requirements': {'r': 'r'},
                        'release_branches': {'r': 'b'},
                        'upstream_sources': {'u': 's'},
                    }
                )
            ],
            (
                'global_config:\n'
                '  release_branches: &id001\n'
                '    r: b\n'
                '  runtime_reqs: &id002\n'
                '    r: r\n'
                '  upstream_sources:\n'
                '    u: s\n'
                'jobs:\n'
                '- arch: x86_64\n'
                '  distro: fc25\n'
                '  release_branches: *id001\n'
                '  runtime_reqs: *id002\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
                '- arch: x86_64\n'
                '  distro: fc26\n'
                '  release_branches:\n'
                '    r: b\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: build-artifacts\n'
                '  substage: default\n'
                '- arch: x86_64\n'
                '  distro: el7\n'
                '  release_branches:\n'
                '    r: b\n'
                '  runtime_reqs:\n'
                '    r: r\n'
                '  script: s\n'
                '  stage: check-patch\n'
                '  substage: default\n'
            )
        ),
    ]
)
def test_pipeline_formatter(threads, expected):
    threads_it = iter(threads)
    out = _pipeline_dict_formatter(threads_it)
    print out
    assert  out == expected
