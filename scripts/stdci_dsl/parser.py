#!/bin/env python
"""stdci_config.py - Read and parse stdci config and generate JobThread objects
"""

from __future__ import absolute_import
from contextlib import contextmanager
import os
import logging
from six import string_types, iteritems
from collections import Mapping, Iterable
from itertools import product
from yaml import safe_load
from .options.parser_utils import get_merged_options
from .job_thread import JobThread, STDCI_CATEGORIES
from ..nested_config import gen_vectors


logger = logging.getLogger(__name__)

# The order of the constants blow matters. It affects the order in which we
# search ci configurations.
PREFIXES = ('', '.')
FILE_NAMES = ('seaci', 'stdci', 'automation', 'ovirtci')
SUFFIXES = ('.yaml', '.yml')
CONFIG_FILES = [''.join(c) for c in product(PREFIXES, FILE_NAMES, SUFFIXES)]


def stdci_parse(project):
    """Parse stdci config and generate JobThread objects

    :param str project: Path to project directory

    :rtype: Iterator
    :returns: Iterator over JobThead objects
    """
    try:
        with stdci_load(project, CONFIG_FILES) as cfg_fd:
            stdci_conf = safe_load(cfg_fd)
    except ConfigurationNotFoundError:
        # In case the configuration was not found, fallback to the empty config
        stdci_conf = {}

    return (
        JobThread(*v) for v in
        gen_vectors(
            data_in=stdci_conf,
            merge_options=get_merged_options,
            categories=STDCI_CATEGORIES,
            normalize_keys=normalize_config_keys,
            normalize_values=normalize_config_values,
        )
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


def normalize_config_values(key, data):
    """If the data is a key in the config (mapping keys), send all the keys to
    remove_case_and_signs recursively for normalization.

    :param str key: The config key where $data is the value. (currently unused)
    :param data:    Data to normalize.

    :returns: If data is a map, return the same map but with all the keys
              (including nested keys) normalized.
              Otherwise, return the data as is.
    """
    logger.debug('Normalizing data: %s', data)
    if isinstance(data, Mapping):
        return dict(
            (_remove_case_and_signs(k), normalize_config_values(k, v))
            for (k, v) in iteritems(data)
        )
    elif isinstance(data, string_types):
        return data
    elif isinstance(data, Iterable):
        return [normalize_config_values(key, d) for d in data]
    return data


def normalize_config_keys(key):
    """Given a key, transform it into it's normal form

    :param str key: Key to normalize

    :rtype: str
    :returns: Normalize key
    """
    if not isinstance(key, string_types):
        raise RuntimeError(
            'key must be string type! not {0}.\n'
            'Received: {1}'.format(type(key), key)
        )
    key = _remove_case_and_signs(key)
    return _normalize_key_name(key)


def _remove_case_and_signs(key):
    """Given a string, transform it into lower case and remove whitespaces,
    dashes and underscores.

    :param str data_in: Option name or (string) value to remove case and signs
                        from.

    :rtype: str
    :returns: String in lower case form and with signs removed
    """
    return key.lower().replace(' ', '').replace('-', '').replace('_', '')


_KEY_NAME_TRANSLATIONS = {
    'distro': 'distro',
    'distros': 'distro',
    'distribution': 'distro',
    'distributions': 'distro',
    'os': 'distro',
    'operatingsystem': 'distro',
    'operatingsystems': 'distro',
    'arch': 'arch',
    'archs': 'arch',
    'architecture': 'arch',
    'architectures': 'arch',
    'stage': 'stage',
    'stages': 'stage',
    'substage': 'substage',
    'substages': 'substage',
}


def _normalize_key_name(key, translations_map=None):
    """Given key and a translations map (optional) will extract this key
    from the given map, or return the key itself if it's not in the map.

    :param str key: Key to normalize
    :param Mapping translations_map: Map from abstract forms of different keys
                                     to the normal value of the key.

    :rtype: str
    :returns: The given key in it's normalized form if it exists.
              Otherwise, return the key as is.
    """
    if not translations_map:
        translations_map = _KEY_NAME_TRANSLATIONS
    return translations_map.get(key, key)
