#!/bin/env python
"""runners.py - Set of data formatters for stdci runners"""

import logging
from yaml import safe_dump


_formatters = {}
logger = logging.getLogger(__name__)


class FormatterNotFoundError(Exception):
    pass


def get_formatter(formatter_name):
    """Given formatter name, return formatter function

    :param str formatter_name: Name of the required formatter

    :rtype: function
    :returns: Formatter function
    """
    formatter_ = _formatters.get(formatter_name, None)
    if formatter_ is None:
        raise FormatterNotFoundError(
            'Could not find formatter_: {0}'.format(formatter_name)
        )
    return formatter_


def formatter(name):
    """Decorator function for formatter registration"""
    def wrapper(function):
        _formatters[name] = function
        logger.debug('Registered runner data formatter: %s', name)
        return function
    return wrapper


@formatter('yaml_dumper')
def _dump_to_yaml_formatter(obj, template=None):
    # TODO: use dict comprehension as soon as python 2.6 support is dropped
    repos_fmt = {}
    for repo_name, repo_url in obj.repos:
        repos_fmt[repo_name] = repo_url

    mounts_fmt = {}
    for src, dst in obj.mounts:
        mounts_fmt[src] = dst
    yumrepos_fmt = '' if obj.yumrepos is None else obj.yumrepos

    data = {
        'script': str(obj.script),
        'yumrepos': yumrepos_fmt,
        'environment': obj.environment,
        'mounts': mounts_fmt,
        'repos': repos_fmt,
        'hash': obj.hash,
        'packages': obj.packages
    }
    return safe_dump(data, default_flow_style=False)
