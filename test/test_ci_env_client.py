#!/usr/bin/env python
"""test_ci_env_client.py - Tests for secrets_file.py
"""
import pytest
from scripts.ci_env_client import (
    serve_request,
    secret_key_ref_provider,
)
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


@pytest.mark.parametrize(
    "user_request,exception",
    [({} , RuntimeError),
     ({'name': 'VAR', 'valueFrom': {'nonExistingPrvdr': {'key': 'username'}}}, RuntimeError),
     ({'name': 'VAR1', '': {'secretKeyRef': {'key': 'username'}}},RuntimeError)]
)
def test_serve_request_exceptions(user_request, exception):
    mock_provider = MagicMock(return_value='password')
    mock_load_providers = MagicMock(return_value={'secretKeyRef':mock_provider})
    with pytest.raises(exception):
        serve_request(user_request, mock_load_providers())


def test_serve_specified_request():
    mock_provider = MagicMock(return_value='password')
    providers = {'secretKeyRef': mock_provider}
    user_request = {'name': 'VAR', 'value': 'Value'}
    assert serve_request(user_request, providers) == ('VAR', 'Value')
