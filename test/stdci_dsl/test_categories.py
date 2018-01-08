#!/bin/env python

import pytest
from scripts.stdci_dsl.categories import apply_default_categories
from scripts.stdci_dsl.job_thread import JobThread


@pytest.mark.parametrize(
    "vectors,expected",
    [
        (
            [],
            []
        ),
        (
            [JobThread(None, None, None, None, {})],
            [JobThread('check-patch', 'default', 'el7', 'x86_64', {})]
        ),
        (
            [
                JobThread(None, 'substage', 'distro', 'arch', {}),
                JobThread('stage', None, 'distro', 'arch', {}),
                JobThread('stage', 'substage', None, 'arch', {}),
                JobThread('stage', 'substage', 'arch', None, {}),
            ],
            [
                JobThread('check-patch', 'substage', 'distro', 'arch', {}),
                JobThread('stage', 'default', 'distro', 'arch', {}),
                JobThread('stage', 'substage', 'el7', 'arch', {}),
                JobThread('stage', 'substage', 'arch', 'x86_64', {}),
            ],
        ),
        (
            [JobThread('stage', 'substage', 'distro', 'arch', {'opts': 'v'})],
            [JobThread('stage', 'substage', 'distro', 'arch', {'opts': 'v'})],
        ),
    ]
)
def test_apply_default_categories(vectors, expected):
    assert list(apply_default_categories(vectors, 'check-patch')) == expected