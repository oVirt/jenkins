#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Barak Korren <bkorren@redhat.com>
# GNU General Public License v3.0+
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: jenkins_ssh_cli_facts

short_description: Get facts from Jenkins SSH CLI

version_added: "2.8"

author:
    - "Barak Korren <bkorren@redhat.com>"

description:
    - Talk to jenkins over SSH
    - Allow limiting the set of facts to obtain

options:
    jenkins_ssh_hostname:
        description:
            - The hostname to connect to ovr SSH
        default: localhost
    jenkins_ssh_port:
        description:
            - the port over which the Jenkins SSH CLI is available
        default: 2222
    jenkins_ssh_username:
        description:
            - The username to use for connecting to the SSH CLI port
        default: admin
    jenkins_ssh_user_key_file:
        description:
            - Path to the private key file used to connect to Jenkins
            - If unspecified, SSH defaults would be used
        required: no
    gather_subset:
        description:
            - If supplied, restrict the additional facts collected to the
              given subset.
            - Possible values: C(plugins)
              Can specify a list of values to specify a larger subset.
            - Values can also be used with an initial C(!) to specify that
              that specific subset should not be collected.  For instance:
              C(!plugins).
        required: false
        default: 'all'
    gather_timeout:
        description:
            - Set the default timeout in seconds for individual fact gathering
        required: false
        default: 10
    filter:
        description:
            - if supplied, only return facts that match this shell-style
              (fnmatch) wildcard.
        required: false
        default: '*'

requirements:
  - I(ssh) installed on the target host
'''

EXAMPLES = '''
- name: Get list of Jenkins plugins
  jenkins_ssh_cli_facts:
    gather_subset: '!any,plugins'
'''

RETURN = '''
jenkins_facts:
    description:
        - Dictionary of facts about Jenkins
    returned: success
    type: dict
'''
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.facts.namespace import PrefixFactNamespace
from ansible.module_utils.facts.collector import BaseFactCollector
from ansible.module_utils.facts import ansible_collector


class JenkinsSSHCLIFactCollector(BaseFactCollector):
    minimal_gather_subset = set([])
    all_collector_classes = []

    @classmethod
    def collector(cls, in_minimal_subset=True):
        def decorator(collector):
            cls.all_collector_classes.append(collector)
            if in_minimal_subset:
                cls.minimal_gather_subset.add(collector.name)
            return collector
        return decorator

    def collect(self, module=None, collected_facts=None):
        facts = {self.name: {}, }

        if module is None:
            return facts

        rc, stdout, stderr = \
            module.run_jenkins_ssh_command(self.command, check_rc=True)

        facts[self.name] = self.parse_cmd_out(stdout, module, collected_facts)
        return facts

    def parse_cmd_out(self, cmd_out, module=None, collected_facts=None):
        if hasattr(self, 'parse_cmd_out_regex'):
            return self.parse_cmd_out_by_regex(
                cmd_out, self.parse_cmd_out_regex
            )
        else:
            raise NotImplementedError(
                'parse_cmd_out not implemented in {}'.format(self.__class__)
            )

    @staticmethod
    def parse_cmd_out_by_regex(cmd_out, regex):
        fsm = re.compile(regex, re.MULTILINE)
        matchers = fsm.finditer(cmd_out)
        groups = [m.groupdict() for m in matchers]
        return groups


@JenkinsSSHCLIFactCollector.collector()
class JenkinsSSHCLIPluginsCollector(JenkinsSSHCLIFactCollector):
    name = 'plugins'
    _fact_ids = set()
    command = 'list-plugins'
    parse_cmd_out_regex = \
        '^(?P<shortName>[^ ]+) +(?P<longName>.+?) +' + \
        '(?P<version>[0-9\\.]+)(?: \\((?P<versionUpdate>[0-9\\.]+)\\))?'


class JenkinsSSHCLIFactsModule(AnsibleModule):
    def __init__(self, *args, **kwargs):
        kwargs['argument_spec'] = self.argspec
        kwargs['supports_check_mode'] = True
        AnsibleModule.__init__(self, *args, **kwargs)

    def execute_module(self):
        gather_subset = self.params['gather_subset']
        gather_timeout = self.params['gather_timeout']
        filter_spec = self.params['filter']

        minimal_gather_subset = \
            JenkinsSSHCLIFactCollector.minimal_gather_subset
        all_collector_classes = \
            JenkinsSSHCLIFactCollector.all_collector_classes

        namespace = PrefixFactNamespace(
            namespace_name='jenkins', prefix='jenkins_'
        )

        fact_collector = ansible_collector.get_ansible_collector(
            all_collector_classes=all_collector_classes,
            namespace=namespace,
            filter_spec=filter_spec,
            gather_subset=gather_subset,
            gather_timeout=gather_timeout,
            minimal_gather_subset=minimal_gather_subset
        )

        facts_dict = fact_collector.collect(module=self)

        self.exit_json(jenkins_facts=facts_dict)

    @property
    def argspec(self):
        args = dict(
            jenkins_ssh_hostname=dict(default='localhost'),
            jenkins_ssh_port=dict(type='int', default=2222),
            jenkins_ssh_username=dict(default='admin'),
            jenkins_ssh_user_key_file=dict(),
            gather_subset=dict(default=["all"], required=False, type='list'),
            gather_timeout=dict(default=10, required=False, type='int'),
            filter=dict(default="*", required=False),
        )
        return args

    def run_jenkins_ssh_command(self, command, **kwargs):
        rc_args = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            self.params['jenkins_ssh_hostname'],
            '-p', str(self.params['jenkins_ssh_port']),
            '-l', self.params['jenkins_ssh_username'],
        ]
        if self.params['jenkins_ssh_user_key_file'] is not None:
            rc_args.extend(['-i', self.params['jenkins_ssh_user_key_file']])
        rc_args.extend(['--', command])
        return self.run_command(rc_args, **kwargs)


def main():
    JenkinsSSHCLIFactsModule().execute_module()


if __name__ == '__main__':
    main()
