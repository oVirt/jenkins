#!/bin/env python
"""test_base.py - Tests of the options base classes and utilities
"""
import pytest
try:
    from unittest.mock import MagicMock, create_autospec, sentinel, call
except ImportError:
    from mock import MagicMock, create_autospec, sentinel, call

from scripts.struct_normalizer import normalize_value, DataNormalizationError
from scripts.stdci_dsl.options import base
from scripts.stdci_dsl.options.base import (
    render_template, template_string, map_with_cased_keys
)
from scripts.stdci_dsl.job_thread import JobThread


@pytest.mark.parametrize(
    "thread,templates,expected",
    [
        (
            JobThread('check-patch', 'default', 'el7', 'x86_64', {}),
            '{{ stage }}.{{ substage }}.{{ distro }}.{{ arch }}',
            'check-patch.default.el7.x86_64'
        )
    ]
)
def test_render_template(thread, templates, expected):
    out = render_template(thread, templates)
    assert out == expected


@pytest.fixture
def a_thread():
    return JobThread('stg', 'subst', 'dist', 'arc', {})


@pytest.mark.parametrize('else_,value,expected', [
    ('terr1', 1, '1'),
    ('terr2', 't2', 't2'),
    ('terr3', ['t3', 't13', 't23'], DataNormalizationError('terr3')),
    ('terr4', {'t4': 4}, DataNormalizationError('terr4')),
])
def test_template_string(monkeypatch, a_thread, else_, value, expected):
    _render_template = create_autospec(render_template)
    monkeypatch.setattr(base, 'render_template', _render_template)
    if isinstance(expected, Exception):
        with pytest.raises(expected.__class__):
            normalize_value(a_thread, value, to=template_string(else_=else_))
    else:
        result = \
            normalize_value(a_thread, value, to=template_string(else_=else_))
        result.mark('rendered')
        assert _render_template.mock_calls == [
            call(a_thread, expected),
            call(a_thread, expected).mark('rendered'),
        ]


def test_map_with_cased_keys(a_thread):
    def normfun(thread, value):
        return getattr(sentinel, value)

    options = {
        'FirstKey': normfun,
        'SecondKey': normfun,
        'thirdkey': normfun,
    }
    input_map = {
        'firstkey': 'first_value',
        'thirdkey': 'third_value',
    }
    expected = {
        'FirstKey': sentinel.first_value,
        'thirdkey': sentinel.third_value,
    }
    out = \
        normalize_value(a_thread, input_map, to=map_with_cased_keys(**options))
    assert out == expected
