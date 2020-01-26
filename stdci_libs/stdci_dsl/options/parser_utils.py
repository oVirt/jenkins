#!/bin/env python
"""parser.py - Options utilities that are being used by the parser
"""

from copy import copy


def get_merged_options(base_opts, mod_opts):
    """Given base options config and modify options config, update base with
    mod.

    This method will overwrite base_opts with mod_opts by updating the values
    that exists in mod_opts.

    :param dict base_opts: Base options configuration we modify.
    :param dict mod_opts:  Options configuration we apply on the base options.

    :rtype: dict
    :returns: New options config that consists of base_opts updated with
              mod_opts.
    """
    ret = copy(base_opts)
    ret.update(mod_opts)
    return ret
