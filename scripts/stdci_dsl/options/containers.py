#!/bin/env python
__metaclass__ = type
"""options/containers.py - The `containers` DSL option
"""
from scripts.struct_normalizer import (
    normalize_value, map_with, list_of, scalar, mandatory, fallback_option,
    all_of
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
        thread = normalize_thread_options(thread, decorate=scalar(
            type=bool, else_='`decorate` must be a boolean value'
        ))
        return normalize_thread_options(thread, containers=mandatory(
            all_of(list_of(self._normalized_container), self._with_decorate),
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

    def _with_decorate(self, thread, cont_list):
        """Add annotation containers to configuration

        :param JobThread thread: The JobThread we're normalizing
        :param object cont_list: Container list we already normalized

        :rtype: list
        :returns: A container list with annotations added, if requested
        """
        if thread.options.get('decorate', False) and cont_list:
            checkout_container = {
                'image': 'centos/s2i-base-centos7',
                'args': [
                    'bash',
                    '-exc',
                    # note: below is one big string passed as a single
                    #       argument to bash
                    'git init . && '
                    'git fetch --tags --progress "$STD_CI_CLONE_URL"'
                        ' +refs/heads/*:refs/remotes/origin/* && '
                    'git fetch --tags --progress "$STD_CI_CLONE_URL"'
                        ' +"$STD_CI_REFSPEC":myhead && '
                    'git checkout myhead && '
                    '{ chmod ug+x ' + thread.options['script'] + ' || :; }'
                ],
            }
            return [checkout_container] + cont_list
        else:
            return cont_list
