#!/usr/bin/env python
"""test_jenkins_objects.py - Tests for jenkins_objects.py
"""
from __future__ import absolute_import, print_function
import pytest
from collections import namedtuple, OrderedDict
from textwrap import dedent
import random
import re
from os import path
import json

from scripts.jenkins_objects import JenkinsObject, NotInJenkins, JobRunSpec, \
    BuildPtr, BuildsList


class TestJobRunSpec(object):
    def test_as_properties_file(self, tmpdir):
        params = OrderedDict((
            ('string1', 'some string'),
            ('string2', 'some other string'),
            ('some_bool', True),
            ('some_false_bool', False),
        ))
        expected_props = dedent("""
            string1=some string
            string2=some other string
            some_bool=true
            some_false_bool=false
        """).lstrip()
        jrc = JobRunSpec('some-job', params)
        out_file = tmpdir.join('output.properties')
        jrc.as_properties_file(str(out_file))
        assert expected_props == out_file.read()

    def test_as_pipeline_build_step(self):
        expected = dict(
            job='some-job',
            parameters=[
                {
                    '$class': 'StringParameterValue',
                    'name': 'string1',
                    'value': 'some string',
                },
                {
                    '$class': 'StringParameterValue',
                    'name': 'string2',
                    'value': 'some other string',
                },
                {
                    '$class': 'BooleanParameterValue',
                    'name': 'some_bool',
                    'value': True,
                },
                {
                    '$class': 'BooleanParameterValue',
                    'name': 'some_false_bool',
                    'value': False,
                },
            ]
        )
        params = OrderedDict((
            ('string1', 'some string'),
            ('string2', 'some other string'),
            ('some_bool', True),
            ('some_false_bool', False),
        ))
        jrc = JobRunSpec('some-job', params)
        out = jrc.as_pipeline_build_step()
        assert expected == out


class TestBuildPtr(object):
    def test_from_currnt_build_env(self, monkeypatch):
        monkeypatch.setenv('JENKINS_URL', 'http://jenkins.example.com')
        monkeypatch.setenv('JOB_BASE_NAME', 'j1')
        monkeypatch.setenv('JOB_URL', 'http://jenkins.example.com/job/j1')
        monkeypatch.setenv('BUILD_ID', '7')
        monkeypatch.setenv('BUILD_URL', 'http://jenkins.example.com/job/j1/7')
        bp = BuildPtr.from_currnt_build_env()
        assert bp.job_name == 'j1'
        assert bp.job_url == 'http://jenkins.example.com/job/j1'
        assert bp.build_id == '7'
        assert bp.build_url == '/job/j1/7'

    @pytest.mark.parametrize(
        ('init_prms', 'exp'),
        [
            (
                dict(job_name='jn', job_url='ju', queue_id=7),
                dict(job_name='jn', job_url='ju', queue_id=7)
            ),
            (
                dict(job_name='jn', job_url='ju', build_id=9, build_url='bu'),
                dict(job_name='jn', job_url='ju', build_id=9, build_url='bu'),
            ),
            (
                dict(job_name='jn', job_url='ju'),
                dict(job_name='jn', job_url='ju'),
            ),
            (
                dict(job_name='jn', job_url='ju', queue_id=8, build_id=9),
                dict(job_name='jn', job_url='ju', queue_id=8),
            ),
        ]
    )
    def test_as_dict(self, init_prms, exp):
        bp = BuildPtr(**init_prms)
        assert exp == bp.as_dict()

    @pytest.mark.parametrize(
        ('init_prms',),
        [
            (dict(job_name='jn', job_url='ju', queue_id=7),),
            (dict(job_name='jn', job_url='ju', build_id=9, build_url='bu'),),
            (dict(job_name='jn', job_url='ju'),),
            (dict(job_name='jn', job_url='ju', queue_id=8, build_id=9),),
        ]
    )
    def test_eq(self, init_prms):
        o1 = BuildPtr(**init_prms)
        o2 = BuildPtr(**init_prms)
        assert id(o1) != id(o2)
        assert o1 == o2

    def test_get_full_url(self, monkeypatch):
        bp = BuildPtr(
            job_name='j3', job_url='u3', build_id=5, build_url='/u3/5'
        )
        url = bp.get_full_url(jenkins_url='http://jenkins.example.com')
        assert 'http://jenkins.example.com/u3/5' == url
        monkeypatch.setenv('JENKINS_URL', 'http://jenkins.example.org')
        url = bp.get_full_url()
        assert 'http://jenkins.example.org/u3/5' == url
        monkeypatch.delenv('JENKINS_URL', raising=False)
        with pytest.raises(NotInJenkins):
            bp.get_full_url()


