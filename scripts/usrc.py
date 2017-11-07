#!/usr/bin/env python
"""usrc.py - A tool for handling upstream source dependencies
"""
from __future__ import absolute_import, print_function
import argparse
import os
import logging
import yaml
from hashlib import sha1, md5
from xdg.BaseDirectory import xdg_cache_home
from time import time
from socket import gethostbyname, gethostname
try:
    from subprocess import check_output, STDOUT
except ImportError:
    from subprocess import STDOUT, Popen, CalledProcessError, PIPE

    # Backport check_output for EL6
    def check_output(*popenargs, **kwargs):
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed.')
        process = Popen(stdout=PIPE, *popenargs, **kwargs)
        output, unused_err = process.communicate()
        retcode = process.poll()
        if retcode:
            cmd = kwargs.get("args")
            if cmd is None:
                cmd = popenargs[0]
            raise CalledProcessError(retcode, cmd)
        return output


UPSTREAM_SOURCES_FILE = 'upstream_sources.yaml'
UPSTREAM_SOURCES_PATH = os.path.join('automation', UPSTREAM_SOURCES_FILE)
CACHE_NAME = 'usrc'

logger = logging.getLogger(__name__)


def main():
    args = parse_args()
    args.handler(args)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Upstream source dependency handling tool'
    )
    subparsers = parser.add_subparsers()
    get_parser = subparsers.add_parser(
        'get', help='Download upstream sources',
        description=(
            'Download upstream sources as listed in upstream_sources.yaml'
            ' and merge them into the local directory'
        ),
    )
    get_parser.set_defaults(handler=get_main)
    update_parser = subparsers.add_parser(
        'update', help='Update upstream source versions',
        description=(
            'Query the upstream source repositories for the latest available'
            ' versions, download them, and update the local'
            ' upstream_sources.yaml file'
        )
    )
    update_parser.set_defaults(handler=update_main)
    update_parser.add_argument(
        '--commit', action='store_true',
        help=(
            'Commit the upstream_sources.yaml change locally.'
            ' This will create a branch called "commit_branch" and commit'
            ' the upstream_sources.yaml change into it. The branch will be'
            ' overwritten if it already exists'
        )
    )
    return parser.parse_args()


def get_main(args):
    get_upstream_sources()


def update_main(args):
    update_upstream_sources()
    if args.commit:
        commit_upstream_sources_update()


def get_upstream_sources():
    """Download the US sources listed in upstream_sources.yaml
    """
    dst_path = os.getcwd()
    sources_doc = read_yaml_to_obj(UPSTREAM_SOURCES_PATH)
    if not sources_doc:
        return

    upstream_source_collector(sources_doc.get('git', []), dst_path)


def update_upstream_sources():
    sources_doc = read_yaml_to_obj(UPSTREAM_SOURCES_PATH)
    if not sources_doc:
        return

    has_changed = update_git_sha_in_yaml(sources_doc.get('git', []))
    if not has_changed:
        return

    with open(UPSTREAM_SOURCES_PATH, 'w') as stream:
        yaml.dump(sources_doc, stream, default_flow_style=False)


def commit_upstream_sources_update():
    status = git('status', '--porcelain', UPSTREAM_SOURCES_PATH).rstrip()
    if not status.endswith(' ' + UPSTREAM_SOURCES_PATH):
        # Skip committing if upstream_sources.yaml not changed
        return
    if check_if_branch_exists('commit_branch'):
        git('branch', '-D', 'commit_branch', append_stderr=True)
    git('checkout', '-b', 'commit_branch', append_stderr=True)
    with open(UPSTREAM_SOURCES_PATH, 'r') as stream:
        checksum = md5(stream.read().encode('utf-8')).hexdigest()
    git('add', UPSTREAM_SOURCES_PATH, append_stderr=True)

    commit_message = generate_gerrit_message('Changed commit SHA1', checksum)
    git('commit', '-m', commit_message)


def read_yaml_to_obj(file_name):
    """
    Opens a yaml file and returns an object

    :param string file_name: yaml file path

    :rtype: dictionary
    :returns: an object out of the yaml
    """
    try:
        with open(file_name, 'r') as stream:
            return yaml.safe_load(stream)
    except IOError:
        logger.info('File {file_name} cannot be opened or is not a'
                    ' valid yaml'.format(file_name=file_name))
        return None


