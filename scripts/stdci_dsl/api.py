#!/bin/env python

from __future__ import absolute_import
from itertools import chain
import logging
from six.moves import filter
from yaml import safe_dump

from .parser import stdci_parse
from .categories import apply_default_categories
from .options.defaults import apply_default_options
from .options.globals import apply_global_options, _get_global_options
from .options.parser_utils import get_merged_options
from .options.normalize import normalize


logger = logging.getLogger(__name__)


class ConfigurationNotFound(Exception):
    pass


class FormatterNotFoundError(Exception):
    pass


class UnknownFileSource(Exception):
    pass


def get_threads(project, stage):
    """Parse stdci config for the given project and get relevant thread for the
    given stage.

    :param str project: Path to stdci project's root directory.
    :param str stage:   stdci stage.

    :rtype: Iterator
    :returns: Iterator over JobThread instances for the the current project and
              stage.
    """
    logger.info("Generating thread objects for project: %s", project)
    all_threads = stdci_parse(project)
    threads_for_current_stage = (
        thread for thread in all_threads
        if thread.stage is None or thread.stage == stage
    )
    threads_with_default_categories = \
        apply_default_categories(threads_for_current_stage, stage)
    threads_with_global_options = \
        apply_global_options(threads_with_default_categories)
    threads_with_default_options = \
        apply_default_options(threads_with_global_options)
    return normalize(project, threads_with_default_options)


def get_formatted_threads(fmt, project, stage):
    """Generate stdci thread objects for a given stage and format the data

    :param str fmt:     Points separated string where the first part is the
                        name of the formatter and the second part is a template
                        or argument for the formatter (second part is optional)
                        Example: "my_formatter:{{ t1 }}.{{ t2 }}"
    :param str project: Path to STDCI project's root directory.
    :param str stage:   STDCI stage.
    """
    fmt_name, _, template = fmt.partition(':')
    # formatters are functions that follow this convention:
    # _{formatter name}_formatter(threads, template)
    formatter = globals().get('_{0}_formatter'.format(fmt_name), None)
    if formatter is None:
        raise FormatterNotFoundError(
            'Could not resolve formatter name {0}.'.format(fmt_name)
        )
    threads = get_threads(project, stage)
    return formatter(threads, template)


def _pipeline_dict_formatter(threads, template=None):
    """Format vectors data into pipeline dict

    :param Iterable vectors: Iterable of JobThread objects
    :param str template:     Format template
                             (currently unused in this formatter)

    :rtype: str
    :returns: yaml config with vectors data from $vectors
    """
    sample_thread = next(threads, None)
    if not sample_thread:
        return ''
    data = {}
    data['global_config'] = {
        'runtime_reqs': sample_thread.options['runtime_requirements'],
        'release_branches': sample_thread.options['release_branches'],
        'upstream_sources': sample_thread.options['upstream_sources'],
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
        } for thread in chain([sample_thread], threads)
    ]
    return safe_dump(data, default_flow_style=False)


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it
    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = level
