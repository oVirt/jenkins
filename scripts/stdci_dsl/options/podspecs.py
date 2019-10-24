#!/bin/env python
from __future__ import absolute_import
__metaclass__ = type
"""options/podspecs.py - The `podspecs` DSL pseudo option
"""
import os
import re
from yaml import dump, Dumper
from itertools import chain


class PodSpecs:
    def normalize(self, thread):
        """A pseudo normalization function that generates the `podspecs` pseudo
        option

        :param JobThread thread: JobThread to read information from

        Function output also depends on the following environment variables:
        - POD_NAME_PREFIX:   If set, used as a prefix to the POD name

        A set of environment variables specified by _CONTIANER_HW_ENV_VARS are
        also passed as-is to the POD containers if found in the environment.

        :rtype: JobThread
        :returns: A JobThread with the podspecs option
        """
        podspecs = []
        containers = thread.options.get('containers')
        if containers:
            podspec = {
                'apiVersion': 'v1',
                'kind': 'Pod',
                'metadata': {
                    'generateName': self._mk_pod_name(thread),
                },
                'spec': {
                    'containers': [
                        self._mk_container_spec(containers[-1], 'main')
                    ],
                    'nodeSelector': {'type': 'vm', 'zone': 'ci'},
                    'restartPolicy': 'Never',
                    'volumes': [{'name': 'workspace', 'emptyDir': {}}],
                }
            }
            self._add_init_containers(containers, podspec)
            self._add_resouce_settings(thread.options, podspec)
            self._add_timeout_option(thread.options, podspec)
            self._add_env_vars(thread, podspec)
            podspecs = [dump(podspec, Dumper=PodConfigDumper)]
        new_options = thread.options.copy()
        new_options['podspecs'] = podspecs
        return thread.with_modified(options=new_options)

    def _mk_pod_name(self, thread):
        """Generate the POD name"""
        pod_name = '.'.join(filter(None, [
            os.environ.get('POD_NAME_PREFIX'),
            thread.stage, thread.substage, thread.distro, thread.arch
        ])).lower()
        # Ensure pod name is DNS compliant as required by K8s
        pod_name = re.sub('[^a-z0-9-\.]+', '-', pod_name)
        return pod_name

    def _mk_container_spec(self, container_opt, name):
        """Make a K8s container specification from thread options section

        :param Mapping container_opt: An entry from the thread`s `containers`
                                      option to make the container spec out of
        :param str name:              The name to assign the container within
                                      the pod

        :rtype: Mapping
        :returns: A K8s container specification data structure
        """
        cont_spec = {
            'imagePullPolicy': 'IfNotPresent',
            'name': name,
            'tty': True,
            'volumeMounts': [
                {'mountPath': '/workspace', 'name': 'workspace'},
            ],
            'workingDir': '/workspace',
        }
        for prop in ('image', 'command', 'args', 'workingDir'):
            if prop.lower() in container_opt:
                cont_spec[prop] = container_opt[prop.lower()]
        return cont_spec

    def _add_init_containers(self, containers, podspec):
        """Add initContainers configuration for the POD

        :param list containers: The value of the containers option from the
                                JobThread
        """
        init_containers = [
            self._mk_container_spec(container_opt, 'ic{}'.format(idx))
            for idx, container_opt in enumerate(containers[:-1])
        ]
        if init_containers:
            podspec['spec']['initContainers'] = init_containers

    def _add_resouce_settings(self, options, podspec):
        """Add HW resource settings to a podspec
        """
        memory = '2Gi'
        runtimerequirements = options.get('runtimerequirements', {})
        if runtimerequirements.get('supportnestinglevel', 0) > 0:
            podspec['spec']['nodeSelector'] = {'model': 'r620'}
            podspec['spec']['securityContext'] = {'privileged': True}
            memory = '14Gi'
        self._update_containers(podspec, resources={
                'limits': {'memory': memory},
                'requests': {'memory': memory},
        })

    _CONTIANER_HW_ENV_VARS = [
        'STD_CI_CLONE_URL',
        'STD_CI_REFSPEC',
        'STD_CI_PROJECT',
        'STD_CI_GIT_SHA',
        'GIT_COMMITTER_NAME',
        'GIT_COMMITTER_EMAIL',
        'BUILD_NUMBER',
        'BUILD_ID',
        'BUILD_DISPLAY_NAME',
        'BUILD_TAG',
        'BUILD_URL',
        'JOB_NAME',
        'JOB_BASE_NAME',
        'JOB_URL',
        'JENKINS_URL',
    ]

    def _add_env_vars(self, thread, podspec):
        """Add environment variable to all containers in POD
        """
        cont_env = [
            {'name': 'STD_CI_STAGE', 'value': thread.stage},
            {'name': 'STD_CI_SUBSTAGE', 'value': thread.substage},
            {'name': 'STD_CI_DISTRO', 'value': thread.distro},
            {'name': 'STD_CI_ARCH', 'value': thread.arch},
        ] + [
            {'name': var, 'value': os.environ[var]}
            for var in self._CONTIANER_HW_ENV_VARS
            if var in os.environ
        ]
        self._update_containers(podspec, env=cont_env)

    def _add_timeout_option(self, options, podspec):
        """Add timeout setting to POD if defined it thread options
        """
        timeout = options.get('timeout', 'unlimited')
        if timeout != 'unlimited':
            podspec['spec']['activeDeadlineSeconds'] = timeout

    def _update_containers(self, podspec, **kwargs):
        """Update a podspec structure in place to add the options given in
        kwargs to all containers
        """
        all_containers = chain(
            podspec['spec'].get('containers', []),
            podspec['spec'].get('initContainers', [])
        )
        for container in all_containers:
            container.update(kwargs)


class PodConfigDumper(Dumper):
    """Custom YAML dumper for dumping POD data.

    This is implemented mostly to prevent having YAML anchors on the output
    stream. But other option are included along the way
    """
    def __init__(self, *args, **kwargs):
        kwargs['default_flow_style'] = False
        super(PodConfigDumper, self).__init__(
            *args, **kwargs
        )

    def ignore_aliases(self, data):
        return True
