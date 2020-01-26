#!/usr/bin/env python
"""resolver_base.py - Base classes for value resolvers used by ci_env_client
"""


class ResolverKeyError(RuntimeError):
    """Exception class for indicating the resolver has no value for the given
    key

    This intentionally does not inherit from KeyError so exception handlers
    will not mix the two
    """
