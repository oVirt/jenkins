#!/bin/env python
"""syntax_utils.py - Utilities for parsing the STDCI DSL syntax"""


def remove_case_and_signs(key):
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
    'report': 'reporting',
    'reports': 'reporting',
    'output': 'reporting',
}


def normalize_key_name(key, translations_map=None):
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
