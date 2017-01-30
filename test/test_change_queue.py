#!/usr/bin/env python
"""test_change_queue.py - Tests for change_queue.python
"""
from __future__ import print_function
import pytest
import random
from math import log, ceil
from copy import copy
from six.moves import range
from collections import namedtuple
import re

from scripts.change_queue import ChangeQueue, ChangeQueueWithDeps


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


class ChangeWithDeps(namedtuple('_ChangeWithDeps', ('id', 'requirements'))):
    @classmethod
    def from_value(cls, chvalue):
        try:
            return cls(int(chvalue), set())
        except ValueError:
            match = re.match('^(\d+)((r\d+(,\d+)*)*)$', str(chvalue))
            if not match:
                raise ValueError('Malformed ChangeWithDeps string')
            chid = int(match.group(1))
            req_set = set()
            req_lists = re.findall('r(\d+(,\d+)*)', match.group(2))
            for req_list, _ in req_lists:
                req_set |= set(int(c) for c in req_list.split(','))
            return cls(chid, req_set)

    def __str__(self):
        out = str(self.id)
        if self.requirements:
            out += 'r' + ','.join(map(str, self.requirements))
        return out

_cwds_fv = ChangeWithDeps.from_value


@pytest.mark.parametrize(
    ('init_param', 'exp_obj'),
    [
        (17, (17, set())),
        ('15', (15, set())),
        ('3r4', (3, set([4]))),
        ('5r6', (5, set([6]))),
        ('7r8r9', (7, set([8, 9]))),
        ('10r11,12r13,14,15', (10, set([11, 12, 13, 14, 15]))),
        ('16r17,18r19r20r21,22', (16, set([19, 21, 22, 17, 18, 20]))),
    ]
)
def test_change_with_deps_from_value(init_param, exp_obj):
    out_obj = ChangeWithDeps.from_value(init_param)
    assert exp_obj == out_obj


def _c2adep(change):
    """Convert a change string to (change, deps) pair"""
    cwd = _cwds_fv(change)
    return cwd, set(cwd.requirements)


@pytest.mark.parametrize(
    ('change', 'exp_c_d_pair'),
    [
        (1, (_cwds_fv(1), set())),
        ('1r5', (_cwds_fv('1r5'), set([5]))),
        ('1r5,6', (_cwds_fv('1r5,6'), set([5, 6]))),
    ]
)
def test_c2adep(change, exp_c_d_pair):
    out = _c2adep(change)
    assert exp_c_d_pair == out


