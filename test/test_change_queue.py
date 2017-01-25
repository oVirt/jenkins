#!/usr/bin/env python
"""test_change_queue.py - Tests for change_queue.python
"""
from __future__ import print_function
import pytest
import random
from math import log, ceil
from copy import copy
from six.moves import range

from scripts.change_queue import ChangeQueue


def _enlist_state(state):
    """Convert queue state into lists"""
    return list(list(st) for st in state)


class TestChangeQueue(object):
    @pytest.mark.parametrize(
        ('initq', 'add_arg', 'expq'),
        [
            ([[]], 1, [[1]]),
            ([[1]], 2, [[1, 2]]),
            ([[1, 2]], 3, [[1, 2, 3]]),
            ([[1, 2, 3], []], 4, [[1, 2, 3], [4]]),
            ([[1, 2, 3], [4]], 5, [[1, 2, 3], [4, 5]]),
            ([[1, 2, 3], [4, 5], []], 6, [[1, 2, 3], [4, 5], [6]]),
        ]
    )
    def test_add(self, initq, add_arg, expq):
        queue = ChangeQueue(initq)
        queue.add(add_arg)
        assert expq == _enlist_state(queue._state)

    @pytest.mark.parametrize(
        ('initq', 'inittk', 'exptk', 'expcl', 'expq'),
        [
            ([[]], None, None, [], [[]]),
            ([[1, 2]], None, '__SOME__', [1, 2], [[1, 2], []]),
            ([[1, 2], [3]], None, '__SOME__', [1, 2], [[1, 2], [3]]),
            ([[1, 2], [3]], 'k1', 'k1', [1, 2], [[1, 2], [3]]),
        ]
    )
    def test_get_next_test(self, initq, inittk, exptk, expcl, expq):
        queue = ChangeQueue(initq, inittk)
        outtk, outcl = queue.get_next_test()
        if exptk == '__SOME__':
            assert outtk is not None
        else:
            assert exptk == outtk
        assert expcl == outcl
        assert expq == _enlist_state(queue._state)
        # Logical invariants:
        assert list(queue._state[0]) == outcl
        assert queue._test_key == outtk

    @pytest.mark.parametrize(
        ('initq', 'inittk', 'tk', 'expsl', 'expfl', 'expq', 'exptk'),
        [
            ([[1, 2], [3]], None, 'k1', [], [], [[1, 2], [3]], None),
            ([[1, 2], [3]], None, None, [], [], [[1, 2], [3]], None),
            ([[1, 2]], None, 'k1', [], [], [[1, 2]], None),
            ([[1, 2], [3]], 'k1', 'k2', [], [], [[1, 2], [3]], 'k1'),
            ([[1, 2], [3]], 'k1', None, [], [], [[1, 2], [3]], 'k1'),
            ([[1, 2], [3]], 'k1', 'k1', [1, 2], [], [[3]], None),
            ([[1, 2], [3], []], 'k1', 'k1', [1, 2], [3], [[]], None),
            ([[1], [3], []], 'k1', 'k1', [1], [3], [[]], None),
            ([[1], [3, 4], []], 'k1', 'k1', [1], [], [[3], [4], []], None),
        ]
    )
    def test_on_test_success(self, initq, inittk, tk,
                             expsl, expfl, expq, exptk):
        queue = ChangeQueue(initq, inittk)
        outsl, outfl = queue.on_test_success(tk)
        assert expsl == outsl
        assert expfl == outfl
        assert expq == _enlist_state(queue._state)
        assert queue._test_key == exptk

    @pytest.mark.parametrize(
        ('initq', 'inittk', 'tk', 'expfl', 'expq', 'exptk'),
        [
            ([[1, 2], [3]], None, 'k1', [], [[1, 2], [3]], None),
            ([[1, 2], [3]], None, None, [], [[1, 2], [3]], None),
            ([[1, 2]], None, 'k1', [], [[1, 2]], None),
            ([[1, 2], [3]], 'k1', 'k2', [], [[1, 2], [3]], 'k1'),
            ([[1, 2], [3]], 'k1', None, [], [[1, 2], [3]], 'k1'),
            ([[1, 2], [3]], 'k1', 'k1', [], [[1], [2], [3]], None),
            ([[1, 2], [3], [4]], 'k1', 'k1', [], [[1], [2], [3], [4]], None),
            ([[1, 2, 3], [4]], 'k1', 'k1', [], [[1], [2, 3], [4]], None),
            ([[1, 2, 3, 4], [5]], 'k1', 'k1', [], [[1, 2], [3, 4], [5]], None),
            ([[1], [2], [3, 4], [5]], 'k1', 'k1', [1], [[2, 3, 4, 5]], None),
            ([[1], [2], []], 'k1', 'k1', [1], [[2]], None),
            ([[1], [2]], 'k1', 'k1', [1], [[2]], None),
        ]
    )
    def test_on_test_failure(self, initq, inittk, tk, expfl, expq, exptk):
        queue = ChangeQueue(initq, inittk)
        outsl, outfl = queue.on_test_failure(tk)
        assert [] == outsl
        assert expfl == outfl
        assert expq == _enlist_state(queue._state)
        assert queue._test_key == exptk

    @pytest.mark.parametrize(
        ('num_changes', 'num_bad'),
        [(99, 1), (100, 1), (3, 1), (4, 1), (100, 2), (45, 3), (5, 5)]
    )
    def test_bad_search(self, num_changes, num_bad):
        for time in range(1, 20):
            changes = range(0, num_changes)
            bad_changes = copy(list(changes))
            random.shuffle(bad_changes)
            bad_changes = set(bad_changes[:num_bad])
            print('bad: ', bad_changes)
            queue = ChangeQueue([changes])
            found_bad = set()
            for attempts in range(0, num_changes * num_bad):
                test_key, test_list = queue.get_next_test()
                assert test_key
                assert test_list
                print(test_list)
                if bad_changes & set(test_list):
                    _, fail_list = queue.on_test_failure(test_key)
                else:
                    _, fail_list = queue.on_test_success(test_key)
                if fail_list:
                    found_bad |= set(fail_list)
                    if len(found_bad) >= num_bad:
                        break
            assert bad_changes == found_bad
            assert attempts <= (ceil(log(num_changes, 2)) + 1) * num_bad
