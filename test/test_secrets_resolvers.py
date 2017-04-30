import pytest
from scripts.secrets_resolvers import (
    ci_secrets_file_resolver,
    filter_secret_data,
)


@pytest.fixture
def secret_data():
    return [
        {'name': 'ovirt-secret_1',
         'project': 'secrets',
         'branch': 'master',
         'secret_data': {'password': 'pass', 'username': 'user'}},
        {'name': 'ovirt-secret_2',
         'project': 'foo',
         'branch': 'master',
         'secret_data': {'password': 'pass', 'username': 'user'}},
        {'name': 'ovirt-secret_3',
         'project': 'secrets',
         'branch': 'foo',
         'secret_data': {'password': 'pass', 'username': 'user'}},
        {'name': 'ovirt-secret_4',
         'project': 'secrets',
         'branch': 'foo',
         'secret_data': {'password': 'pass', 'username': 'user'}},
        {'name': 'ovirt-secret_*',
         'secret_data': {'password': 'pass', 'username': 'user'}}
    ]

@pytest.mark.parametrize(
    "user_request,expected",
    [('ovirt-secret_1', {'password': 'pass', 'username': 'user'}),
     ('ovirt-secret_RGX', {'password': 'pass', 'username': 'user'})],
)
def test_ci_secret_file_resolver(user_request, expected, secret_data):
    assert ci_secrets_file_resolver(
        secret_data, user_request
    ) == expected


@pytest.mark.parametrize(
    "user_request,exception",
    [('', RuntimeError)]
)
def test_ci_secret_file_resolver_exceptions(user_request, exception, secret_data):
    with pytest.raises(exception):
        ci_secrets_file_resolver(secret_data, user_request)


@pytest.fixture
def expected_filtered_secret_data():
    return [
        {'name': 'ovirt-secret_1',
         'project': 'secrets',
         'branch': 'master',
         'secret_data': {'password': 'pass', 'username': 'user'}},
        {'name': 'ovirt-secret_*',
         'secret_data': {'password': 'pass', 'username': 'user'}}
    ]
def test_filter_secret_data(secret_data, expected_filtered_secret_data):
    assert list(filter_secret_data("secrets", "master", secret_data)) \
           == expected_filtered_secret_data
