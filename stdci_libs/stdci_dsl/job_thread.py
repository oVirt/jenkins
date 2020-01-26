#!/bin/env python
"""job_thread.py - stdci categories and JobThread object"""

from collections import namedtuple


STDCI_CATEGORIES = ('stage', 'substage', 'distro', 'arch')


class JobThread(namedtuple('_JobThread', STDCI_CATEGORIES + ('options',))):
    def with_modified(
        self, stage=None, substage=None, distro=None, arch=None, options=None
    ):
        """Return a new JobThread instance with modified keys

        :param str stage:           stdci stage to set
        :param str substage:        stdci substage to set
        :param str distro:          stdci distro to set
        :param str arch:            stdci arch to set
        :param Mapping options:     stdci options to set

        :rtype: JobThread
        :returns: JobThread instance with updated values
        """
        stage = self.stage if stage is None else stage
        substage = self.substage if substage is None else substage
        distro = self.distro if distro is None else distro
        arch = self.arch if arch is None else arch
        options = self.options if options is None else options
        return JobThread(stage, substage, distro, arch, options)
