#!/bin/env python
"""test_containers.py - Tests of the `containers` option
"""
import pytest
from six import iteritems
from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.options.base import ConfigurationSyntaxError
from scripts.stdci_dsl.options.containers import Containers
from scripts.struct_normalizer import DataNormalizationError


class TestContainers:
    @pytest.mark.parametrize('options,env,expected', [
        ({
            'script': 'script.sh',
            'containers': [
                {'image': 'docker.io/centos', 'args': ['/usr/bin/sleep', '1']},
                {'image': 'docker.io/fedora'},
                'docker.io/fedora:30',
                'docker.io/ovirtci/stdci:{{distro}}-{{arch}}',
            ],
        }, {}, {
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
        }, {}, {
            'script': 'script.sh',
            'containers': [
                {
                    'image': 'docker.io/centos',
                    'command': ['/bin/bash'],
                    'args': ['script.sh'],
                    'workingDir': '/src',
                },
            ]
        }),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/fedora:30',
        }, {}, {
            'script': 'script.sh',
            'containers': [
                {'image': 'docker.io/fedora:30', 'args': ['script.sh']},
            ]
        }),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/ovirtci/stdci:{{distro}}-{{arch}}',
        }, {}, {
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
            {},
            {'script': 'script.sh', 'containers': []}
        ),
        (
            {'script': 'script.sh', 'containers': []},
            {},
            {'script': 'script.sh', 'containers': []}
        ),
        (
            {'script': 'script.sh', 'containers': {}},
            {},
            DataNormalizationError('Image missing in container config')
        ),
        (
            {'script': 'script.sh', 'containers': ''},
            {},
            DataNormalizationError('Invalid container image given'),
        ),
        (
            {'script': 'script.sh', 'containers': [{'image': {}}]},
            {},
            DataNormalizationError('Invalid container image given'),
        ),
        ({
            'script': 'script.sh',
            'containers': 'docker.io/fedora:30',
            'decorate': True,
        }, {}, {
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
        }, {}, {
            'script': 'script.sh',
            'decorate': True,
            'containers': []
        }),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos',
                    'securitycontext': { 'runasuser': '0', },
                },
            },
            {'CI_SECURE_IMAGES': 'docker.io/centos'},
            {
                'script': 'script.sh',
                'containers': [{
                    'image': 'docker.io/centos',
                    'args': ['script.sh'],
                    'securityContext': { 'runAsUser': '0', },
                }],
            }
        ),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos',
                    'securitycontext': { 'runasuser': '0', },
                },
            },
            {},
            ConfigurationSyntaxError('Security set for insecure image'),
        ),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos/foo',
                    'securitycontext': { 'runasuser': '0', },
                },
            },
            {'CI_SECURE_IMAGES': 'docker.io/centos/*'},
            {
                'script': 'script.sh',
                'containers': [{
                    'image': 'docker.io/centos/foo',
                    'args': ['script.sh'],
                    'securityContext': { 'runAsUser': '0', },
                }],
            }
        ),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos/foo',
                    'securitycontext': { 'runasuser': '0', },
                    'command': ['/bin/bash'],
                },
            },
            {'CI_SECURE_IMAGES': 'docker.io/centos/*'},
            ConfigurationSyntaxError('`command` forbidden for secure image'),
        ),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos/foo',
                    'securitycontext': {},
                    'command': ['/bin/bash'],
                },
            },
            {'CI_SECURE_IMAGES': 'docker.io/centos/*'},
            {
                'script': 'script.sh',
                'containers': [{
                    'image': 'docker.io/centos/foo',
                    'args': ['script.sh'],
                    'securityContext': {},
                    'command': ['/bin/bash'],
                }],
            }
        ),
        (
            {
                'script': 'script.sh',
                'containers': {
                    'image': 'docker.io/centos',
                    'securitycontext': {},
                },
            },
            {},
            {
                'script': 'script.sh',
                'containers': [{
                    'image': 'docker.io/centos',
                    'args': ['script.sh'],
                    'securityContext': {},
                }],
            }
        ),
    ])
    def test_normalize(self, monkeypatch, options, env, expected):
        option_object = Containers()
        for var in ('CI_SECURE_IMAGES',):
            monkeypatch.delenv(var, raising=False)
        for var, val in iteritems(env):
            monkeypatch.setenv(var, str(val))
        jt = JobThread('st', 'sbst', 'dst', 'ar', options)
        if isinstance(expected, Exception):
            with pytest.raises(expected.__class__) as out_exinfo:
                option_object.normalize(jt)
            assert out_exinfo.value.args == expected.args
        else:
            out = option_object.normalize(jt)
            assert out.options == expected
