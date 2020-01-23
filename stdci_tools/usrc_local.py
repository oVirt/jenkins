#!/usr/bin/env python
"""usrc_local.py - A simple wrapper around usrc.py

This script is meant for use by CI systems to gain `usrc.py` functionality.
The idea is that in downstream repos of this one this script will be a full
copy of `usrc.py`. This way a system using a downstream repo can gain access to
some version of `usrc.py` even before pulling this one, while still have access
to an updated `usrc.py` once it does.
"""
from __future__ import absolute_import, print_function
import sys
import os

sys.path.append(os.path.dirname(__file__))

from usrc import * # noqa

if __name__ == '__main__':
    main()
