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

from scripts.jenkins_objects import JenkinsObject, NotInJenkins, JobRunSpec


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
