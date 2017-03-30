#!/usr/bin/env python
"""gerrit.py - Objects to work with Gerrit
"""
from __future__ import absolute_import, print_function
from os import environ
from collections import namedtuple
from base64 import b64decode


class GerritServer(namedtuple('_GerritServer', ('host', 'port', 'schema'))):
    @classmethod
    def from_jenkins_env(cls, env=environ):
        return cls(
            host=env['GERRIT_HOST'],
            port=int(env['GERRIT_PORT']),
            schema=env['GERRIT_SCHEME'],
        )


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
