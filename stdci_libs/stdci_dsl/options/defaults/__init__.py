#!/bin/env python
"""stdci.options.defaults - Get and apply default option values
"""

from __future__ import absolute_import
import os
import logging
from six.moves import map
from six import string_types
from itertools import tee
from copy import copy
from .values import DEFAULT_VALUES, DefaultValue


logger = logging.getLogger(__name__)


def apply_default_options(threads):
    """Apply default option values on iterable of JobThread instances.
    Default option values will be set only for options that were not pre defined
    by the user.

    :param Iterable threads: Iterable of JobThread instances to set defaults

    :rtype: Iterator
    :returns: Iterator over JobThread instances with default options values set
    """
    return map(_apply_default_options, threads)


def _apply_default_options(thread):
    """Apply default option values for a given job thread object.
    Default option values will be set only for options that were not defined by
    the user. This method will not overwrite user's definitions.

    :param JobThread thread: JobThread instance to set default options.

    :rtype: JobThread
    :returns: JobThread object with default options values set.
    """
    if thread.substage != 'default':
        defaults_type = 'user_specified_substage'
    else:
        defaults_type = 'default_substage'
    options = copy(DEFAULT_VALUES[defaults_type])
    options.update(thread.options)
    if 'ignore_if_missing_script' not in options:
        if isinstance(options['script'], string_types):
            # If script was specified inline
            options['ignore_if_missing_script'] = False
        else:
            options['ignore_if_missing_script'] = DefaultValue in options['script']

    return thread.with_modified(options=options)
