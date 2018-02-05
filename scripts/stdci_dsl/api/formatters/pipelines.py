#!/bin/env python
"""pipelines.py - Set of data formatters for stdci pipelines"""

import logging
from itertools import chain
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
        logger.debug('Registered pipelines data formatter: %s', name)
        return function
    return wrapper


@formatter('pipeline_dict')
def _pipeline_dict_formatter(threads, global_options, template=None):
    """Format vectors data into pipeline dict

    :param Iterable vectors:     Iterable of JobThread objects
    :param dict global_options : Global options config
    :param str template:     Format template
                             (currently unused in this formatter)

    :rtype: str
    :returns: yaml config with vectors data from $vectors
    """
    data = {}
    data['global_config'] = {
        'runtime_reqs': global_options['runtime_requirements'],
        'release_branches': global_options['release_branches'],
        'upstream_sources': global_options['upstream_sources']
    }
    data['jobs'] = [
        {
            'stage': thread.stage,
            'substage': thread.substage,
            'distro': thread.distro,
            'arch': thread.arch,
            'script': str(thread.options['script']),
            'runtime_reqs': thread.options['runtime_requirements'],
            'release_branches': thread.options['release_branches'],
        } for thread in threads
    ]
    return safe_dump(data, default_flow_style=False)
