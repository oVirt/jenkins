#!/usr/bin/env python
"""gdbm_db_resolvers.py - Resolver to resolve .dbm db that represents `environ`
"""
from six.moves import dbm_gnu as dbm, filter
from six import iteritems
from contextlib import contextmanager
from os import environ
from re import match
import argparse


try:
    from resolver_base import ResolverKeyError
except ImportError:
    from stdci_libs.resolver_base import ResolverKeyError


class gdbm_resolver:
    def __init__(self, database_path):
        self._database = dbm.open(database_path, 'c')

    def __del__(self):
        self._database.close()

    def __call__(self, request):
        try:
            return (self._database[request.encode('utf-8')]).decode('utf-8')
        except KeyError:
            raise ResolverKeyError(
                "[DBM_RESOLVER] No such key {0} in env runtime."
                .format(request)
            )


def main():
    database_file_path = parse_args()
    gen_gdbm_from_dict(database_file_path)


def parse_args():
    """Parse positional arguments and return their values"""
    parser = argparse.ArgumentParser(
        description="Generate filtered dbm database from environ"
    )
    parser.add_argument(
        "database",
        help=("Path that points to the location where the dbm db will be"
              " generated")
    )
    args = parser.parse_args()
    return args.database


def gen_gdbm_from_dict(database_file_path, dict_=None):
    """Generate dbm database from a given dict

    :param str database_file_path: Path that points to the location where the
                                   dbm database will be generated.
                                   Note that if the file exists, it will be
                                   overwritten.
    :param dict dict_:               A dict from which to generate gdbm database
    """
    if dict_ is None:
        dict_ = environ
    with _gdbm_open(database_file_path, 'c') as db:
        for key, value in filter(is_key_safe, iteritems(dict_)):
            db[key] = value
        db.sync()


def is_key_safe(pair):
    """Check if key is sensitive - check if key is a function or has a '_'
    prefix

    :param tuple pair: A pair of (key, value) where key's sensitivity will be
                       checked.

    :rtype: bool
    :returns: True if key is safe for injection, False otherwise
    """
    key, _ = pair
    return not bool(match(r'(^_.*|^BASH_FUNC_.*)', key))


@contextmanager
def _gdbm_open(path, flag='r', mode=0o666):
    """Make sure we close the database after updating the input.
    This context manager is actually a wrapper around dbm.open and it accepts
    the same arguments.
    :param str path:  Path where to open the database
    :param str flag:  Mode in which we open the database (r,w,c,n)
    """
    try:
        database = dbm.open(path, flag, mode)
        yield database
    finally:
        try:
            database.close()
        except NameError:
            # Don't fail if database was never opened
            pass


if __name__ == "__main__":
    main()
