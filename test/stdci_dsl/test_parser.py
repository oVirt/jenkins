#!/bin/env python

import pytest
from scripts.stdci_dsl.parser import (
    normalize_config_values, normalize_config_keys
)


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            {},
            {}
        ),
        (
            {'some-key': ['v-1', 'v-2']},
            {'somekey': ['v-1', 'v-2']}
        ),
        (
            {'some_key': 'x86_64'},
            {'somekey': 'x86_64'}
        ),
        (
            {'some_key': {'nested_key': 'some-value'}},
            {'somekey': {'nestedkey': 'some-value'}}
        ),
        (
            {'some_key': {'nested-key': ['v-1', 'v-2', 'v_3']}},
            {'somekey': {'nestedkey': ['v-1', 'v-2', 'v_3']}}
        ),
        (
            {'some_key': [{'nested-key': 'v-1'}, 'nested-value']},
            {'somekey': [{'nestedkey': 'v-1'}, 'nested-value']}
        ),
        (
            {'some_key':
             [{'nested-key': ['v-1', 'v-2', {'nested-key2': 'v-1.2'}]}]},
            {'somekey':
             [{'nestedkey': ['v-1', 'v-2', {'nestedkey2': 'v-1.2'}]}]}
        ),
        (
            ['v-1', 'v-2'],
            ['v-1', 'v-2'],
        ),
        (
            'v-1',
            'v-1',
        ),
    ]
)
def test_normalize_config_values(data, expected):
    out = normalize_config_values('', data)
    assert out == expected


@pytest.mark.parametrize(
    "key,expected",
    [
        ('distro', 'distro'),
        ('disTros', 'distro'),
        ('distribution', 'distro'),
        ('diStributions', 'distro'),
        ('OS', 'distro'),
        ('operatingSystem', 'distro'),
        ('operating_systems', 'distro'),
        ('ARCH', 'arch'),
        ('architeCture', 'arch'),
        ('ARCHITECTURES', 'arch'),
        ('staGe', 'stage'),
        ('stages', 'stage'),
        ('subStage', 'substage'),
        ('sub_stages', 'substage'),
    ]
)
def test_config_keys(key, expected):
    out = normalize_config_keys(key)
    assert out == expected