class TestChangeQueueWithDeps(object):
    @pytest.mark.parametrize(
        ('change', 'exp'),
        [
            (_cwds_fv('1r2'), [2]),
            (_cwds_fv('1r2,3'), [2, 3]),
            (_cwds_fv('1'), []),
        ]
    )
    def test_change_requirements(self, change, exp):
        out = ChangeQueueWithDeps._change_requirements(change)
        assert set(exp) == out

    @pytest.mark.parametrize(
        ('initq', 'change', 'exp_deps'),
        [
            ([[1], [2, 3]], 4, []),
            ([[1], [2, 3]], '4r5', [5]),
            ([[1], [2, 3]], '4r2', []),
            ([[1], [2, 3]], '4r2,1', []),
            ([[1], [2, 3]], '4r2,5,1', [5]),
            ([[1], [2, 3]], '4r2,5,1,6', [5, 6]),
        ]
    )
    def test_get_missing_deps(self, initq, change, exp_deps):
        queue = ChangeQueueWithDeps(initq)
        out_deps = queue._get_missing_deps(_cwds_fv(change))
        assert set(exp_deps) == set(out_deps)

    @pytest.mark.parametrize(
        ('change_id', 'changes', 'exp_deps'),
        [
            (0, [], []),
            (0, [0, 1, 2], []),
            (0, [0, '1r0', '2r3'], [1]),
            (0, [0, '1r0', '2r0', 3], [1, 2]),
            (0, ['0r3,4', '1r0', '2r0', 3], [1, 2]),
            (0, ['0r0', '1r0', '2r0', 3], [0, 1, 2]),
            (0, ['0r1', '1r0', '2r0', 3], [0, 1, 2]),
            (0, ['0r1', '1r2', '2r0', '3r1'], [0, 1, 2, 3]),
            (0, ['0r1,4', '1r2', '2r0', '3r1', 4], [0, 1, 2, 3]),
            (0, ['0r1,4,5', '1r2', '2r0', '3r1', '4r5'], [0, 1, 2, 3]),
        ]
    )
    def test_find_dependants_on(self, change_id, changes, exp_deps):
        deps = ChangeQueueWithDeps._find_dependants_on(
            change_id, map(_cwds_fv, changes)
        )
        assert set(exp_deps) == set(deps)

    @pytest.mark.parametrize(
        ('adeps', 'dep_ids', 'exp_out', 'exp_a_deps'),
        [
            ([], [], [], []),
            ([], [1, 2, 3], [], []),
            ([1, 2, 3, 4, 5], [2, 4, 6], [2, 4], [1, 3, 5]),
        ]
    )
    def test_rm_a_deps_by_ids(self, adeps, dep_ids, exp_out, exp_a_deps):
        queue = ChangeQueueWithDeps(awaiting_deps=map(_c2adep, adeps))
        out = queue._remove_awaiting_deps_by_ids(set(dep_ids))
        assert list(map(_c2adep, exp_out)) == out
        assert list(map(_c2adep, exp_a_deps)) == list(queue._awaiting_deps)

    @pytest.mark.parametrize(
        ('add_sequence', 'exp_state_ids', 'exp_loop_ids'),
        [
            ([1, 2, 3], [1, 2, 3], []),
            ([1, '2r1', '3r1'], [1, 2, 3], []),
            (['2r1', '3r1', 1], [1, 2, 3], []),
            (['3r1,2', '2r1', 1], [1, 2, 3], []),
            (['3r2', '2r1', 1], [1, 2, 3], []),
            (['2r1', '4r5', 1, '3r2'], [1, 2, 3], []),
            (['2r1,4', '4r5', 1, '3r2'], [1], []),
            (['2r1,4', '4r5', 1, '3r2', 5], [1, 5, 4, 2, 3], []),
            (['3r2', '5r4', '2r1', '6r5', '4r1', 1], [1, 2, 3, 4, 5, 6], []),
            (['1r2,3', 3, 2], [3, 2, 1], []),
            (['1r1'], [], [1]),
            ([1, '2r2', 3], [1, 3], [2]),
            (['1r3', 2, '3r1'], [2], [3, 1]),
            (['1r3', '2r3', '3r1'], [], [3, 1, 2]),
            (['1r2', '2r3', '3r2'], [], [3, 2, 1]),
            (['1r2', '2r3', '3r1'], [], [3, 2, 1]),
            (['1r2', '5r4', '2r3', 4, '3r1'], [4, 5], [3, 2, 1]),
            (['1r2', '5r4', '2r3', '4r1', '3r1'], [], [3, 2, 1, 4, 5]),
        ]
    )
    def test_add(self, add_sequence, exp_state_ids, exp_loop_ids):
        queue = ChangeQueueWithDeps()
        loop_ids = []
        for change in add_sequence:
            added, in_loop = queue.add(_cwds_fv(change))
            print('added: ', added)
            print('in_loop:', in_loop)
            loop_ids.extend(map(ChangeQueueWithDeps._change_id, in_loop))
        assert exp_state_ids == \
            list(map(ChangeQueueWithDeps._change_id, queue._state[0]))
        assert exp_loop_ids == loop_ids

    @pytest.mark.parametrize(
        ('initq', 'initwd', 'expfl', 'expq', 'expwd'),
        [
            (
                [[1, 2, '3r1', '4r2', 5, '6r1', '7r2', '8r1', '9r6'], []],
                ['10r2,99', '11r98', '12r1,99', '13r99'],
                [],
                [[1, 2, '3r1', '4r2'], [5, '6r1', '7r2', '8r1', '9r6'], []],
                ['10r2,99', '11r98', '12r1,99', '13r99'],
            ),
            (
                [[1], [2, '3r1', '4r2', 5, '6r1', '7r2', '8r1', '9r6'], []],
                ['10r2,99', '11r98', '12r1,99', '13r99'],
                [1, 3, 6, 8, 9, 12],
                [[2, '4r2', 5, '7r2']],
                ['10r2,99', '11r98', '13r99'],
            ),
            (
                [[1], [2, '3r1', '4r2', 5, '6r1'], ['7r2', '8r1', '9r6']],
                ['10r2,99', '11r98', '12r1,99', '13r99'],
                [1, 3, 6, 8, 9, 12],
                [[2, '4r2', 5, '7r2']],
                ['10r2,99', '11r98', '13r99'],
            ),
        ]
    )
    def test_on_test_failure(self, initq, initwd, expfl, expq, expwd):
        queue = ChangeQueueWithDeps(
            (map(_cwds_fv, s) for s in initq), 'k1', map(_c2adep, initwd)
        )
        outsl, outfl = queue.on_test_failure('k1')
        assert [] == outsl
        assert expfl == list(map(ChangeQueueWithDeps._change_id, outfl))
        assert [list(map(_cwds_fv, s)) for s in expq] == \
            _enlist_state(queue._state)
        assert list(map(_c2adep, expwd)) == list(queue._awaiting_deps)
