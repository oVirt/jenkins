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
    runif_condition = ret.get('runif', None)
    if not runif_condition:
        return ret
    merged_runif = _merge_runif(
        base_opts.get('runif', None), mod_opts.get('runif', None)
    )
    ret['runif'] = merged_runif
    return ret


def _merge_runif(base_condition, other_condition):
    """Merge two runif condition into one condition with 'all' operator between
    """
    combined_list = []
    if base_condition:
        if not other_condition:
            return base_condition
        combined_list = [base_condition]
    if other_condition:
        if not base_condition:
            return other_condition
        combined_list = combined_list + [other_condition]
    return {'all': combined_list}