class TestBuildsList(object):
    def test_init(self):
        assert BuildsList() == []
        data = [
            BuildPtr(job_name='j1', job_url='u1', queue_id=1),
            BuildPtr(job_name='j2', job_url='u2', build_id=2, build_url='bu2'),
        ]
        bl = BuildsList(data)
        assert bl == data
        data = [
            BuildPtr(job_name='j1', job_url='u1', queue_id=1),
            dict(job_name='j2', job_url='u2', build_id=2, build_url='bu2'),
        ]
        with pytest.raises(TypeError):
            BuildsList(data)

    @property
    def data(self):
        return [
            dict(job_name='j1', job_url='u1', queue_id=1),
            dict(job_name='j2', job_url='/u2', build_id=2, build_url='/u2/2'),
        ]

    @property
    def more_data(self):
        return [
            dict(job_name='j3', job_url='/u3', build_id=5, build_url='/u3/5'),
            dict(job_name='j4', job_url='/u4', build_id=3, build_url='/u4/3'),
        ]

    @property
    def data_str(self):
        return json.dumps(self.data)

    def test_from_dict_list(self):
        bl = BuildsList.from_dict_list(self.data)
        assert len(self.data) == len(bl)
        assert next((False for b in bl if not isinstance(b, BuildPtr)), True)

    def test_from_json_str(self):
        exp = BuildsList.from_dict_list(self.data)
        bl = BuildsList.from_json_str(self.data_str)
        assert id(exp) != id(bl)
        assert exp == bl

    def test_from_env_json(self, monkeypatch):
        exp = BuildsList.from_dict_list(self.data)
        monkeypatch.setenv('BUILDS_LIST', self.data_str)
        bl = BuildsList.from_env_json()
        assert id(exp) != id(bl)
        assert exp == bl
        monkeypatch.delenv('BUILDS_LIST', raising=False)
        bl = BuildsList.from_env_json()
        assert bl == []

    def test_from_currnt_build_env(self, monkeypatch):
        monkeypatch.setenv('JENKINS_URL', 'http://jenkins.example.com')
        monkeypatch.setenv('JOB_BASE_NAME', 'j1')
        monkeypatch.setenv('JOB_URL', 'http://jenkins.example.com/job/j1')
        monkeypatch.setenv('BUILD_ID', '7')
        monkeypatch.setenv('BUILD_URL', 'http://jenkins.example.com/job/j1/7')
        bl = BuildsList.from_currnt_build_env()
        bp = BuildPtr.from_currnt_build_env()
        assert len(bl) == 1
        assert id(bl[0]) != id(bp)
        assert bl[0] == bp

    def test_add(self):
        bl1 = BuildsList.from_dict_list(self.data)
        bl2 = BuildsList.from_dict_list(self.more_data)
        exp_data = self.data + self.more_data
        exp_bl = BuildsList.from_dict_list(exp_data)
        out_bl = bl1 + bl2
        assert id(out_bl) != id(exp_bl)
        assert out_bl == exp_bl
        assert len(out_bl) == len(self.data) + len(self.more_data)
        assert isinstance(out_bl, BuildsList)

    def test_as_repoman_conf(self, monkeypatch):
        monkeypatch.setenv('JENKINS_URL', 'http://jenkins.example.org')
        exp = dedent("""
            http://jenkins.example.org/u3/5
            http://jenkins.example.org/u4/3
        """).lstrip()
        bl = BuildsList.from_dict_list(self.more_data)
        out = bl.as_repoman_conf()
        assert exp == out

    def test_as_dict_list(self):
        bl = BuildsList.from_dict_list(self.data)
        out = bl.as_dict_list()
        assert self.data == out


