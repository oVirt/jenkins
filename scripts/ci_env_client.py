#!/usr/bin/env python
"""ci_env_client.py - Client to generate environmental variables for STD CI
"""
from six import iteritems
from functools import partial
from difflib import get_close_matches
try:
    from secrets_resolvers import ci_secrets_file_resolver, load_secret_data
    from gdbm_db_resolvers import  gdbm_resolver
except ImportError:
    from scripts.secrets_resolvers import (
        ci_secrets_file_resolver, load_secret_data
    )
    from scripts.gdbm_db_resolvers import gdbm_resolver


def gen_env_vars_from_requests(requests, providers):
    """Generate a dictionary of var_name:value from a given requests file
    A requests file is a yaml file with the following structure:
        - name: 'var_name'
            valueFrom:
                secretProvider:
                    name: 'requested secret name'
                    key: 'requested key from the secret'
        - name: 'var_name2'
            value: 'specified value'
        - name: 'var_name3'
            valueFrom:
                environ:
                    name: 'env var name'

    :param list requests:  A list with user's requests
    :param dict providers: A dictionary with available providers to serve user
                           requests.

    :rtype: dict
    :returns: A dictionary of {var_name(s): value(s)}, where value is extracted
              from secrets file per user's request or specified in the request.
    """
    return dict([serve_request(request, providers) for request in requests])


def serve_request(request, providers):
    """Parse request and return the required secret and key

    :param dict request:    A valid request
    :param dict providers:  Dict of available secret providers

    :rtype: pair
    :returns: A tuple of (env_var_name, value) where value is extracted from
              the secret file or specified in the request.
    """
    try:
        var_name = request['name']
    except KeyError:
        raise RuntimeError(
            "[ENV_CLIENT] Invalid request: 'name' was not specified"
        )
    if 'value' in request:
        return var_name, str(request['value'])
    try:
        req_provider, req_data = next(iteritems(request['valueFrom']))
    except (KeyError, StopIteration):
        raise RuntimeError("[ENV_CLIENT] Invalid request {0}".format(var_name))
    try:
        return var_name, str(providers[req_provider](req_data))
    except KeyError:
        raise RuntimeError(
            "[ENV_CLIENT] Could not find provider: {0}. Did you mean: {1}?"
            .format(
                req_provider, get_close_matches(req_provider, providers.keys())
            )
        )


def secret_key_ref_provider(resolver, request):
    """Provide secret data by secret key reference

    :param function resolver:    A resolver function to resolve secret data
    :param dict request:         A request for secret data {name: , key:}

    :rtype: str
    :returns: The requested data.
    """
    try:
        # Try to get matching secret from the resolver
        req_secret = resolver(request['name'])
    except KeyError:
        raise RuntimeError("[ENV_CLIENT] Secret name must be specified.")
    try:
        data = req_secret[request['key']]
    except KeyError:
        # Check if the requested key is available in the secret
        raise RuntimeError("[ENV_CLIENT] No such key: {0} in secret: {1}"
                           .format(request['key'], request['name']))
    return data


def load_providers(dbm_db, secret_data=None):
    """A dictionary of all available secret providers

    :param str dbm_db:      Path to dbm database from which we
                            provide data.
    :param str secret_data: (optional) Path to ci secrets file from which we
                            provide data.
                            Default: ${xdg_config_home}/ci_secrets_file.yaml

    :rtype: dict
    :returns: A dict of all available providers, loaded with the relevant data
    """
    return {
        'secretKeyRef': partial(
            secret_key_ref_provider, partial(
                ci_secrets_file_resolver, load_secret_data(secret_data)
            )
        ),
        'runtimeEnv': gdbm_resolver(dbm_db)
    }
