#!/usr/bin/env python
"""change_queue.py - Change queue management functions
"""
from uuid import uuid4
from itertools import chain
from collections import deque, namedtuple
from six.moves import map, reduce, range, cPickle
from six import iteritems
from copy import copy
from os import environ, path, makedirs
from base64 import b64decode, b64encode
from bz2 import compress, decompress, BZ2File
from contextlib import contextmanager
import json


class ChangeQueue(object):
    """Class for managing a change queue that can initialize change testing
    processes as changes are added and use a bisection algorithm to find the
    change that caused a testing failure.

    The changes in the queue can be any kind of object but immutable objects
    are preferred.

    Constructor arguments:
    :param Iterable initial_state: (Optional) The initial state of the queue,
                                   should be an iterable of iterables with at
                                   least one member.
    :param str test_key:           (Optional) Key identifying a currently
                                   running test

    If test_key is specified (not None), then initial_state must have more then
    one member where the last member is the list of changes being tested
    """
    def __init__(self, initial_state=None, test_key=None):
        if initial_state is None:
            self._state = deque([deque()])
        else:
            self._state = deque(deque(subq) for subq in initial_state)
        if test_key is not None and len(self._state) < 2:
            raise TypeError(
                'test_key cannot be set when len(initial_state) < 2'
            )
        self._test_key = test_key

    def add(self, change):
        """Add a change to the queue

        :param object change: The change to add (can be almost anything, as
                              long as identical copies of it compare
                              positively)
        :returns: None
        """
        self._state[-1].append(change)

    def get_next_test(self):
        """Returns the next test that needs to be performed

        :rtype: tuple
        :retuns: A tuple of a test key used to identify the test when it
                 reports back the results, and a list of changes to test.
                 If no test is needed the returned key is none and the list is
                 empty
        """
        change_list = list(self._state[0])
        if change_list:
            if len(self._state) <= 1:
                self._state.append([])
            if self._test_key is None:
                self._test_key = str(uuid4())
        return (self._test_key, change_list)

    def on_test_success(self, test_key):
        """Updated the queue when a test is successful

        :param str test_key: The test key of the test. Must match the test key
                             return from the last call to get_next_test,
                             otherwise the test result will be ignored.

        If one of the on_test_* methods was already called with the proper test
        key following the last call to get_next_test, this call will be ignored

        :rtype: tuple
        :returns: A tuple of successful changes list and failed changes list if
                  we now have enough information to determine them. The
                  returned changes will be removed from the queue. On ignored
                  calls empty lists are returned
        """
        if test_key is None or test_key != self._test_key:
            return [], []
        success_list = list(self._state.popleft())
        if len(self._state) > 1:
            fail_list = self.on_test_failure(test_key)[1]
        else:
            fail_list = []
        self._test_key = None
        return success_list, fail_list

    def on_test_failure(self, test_key):
        """Updated the queue when a test failed

        :param str test_key: The test key of the test that failed, must match
                             the test key return from the last call to
                             get_next_test, otherwise the test result will be
                             ignored.

        If one of the on_test_* methods was already called with the proper test
        key following the last call to get_next_test, this call will be ignored

        Unless the test tested exactly one change, the queue will be bisected
        internally so that the next test will test half of the changes that
        were tested before.

        :rtype: tuple
        :returns: A tuple of successful changes list and failed changes list if
                  we now have enough information to determine them. The
                  returned changes will be removed from the queue. On ignored
                  calls empty lists are returned
        """
        if test_key is None or test_key != self._test_key:
            return [], []
        self._test_key = None
        fail_list = list(self._state.popleft())
        if len(fail_list) == 1:
            self._state = deque([deque(chain.from_iterable(self._state))])
            return [], fail_list
        self._state.extendleft([
            deque(fail_list[int(len(fail_list)/2):]),
            deque(fail_list[:int(len(fail_list)/2)])
        ])
        return [], []


