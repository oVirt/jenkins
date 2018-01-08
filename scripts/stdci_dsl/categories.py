#!/bin/env python
"""categories.py - This module holds the default set of categories for all stdci
modules to use and a function to apply default category values on a given
list of JobThread objects."""

from scripts.stdci_dsl.job_thread import JobThread


def apply_default_categories(threads, current_stage=None):
    """Apply default values for categories in a given list of JobThread objects

    :param Iterable threads: Iterable of threads to set default values for.
    :param str current_stage:    Current stage we process threads for.

    :rtype: Iterator
    :returns: Iterator over a new list of threads whith default categories set.
    """
    return (
        JobThread(
            stage=thread.stage if thread.stage is not None else current_stage,
            substage=thread.substage if thread.substage is not None else 'default',
            distro=thread.distro if thread.distro is not None else 'el7',
            arch=thread.arch if thread.arch is not None else 'x86_64',
            options=thread.options
        ) for thread in threads
    )
