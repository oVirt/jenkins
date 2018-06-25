#!/usr/bin/env python
"""git_utils.py - Wrappers and utilities for interacting with Git
"""

from __future__ import absolute_import
from subprocess import Popen, STDOUT, PIPE, CalledProcessError
from collections import namedtuple
import logging


logger = logging.getLogger(__name__)


class GitProcessError(CalledProcessError):
    pass


def git(*args, **kwargs):
    """
    Util function to execute git commands

    :param list *args:         A list of git command line args
    :param bool append_stderr: If set to true, append STDERR to the output

    Executes git commands and return output. Raise GitProcessError if Git fails

    :rtype: string
    :returns: output or error of the command
    """
    git_command = ['git']
    git_command.extend(args)

    stderr = (STDOUT if kwargs.get('append_stderr', False) else PIPE)
    logger.info("Executing command: '%s'", ' '.join(git_command))
    process = Popen(git_command, stdout=PIPE, stderr=stderr)
    output, error = process.communicate()
    retcode = process.poll()
    if error is None:
        error = ''
    else:
        error = error.decode('utf-8')
    output = output.decode('utf-8')
    logger.debug('Git exited with status: %d', retcode, extra={'blocks': (
        ('stderr', error), ('stdout', output)
    )},)
    if retcode:
        raise GitProcessError(retcode, git_command)
    return output


class InvalidGitRef(Exception):
    def __init__(self, message, ref):
        super(InvalidGitRef, self).__init__(message)
        self.ref = ref


def git_rev_parse(ref):
    """Parse a git ref and return the equivalent hash

    :param str ref: A git commit reference to parse (branch name, tag, etc.)

    :rtype: str
    """
    try:
        return git('rev-parse', "{0}^{{commit}}".format(ref)).rstrip()
    except GitProcessError as e:
        if e.returncode == 128:
            raise InvalidGitRef(
                "Invalid Git ref given: '{0}'".format(ref), ref
            )
        else:
            raise