class ChangeQueueWithDeps(ChangeQueue):
    """Class for managing a change queue where changes can have dependencies on
    one another.

    The changes in the queue can be any kind of object as long as it is either
    immutable and hashable or contains an immutable and hashable 'id' attribute
    that will allow it to be identified as a requirement for other changes.
    To indicate that a change depends on other changes it needs to include a
    'requirements' property that returns a collection of required changes or
    change ids.
    If a change added to the queue requires a change that is not yet in the
    queue, it is placed in an 'awaiting_deps' side-queue until the needed
    change is added. A change will be placed in The queue before any change
    that requires it.

    Constructor arguments:
    :param Iterable initial_state: (Optional) The initial state of the queue,
                                   should be an iterable of iterables with at
                                   least one member.
    :param str test_key:           (Optional) Key identifying a currently
                                   running test
    :param str awaiting_deps:      (Optional) The initial state of the queue of
                                   changes with missing dependencies. This is
                                   a list of pairs cf changes and their missing
                                   dependencies.

    If test_key is specified (not None), then initial_state must have more then
    one member where the last member is the list of changes being tested
    """
    @staticmethod
    def _change_id(change):
        if hasattr(change, 'id'):
            return change.id
        else:
            return change

    @staticmethod
    def _change_requirements(change):
        if hasattr(change, 'requirements'):
            return set(change.requirements)
        else:
            return set()

    def __init__(self, initial_state=None, test_key=None, awaiting_deps=None):
        super(ChangeQueueWithDeps, self).__init__(initial_state, test_key)
        if awaiting_deps is None:
            self._awaiting_deps = deque()
        else:
            self._awaiting_deps = deque(awaiting_deps)

    def add(self, change):
        """Attempts to add a change to the queue

        :param object change: The change to add

        A change will only be added if all its dependencies are already in the
        queue. Otherwise the change is added to the side queue until all the
        dependencies for it are added as well.

        When a change is added, changes in the side queue are also scanned to
        check if it resolves their dependencies, and are added if it does.

        Changes are checked for cyclic dependencies, if such are found changes
        are removed from the queue

        :rtype: tuple
        :returns: A tuple containing a list of changes added to the queue at
        this time and another list of changes that were rejected because of
        cyclic dependencies
        """
        change_id = self._change_id(change)
        dependant_ids = self._find_dependants_on(
            change_id,
            chain([change], (chg for chg, _ in self._awaiting_deps))
        )
        dependants = chain(
            [(change, self._get_missing_deps(change))],
            self._remove_awaiting_deps_by_ids(dependant_ids)
        )
        if change_id in dependant_ids:
            # Change depends on itself - a dependency loop
            return [], [cng for cng, _ in dependants]
        changes_added = deque()
        change_ids_added = set()
        for chg, mdeps in dependants:
            mdeps.difference_update(change_ids_added)
            if mdeps:
                self._awaiting_deps.append((chg, mdeps))
            else:
                super(ChangeQueueWithDeps, self).add(chg)
                changes_added.append(chg)
                change_ids_added.add(self._change_id(chg))
        return list(changes_added), []

    def _get_missing_deps(self, change):
        """Get a set of missing dependencies for the given change
        """
        return \
            self._change_requirements(change) - \
            set(map(self._change_id, chain.from_iterable(self._state)))

    @staticmethod
    def _find_dependants_on(change_id, changes):
        """Find in the changes collection, all changes that are directly on
        indirectly dependant on the given change ID. The collection should also
        include the change whose Id is given if loop detection is desired.

        :rtype: set
        :returns: a set of dependant change IDs
        """
        depmap = dict()
        for change in changes:
            for cdid in ChangeQueueWithDeps._change_requirements(change):
                depmap.setdefault(cdid, set()).add(
                    ChangeQueueWithDeps._change_id(change)
                )
        dependants = set()
        recurse_into = deque([change_id])
        while recurse_into:
            c_id = recurse_into.popleft()
            c_deps = depmap.pop(c_id, set()) - dependants
            dependants.update(c_deps)
            recurse_into.extend(c_deps)
        return dependants

    def _remove_awaiting_deps_by_ids(self, dep_ids):
        self._awaiting_deps, removed_deps = reduce(
            lambda res, dep:
                (res[0], res[1] + [dep])
                if self._change_id(dep[0]) in dep_ids else
                (res[0] + [dep], res[1]),
            self._awaiting_deps,
            ([], [])
        )
        return removed_deps

    def on_test_failure(self, test_key):
        """Updated the queue when a test is successful

        Works like the superclass's method, but when failed changes are
        removed, changes that depend on them are removed as well.
        """
        success_list, fail_list = \
            super(ChangeQueueWithDeps, self).on_test_failure(test_key)
        for failed_change in copy(fail_list):
            failed_change_id = self._change_id(failed_change)
            dependant_ids = self._find_dependants_on(failed_change_id, chain(
                chain.from_iterable(self._state),
                (chg for chg, _ in self._awaiting_deps)
            ))
            fail_list.extend(self._remove_deps_by_ids(dependant_ids))
            fail_list.extend(
                adep[0] for adep in
                self._remove_awaiting_deps_by_ids(dependant_ids)
            )
        return success_list, fail_list

    def _remove_deps_by_ids(self, dep_ids):
        removed_deps = deque()
        for i in range(0, len(self._state)):
            self._state[i], section_removed_deps = reduce(
                lambda res, dep:
                    (res[0], res[1] + [dep])
                    if self._change_id(dep) in dep_ids else
                    (res[0] + [dep], res[1]),
                self._state[i],
                ([], [])
            )
            removed_deps.extend(section_removed_deps)
        return removed_deps


