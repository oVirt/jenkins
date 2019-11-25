#!/bin/env python
__metaclass__ = type
"""options/containers.py - The `containers` DSL option
"""
import os
from fnmatch import fnmatchcase

from scripts.struct_normalizer import (
    normalize_value, map_with, list_of, scalar, mandatory, fallback_option,
    all_of
)

from .base import (
    ConfigurationSyntaxError, template_string, normalize_thread_options,
    map_with_cased_keys
)


class Containers:
    def normalize(self, thread):
        """Normalize the containers option

        :param JobThread thread: JobThread to normalize

        :rtype: JobThread
        :returns: A JobThread with the relevant option normalized
        """
        thread = normalize_thread_options(thread, decorate=scalar(
            type=bool, else_='`decorate` must be a boolean value'
        ))
        return normalize_thread_options(thread, containers=mandatory(
            all_of(
                list_of(self._normalized_container),
                self._with_decorate,
                self._is_secure,
            ),
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
        return normalize_value(thread, cont_conf, to=map_with_cased_keys(
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
            workingDir=template_string(
                else_='Invalid value for container `workingdir` field'
            ),
            securityContext=map_with_cased_keys(
                fsGroup=scalar(type=str, else_='Bad value for fsgroup'),
                runAsGroup=scalar(type=str, else_='Bad value for runasgroup'),
                runAsUser=scalar(type=str, else_='Bad value for runasuser'),
                privileged=scalar(type=bool, else_='Bad value for privileged'),
            ),
        ))

    def _with_decorate(self, thread, cont_list):
        """Add annotation containers to configuration

        :param JobThread thread: The JobThread we're normalizing
        :param object cont_list: Container list we already normalized

        :rtype: list
        :returns: A container list with annotations added, if requested
        """
        if thread.options.get('decorate', False) and cont_list:
            checkout_container = {
                'image': 'quay.io/bkorren/stdci-tools:mb201911251538',
                'args': ['decorate'],
            }
            return [checkout_container] + cont_list
        else:
            return cont_list

    def _is_secure(self, thread, cont_list):
        """Inspect list of containers for security issues

        :param JobThread thread: The JobThread we're normalizing
        :param object cont_list: Container list we already normalized

        The function will raise an exception if any security issues are found.
        Right now it ensures that all containers for which the securitycontext
        is set to a nonempty value:
          1. Have an image that is listed in the CI_SECURE_IMAGES env var.
          2. Do not have the `command` option specified

        :rtype: list
        :returns: The given container list, unchanged
        """
        secure_image_patterns = os.environ.get('CI_SECURE_IMAGES', '').split()
        for container in cont_list:
            if not container.get('securityContext', {}):
                continue
            if not any(
                fnmatchcase(container['image'], sip)
                for sip in secure_image_patterns
            ):
                raise ConfigurationSyntaxError(
                    'Security set for insecure image'
                )
            if 'command' in container:
                raise ConfigurationSyntaxError(
                    '`command` forbidden for secure image'
                )
        return cont_list
