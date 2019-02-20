"""test_tree_checksum.py - Unit tests for tree_checksun.py
"""
from __future__ import (absolute_import, division, print_function)
from hashlib import sha256

from tree_checksum import calculate_tree_checksum


def test_calculate_tree_checksum(tmpdir):
    files = (
        ('dirA/fileA1.txt', 'Some more file contents\n'),
        ('dirA/fileA2.txt', 'Even more file ontents'),
        ('dirB/dirC/fileC1.txt', 'More stuff\nin a file\n'),
        ('dirB/fileB1.txt', 'Stuff that also\ngoes in a file'),
        ('file1.txt', 'Some file content\n'),
    )
    locations = [
        'some_location', 'another_location', 'deeply/neste/location',
    ]
    expected_calc = sha256()
    for pth, fil in files:
        expected_calc.update(pth.encode())
        expected_calc.update(fil.encode())
    expected_digest = expected_calc.hexdigest()
    for loc in locations:
        for pth, fil in files:
            fil_path = tmpdir / loc / pth
            fil_path.write_binary(fil.encode(), ensure=True)
    for loc in locations:
        loc_pth = tmpdir / loc
        out = calculate_tree_checksum(str(loc_pth), sha256)
        assert out == expected_digest
