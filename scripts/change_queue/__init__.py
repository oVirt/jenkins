#!/usr/bin/env python
"""change_queue.py - Change queue management functions
"""
from __future__ import absolute_import, print_function
from uuid import uuid4
from itertools import chain
from collections import deque, namedtuple
from six.moves import map, reduce, range
from copy import copy
from os import path
import logging
from jinja2 import Environment, PackageLoader

from .changes import DisplayableChangeWrapper, ChangeInStreamWrapper
from scripts.jenkins_objects import JenkinsObject, JobRunSpec


logger = logging.getLogger(__name__)


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

    def test_key_match(self, test_key):
        """Returns True if the given test_key matches the last generated one
        """
        return test_key is not None and test_key == self._test_key

    def on_test_success(self, test_key):
        """Updated the queue when a test is successful

        :param str test_key: The test key of the test. Must match the test key
                             return from the last call to get_next_test,
                             otherwise the test result will be ignored.

        If one of the on_test_* methods was already called with the proper test
        key following the last call to get_next_test, this call will be ignored

        :rtype: tuple
        :returns: A tuple of successful changes list, failed changes list if
                  we now have enough information to determine them and the
                  change that caused the failure if we know which one is it.
                  The changes in the returned lists will be removed from the
                  queue. On ignored calls empty lists are returned
        """
        if not self.test_key_match(test_key):
            return [], [], None
        success_list = list(self._state.popleft())
        if len(self._state) > 1:
            _, fail_list, cause = self.on_test_failure(test_key)
        else:
            fail_list, cause = [], None
        self._test_key = None
        return success_list, fail_list, cause

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
        if not self.test_key_match(test_key):
            return [], [], None
        self._test_key = None
        fail_list = list(self._state.popleft())
        if len(fail_list) == 1:
            self._state = deque([deque(chain.from_iterable(self._state))])
            return [], fail_list, next(iter(fail_list), None)
        self._state.extendleft([
            deque(fail_list[int(len(fail_list)/2):]),
            deque(fail_list[:int(len(fail_list)/2)])
        ])
        return [], [], None


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
    :param Iterable awaiting_deps: (Optional) The initial state of the queue of
                                   changes with missing dependencies. This is
                                   a list of pairs of changes and their missing
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
        success_list, fail_list, cause = \
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
        return success_list, fail_list, cause

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


