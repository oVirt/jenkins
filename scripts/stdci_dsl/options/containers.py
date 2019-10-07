#!/bin/env python
__metaclass__ = type
"""options/containers.py - The `containers` DSL option
"""
from scripts.struct_normalizer import (
    normalize_value, map_with, list_of, scalar, mandatory, fallback_option
)

from .base import (
    ConfigurationSyntaxError, template_string, normalize_thread_options
)


class Containers:
    def normalize(self, thread):
        """Normalize the containers option

        :param JobThread thread: JobThread to normalize

        :rtype: JobThread
        :returns: A JobThread with the relevant option normalized
        """
        return normalize_thread_options(thread, containers=mandatory(
            list_of(self._normalized_container),
            default=[]
        ))

    def _normalized_container(self, thread, cont_conf):
        """Normalize given value to a container structure

        :param JobThread thread: The JobThread the container is a part of
        :param object cont_conf: The container configuration as found in the
                                 YAML file
        :rtype: dict
        :returns: A normalized container configuration structure
        """
        return normalize_value(thread, cont_conf, to=map_with(
            image=fallback_option(mandatory(
                template_string(else_='Invalid container image given'),
                else_='Image missing in container config'
            )),
            args=mandatory(
                list_of(template_string(
                    else_='Invalid value for container `args` field'
                )),
                default=[thread.options['script']]
            ),
            command=list_of(template_string(
                else_='Invalid value for container `command` field'
            )),
            workingdir=template_string(
                else_='Invalid value for container `workingdir` field'
            ),
        ))