def upstream_source_collector(git_section, dst_path):
    """
    Processing the git section in the upstream_sources.yaml

    :param list git_section: list of us git repos
    :param string dst_path:  path to project

    Go over all repos in git section and copy them on top of the current
    project. In the end, just reset all modified files so they'll go back to be
    their current project's version
    """
    for repo in git_section:
        work_dir_name = sha1(repo['url'].encode('utf-8')).hexdigest()
        work_dir = os.path.join(xdg_cache_home, CACHE_NAME, work_dir_name)
        clone_repo(repo['url'], repo['commit'], repo['branch'], work_dir)
        git(
            '--git-dir=' + os.path.join(work_dir, '.git'),
            '--work-tree=' + dst_path,
            'checkout', repo['commit'], '-f',
            append_stderr=True
        )

    # the below code will 'prefer' ds changes over us ones
    git(
        '--git-dir=' + os.path.join(dst_path, '.git'),
        '--work-tree=' + dst_path,
        "reset", "--hard",
        append_stderr=True
    )


def clone_repo(git_url, git_commit, branch, work_dir):
    """
    Will clone a repo to the relevant folder

    :param string git_url:    git repo url
    :param string git_commit: git SHA1 to checkout to
    :param string branch:     git branch to fetch commit from
    """
    git('init', work_dir, append_stderr=True)
    # TODO: check if git_commit is already available locally and skip fetching
    git(
        '--git-dir=' + os.path.join(work_dir, '.git'),
        'fetch', '--tags', git_url, branch,
        append_stderr=False
    )


def update_git_sha_in_yaml(git_section):
    """
    update upstream sources yaml with newer commits SHA1

    :param list git_section: list of git upstream repos, branchs and SHA1s

    :rtype: boolean
    :returns: whether the yaml doc has been updates or not
    """
    has_changed = False

    for repo in git_section:
        latest_commit = get_latest_commit(repo['branch'], repo['url'])
        if not latest_commit:
            continue
        has_changed = has_changed or (latest_commit != repo['commit'])
        repo['commit'] = latest_commit

    return has_changed


def get_latest_commit(branch, git_url):
    """
    Get latest commit of a branch from remote repository

    :param string branch:  git branch
    :param string git_url: git repository url

    :rtype: string
    :returns: last commit of a branch or None if it couldn't be found
    """
    # TODO: Fetch commit into the cached upstream repo instead of just using
    # ls-remote
    branches_and_refs = git('ls-remote', git_url, branch).splitlines()
    if len(branches_and_refs) >= 1:
        sha = branches_and_refs[0].split()[0]
        if not isinstance(sha, str):
            # We normalize unicode output into an Ascii string because we know
            # git SHAs are only hex numbers and therefore only contain Ascii
            # characters.
            # We need to do this so we don't get strange unicode flags in YAML
            # we produce form Python2
            sha = sha.encode('ascii', 'ignore')
        return sha

    logger.warn("Could not find latest commit for branch: {0}".format(branch))
    return None


def generate_gerrit_message(message, checksum):
    """
    Generate commit message

    :param string message:         git commit message
    :param string checksum:        sources file checksum

    generate change ID hash for the commit message
    so gerrit will be able to create a new patch.
    Moreover, for patch duplication, add checksum
    so the next poll run will be able to check whether
    the same patch has already been merged or not

    :rtype: string
    :returns: commit message with change ID and checksum
    """
    message_template = '{message}\n\nx-md5: {md5}\n\n\nChange-Id: I{change_id}'

    with open('change_id_data', 'w') as cid:
        cid.write("tree {tree}".format(tree=git('write-tree')))
        parent = git('rev-parse', 'HEAD^0')
        if parent:
            cid.write("parent {parent}".format(parent=parent))
        cid.write(str(time()))
        cid.write(os.uname()[1])
        cid.write(gethostbyname(gethostname()))
        cid.write(message)

    change_id = git('hash-object', '-t', 'commit', 'change_id_data')

    return message_template.format(message=message, md5=checksum,
                                   change_id=change_id)


def check_if_branch_exists(branch_to_check):
    """
    Checks if a local branch already exists

    :param string branch_to_check: branch to check if already exists
    :param string work_folder_cmd: git-dir parameter to git commands

    :rtype: boolean
    :returns: whether a branch exists or not
    """
    branches = git('branch').splitlines()
    for branch in branches:
        if branch.strip() == branch_to_check:
            return True

    return False


def git(*args, **kwargs):
    """
    Util function to execute git commands

    :param list args:         a list of git command line args
    :param dictionary kwargs: for example,
                              if one wants to append the stderr to
                              the stdout, he can set append_stderr
                              key to true

    :rtype: string
    :returns: output or error of the command

    Executes git commands and return output or empty
    string if command has failed
    """
    git_command = ['git']
    git_command.extend(args)

    stderr = (STDOUT if kwargs.get('append_stderr', False) else None)
    logger.info("Executing command: "
                "{command}".format(command=' '.join(git_command)))
    std_out = check_output(git_command, stderr=stderr)
    if kwargs.get('print_command_output', True):
        for log_line in std_out.splitlines():
            logger.info(log_line)

    return std_out.decode('utf-8')


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it

    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = level


if __name__ == '__main__':
    main()
