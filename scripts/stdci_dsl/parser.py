#!/bin/env python
"""stdci_config.py - Read and parse stdci config and generate JobThread objects
"""

from contextlib import contextmanager
import os
import logging
from six import string_types
from yaml import safe_load
from scripts.nested_config import gen_vectors
from scripts.stdci_dsl.options.parser_utils import get_merged_options
from scripts.stdci_dsl.job_thread import JobThread, STDCI_CATEGORIES


logger = logging.getLogger(__name__)
CONFIG_FILES = (
    'automation.yaml', 'automation.yml', '.automation.yaml', '.automation.yml',
)


def stdci_parse(project):
    """Parse stdci config and generate JobThread objects

    :param str project: Path to project directory

    :rtype: Iterator
    :returns: Iterator over JobThead objects
    """
    with stdci_load(project, CONFIG_FILES) as cfg_fd:
        stdci_conf = safe_load(cfg_fd)

    return (
        JobThread(*v) for v in
        gen_vectors(stdci_conf, get_merged_options, STDCI_CATEGORIES)
    )


class ConfigurationNotFoundError(Exception):
    pass


@contextmanager
def stdci_load(sdir, files, flag=None):
    """Open fd to the first matching stdci config.

    :param str sdir:       Source directory where we search config files in.
    :param Iterable files: Iterable over potential config file names.
    :param str flag:       Flag to pass to open() builtin
                           (r, r+, w, ... )

    :rtupe: file
    :returns: File descriptor to the first existing stdci config.
    """
    if isinstance(files, string_types):
        files = [files]
    flag = 'r' if flag is None else flag
    for file_ in files:
        try:
            with open(os.path.join(sdir, file_), flag) as rf:
                yield rf
                return
        except IOError:
            pass
    raise ConfigurationNotFoundError('Could not find a valid config')