class ChangeQueueWithStreams(ChangeQueue):
    """Class for managing change queues with change stream tracking

    Change streams are sources of changes where each change contains all the
    previous changes. Examples of such change sources are package repositories
    and SCM branches.

    Failures in change streams typically happen in sequences, once a change
    causes a testing failure, all subsequent changes will also fail until a
    fixing change is submitted. In this case it makes sense to keep track of
    the first failing change in a sequence, and report it as causing all
    subsequent failures that have to do with changes in the same stream.

    For a change to belong to a change stream, it need to have a 'stream_id'
    property that wither returns 'None' (which means no stream) or a hashable
    object.

    Constructor arguments:
    :param Iterable initial_state: (Optional) The initial state of the queue,
                                   should be an iterable of iterables with at
                                   least one member.
    :param str test_key:           (Optional) Key identifying a currently
                                   running test
    :param Iterable stream_map:    (Optional) The initial state of the mapping
                                   of change stream IDs to failure-sequence
                                   starting changes.

    If test_key is specified (not None), then initial_state must have more then
    one member where the last member is the list of changes being tested
    """
    def __init__(self, initial_state=None, test_key=None, stream_map=None):
        super(ChangeQueueWithStreams, self).__init__(initial_state, test_key)
        if stream_map is None:
            self._stream_map = dict()
        else:
            self._stream_map = dict(
                getattr(
                    stream_map, 'iteritems', getattr(
                        stream_map, 'items', getattr(stream_map, '__iter__')
                    )
                )()
            )

    def _get_cause_from_stream(self, cause):
        """Given a failure causing change, if we're seeing a failure sequence
        for that change`s stream, return the first failing change in the
        sequence
        """
        cause_stream_id = ChangeInStreamWrapper(cause).stream_id
        if cause_stream_id is None:
            return cause
        return self._stream_map.setdefault(cause_stream_id, cause)

    def on_test_failure(self, test_key):
        """Updated the queue when a test is successful

        Works like the superclass's method, but if the failed change belongs
        to a change stream in which we see a sequence of failed changed, the
        first failing change in the sequence will be returned as the failure
        cause.
        """
        if hasattr(self, '_orig_cause'):
            del self._orig_cause
        success_list, fail_list, cause = \
            super(ChangeQueueWithStreams, self).on_test_failure(test_key)
        return success_list, fail_list, self._get_cause_from_stream(cause)

    def on_test_success(self, test_key):
        """Updated the queue when a test is successful

        Works like the superclass's method, but if a successful change belongs
        to a change stream in which we seen a sequence of failed changed, we
        store the information about the sequence having ended.
        """
        # We want the superclass on_test_success to call the superclass
        # on_test_failure because we want to get the original failure cause if
        # any and not the one that our version of on_test_failure calculates
        orig_on_test_failure = self.__dict__.get('on_test_failure')
        self.on_test_failure = \
            super(ChangeQueueWithStreams, self).on_test_failure
        try:
            success_list, fail_list, cause = \
                super(ChangeQueueWithStreams, self).on_test_success(test_key)
        finally:
            if orig_on_test_failure is None:
                del self.on_test_failure
            else:
                self.on_test_failure = orig_on_test_failure
        for succ_chg in success_list:
            succ_stream_id = ChangeInStreamWrapper(succ_chg).stream_id
            if succ_stream_id is None:
                continue
            self._stream_map.pop(succ_stream_id, None)
        return success_list, fail_list, self._get_cause_from_stream(cause)


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

    def act_on_job_params(self, queue_action, action_arg, actor_url=None):
        """Perform the queue action according to parameters passed to the job

        :param str queue_action: The queue action to perform ('add',
                                 'on_test_success', 'on_test_failure', or
                                 'get_next_test')
        :param str action_arg:   An argument to the queue_action if needed.
                                 Objects to be added need to be serialized with
                                 JenkinsObject.object_to_param_str
        :param str actor_url:    (Optional) The URL of the thing (typically a
                                 job build) that asked for the queue action.
                                 This is used in reporting

        This method is probably what the queue jobs will call. Apart from
        performing the queue action it will also run reporting methods on
        change objects to report their status, create changes list file if
        requested, and a status HTML file showing the state of the queue.
        """
        self._cleanup_result_files()
        if queue_action == 'add':
            change = self.param_str_to_object(action_arg)
            logger.info('Queue action: add {0}'.format(
                DisplayableChangeWrapper(change).presentable_id
            ))
            added, rejected = self.add(change)
            qname = self.get_queue_name()
            self._report_changes_status(added, 'added', qname)
            self._report_changes_status(rejected, 'rejected', qname)
            self._schedule_tester_run()
        elif queue_action == 'on_test_success':
            test_key = action_arg
            logger.info('Queue action: on_test_success {0}'.format(test_key))
            if self.test_key_match(test_key):
                self._last_successful_test = actor_url
            success_list, fail_list, cause = self.on_test_success(test_key)
            self._post_test_report(success_list, fail_list, cause)
            self._schedule_tester_run()
        elif queue_action == 'on_test_failure':
            test_key = action_arg
            logger.info('Queue action: on_test_failure {0}'.format(test_key))
            if self.test_key_match(test_key):
                self._last_failed_test = actor_url
            success_list, fail_list, cause = self.on_test_failure(test_key)
            self._post_test_report(success_list, fail_list, cause)
            self._schedule_tester_run()
        elif queue_action == 'get_next_test':
            logger.info('Queue action: get_next_test')
            test_key, change_list = self.get_next_test()
            if test_key is not None:
                self._build_change_list(test_key, change_list)
        else:
            raise InvalidChangeQueueAction(queue_action)
        self._write_status_file()

    @staticmethod
    def _cleanup_result_files():
        JenkinsTestedChangeList.clean_artifact()
        JobRunSpec.clean_pipeline_build_step_json()

    def _post_test_report(self, success_list, fail_list, cause):
        qname = self.get_queue_name()
        self._report_changes_status(
            success_list, 'successful', qname, cause,
            getattr(self, '_last_successful_test', None)
        )
        self._report_changes_status(
            fail_list, 'failed', qname, cause,
            getattr(self, '_last_failed_test', None)
        )

    @classmethod
    def _report_changes_status(cls, changes, status, qname, cause, turl=None):
        """Call methods on changes to report their status
        """
        if not changes:
            return
        logger.info('Reporting {0} {1} changes'.format(len(changes), status))
        for change in changes:
            cls._report_change_status(change, status, qname, cause, turl)

    @staticmethod
    def _report_change_status(change, status, qname, cause, test_url=None):
        """Call methods on change to report its status

        Try to call the report_status method on the change object passing it
        the status, the qname, the change to blame and the test job URL.
        """
        getattr(change, 'report_status', (lambda *x: None))(
            status, qname, cause, test_url
        )

    def _schedule_tester_run(self):
        logger.info('Scheduling testes job run')
        JobRunSpec(self.tester_job_name(), {}).as_pipeline_build_step_json()

    @staticmethod
    def _build_change_list(test_key, change_list):
        JenkinsTestedChangeList(test_key, change_list).save_to_artifact()

    def _write_status_file(self):
        env = self._get_jinja_env()
        tmpl = env.get_template('queue-status.html.j2')
        num_changes = sum(map(len, self._state), len(self._awaiting_deps))
        displayable_state = \
            [list(map(DisplayableChangeWrapper, subs)) for subs in self._state]
        displayable_awaiting_deps = [
            (DisplayableChangeWrapper(chg), deps)
            for chg, deps in self._awaiting_deps
        ]
        result_file = path.join(self.ARTIFACTS_DIR, 'queue-status.html')
        with open(result_file, 'w') as fil:
            fil.writelines(tmpl.generate(
                num_changes=num_changes,
                state=displayable_state,
                awaiting_deps=displayable_awaiting_deps,
                test_key=self._test_key,
            ))

    @classmethod
    def _get_jinja_env(cls):
        if not hasattr(cls, '_jinja_env'):
            cls._jinja_env = Environment(loader=PackageLoader(__name__))
        return cls._jinja_env


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
