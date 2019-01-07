"""test_jenkins_ssh_cli_facts.py - Tests for the jenkins_ssh_cli_facts Ansible
module
"""
from __future__ import absolute_import, division, print_function
from textwrap import dedent

from jenkins_ssh_cli_facts import JenkinsSSHCLIPluginsCollector


class TestJenkinsSSHCLIPluginsCollector(object):
    def test_parse_cmd_out(self):
        cmd_out = dedent(
            """
            ssh-slaves      SSH Slaves plugin           1.29.1 (1.29.4)
            script-security Script Security Plugin      1.49
            email-ext       Email Extension Plugin      2.63
            junit           JUnit Plugin                1.26.1
            blueocean-rest  REST API for Blue Ocean     1.9.0 (1.10.1)
            ghprb           GitHub Pull Request Builder 1.42.0
            ssh-agent       SSH Agent Plugin            1.17
            """
        ).lstrip()
        expected = [
            {'shortName': 'ssh-slaves', 'longName': 'SSH Slaves plugin',
             'version': '1.29.1', 'versionUpdate': '1.29.4'},
            {'shortName': 'script-security',
             'longName': 'Script Security Plugin', 'version': '1.49',
             'versionUpdate': None},
            {'shortName': 'email-ext', 'longName': 'Email Extension Plugin',
             'version': '2.63', 'versionUpdate': None},
            {'shortName': 'junit', 'longName': 'JUnit Plugin',
             'version': '1.26.1', 'versionUpdate': None},
            {'shortName': 'blueocean-rest',
             'longName': 'REST API for Blue Ocean', 'version': '1.9.0',
             'versionUpdate': '1.10.1'},
            {'shortName': 'ghprb', 'longName': 'GitHub Pull Request Builder',
             'version': '1.42.0', 'versionUpdate': None},
            {'shortName': 'ssh-agent', 'longName': 'SSH Agent Plugin',
             'version': '1.17', 'versionUpdate': None},
        ]
        coll = JenkinsSSHCLIPluginsCollector()
        out = coll.parse_cmd_out(cmd_out)
        assert out == expected
