#!/usr/bin/env python
"""git_utils.py - Wrappers and utilities for interacting with Git
"""

from __future__ import absolute_import
from subprocess import Popen, STDOUT, PIPE, CalledProcessError
from collections import namedtuple
from functools import partial
from hashlib import md5
from six.moves import filter
from six import iteritems
from stdci_libs import file_utils
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

def commit_files(
    files, branch=None, commit_msg=None,
    add_change_id=True, add_headers=None, repo_dir='.', change_id_headers=None
):
    """
    executes staging and committing with specified params

    :param list<str> files a list of git command line args
    :param str branch: git branch to be on
    :param str commit_msg: message body(w/o any header) for the commit msg
    :param bool add_change_id: if Change-Id should be appended to commit msg
    :param str repo_dir: dir to stay on when executing git commands
    :param list<str> change_id_headers: a list of change_id that need to be appended
    to commit msg

    raises IOError when files to be committed cannot be accessed
    :rtype: list a list of changed files
:   returns: output or error of the command
    """
    if repo_dir and repo_dir.strip():
        file_utils.workdir(repo_dir.strip())

    if change_id_headers:
        change_id_headers = set(change_id_headers)
    else: change_id_headers = set()

    if add_change_id:
        change_id_headers.add('Change-Id')

    if len(git('log', '--oneline').splitlines()):
        git('reset', 'HEAD')

    git('add', *filter(os.path.exists, files))
    changed_files = staged_files()
    if changed_files:
        if branch:
            git('checkout', '-B', branch)
        git('commit', '-m', commit_message(
            changed_files, commit_msg, change_id_headers, add_headers
        ))

    return changed_files

def staged_files():
    """
    gets a list of staged files in current index

    rtype: list<str> staged files
    """
    return git('diff', '--staged', '--name-only').splitlines()

def commit_message(
    changed_files=None, commit_message=None,
    change_id_headers=None, extra_headers=None
):
    """
    generates commit message

    :param list<str> changed_files: paths of changed files
    :param str commit_message: msg body(w/o any header) for the commit
    :param list<str> change_id_headers: a list of change_id need to be appended
                                        to commit msg
    :param list<str> extra_headers: a list of extra headers (e.x. `Signed-off-by:`)
                                    need to be appended to commit msg

    :rtype: str
:   returns: generated commit msg
    """
    if commit_message:
        commit_message = str(commit_message).strip()
    if not commit_message:
        commit_message = commit_title(changed_files)
        if len(changed_files) > 1:
            commit_message += '\n\nChanged files:\n'
            commit_message += '\n'.join(
                '- ' + fil for fil in changed_files
            )
    headers = commit_headers(
        changed_files, change_id_headers, extra_headers
    )
    if headers:
        commit_message += '\n'
        commit_message += headers
    return commit_message

def commit_title(changed_files, max_title=60):
    """
    generates commit title for a git commit msg

    :param list<str> changed_files: file paths of changed files
    :param int max_titile: maximum length for commit title

    :rtype: str
:   returns: commit title
    """
    if len(changed_files) != 1:
        return 'Changed {} files'.format(len(changed_files))
    title = 'Changed: {}'.format(changed_files[0])
    if len(title) <= max_title:
        return title
    title = 'Changed: {}'.format(os.path.basename(changed_files[0]))
    if len(title) <= max_title:
        return title
    return 'Changed one file'


def commit_headers(changed_files, change_id_headers, extra_headers):
    """
    generates commit headers with line breaks

    :param list<str> changed_files: file paths of changed files
    :param list<str> change_id_headers: a list of change_id need to be appended
                                        to commit msg
    :param list<str> extra_headers: a list of extra headers (e.x. `Signed-off-by:`)
                                    need to be appended to commit msg

    :rtype: str
:   returns: line-breaked commit headers
    """
    headers = ''
    if extra_headers:
        for hdr, val in sorted(iteritems(extra_headers)):
            headers += '\n{}: {}'.format(hdr, val)
    if changed_files and change_id_headers:
        change_id_set = False
        change_id = 'I' + files_checksum(changed_files)
        for hdr in sorted(set(change_id_headers)):
            if hdr == 'Change-Id':
                change_id_set = True
                continue
            headers += '\n{}: {}'.format(hdr, change_id)
        # Ensure that 'Change-Id' is the last header we set because Gerrit
        # needs it to be on the very last line of the commit message
        if change_id_set:
            headers += '\nChange-Id: {}'.format(change_id)
    return headers


def files_checksum(changed_files):
    """
    generates md5 checksum for a list of files

    :param list<str>:changed_files: paths for changed files

    :rtype: str
    returns: checksum what will be used as change-Id representing changed files
    """
    digest = md5()
    for fil in sorted(set(changed_files)):
        digest.update(fil.encode('utf-8'))
        with open(fil, 'rb') as f:
            digest.update(f.read())
    return digest.hexdigest()



def git(*args, **kwargs):
    """
    Util function to execute git commands

    :param list *args: a list of git command line args
    :param bool append_stderr: if set to true, append STDERR to the output

    Executes git commands and return output.

    raise GitProcessError: if git fails

    :rtype: str
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

    :param str ref: a git commit reference to parse (branch name, tag, etc.)
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

    :raises ValueError: when it fails to parse the URL and extract the repo
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
