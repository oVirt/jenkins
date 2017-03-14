#!/usr/bin/env python
"""change_queue.changes - Change objects for use with change_queue classes
"""
from scripts.object_utils import object_witp_opt_attrs, object_proxy


class DisplayableChange(object_witp_opt_attrs):
    """Base/Mixin class that ensures a change has the attributes that allow it
    to be displayed to users
    """
    @property
    def default_id(self):
        return self

    @property
    def default_presentable_id(self):
        return self.id

    def _cast_presentable_id(self, value):
        return str(value)

    default_url = None


class DisplayableChangeWrapper(DisplayableChange, object_proxy):
    """Wrapper class to make non-displayable change objects look like
    displayable ones
    """
