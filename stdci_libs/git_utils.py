#!/usr/bin/env python
"""git_utils.py - Wrappers and utilities for interacting with Git
"""

from __future__ import absolute_import
from subprocess import Popen, STDOUT, PIPE, CalledProcessError
from collections import namedtuple
from functools import partial
try:
    from urllib.parse import urlsplit
except ImportError:
    # python2 compatability
    from urlparse import urlsplit
import logging
import os


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


def git_rev_parse(ref, git_func=git):
    """Parse a git ref and return the equivalent hash

    :param str ref: A git commit reference to parse (branch name, tag, etc.)
    :param Callable git_func: (optional) A git function to use instead of the
                              default one: git

    :rtype: str
    """
    try:
        return git_func('rev-parse', "{0}^{{commit}}".format(ref)).rstrip()
    except GitProcessError as e:
        if e.returncode == 128:
            raise InvalidGitRef(
                "Invalid Git ref given: '{0}'".format(ref), ref
            )
        else:
            raise


def prep_git_repo(path, url, refspec=None, checkout=False):
    """Initialize git repo at the specified path and add a remote.

    :param str path: path in which to initialize the repository at
    :param str url: this URL will be set as origin for pulling and pushing
    :param str refspec: if provided, will fetch and checkout to specified ref.
                        a following branch with the same name as the refspec
                        will be created.
    :param bool checkout: if set to True, will checkout to the fetched refspec.
                          this will do nothing if `refspec` is not specified.

    :raises GitProcessError: if the git process failed for any reason
    :returns: git function set to use the initialized git dir and the second
              element is the sha of the fetched refspec (if exists).
    """
    local_ref_name = 'myhead'
    root_path = os.path.realpath(str(path))

    git('init', root_path)
    git_func = partial(
        git,
        '--git-dir={0}'.format(os.path.join(root_path, ".git")),
        '--work-tree={0}'.format(root_path)
    )
    git_func('remote', 'add', 'origin', url)
    if refspec:
        logger.info('will fetch {}'.format(refspec))
        git_func('fetch', 'origin', '+{0}:{1}'.format(refspec, local_ref_name))
        if checkout:
            git_func('checkout', local_ref_name)
        return git_func, git_rev_parse(local_ref_name, git_func)
    return git_func, ''


class CouldNotParseRepoURL(Exception):
    """Tell the user that we failed to parse repo URL"""
    pass


def get_name_from_repo_url(repo_url):
    """Extract the name of the repository from a given url

    :param str repo_url: the URL of the repository

    :rasises ValueError: when it fails to parse the URL and extract the repo
                         name from it
    :returns: the repo name
    """
    repo_path = urlsplit(repo_url).path
    # splitext always returns a tuple of len(2). Even if repo_path is empty.
    repo_name = os.path.basename(os.path.splitext(repo_path)[0])
    if not repo_name:
        raise CouldNotParseRepoURL(
            'could not parse repo name from repo url: {0}'.format(repo_url)
        )
    logger.info('parsed repo name from url: %s', repo_name)
    return repo_name
