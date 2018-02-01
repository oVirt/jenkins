#!/bin/env python

import pytest
from scripts.nested_config import (
    _dfs, _merge, _cartesian_multiplication, _dedup, _aggregate, gen_vectors
)
try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call


def mock_merge_options(o1, o2):
    return {'merged options': None}


@pytest.mark.parametrize(
    "data_in,categories,expected",
    [
        (
            {'cat': {'v': {'ncat': 'v2'}}},
            ['cat', 'ncat'],
            [('v', 'v2', {'merged options': None})]
        ),
        (
            {'cat': {'v': {'cat': 'v2'}}},
            ['cat'],
            [('v', {'merged options': None})]
        ),
        (
            {'cat1': ['v1', 'v2'], 'cat2': ['v3', 'v4']},
            ['cat1', 'cat2'],
            [
                ('v1', None, {}),
                ('v2', None, {}),
                (None, 'v3', {}),
                (None, 'v4', {})
            ]
        ),
        (
            {'cat1': 'v1', 'cat2': 'v2'},
            ['cat1', 'cat2'],
            [
                ('v1', None, {}),
                (None, 'v2', {})
            ]
        ),
        (
            {'cat1': [{'v1': {'nested1': 'v2'}}, ]},
            ['cat1', 'nested1'],
            [
                ('v1', 'v2', {'merged options': None})
            ]
        ),
        (
            {'cat1': [{'v1': {'cat1': 'v2'}}, ]},
            ['cat1'],
            [
                ('v1', {'merged options': None})
            ],
        ),
        (
            {'cat1': ['v1'], 'repos': 'ov1'},
            ['cat1'],
            [
                ('v1', {'repos': 'ov1'})
            ]
        ),
        (
            {},
            ['cat1'],
            [
                (None, {})
            ]
        ),
        (
            {'arch': ['x', 'y', 'z'], 'distro': [1, {2: {'arch': ['y']}}]},
            ['arch', 'distro'],
            [
                ('x', None, {}),
                ('y', None, {}),
                ('z', None, {}),
                (None, '1', {}),
                ('y', '2', {'merged options': None})
            ]
        ),
        (
            {
                'distro': ['el6', 'fc25', 'fc26', 'el7'],
                'substage':
                [
                    'default',
                    {
                        'another':
                        {
                            'distro': 'el7',
                            'script': {'abc':'efg'},
                            'stage': 'check-patch'
                        }
                    }
                ]
            },
            ('stage', 'substage', 'distro', 'arch'),
            [
                (None, 'default', None, None, {}),
                ('check-patch', 'another', 'el7', None, {'merged options': None}),
                (None, None, 'el6', None, {}),
                (None, None, 'fc25', None, {}),
                (None, None, 'fc26', None, {}),
                (None, None, 'el7', None, {})
            ]
        ),
    ]
)
def test_dfs(data_in, categories, expected):
    out = list(_dfs(data_in, categories, mock_merge_options))
    assert out == expected


@pytest.mark.parametrize(
    "data_in,expected",
    [
        (
            [],
            SyntaxError
        ),
    ]
)
def test_dfs_exceptions(data_in, expected):
    with pytest.raises(expected):
        list(_dfs(data_in, ('a', 'b'), mock_merge_options))


@pytest.mark.parametrize(
    "list_of_vectors,expected_list,expected_change",
    [
        (
            [('cat1', 'cat2', {}),
             ('cat3', 'cat4', {})],
            [('cat1', 'cat2', {}),
             ('cat3', 'cat4', {})],
            False
        ),
        (
            [('cat1', None, {}),
             (None, 'cat2', {}),
             ('cat3', None, {})],
            [('cat1', 'cat2', {'merged options': None}),
             ('cat3', 'cat2', {'merged options': None})],
            True
        ),
        (
            [('cat1', None, 'cat3', {}),
             ('cat1', 'cat2', 'cat3', {}),
             ('cat1', 'cat4', 'cat3', {})],
            [('cat1', 'cat2', 'cat3', {'merged options': None}),
             ('cat1', 'cat4', 'cat3', {'merged options': None})],
            True
        ),
        (
            [],
            [],
            False
        )
    ]
)
def test_cartesian_multiplication(
    list_of_vectors,
    expected_list,
    expected_change
):
    was_changed, returned_vectors = \
        _cartesian_multiplication(list_of_vectors, mock_merge_options)
    assert was_changed == expected_change
    assert sorted(returned_vectors, key=lambda x: hash(x[:-1])) == \
        sorted(expected_list, key=lambda x: hash(x[:-1]))


