#!/usr/bin/env python
"""test_ci_env_client.py - Tests for secrets_file.py
"""
import pytest
from scripts import ci_env_client
from scripts.ci_env_client import (
    serve_request,
    secret_key_ref_provider,
    gen_env_vars_from_requests,
)
from scripts.resolver_base import ResolverKeyError
try:
    from mock import MagicMock, call
except ImportError:
    from unittest.mock import MagicMock, call


def test_secret_key_ref_provider_no_such_secret():
    user_request = {'name': 'secret'}
    mock_resolver = MagicMock()
    mock_resolver.side_effect = KeyError
    with pytest.raises(RuntimeError):
        secret_key_ref_provider(mock_resolver, user_request)
    try:
        mock_resolver.assert_called_with(user_request['name'])
    except KeyError:
        pass


def test_secret_key_ref_provider_no_such_key():
    user_request = {'name': 'secret', 'key': 'username'}
    mock_resolver = MagicMock(return_value={'password': 1234})
    with pytest.raises(RuntimeError):
        secret_key_ref_provider(mock_resolver, user_request)


def test_secret_key_ref_provider():
    user_request = {'name': 'secret', 'key': 'password'}
    mock_resolver = MagicMock(return_value={'password': 1234})
    assert secret_key_ref_provider(mock_resolver, user_request) == 1234
    mock_resolver.assert_called_with('secret')


@pytest.mark.parametrize('request_,expected', [
    (
        {'name': 'VAR', 'value': 'VAL'},
        ('VAR', 'VAL')
    ),
    (
        {'name': 'VAR'},
        RuntimeError
    ),
    (
        {'value': 'VAL'},
        RuntimeError
    ),
    (
        {'name': 'VAR', 'valueFrom': {'dummy': '*key*'}},
        ('VAR', '*value*')
    ),
    (
        {'name': 'VAR', 'valueFrom': {'no_such_prov': '*key*'}},
        RuntimeError
    ),
    (
        {'name': 'VAR', 'valueFrom': {'dummy': 'no_key'}},
        RuntimeError
    ),
    (
        {'name': 'VAR', 'valueFrom': {'dummy': 'no_key'}, 'default': 'DEF'},
        ('VAR', 'DEF')
    ),
    (
        {'name': 'VAR', 'valueFrom': {'dummy': 'no_key'}, 'optional': True},
        None
    ),
    (
        {'name': 'VAR', 'valueFrom': {'dummy': 'no_key'}, 'optional': False},
        RuntimeError
    ),
    (
        {
            'name': 'VAR', 'valueFrom': {'dummy': 'no_key'},
            'optional': False, 'default': 'DEF'
        },
        RuntimeError
    ),
    (
        {
            'name': 'VAR', 'valueFrom': {'dummy': 'no_key'},
            'optional': True, 'default': 'DEF'
        },
        ('VAR', 'DEF')
    ),
])
def test_serve_request(request_, expected):
    def provider(key):
        if key == '*key*':
            return '*value*'
        else:
            raise ResolverKeyError

    providers = {'dummy': provider}
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            serve_request(request_, providers)
    else:
        out = serve_request(request_, providers)
        assert out == expected


def test_serve_specified_request():
    mock_provider = MagicMock(return_value='password')
    providers = {'secretKeyRef': mock_provider}
    user_request = {'name': 'VAR', 'value': 'Value'}
    assert serve_request(user_request, providers) == ('VAR', 'Value')


def test_gen_env_vars_from_requests(monkeypatch):
    pairs = list(zip('abc', '123'))
    serve_request = MagicMock(side_effect=pairs)
    monkeypatch.setattr(ci_env_client, 'serve_request', serve_request)
    requests = 'DEF'
    providers = '__providers__'
    expected = dict(pairs)
    out = gen_env_vars_from_requests(requests, providers)
    assert out == expected
    assert serve_request.call_count == len(requests)
    assert serve_request.call_args_list == [
        call(r, providers) for r in requests
    ]


def test_gen_env_vars_from_requests_with_nulls(monkeypatch):
    pairs = list(zip('abc', '123'))
    pairs_with_nulls = list(pairs)
    pairs_with_nulls.insert(1, None)
    pairs_with_nulls.append(None)
    serve_request = MagicMock(side_effect=pairs_with_nulls)
    monkeypatch.setattr(ci_env_client, 'serve_request', serve_request)
    requests = 'DEFGH'
    providers = '__providers__'
    expected = dict(pairs)
    out = gen_env_vars_from_requests(requests, providers)
    assert out == expected
    assert serve_request.call_count == len(requests)
    assert serve_request.call_args_list == [
        call(r, providers) for r in requests
    ]
