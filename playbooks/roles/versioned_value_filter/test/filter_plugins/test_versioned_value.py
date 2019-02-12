#!/usr/bin/python

"""test_versioned_value.py - Unit tests for versioned_value.py
"""
import pytest
from ansible import errors
from versioned_value import versioned_value


@pytest.mark.parametrize("dict_input, version_input, expected", [
    (
        {
            'v3.6.0': 'authorization.openshift.io/v1',
            'v3.9.0': 'rbac.authorization.k8s.io/v1',
        },
        'v3.6.0',
        'authorization.openshift.io/v1'
    ),
    (
        {
            'v3.6.0': 'authorization.openshift.io/v1',
            'v3.9.0': 'rbac.authorization.k8s.io/v1'
        },
        'v3.9.0',
        'rbac.authorization.k8s.io/v1'
    ),
    (
        {
            'v3.6.0': 'authorization.openshift.io/v1',
            'v3.9.0': 'rbac.authorization.k8s.io/v1'
        },
        'v3.11.0',
        'rbac.authorization.k8s.io/v1'
    ),
    (
        {
            'v3.6.0': 'authorization.openshift.io/v1',
            'v3.9.0': 'rbac.authorization.k8s.io/v1'
        },
        'v3.7.0', 'authorization.openshift.io/v1'
    ),
])
def test_versioned_value(dict_input, version_input, expected):
    assert versioned_value(dict_input, version_input) == expected


@pytest.mark.parametrize("dict_input, version_input", [
    (
        {},
        'v0.0.0'
    ),
    (
        3,
        'v0.3.0'
    ),
    (
        'hello world',
        'v7.0.0'
    ),
    (
        {
            'v3.6.0': 'authorization.openshift.io/v1',
            'v3.9.0': 'rbac.authorization.k8s.io/v1'
        },
        'v3.5.0'
    )
])
def test_versioned_value_exceptions(dict_input, version_input):
    with pytest.raises(errors.AnsibleFilterError):
        versioned_value(dict_input, version_input)
