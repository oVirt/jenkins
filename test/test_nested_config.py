#!/bin/env python

import pytest
from stdci_libs.nested_config import (
    _dfs, _merge_vectors, _cartesian_multiplication, _dedup, _aggregate,
    gen_vectors, _merge_options_wrapper, DepthLevel,
)
from stdci_libs.stdci_dsl.parser import (
    normalize_config_values, normalize_config_keys
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
                ('v1', None, {DepthLevel: 1}),
                ('v2', None, {DepthLevel: 1}),
                (None, 'v3', {DepthLevel: 1}),
                (None, 'v4', {DepthLevel: 1})
            ]
        ),
        (
            {'cat1': 'v1', 'cat2': 'v2'},
            ['cat1', 'cat2'],
            [
                ('v1', None, {DepthLevel: 1}),
                (None, 'v2', {DepthLevel: 1})
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
                ('v1', {'repos': 'ov1', DepthLevel: 1})
            ]
        ),
        (
            {},
            ['cat1'],
            [
                (None, {DepthLevel: 1})
            ]
        ),
        (
            {'arch': ['x', 'y', 'z'], 'distro': [1, {2: {'arch': ['y']}}]},
            ['arch', 'distro'],
            [
                ('x', None, {DepthLevel: 1}),
                ('y', None, {DepthLevel: 1}),
                ('z', None, {DepthLevel: 1}),
                (None, '1', {DepthLevel: 1}),
                ('y', '2', {'merged options': None})
            ]
        ),
        (
            {
                'DISTRO': ['el6', 'fc25', 'fc26', 'el7'],
                'SubStage':
                [
                    'default',
                    {
                        'another':
                        {
                            'Distro': 'el7',
                            'Script': {'abc': 'efg'},
                            'Stage': 'check-patch'
                        }
                    }
                ]
            },
            ('stage', 'substage', 'distro', 'arch'),
            [
                (None, 'default', None, None, {DepthLevel: 1}),
                ('check-patch', 'another', 'el7', None,
                 {'merged options': None}),
                (None, None, 'el6', None, {DepthLevel: 1}),
                (None, None, 'fc25', None, {DepthLevel: 1}),
                (None, None, 'fc26', None, {DepthLevel: 1}),
                (None, None, 'el7', None, {DepthLevel: 1})
            ]
        ),
    ]
)
def test_dfs(data_in, categories, expected, monkeypatch):
    def _merge_wrapper(a, b, c):
        return mock_merge_options(b, c)
    monkeypatch.setattr(
        'stdci_libs.nested_config._merge_options_wrapper', _merge_wrapper
    )
    out = list(
        _dfs(data=data_in, merge_options=mock_merge_options,
             categories=categories, normalize_keys=normalize_config_keys,
             normalize_values=normalize_config_values)
    )
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
            [('cat1', 'cat2', {DepthLevel: 0}),
             ('cat3', 'cat4', {DepthLevel: 0})],
            [('cat1', 'cat2', {DepthLevel: 0}),
             ('cat3', 'cat4', {DepthLevel: 0})],
            False
        ),
        (
            [('cat1', None, {DepthLevel: 0}),
             (None, 'cat2', {DepthLevel: 0}),
             ('cat3', None, {DepthLevel: 0})],
            [('cat3', 'cat2', {'merged options': None}),
             ('cat3', 'cat2', {'merged options': None}),
             ('cat1', 'cat2', {'merged options': None}),
             ('cat1', 'cat2', {'merged options': None})],
            True
        ),
        (
            [('cat1', None, 'cat3', {DepthLevel: 0}),
             ('cat1', 'cat2', 'cat3', {DepthLevel: 0}),
             ('cat1', 'cat4', 'cat3', {DepthLevel: 0})],
            [('cat1', 'cat4', 'cat3', {'merged options': None}),
             ('cat1', 'cat4', 'cat3', {'merged options': None}),
             ('cat1', 'cat2', 'cat3', {'merged options': None}),
             ('cat1', 'cat2', 'cat3', {'merged options': None})],
            True
        ),
        (
            [(None, None, 'el6', None, {DepthLevel: 0}),
             (None, None, 'el7', None, {DepthLevel: 0}),
             (None, None, 'fc25', None, {DepthLevel: 0}),
             (None, None, 'fc26', None, {DepthLevel: 0}),
             (None, None, 'fcraw', None, {DepthLevel: 0}),
             (None, None, 'el7', 'ppc64le', {DepthLevel: 0}),
             (None, None, 'fc27', 's390x', {DepthLevel: 0})],
            [(None, None, 'el6', None, {DepthLevel: 0}),
             (None, None, 'el7', 'ppc64le', {'merged options': None}),
             (None, None, 'el7', 'ppc64le', {'merged options': None}),
             (None, None, 'fc27', 's390x', {DepthLevel: 0}),
             (None, None, 'fcraw', None, {DepthLevel: 0}),
             (None, None, 'fc25', None, {DepthLevel: 0}),
             (None, None, 'fc26', None, {DepthLevel: 0})],
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
    list_of_vectors, expected_list, expected_change
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
def test_aggregate(vectors, expected, monkeypatch):
    _mock_merge_wrapper = MagicMock(return_value={'merged options': None})
    monkeypatch.setattr(
        'stdci_libs.nested_config._merge_options_wrapper', _mock_merge_wrapper
    )
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
            [(None, None, {'o1': ['ov1', 'ov1.2'], 'repos': 'ov2', DepthLevel: 1}),],
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
def test_gen_vectors(data_in, categories, expected, monkeypatch):
    def _mock_merge_wrapper(a, b ,c):
        return mock_merge_options(b, c)
    monkeypatch.setattr(
        'stdci_libs.nested_config._merge_options_wrapper', _mock_merge_wrapper
    )
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
def test_merge_vectors(vector1, vector2, expected, monkeypatch):
    mock_merge_options = MagicMock(return_value={'merged options': None})
    monkeypatch.setattr(
        'stdci_libs.nested_config._merge_options_wrapper', mock_merge_options
    )
    assert _merge_vectors(vector1, vector2, mock_merge_options) == expected


@pytest.mark.parametrize(
    "first,second",
    [
        (
            ('cat1', None, {DepthLevel: 0, 'first': 1}),
            ('cat1', None, {DepthLevel: 1, 'second': 1}),
        ),
        (
            ('cat1', None, {DepthLevel: 0, 'first': 1}),
            (None, 'cat2', {DepthLevel: 0, 'second': 1}),
        ),
        (
            ('cat1', None, {DepthLevel: 0, 'first': 1}),
            ('cat1', 'cat2', {DepthLevel: 0, 'second': 1}),
        ),
        (
            ('cat1', None, {DepthLevel: 0, 'first': 1}),
            (None, 'cat2', {DepthLevel: 0, 'second': 1}),
        ),
        (
            ('cat1', None, 'cat3', {DepthLevel: 0, 'first': 1}),
            (None, 'cat2', 'cat3', {DepthLevel: 0, 'second': 1}),
        ),
        (
            ('cat1', None, 'cat3', {DepthLevel: 0, 'first': 1}),
            ('cat1.1', None, 'cat3.1', {DepthLevel: 0, 'second': 1}),
        ),
    ]
)
def test_merge_options_wrapper(first, second, monkeypatch):
    merge_options = MagicMock(return_value='RETURNED')
    out = _merge_options_wrapper(merge_options, first, second)
    assert out == 'RETURNED'
    assert merge_options.call_args == call(first[-1], second[-1])


def test_merge_options_dfs_calls(monkeypatch):
    mock_merge_options = MagicMock(return_value={'merged options': None})
    monkeypatch.setattr(
        'stdci_libs.nested_config._merge_options_wrapper', mock_merge_options
    )
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
    assert list(
        _dfs(simple_data, ('stage', 'distro'), mock_merge_options)
    ) == [('check-patch', 'el7', {'merged options': None})]
    calls = [
        call(
            mock_merge_options,
            (None, 'el7', {DepthLevel: 2, 'packages': 'p'}),
            (None, None, {DepthLevel: 3, 'packages': 'pdepth'}))
    ]
    mock_merge_options.assert_has_calls(calls, any_order=False)
    assert mock_merge_options.call_count == 2
