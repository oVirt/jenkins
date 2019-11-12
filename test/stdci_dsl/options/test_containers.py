#!/bin/env python
"""test_containers.py - Tests of the `containers` option
"""
import pytest
from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.options.base import ConfigurationSyntaxError
from scripts.stdci_dsl.options.containers import Containers
from scripts.struct_normalizer import DataNormalizationError


class TestContainers:
    @pytest.mark.parametrize('options, expected', [
        ({
            'script': 'script.sh',
            'containers': [
                {'image': 'docker.io/centos', 'args': ['/usr/bin/sleep', '1']},
                {'image': 'docker.io/fedora'},
                'docker.io/fedora:30',
                'docker.io/ovirtci/stdci:{{distro}}-{{arch}}',
            ],
        }, {
            'script': 'script.sh',
            'containers': [
                {'image': 'docker.io/centos', 'args': ['/usr/bin/sleep', '1']},
                {'image': 'docker.io/fedora', 'args': ['script.sh']},
                {'image': 'docker.io/fedora:30', 'args': ['script.sh']},
                {
                    'image': 'docker.io/ovirtci/stdci:dst-ar',
                    'args': ['script.sh'],
                },
            ],
        }),
        ({
            'script': 'script.sh',
            'containers': {
                'image': 'docker.io/centos',
                'command': ['/bin/bash'],
                'workingdir': '/src',
            },
        }, {
            'script': 'script.sh',
            'containers': [
                {
                    'image': 'docker.io/centos',
                    'command': ['/bin/bash'],
                    'args': ['script.sh'],
                    'workingdir': '/src',
                },
            ]
        }),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/fedora:30',
        }, {
            'script': 'script.sh',
            'containers': [
                {'image': 'docker.io/fedora:30', 'args': ['script.sh']},
            ]
        }),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/ovirtci/stdci:{{distro}}-{{arch}}',
        }, {
            'script': 'script.sh',
            'containers': [
                {
                    'image': 'docker.io/ovirtci/stdci:dst-ar',
                    'args': ['script.sh'],
                },
            ]
        }),
        (
            {'script': 'script.sh'},
            {'script': 'script.sh', 'containers': []}
        ),
        (
            {'script': 'script.sh', 'containers': []},
            {'script': 'script.sh', 'containers': []}
        ),
        (
            {'script': 'script.sh', 'containers': {}},
            DataNormalizationError('Image missing in container config')
        ),
        (
            {'script': 'script.sh', 'containers': ''},
            DataNormalizationError('Invalid container image given'),
        ),
        (
            {'script': 'script.sh', 'containers': [{'image': {}}]},
            DataNormalizationError('Invalid container image given'),
        ),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/fedora:30',
            'decorate': True,
        }, {
            'script': 'script.sh',
            'decorate': True,
            'containers': [
                {
                    'image': 'centos/s2i-base-centos7',
                    'args': [
                        'bash',
                        '-exc',
                        # note: below is one big string passed as a single
                        #       argument to bash
                        'git init . && '
                        'git fetch --tags --progress "$STD_CI_CLONE_URL"'
                            ' +refs/heads/*:refs/remotes/origin/* && '
                        'git fetch --tags --progress "$STD_CI_CLONE_URL"'
                            ' +"$STD_CI_REFSPEC":myhead && '
                        'git checkout myhead && '
                        '{ chmod ug+x script.sh || :; }'
                    ],
                },
                {'image': 'docker.io/fedora:30', 'args': ['script.sh']},
            ]
        }),
        ({
            'script': 'script.sh',
            'containers': [],
            'decorate': True,
        }, {
            'script': 'script.sh',
            'decorate': True,
            'containers': []
        }),
    ])
    def test_normalize(self, options, expected):
        option_object = Containers()
        jt = JobThread('st', 'sbst', 'dst', 'ar', options)
        if isinstance(expected, Exception):
            with pytest.raises(expected.__class__) as out_exinfo:
                option_object.normalize(jt)
            assert out_exinfo.value.args == expected.args
        else:
            out = option_object.normalize(jt)
            assert out.options == expected
