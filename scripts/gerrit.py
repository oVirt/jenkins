#!/usr/bin/env python
"""gerrit.py - Objects to work with Gerrit
"""
from __future__ import absolute_import, print_function
from itertools import chain
from os import environ
from collections import namedtuple
from six import iteritems
from base64 import b64decode
from paramiko.client import SSHClient
from socket import timeout
from subprocess import CalledProcessError


class GerritServer(namedtuple('_GerritServer', ('host', 'port', 'schema'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            host=env['GERRIT_HOST'],
            port=int(env['GERRIT_PORT']),
            schema=env['GERRIT_SCHEME'],
        )

    def run_ssh_command(self, command, cmd_input=None):  # noqa - ignore mccabe
        """Run an SSH command against the Gerrit server

        :param str command: The Gerrit command to run and its arguments
        :param str input:   (Optional) text to pass to the command's stdin

        :rtype: (str, str)
        :returns: A pair of strings containing the command's stdout and stderr
                  respectively
        """
        with SSHClient() as client:
            client.load_system_host_keys()
            fds = []
            try:
                client.connect(self.host, port=self.port, timeout=30)
                fds = client.exec_command('gerrit ' + command)
                channel = fds[0].channel
                channel.setblocking(0)
                stdout_str, stderr_str = [''] * 2
                send_needed = bool(cmd_input)
                recv_needed, err_needed = [True] * 2
                while send_needed or recv_needed or err_needed:
                    if send_needed and channel.send_ready():
                        bytes_sent = channel.send(cmd_input)
                        cmd_input = str(cmd_input)[bytes_sent:]
                        send_needed = bool(cmd_input)
                    if recv_needed:
                        try:
                            data = channel.recv(1024)
                            if data:
                                stdout_str += data
                            else:
                                recv_needed = False
                        except timeout:
                            pass
                    if err_needed:
                        try:
                            data = channel.recv_stderr(1024)
                            if data:
                                stderr_str += data
                            else:
                                err_needed = False
                        except timeout:
                            pass
                channel.setblocking(1)
                exit_status = channel.recv_exit_status()
                if exit_status == 0:
                    return (stdout_str, stderr_str)
                raise CalledProcessError(
                    exit_status, command, stdout_str + stderr_str
                )
            finally:
                for fd in fds:
                    fd.close()


class GerritPerson(namedtuple('_GerritPerson', ('name', 'email'))):
    @classmethod
    def from_jenkins_env(cls, prefix='', env=environ):
        return cls(env[prefix + '_NAME'], env[prefix + '_EMAIL'])


class GerritProject(namedtuple('_GerritProject', ('server', 'name'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            server=GerritServer.from_jenkins_env(env),
            name=env['GERRIT_PROJECT'],
        )


class GerritBranch(namedtuple('_GerritBranch', ('project', 'name'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            project=GerritProject.from_jenkins_env(env),
            name=env['GERRIT_BRANCH'],
        )

    @property
    def server(self):
        return self.project.server


class GerritChange(namedtuple('_GerritChange', (
    'branch', 'change_id', 'number', 'owner', 'subject', 'url',
))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            branch=GerritBranch.from_jenkins_env(env),
            change_id=env['GERRIT_CHANGE_ID'],
            number=int(env['GERRIT_CHANGE_NUMBER']),
            owner=GerritPerson.from_jenkins_env('GERRIT_CHANGE_OWNER', env),
            subject=env['GERRIT_CHANGE_SUBJECT'],
            url=env['GERRIT_CHANGE_URL'],
        )

    @property
    def server(self):
        return self.branch.server

    @property
    def project(self):
        return self.branch.project


class GerritPatchset(namedtuple('_GerritPatchset', (
    'change',
    'refspec', 'patchset_number', 'uploader', 'revision',
    'commit_message', 'topic',
))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            change=GerritChange.from_jenkins_env(env),
            refspec=env['GERRIT_REFSPEC'],
            patchset_number=int(env['GERRIT_PATCHSET_NUMBER']),
            uploader=GerritPerson.from_jenkins_env(
                'GERRIT_PATCHSET_UPLOADER', env
            ),
            revision=env['GERRIT_PATCHSET_REVISION'],
            commit_message=b64decode(
                env['GERRIT_CHANGE_COMMIT_MESSAGE'].encode()
            ).decode(),
            topic=env['GERRIT_TOPIC'],
        )

    @property
    def server(self):
        return self.change.server

    @property
    def project(self):
        return self.change.project

    @property
    def branch(self):
        return self.change.branch

    def review(self, *args, **kwargs):
        """Add a review for the patch set

        :param bool abandon:  True to abandon patch (default: False)
        :param Mapping label: (Optional) A mapping of code-review labels to the
                              scores to assign to them
        :param str message:   (Optional) A message to post as a comment
        :param bool publish:  True to publish a draft patch set
                              (default: False)
        :param bool rebase:   True to rebase the patch set (default: False)
        :param bool restore:  True to restore an abandoned patch
                              (default: False)
        :param bool submit:   True to submit the patch (default: False)

        All non-keyword arguments are converted to strings and appended with
        spaces to 'message'. Additional keyword arguments are converted to
        label names by converting underscores ('_') to hyphens ('-') and added
        to the 'label' mapping.
        """
        review_cmd = [
            'review {0},{1}'.format(self.change.number, self.patchset_number)
        ]
        msg_parts = list(str(mp) for mp in chain(
            [kwargs.pop('message', '')], args
        ) if str(mp))
        if msg_parts:
            full_msg = ' '.join(msg_parts).replace("'", "'\"'\"'")
            review_cmd.append("--message '{0}'".format(full_msg))
        for flag in ['abandon', 'publish', 'rebase', 'restore', 'submit']:
            if kwargs.pop(flag, False):
                review_cmd.append('--' + flag)
        labels = kwargs.pop('label', {})
        for label, value in iteritems(kwargs):
            labels.setdefault(str(label).replace('_', '-'), value)
        for label, value in sorted(iteritems(labels)):
            review_cmd.append('--label {0}={1}'.format(str(label), str(value)))
        self.server.run_ssh_command(' '.join(review_cmd))
