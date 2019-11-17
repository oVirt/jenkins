#!/bin/env python
"""test_podspecs.py - Tests of the `podspces` pseudo option
"""
import pytest
try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call
from textwrap import dedent
from six import iteritems

from scripts.stdci_dsl.job_thread import JobThread
from scripts.stdci_dsl.options.podspecs import PodSpecs
from scripts.stdci_dsl.options import podspecs


class TestPodSpecs:
    @pytest.mark.parametrize('options,env,rnd,expected', [
        (
            {'podspecs': ['foo', 'bar']},
            {},
            None,
            {'podspecs': []}
        ),
        (
            {'podspecs': ['foo', 'bar'], 'containers': []},
            {},
            None,
            {'podspecs': [], 'containers': []}
        ),
        (
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
            },
            {},
            12345,
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        - carg1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      nodeSelector:
                        type: vm
                        zone: ci
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 2024033647
                        runAsGroup: 2024033647
                        runAsUser: 2024033647
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [{'image': 'cimg2', 'args': ['ccmd2']}],
                'timeout': 3600,
            },
            {},
            56780,
            {
                'containers': [{'image': 'cimg2', 'args': ['ccmd2']}],
                'timeout': 3600,
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      activeDeadlineSeconds: 3600
                      containers:
                      - args:
                        - ccmd2
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg2
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      nodeSelector:
                        type: vm
                        zone: ci
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 1579683647
                        runAsGroup: 1579683647
                        runAsUser: 1579683647
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [
                    {'image': 'cimg1', 'args': ['ccmd1', 'carg1']}
                ],
                'runtimerequirements': {'supportnestinglevel': 1},
            },
            {},
            12345,
            {
                'containers': [
                    {'image': 'cimg1', 'args': ['ccmd1', 'carg1']}
                ],
                'runtimerequirements': {'supportnestinglevel': 1},
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        - carg1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 14Gi
                          requests:
                            memory: 14Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      nodeSelector:
                        model: r620
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 2024033647
                        runAsGroup: 2024033647
                        runAsUser: 2024033647
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [
                    {'image': 'cimg1', 'args': ['ccmd1', 'carg1']}
                ],
                'runtimerequirements': {'supportnestinglevel': 1},
            },
            {
                'OPENSHIFT_PROJECT':   'some-project',
                'POD_NAME_PREFIX':     'job001',
                'STD_CI_CLONE_URL':    'the_url',
                'STD_CI_REFSPEC':      'the_refspec',
                'STD_CI_PROJECT':      'the_project',
                'STD_CI_GIT_SHA':      'the_git_sha',
                'GIT_COMMITTER_NAME':  'someone',
                'GIT_COMMITTER_EMAIL': 'some@email',
                'BUILD_NUMBER':        '1000',
                'BUILD_ID':            '1000',
                'BUILD_DISPLAY_NAME':  '#1000',
                'BUILD_TAG':           'jenkins-j1-1000',
                'BUILD_URL':           'https://jen/job/j1/1000/',
                'JOB_NAME':            'j1',
                'JOB_BASE_NAME':       'j1',
                'JOB_URL':             'https://jen/job/j1/',
                'JENKINS_URL':         'https://jen/',
                'STD_CI_JOB_KEY':      'foobar',
                'STD_CI_POD_ACCT':     'some-slave-acct',
            },
            12345,
            {
                'containers': [
                    {'image': 'cimg1', 'args': ['ccmd1', 'carg1']}
                ],
                'runtimerequirements': {'supportnestinglevel': 1},
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: job001.st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        - carg1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        - name: STD_CI_CLONE_URL
                          value: the_url
                        - name: STD_CI_REFSPEC
                          value: the_refspec
                        - name: STD_CI_PROJECT
                          value: the_project
                        - name: STD_CI_GIT_SHA
                          value: the_git_sha
                        - name: GIT_COMMITTER_NAME
                          value: someone
                        - name: GIT_COMMITTER_EMAIL
                          value: some@email
                        - name: BUILD_NUMBER
                          value: '1000'
                        - name: BUILD_ID
                          value: '1000'
                        - name: BUILD_DISPLAY_NAME
                          value: '#1000'
                        - name: BUILD_TAG
                          value: jenkins-j1-1000
                        - name: BUILD_URL
                          value: https://jen/job/j1/1000/
                        - name: JOB_NAME
                          value: j1
                        - name: JOB_BASE_NAME
                          value: j1
                        - name: JOB_URL
                          value: https://jen/job/j1/
                        - name: JENKINS_URL
                          value: https://jen/
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 14Gi
                          requests:
                            memory: 14Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      nodeSelector:
                        model: r620
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 2024030407
                        runAsGroup: 2024030407
                        runAsUser: 2024030407
                      serviceAccount: some-slave-acct
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
            },
            {
                'STD_CI_JOB_UID': 76543210,
            },
            None,
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        - carg1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      nodeSelector:
                        type: vm
                        zone: ci
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 76543210
                        runAsGroup: 76543210
                        runAsUser: 76543210
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [
                    {'image': 'ici1', 'args': ['icc1']},
                    {'image': 'ici2', 'args': ['icc2'], 'workingdir': '/wd1'},
                    {'image': 'cimg1', 'args': ['ccmd1']},
                ],
            },
            {},
            12345,
            {
                'containers': [
                    {'image': 'ici1', 'args': ['icc1']},
                    {'image': 'ici2', 'args': ['icc2'], 'workingdir': '/wd1'},
                    {'image': 'cimg1', 'args': ['ccmd1']},
                ],
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      initContainers:
                      - args:
                        - icc1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: ici1
                        imagePullPolicy: IfNotPresent
                        name: ic0
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /workspace
                      - args:
                        - icc2
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: ici2
                        imagePullPolicy: IfNotPresent
                        name: ic1
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        workingDir: /wd1
                      nodeSelector:
                        type: vm
                        zone: ci
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 2024033647
                        runAsGroup: 2024033647
                        runAsUser: 2024033647
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                    '''
                )],
            }
        ),
        (
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
                'decorate': True,
            },
            {
                'EXPORTED_ARTIFACTS_HOST': '1.2.3.4',
            },
            12345,
            {
                'containers': [{'image': 'cimg1', 'args': ['ccmd1', 'carg1']}],
                'decorate': True,
                'podspecs': [dedent(
                    '''\
                    apiVersion: v1
                    kind: Pod
                    metadata:
                      generateName: st.sbst.dst.a-r
                    spec:
                      containers:
                      - args:
                        - ccmd1
                        - carg1
                        env:
                        - name: STD_CI_STAGE
                          value: st
                        - name: STD_CI_SUBSTAGE
                          value: sbst
                        - name: STD_CI_DISTRO
                          value: Dst
                        - name: STD_CI_ARCH
                          value: a_r
                        image: cimg1
                        imagePullPolicy: IfNotPresent
                        name: main
                        resources:
                          limits:
                            memory: 2Gi
                          requests:
                            memory: 2Gi
                        tty: true
                        volumeMounts:
                        - mountPath: /workspace
                          name: workspace
                        - mountPath: /exported-artifacts
                          name: exported-artifacts
                        workingDir: /workspace
                      nodeSelector:
                        type: vm
                        zone: ci
                      restartPolicy: Never
                      securityContext:
                        fsGroup: 2024033647
                        runAsGroup: 2024033647
                        runAsUser: 2024033647
                      serviceAccount: jenkins-slave-privileged
                      volumes:
                      - emptyDir: {}
                        name: workspace
                      - name: exported-artifacts
                        nfs:
                          path: /exported-artifacts/st.sbst.Dst.a_r
                          server: 1.2.3.4
                    '''
                )],
            }
        ),
    ])
    def test_normalize(self, options, rnd, env, expected, monkeypatch):
        option_object = PodSpecs()
        for var in (PodSpecs._CONTIANER_HW_ENV_VARS + [
            'POD_NAME_PREFIX', 'STD_CI_POD_ACCTR', 'STD_CI_JOB_KEY',
            'STD_CI_JOB_UID',
        ]):
            monkeypatch.delenv(var, raising=False)
        for var, val in iteritems(env):
            monkeypatch.setenv(var, str(val))
        randrange = MagicMock(side_effect=(777 if rnd is None else rnd,))
        monkeypatch.setattr(podspecs, 'randrange', randrange)
        jt = JobThread('st', 'sbst', 'Dst', 'a_r', options)
        out = option_object.normalize(jt)
        if rnd is None:
            assert not randrange.called
        else:
            assert randrange.call_count == 1
            assert randrange.call_args == call(0, 100000)
        assert out.options == expected

    @pytest.mark.parametrize('stage,substage,distro,arch,expected', [
        ('st', 'sbst', 'dst', 'ar', '/exported-artifacts/st.sbst.dst.ar'),
        ('st', 'default', 'dst', 'ar', '/exported-artifacts/st.dst.ar'),
    ])
    def test_artifacts_path(self, stage, substage, distro, arch, expected):
        option_object = PodSpecs()
        jt = JobThread(stage, substage, distro, arch, {})
        out = option_object._artifacts_path(jt)
        assert out == expected
