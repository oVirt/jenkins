#!/bin/env python
"""globals.py - Get global options config for JobThread objects
"""

from itertools import tee


GLOBAL_OPTIONS = ('releasebranches', 'upstreamsources',)


def apply_global_options(threads):
    """Set global option config on a given iterable of threads

    :param Iterable threads: Iterable of JobThread instances

    :rtype: Iterator
    :returns: Iterator over JobThread instances with global options set
    """
    get_options_it, set_options_it = tee(threads)
    global_options = _get_global_options(get_options_it)
    return (
        thread.with_modified(
            options=thread.options.update(global_options)
        ) for thread in set_options_it
    )


def _get_global_options(threads):
    """Iterate over given job_threads and extract global options config

    :param Iterable job_threads: Iterable of job_threads

    :rtype: dict
    :returns: Global options config to apply on all job_threads
    """
    global_config = {}
    for thread in threads:
        for global_option in GLOBAL_OPTIONS:
            if global_option in thread.options:
                global_config[global_option] = thread.options[global_option]
    return global_config
