#!/usr/bin/env python
"""jenkins_objects.py - Objects that run in the contest of Jenkins
"""
from __future__ import absolute_import, print_function
from collections import namedtuple
from six.moves import cPickle
from six import iteritems
from os import environ, path, makedirs, unlink
from base64 import b64decode, b64encode
from bz2 import compress, decompress, BZ2File
from contextlib import contextmanager
import json
import logging


class JobRunSpec(namedtuple('_JobRunSpec', ('job_name', 'params'))):
    """Class representing a specification for running a Jenkins job"""
    default_properties_file = 'job_params.properties'
    default_pipelins_build_step_json_file = 'build_args.json'

    @staticmethod
    def _clean_file(file_name):
        if path.exists(file_name):
            unlink(file_name)

    def as_properties_file(self, file_name=None):
        if file_name is None:
            file_name = self.default_properties_file
        with open(file_name, 'w') as fil:
            for name, value in iteritems(self.params):
                if isinstance(value, bool):
                    str_value = 'true' if value else 'false'
                else:
                    str_value = str(value)
                fil.write('{0}={1}\n'.format(str(name), str_value))

    @classmethod
    def clean_properties_file(cls, file_name=None):
        if file_name is None:
            file_name = cls.default_properties_file
        cls._clean_file(file_name)

    def as_pipeline_build_step(self):
        step_struct = dict(job=self.job_name, parameters=[])
        for name, value in iteritems(self.params):
            param_struct = dict(name=name)
            if isinstance(value, bool):
                param_struct['value'] = value
                param_struct['$class'] = 'BooleanParameterValue'
            else:
                param_struct['value'] = str(value)
                param_struct['$class'] = 'StringParameterValue'
            step_struct['parameters'].append(param_struct)
        return step_struct

    def as_pipeline_build_step_json(self, file_name=None):
        if file_name is None:
            file_name = self.default_pipelins_build_step_json_file
        with open(file_name, 'w') as fil:
            json.dump(self.as_pipeline_build_step(), fil)

    @classmethod
    def clean_pipeline_build_step_json(cls, file_name=None):
        if file_name is None:
            file_name = cls.default_pipelins_build_step_json_file
        cls._clean_file(file_name)


class NotInJenkins(Exception):
    def __init__(self):
        super(NotInJenkins, self).__init__('This Code must run from Jenkins')


class JenkinsObject(object):
    """Base class for objects that run inside Jenkins
    """
    ARTIFACTS_DIR = 'exported-artifacts'

    @staticmethod
    def param_str_to_object(param_str):
        """Convert a string that supposedly came from a job parameter into a
        change object
        """
        return cPickle.loads(decompress(b64decode(param_str.encode())))

    @staticmethod
    def object_to_param_str(change):
        """Convert a change object into a format suitable for passing in job
        parameters
        """
        return b64encode(compress(cPickle.dumps(change))).decode()

    @staticmethod
    def verify_in_jenkins():
        """Verify that we are running inside Jenkins"""
        if 'JOB_BASE_NAME' not in environ:
            raise NotInJenkins

    @classmethod
    def get_job_name(cls):
        cls.verify_in_jenkins()
        return environ['JOB_BASE_NAME']

    @classmethod
    def verify_artifacts_dir(cls):
        try:
            makedirs(cls.ARTIFACTS_DIR)
        except OSError as e:
            # errno 17 is returned when the directory exists
            if e.errno != 17:
                raise

    @classmethod
    def object_from_artifact(cls, artifact_file, fallback_cls=None):
        fd = None
        try:
            fd = BZ2File(path.join(cls.ARTIFACTS_DIR, artifact_file))
            return cPickle.loads(fd.read())
        except IOError as e:
            # errno 2 is 'No such file or directory'
            if e.errno == 2 and fallback_cls is not None:
                return fallback_cls()
            raise
        finally:
            if fd is not None:
                fd.close()

    @classmethod
    def object_to_artifact(cls, obj, artifact_file):
        cls.verify_artifacts_dir()
        fd = None
        try:
            fd = BZ2File(path.join(cls.ARTIFACTS_DIR, artifact_file), 'w')
            fd.write(cPickle.dumps(obj))
        finally:
            if fd is not None:
                fd.close()

    @classmethod
    def load_from_artifact(cls, artifact_file=None, fallback_to_new=True):
        if artifact_file is None:
            artifact_file = cls.__name__ + '.dat'
        return cls.object_from_artifact(
            artifact_file, cls if fallback_to_new else None
        )

    def save_to_artifact(self, artifact_file=None):
        if artifact_file is None:
            artifact_file = self.__class__.__name__ + '.dat'
        self.object_to_artifact(self, artifact_file)

    @classmethod
    def clean_artifact(cls, artifact_file=None):
        if artifact_file is None:
            artifact_file = cls.__name__ + '.dat'
        artifact_path = path.join(cls.ARTIFACTS_DIR, artifact_file)
        if path.exists(artifact_path):
            unlink(artifact_path)

    @classmethod
    @contextmanager
    def persist_in_artifacts(cls, artifact_file=None):
        obj = cls.load_from_artifact(artifact_file)
        yield obj
        obj.save_to_artifact(artifact_file)

    @staticmethod
    def setup_logging(level=logging.INFO):
        """Globally setup logging so its useful in Jenkins"""
        logging.basicConfig()
        logging.getLogger().level = level
