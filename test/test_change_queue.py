#!/usr/bin/env python
"""test_change_queue.py - Tests for change_queue.python
"""
from __future__ import print_function
import pytest
import random
from math import log, ceil
from copy import copy
from six.moves import range
from six import iteritems
from collections import namedtuple, OrderedDict
import re
from base64 import b64encode
from textwrap import dedent
from os import path

from scripts.change_queue import ChangeQueue, ChangeQueueWithDeps, \
    GerritPatchset, JobRunSpec, JenkinsObject, NotInJenkins


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


class TestGerritPatchset(object):
    def test_from_jenkins_env(self, monkeypatch):
        msg = 'This is a commit message'
        env = {
            'GERRIT_BRANCH': 'master',
            'GERRIT_CHANGE_COMMIT_MESSAGE': b64encode(msg.encode()).decode(),
            'GERRIT_CHANGE_ID': 'I5b35b72af9a40b1564792dbfcf30a82cf3f5ccb5',
            'GERRIT_CHANGE_NUMBER': '4',
            'GERRIT_CHANGE_OWNER_EMAIL': 'bkorren@redhat.com',
            'GERRIT_CHANGE_OWNER_NAME': 'Barak Korren',
            'GERRIT_CHANGE_SUBJECT': 'Just a dummy change for testing',
            'GERRIT_CHANGE_URL': 'https://gerrit-staging.phx.ovirt.org/4',
            'GERRIT_HOST': 'gerrit-staging.phx.ovirt.org',
            'GERRIT_PATCHSET_NUMBER': '2',
            'GERRIT_PATCHSET_REVISION': 'some-revision',
            'GERRIT_PATCHSET_UPLOADER_EMAIL': 'bkorren@redhat.com',
            'GERRIT_PATCHSET_UPLOADER_NAME': 'Barak Korren',
            'GERRIT_PORT': '29418',
            'GERRIT_PROJECT': 'barak-test',
            'GERRIT_REFSPEC': 'refs/changes/04/4/2',
            'GERRIT_SCHEME': 'ssh',
            'GERRIT_TOPIC': 'Dummy change for testing',
        }
        for var, val in iteritems(env):
            monkeypatch.setenv(var, val)
        ps = GerritPatchset.from_jenkins_env()
        assert ps.refspec == env['GERRIT_REFSPEC']
        assert ps.change.branch.project.server.host == env['GERRIT_HOST']
        assert ps.change.branch.project.server.port == int(env['GERRIT_PORT'])
        assert ps.change.branch.project.name == env['GERRIT_PROJECT']
        assert ps.change.branch.name == env['GERRIT_BRANCH']
        assert ps.change.change_id == env['GERRIT_CHANGE_ID']
        assert ps.change.number == int(env['GERRIT_CHANGE_NUMBER'])
        assert ps.refspec == env['GERRIT_REFSPEC']
        assert ps.patchset_number == int(env['GERRIT_PATCHSET_NUMBER'])
        assert ps.commit_message == msg


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


@pytest.fixture
def jenkins_env(monkeypatch, tmpdir):
    env_spec = dict(
        job_base_name='some_job',
        worspace=tmpdir,
    )
    for var, value in iteritems(env_spec):
        monkeypatch.setenv(var.upper(), value)
    monkeypatch.chdir(env_spec['worspace'])
    return namedtuple('jenkins_env_spec', env_spec.keys())(*env_spec.values())


@pytest.fixture
def not_jenkins_env(monkeypatch):
    monkeypatch.delenv('JOB_BASE_NAME', False)


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
