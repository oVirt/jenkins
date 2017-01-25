#!/usr/bin/env python
"""change_queue.py - Change queue management functions
"""
from uuid import uuid4
from itertools import chain
from collections import deque


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
