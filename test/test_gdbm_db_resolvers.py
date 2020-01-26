#!/user/bin/env python
"""test_gdbm_db_resolvers.py - Tests for gdbm_db_resolvers.py
"""
import pytest
from stdci_libs.gdbm_db_resolvers import (
    gdbm_resolver, is_key_safe, gen_gdbm_from_dict
)
from stdci_libs.resolver_base import ResolverKeyError


@pytest.fixture
def database_fixture():
    return {'var': '1234'}


@pytest.mark.parametrize(
    "key,sensitivity",
    [('_SENSITIVE', False),
     ('BASH_FUNC_', False),
     ('NON_SENSITIVE', True)]
)
def test_is_key_safe(key, sensitivity):
    assert is_key_safe((key, '')) is sensitivity


def test_gdbm_resolver(database_fixture, tmpdir):
    database_path = str(tmpdir.join("test_dbm.dbm"))
    gen_gdbm_from_dict(database_path, database_fixture)
    resolver = gdbm_resolver(database_path)
    assert resolver('var') == '1234'
    with pytest.raises(ResolverKeyError):
        resolver('no such key')