class GerritServer(namedtuple('_GerritServer', ('host', 'port', 'schema'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            host=env['GERRIT_HOST'],
            port=int(env['GERRIT_PORT']),
            schema=env['GERRIT_SCHEME'],
        )


class GerritPerson(namedtuple('_GerritPerson', ('name', 'email'))):
    @classmethod
    def from_jenkins_env(cls, prefix='', env=environ):
        return cls(env[prefix + '_NAME'], env[prefix + '_EMAIL'])


class GerritProject(namedtuple('_GerritProject', ('server', 'name'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            server=GerritServer.from_jenkins_env(env),
            name=env['GERRIT_PROJECT'],
        )


class GerritBranch(namedtuple('_GerritBranch', ('project', 'name'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            project=GerritProject.from_jenkins_env(env),
            name=env['GERRIT_BRANCH'],
        )


class GerritChange(namedtuple('_GerritChange', (
    'branch', 'change_id', 'number', 'owner', 'subject', 'url',
))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            branch=GerritBranch.from_jenkins_env(env),
            change_id=env['GERRIT_CHANGE_ID'],
            number=int(env['GERRIT_CHANGE_NUMBER']),
            owner=GerritPerson.from_jenkins_env('GERRIT_CHANGE_OWNER', env),
            subject=env['GERRIT_CHANGE_SUBJECT'],
            url=env['GERRIT_CHANGE_URL'],
        )


class GerritPatchset(namedtuple('_GerritPatchset', (
    'change',
    'refspec', 'patchset_number', 'uploader', 'revision',
    'commit_message', 'topic',
))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            change=GerritChange.from_jenkins_env(env),
            refspec=env['GERRIT_REFSPEC'],
            patchset_number=int(env['GERRIT_PATCHSET_NUMBER']),
            uploader=GerritPerson.from_jenkins_env(
                'GERRIT_PATCHSET_UPLOADER', env
            ),
            revision=env['GERRIT_PATCHSET_REVISION'],
            commit_message=b64decode(
                env['GERRIT_CHANGE_COMMIT_MESSAGE'].encode()
            ).decode(),
            topic=env['GERRIT_TOPIC'],
        )


class JobRunSpec(namedtuple('_JobRunSpec', ('job_name', 'params'))):
    """Class representing a specification for running a Jenkins job"""
    def as_properties_file(self, file_name='job_params.properties'):
        with open(file_name, 'w') as fil:
            for name, value in iteritems(self.params):
                if isinstance(value, bool):
                    str_value = 'true' if value else 'false'
                else:
                    str_value = str(value)
                fil.write('{0}={1}\n'.format(str(name), str_value))

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

    def as_pipeline_build_step_json(self, file_name='build_args.json'):
        with open(file_name, 'w') as fil:
            json.dump(self.as_pipeline_build_step, fil)


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
    @contextmanager
    def persist_in_artifacts(cls, artifact_file=None):
        obj = cls.load_from_artifact(artifact_file)
        yield obj
        obj.save_to_artifact(artifact_file)


class JenkinsChangeQueueObject(JenkinsObject):
    """Utility base class to objects that represent the change queue in Jenkins
    """
    QUEUE_JOB_SUFFIX = '_change-queue'
    TESTER_JOB_SUFFIX = '_change-queue-tester'

    def queue_job_name(self, queue_name=None):
        if queue_name is None:
            queue_name = self.get_queue_name()
        return str(queue_name) + self.QUEUE_JOB_SUFFIX

    def tester_job_name(self, queue_name=None):
        if queue_name is None:
            queue_name = self.get_queue_name()
        return str(queue_name) + self.TESTER_JOB_SUFFIX

    @classmethod
    def job_to_queue_name(cls, job_name):
        if job_name.endswith(cls.QUEUE_JOB_SUFFIX):
            return job_name[:-len(cls.QUEUE_JOB_SUFFIX)]
        if job_name.endswith(cls.TESTER_JOB_SUFFIX):
            return job_name[:-len(cls.TESTER_JOB_SUFFIX)]
        return None

    def get_queue_name(self):
        self.verify_in_jenkins()
        return self.job_to_queue_name(self.get_job_name())

    def get_queue_job_run_spec(self, queue_action, action_arg):
        return JobRunSpec(
            job_name=self.queue_job_name(),
            params=dict(QUEUE_ACTION=queue_action, ACTION_ARG=action_arg),
        )


class NotCQJob(Exception):
    def __init__(self):
        super(NotCQJob, self).__init__(
            'This code must be run from a change queue Jenkins job'
        )


class InvalidChangeQueueAction(Exception):
    def __init__(self, bad_action):
        super(InvalidChangeQueueAction, self).__init__(
            "Invalid queue action specified: '{}'".format(str(bad_action))
        )


class JenkinsChangeQueue(JenkinsChangeQueueObject, ChangeQueueWithDeps):
    """Class for representing a change queue in the context of Jenkins.

    A change queue is represented in Jenkins as a job. The queue state is
    maintained between job invocations by dumping it from memory into a file
    that will be preserved as a build artifact.
    Changes and test results are submitted to the queue by triggering the queue
    job with specific parameters. Test instructions are also dumped to files to
    be passed to testing jobs as build artifacts.
    """
    def get_queue_name(self):
        queue_name = super(JenkinsChangeQueue, self).get_queue_name()
        if queue_name is None or \
                self.get_job_name() != self.queue_job_name(queue_name):
            raise NotCQJob
        return queue_name

    def act_on_job_params(self, queue_action, action_arg):
        """Perform the queue action according to parameters passed to the job

        This method is probably what the queue jobs will call. Apart from
        performing the queue action it will also run reporting methods on
        change objects to report their status, create changes list file if
        requested, and a status HTML file showing the state of the queue.
        """
        queue_name = self.get_queue_name()
        if queue_action == 'add':
            change = self.param_str_to_object(action_arg)
            added, rejected = self.add(change)
            self._report_changes_status(queue_name, 'added', added)
            self._report_changes_status(queue_name, 'rejected', rejected)
        elif queue_action == 'on_test_success':
            test_key = action_arg
            success_list, fail_list = self.on_test_success(test_key)
            self._report_changes_status(queue_name, 'successful', success_list)
            self._report_changes_status(queue_name, 'failed', fail_list)
        elif queue_action == 'on_test_failure':
            test_key = action_arg
            success_list, fail_list = self.on_test_failure(test_key)
            self._report_changes_status(queue_name, 'successful', success_list)
            self._report_changes_status(queue_name, 'failed', fail_list)
        elif queue_action == 'get_next_test':
            test_key, change_list = self.get_next_test()
            if test_key is not None:
                self._build_change_list(test_key, change_list)
        else:
            raise InvalidChangeQueueAction(queue_action)
        self._write_status_file()

    @classmethod
    def _report_changes_status(cls, changes, status, queue_name):
        """Call methods on changes to report their status
        """
        if not changes:
            return
        # We always blame things on the 1st change
        change_at_fault = changes[0]
        for change in changes:
            cls._report_change_status(
                change, status, queue_name, change_at_fault
            )

    @staticmethod
    def _report_change_status(change, status, queue_name, change_at_fault):
        """Call methods on change to report its status

        Try to call the report_status method on the change object passing it
        the status, the queue_name and the change to blame.
        """
        getattr(change, 'report_status', (lambda *x: None))(
            status, queue_name, change_at_fault
        )

    @staticmethod
    def _build_change_list(test_key, change_list):
        JenkinsTestedChangeList((test_key, change_list)).save_to_artifact()

    def _write_status_file(self):
        # TODO: Write html file showing queue status
        pass


class JenkinsChangeQueueClient(JenkinsChangeQueueObject):
    """Class for representing the change queue for Jenkins jobs that need to
    communicate with it via Jenkins` job triggering mechanisms

    Constructor arguments:
    :param str queue_name: The name of the change queue we want to communicate
                           with. It is represented as a job in Jenkins.
    """
    def __init__(self, queue_name):
        self._queue_name = queue_name

    def get_queue_name(self):
        # Override inherited method because we get queue name as parameter and
        # not from job name
        return self._queue_name

    def add(self, change):
        """Add a change object to the change queue

        :rtype: JobRunSpec
        :returns: A specification of which job to run with what parameters in
                  order to add the change to the queue
        """
        return self.get_queue_job_run_spec(
            queue_action='add',
            action_arg=self.object_to_param_str(change),
        )


class JenkinsTestedChangeList(JenkinsChangeQueueObject, namedtuple(
    '_JenkinsTestedChangeList', ('test_key', 'change_list')
)):
    """Class for representing the set of changes to be tested in a change queue
    tester job.

    Also includes the mechanisms to report test results back to the queue
    """
    def on_test_success(self):
        """Report a successful test to the queue
        :rtype: JobRunSpec
        :returns: A specification of which job to run with what parameters in
                  order to add the change to the queue
        """
        return self.get_queue_job_run_spec('on_test_success', self.test_key)

    def on_test_failure(self):
        """Report a successful test to the queue
        :rtype: JobRunSpec
        :returns: A specification of which job to run with what parameters in
                  order to add the change to the queue
        """
        return self.get_queue_job_run_spec('on_test_failure', self.test_key)