class RandomJenkinsObject(JenkinsObject, namedtuple('_RandomJenkinsObject', (
    'int', 'string', 'list', 'tuple'
))):
    @staticmethod
    def rand_gen(minint=0, maxint=2 ** 32):
        return (
            random.randint(minint, maxint)
            for n in range(0, random.randint(50, 150))
        )

    @staticmethod
    def __new__(cls, *args, **kwargs):
        if args or kwargs:
            return \
                super(RandomJenkinsObject, cls).__new__(cls, *args, **kwargs)
        else:
            return super(RandomJenkinsObject, cls).__new__(
                cls,
                int=random.randint(0, 2 ** 32),
                string=''.join(map(chr, cls.rand_gen(maxint=172))),
                list=list(cls.rand_gen()),
                tuple=tuple(cls.rand_gen()),
            )


class TestJenkinsObject(object):
    def test_param_str_conversion(self):
        for time in range(0, 10):
            obj = RandomJenkinsObject()
            obj_prm_str = JenkinsObject.object_to_param_str(obj)
            assert re.match('^[A-Za-z0-9+/]*=*$', obj_prm_str)
            robj = JenkinsObject.param_str_to_object(obj_prm_str)
            assert id(robj) != id(obj)
            assert robj == obj

    def test_verify_in_jenkins_positive(self, jenkins_env):
        # should not raise excpetions
        JenkinsObject.verify_in_jenkins()

    def test_verify_in_jenkins_negative(self, not_jenkins_env):
        with pytest.raises(NotInJenkins):
            JenkinsObject.verify_in_jenkins()

    def test_get_job_name(self, jenkins_env):
        out = JenkinsObject.get_job_name()
        assert jenkins_env.job_base_name == out

    def test_get_job_name_fail(self, not_jenkins_env):
        with pytest.raises(NotInJenkins):
            JenkinsObject.get_job_name()

    def test_verify_artifacts_dir(self, jenkins_env):
        assert not path.isdir(JenkinsObject.ARTIFACTS_DIR)
        JenkinsObject.verify_artifacts_dir()
        assert path.isdir(JenkinsObject.ARTIFACTS_DIR)
        JenkinsObject.verify_artifacts_dir()
        assert path.isdir(JenkinsObject.ARTIFACTS_DIR)

    def test_to_form_artifact(self, jenkins_env):
        art_file = '_artifact.dat'
        art_path = path.join(JenkinsObject.ARTIFACTS_DIR, art_file)
        assert not path.exists(art_path)
        with pytest.raises(IOError):
            JenkinsObject.object_from_artifact(art_file)
        assert not path.exists(art_path)
        inobj = JenkinsObject.object_from_artifact(
            art_file, RandomJenkinsObject
        )
        assert inobj is not None
        assert not path.exists(art_path)
        assert isinstance(inobj, RandomJenkinsObject)
        JenkinsObject.object_to_artifact(inobj, art_file)
        assert path.isfile(art_path)
        outobj = JenkinsObject.object_from_artifact(art_file)
        assert id(outobj) != id(inobj)
        assert outobj == inobj

    def test_load_save_artifact(self, jenkins_env):
        art_path = path.join(JenkinsObject.ARTIFACTS_DIR,
                             'RandomJenkinsObject.dat')
        assert not path.exists(art_path)
        with pytest.raises(IOError):
            RandomJenkinsObject.load_from_artifact(fallback_to_new=False)
        assert not path.exists(art_path)
        inobj = RandomJenkinsObject.load_from_artifact()
        assert not path.exists(art_path)
        assert inobj is not None
        assert isinstance(inobj, RandomJenkinsObject)
        inobj.save_to_artifact()
        assert path.isfile(art_path)
        outobj = RandomJenkinsObject.load_from_artifact()
        assert id(outobj) != id(inobj)
        assert outobj == inobj

    def test_persistance(self, jenkins_env):
        art_path = path.join(JenkinsObject.ARTIFACTS_DIR,
                             'RandomJenkinsObject.dat')
        assert not path.exists(art_path)
        with RandomJenkinsObject.persist_in_artifacts() as obj:
            assert obj is not None
            assert isinstance(obj, RandomJenkinsObject)
        assert path.isfile(art_path)
        nobj = RandomJenkinsObject()
        with RandomJenkinsObject.persist_in_artifacts() as lobj:
            assert lobj is not None
            assert isinstance(lobj, RandomJenkinsObject)
            assert id(obj) != id(lobj)
            assert id(nobj) != id(lobj)
            assert obj == lobj
            assert obj != nobj