@pytest.mark.parametrize(
    ("vectors,expected"),
    [
        (
            [],
            []
        ),
        (
            [
                ('va', 'vb', 'vc', {'packages': 'ov', 'repos': 'o2v'}),
                ('va', 'vb', 'vc', {'packages': 'ov', 'repos': 'o2v'}),
                ('va', 'vb', 'vc', {'packages': 'ov', 'repos': 'o2v'})
            ],
            [
                ('va', 'vb', 'vc', {'merged options': None})
            ]
        ),
        (
            [
                ('va', 'vb', 'vc', {'packages': 'ov', 'repos': 'o2v'}),
                ('va', 'vb', 'vc', {'packages': 'ov', 'repos': 'o2v'}),
                ('a', 'b', 'c', {'packages': 'ov1', 'repos': 'o2v1'})
            ],
            [
                ('va', 'vb', 'vc', {'merged options': None}),
                ('a', 'b', 'c', {'packages': 'ov1', 'repos': 'o2v1'})
            ]
        ),
        (
            [
                ('a', 'b', 'c', {'packages': 'v'}),
                ('a', 'b', 'c', {'oa': 'va'})
            ],
            [
                ('a', 'b', 'c', {'merged options': None})
            ]
        ),
        (
            [
                ('a', None, None, ),
                (None, 'b', None, ),
                (None, None, 'c', )
            ],
            [
                ('a', None, None, ),
                (None, 'b', None, ),
                (None, None, 'c', )
            ]
        ),
        (
            [
                ('el6', None, 'build', None, {'merged options': None}),
                ('el7', None, 'build', 'ppc64le', {'merged options': None}),
                ('el7', 'check-merged', 'build', 'x86_64', {'merged options': None}),
                ('el7', 'check-patch', 'build', 'x86_64', {'merged options': None})
            ],
            [
                ('el6', None, 'build', None, {'merged options': None}),
                ('el7', None, 'build', 'ppc64le', {'merged options': None}),
                ('el7', 'check-merged', 'build', 'x86_64', {'merged options': None}),
                ('el7', 'check-patch', 'build', 'x86_64', {'merged options': None})
            ],
        ),
        (
            [
                ('va1', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb1', 'cc2', {'merged options': None}),
                ('va1', 'vb1', 'cc2', {'merged options': None}),
                ('va1', 'vb2', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc2', {'merged options': None}),
                ('va1', 'vb2', 'cc2', {'merged options': None}),
                ('va2', 'vb1', 'cc1', {'merged options': None}),
                ('va2', 'vb1', 'cc1', {'merged options': None}),
                ('va2', 'vb1', 'cc2', {'merged options': None}),
                ('va2', 'vb1', 'cc2', {'merged options': None}),
                ('va2', 'vb2', 'cc1', {'merged options': None}),
                ('va2', 'vb2', 'cc1', {'merged options': None}),
                ('va2', 'vb2', 'cc2', {'merged options': None}),
                ('va2', 'vb2', 'cc2', {'merged options': None})
            ],
            [
                ('va1', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb1', 'cc2', {'merged options': None}),
                ('va1', 'vb2', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc2', {'merged options': None}),
                ('va2', 'vb1', 'cc1', {'merged options': None}),
                ('va2', 'vb1', 'cc2', {'merged options': None}),
                ('va2', 'vb2', 'cc1', {'merged options': None}),
                ('va2', 'vb2', 'cc2', {'merged options': None})
            ]
        )
    ]
)
def test_dedup(vectors, expected):
    assert list(_dedup(vectors, mock_merge_options)) == list(expected)


@pytest.mark.parametrize(
    ("vectors,expected"),
    [
        (
            [
                ('va', 'vb', None, {'packages': 'ov', 'repos': 'o2v'}),
                ('va', None, 'vc', {'packages': 'ov'}),
                (None, 'vb', 'vc', {'repos': 'o2v'})
            ],
            [
                ('va', 'vb', 'vc', {'merged options': None})
            ]
        ),
        (
            [
                (None, None, 'cc1', {'packages': 'x'}),
                (None, None, 'cc2', {'packages': 'x'}),
                (None, 'vb1', None, {'packages': 'x'}),
                (None, 'vb2', None, {'packages': 'x'}),
                ('va1', None, None, {'packages': 'x'}),
                ('va2', None, None, {'packages': 'x'})
            ],
            [
                ('va2', 'vb2', 'cc2', {'merged options': None}),
                ('va2', 'vb2', 'cc1', {'merged options': None}),
                ('va2', 'vb1', 'cc2', {'merged options': None}),
                ('va2', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc2', {'merged options': None}),
                ('va1', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb1', 'cc2', {'merged options': None})
            ]
        ),
    ]
)
def test_aggregate(vectors, expected):
    assert sorted(
        list(_aggregate(vectors, mock_merge_options)),
        key=lambda x: hash(x[:-1])
    ) == sorted(expected, key=lambda x: hash(x[:-1]))


@pytest.mark.parametrize(
    ("data_in,categories,expected"),
    [
        (
            {'cat1': ['v1', 'v2'], 'cat2': ['v3', 'v4']},
            ['cat1', 'cat2'],
            [
                ('v1', 'v3', {'merged options': None}),
                ('v1', 'v4', {'merged options': None}),
                ('v2', 'v3', {'merged options': None}),
                ('v2', 'v4', {'merged options': None})
            ]
        ),
        (
            {'cat1': 'v1', 'cat2': 'v2', 'cat3': 'v3'},
            ['cat1', 'cat2', 'cat3'],
            [
                ('v1', 'v2', 'v3', {'merged options': None}),
            ]
        ),
        (
            {'cat1': 'v1', 'cat2': 'v2', 'cat3': 'v3'},
            ['cat1', 'cat2', 'cat3'],
            [
                ('v1', 'v2', 'v3', {'merged options': None}),
            ]
        ),
        (
            {
                'ca': ['va1', 'va2'],
                'cb': ['vb1', 'vb2'],
                'cc': ['cc1', 'cc2'],
                'packages': 'x'
            },
            ['ca', 'cb', 'cc'],
            [
                ('va2', 'vb2', 'cc2', {'merged options': None}),
                ('va2', 'vb2', 'cc1', {'merged options': None}),
                ('va2', 'vb1', 'cc2', {'merged options': None}),
                ('va2', 'vb1', 'cc1', {'merged options': None}),
                ('va1', 'vb2', 'cc2', {'merged options': None}),
                ('va1', 'vb2', 'cc1', {'merged options': None}),
                ('va1', 'vb1', 'cc2', {'merged options': None}),
                ('va1', 'vb1', 'cc1', {'merged options': None})
            ]
        ),
        (
            {
                'distro': [{'el7': {'arch': 'ppc64le'}}, 'el6'],
                'stage': [
                    {'check-patch': {'arch': [{'x86_64': {'distro': 'el7'}}]}},
                    {'check-merged': {'arch': [{'x86_64': {'distro': 'el7'}}]}}
                ],
                'substage': [{'build': {'packages': ['p3']}}]
            },
            ['distro', 'stage', 'substage', 'arch'],
            [('el6', None, 'build', None, {'merged options': None}),
             ('el7', None, 'build', 'ppc64le', {'merged options': None}),
             ('el7', 'check-merged', 'build', 'x86_64', {'merged options': None}),
             ('el7', 'check-patch', 'build', 'x86_64', {'merged options': None})]
        ),
        (
            {'o1': ['ov1', 'ov1.2'], 'repos': 'ov2'},
            ['c1', 'c2'],
            [(None, None, {'o1': ['ov1', 'ov1.2'], 'repos': 'ov2'}),],
        ),
        (
            {'stage': [{'check-patch': {'arch': ['x86_64', 'ppc64le'],
             'distro': 'el7',
             'stage': [{'check-merged': {'distro': 'el7'}}]}}]},
            ['stage', 'arch', 'distro',],
            [('check-patch', 'x86_64', 'el7', {'merged options': None}),
             ('check-patch', 'ppc64le', 'el7', {'merged options': None})]
        ),
    ]
)
def test_gen_vectors(data_in, categories, expected):
    assert sorted(
        list(gen_vectors(data_in, mock_merge_options, categories)),
        key=lambda x: hash(x[:-1])
    ) == sorted(expected, key=lambda x: hash(x[:-1]))


@pytest.mark.parametrize(
    ("vector1,vector2,expected"),
    [
        (
            ('v1', None, {}),
            (None, 'v2', {}),
            ('v1', 'v2', {'merged options': None})
        ),
        (
            ('v1', None, {}),
            ('v1', 'v2', {}),
            ('v1', 'v2', {'merged options': None})
        ),
        (
            ('v1', {}),
            (None, {'repos': 'ov1'}),
            ('v1', {'merged options': None})
        ),
        (
            ('v1', None, 'v3', {'repos': 'ov1'}),
            ('v1', 'v2', None, {'packages': 'ov2'}),
            ('v1', 'v2', 'v3', {'merged options': None})
        ),
        (
            ('v1', None, {'repos': 'ov1'}),
            ('v2', None, {'packages': 'ov2'}),
            None
        ),
        (
            ('v1', None),
            ('v2', None),
            None
        ),
    ]
)
def test_merge(vector1, vector2, expected):
    assert _merge(vector1, vector2, mock_merge_options) == expected


def test_merge_options_dfs_calls():
    mock_merge_options = MagicMock(return_value={'merged options': None})
    simple_data = {
        'packages': 'p3',
            'stage': [
                {'check-patch':
                    {'packages': 'p',
                        'distro': [
                            {'el7': {'packages': 'pdepth'}}
                        ]
                    }
                }
            ]
    }
    assert list(_dfs(simple_data, ('stage', 'distro'), mock_merge_options)) == \
        [('check-patch', 'el7', {'merged options': None})]
    calls = [
        call({'packages': 'p'}, {'packages': 'pdepth'}),
        call({'packages': 'p3'}, {'merged options': None})
    ]
    mock_merge_options.assert_has_calls(calls, any_order=False)
    assert mock_merge_options.call_count == 2


def test_merge_options_merge_calls():
    mock_merge_options = MagicMock(return_value={'merged options': None})
    vector1 = ('cp', 'fc', {'rp': 'r'})
    vector2 = ('cp', None, {'pg': 'p'})
    assert _merge(vector1, vector2, mock_merge_options) == \
        ('cp', 'fc', {'merged options': None})
    mock_merge_options.assert_called_once_with({'rp': 'r'}, {'pg': 'p'})
    assert mock_merge_options.call_count == 1
