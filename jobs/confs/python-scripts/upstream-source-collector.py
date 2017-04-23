#!/usr/bin/env python
"""
upstream-source-collector.py
The script will make sure that all upstream
projects (if exists) will be copied on top
of their downstream corresponding while
downstream changes will be preferred on top
of upstream
"""

import yaml
import os
import logging
import contextlib
import glob
from subprocess import check_output, STDOUT
from six.moves import map

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger('upstream-source-collector')


def main():
    """
    Find all projects' workspaces under Jenkins job's workspace
    and rebase thier upstream sources on top of them
    """
    for rel_path in glob.glob('**/.git'):
        parse_yaml_clone_and_override(rel_path)


def parse_yaml_clone_and_override(rel_path_to_git):
    """
    Processing the upstream_sources.yaml

    :param string rel_path_to_git: relative path to git folder

    Get yaml object and work on its git section
    """
    folder = os.path.dirname(rel_path_to_git)
    dst_path = os.path.join(os.path.abspath(os.path.curdir), folder)
    path_to_sources_yaml = ("{dst_folder}/automation/upstream_"
                            "sources.yaml".format(dst_folder=dst_path))

    sources_doc = read_yaml_to_obj(path_to_sources_yaml)
    if not sources_doc:
        return

    upstream_source_collector(sources_doc.get('git', []), dst_path, folder)


def upstream_source_collector(git_section, dst_path, folder):
    """
    Processing the git section in the upstream_sources.yaml

    :param list git_section: list of us git repos
    :param string dst_path:  path to project
    :param string folder:    project's folder

    Go over all repos in git section and
    copy them on top of he current project. In the
    end, just reset all modified files so they'll
    go back to be their current project's version
    """
    for index, repo in enumerate(git_section):
        us_root_dir = "{folder}._upstream".format(folder=folder)
        git_dir = 'git.{index:0>4}'.format(index=index)
        work_folder = os.path.join(us_root_dir, git_dir)
        work_folder_cmd = \
            '--git-dir={work_folder}/.git'.format(work_folder=work_folder)
        clone_repo(repo['url'], repo['commit'], work_folder, work_folder_cmd)
        git(work_folder_cmd, '--work-tree={dst_dir}/'.format(dst_dir=dst_path),
            'checkout', repo['commit'], '-f', append_stderr=True)

    work_folder_cmd = '--git-dir={dst_path}/.git'.format(dst_path=dst_path)

    # the below code will 'prefer' ds changes over us ones
    git(work_folder_cmd, '--work-tree={dst_dir}/'.format(dst_dir=dst_path),
        "reset", "--hard", append_stderr=True)


def clone_repo(git_url, git_commit, work_folder, work_folder_cmd):
    """
    Will clone a repo to the relevant folder

    :param string git_url:    git repo url
    :param string git_commit: git SHA1 to checkout to
    :param  index:         indexed number of the
                              prerequisit repo
    """
    git('init', work_folder, append_stderr=True)
    branch = branch_of_commit(git_commit, git_url)
    git(work_folder_cmd, 'fetch', '--tags', '--progress', git_url, branch,
        append_stderr=True)


@contextlib.contextmanager
def working_directory(path, **kwargs):
    """
    :param string path:      path to folder
    :param directory kwargs: create the dir if missing

    A context manager which creates a working directory if needed,
    changes the working directory to the given path, and then changes
    it back to its previous value on exit.
    """
    prev_cwd = os.getcwd()
    if kwargs['mkdir']:
        os.mkdir(path)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def branch_of_commit(commit_sha, git_url):
    """
    Find the remote branch of a certain commit

    :param string commit_sha:  commit SHA1
    :param string git_url: url to git repo

    :rtype: string
    :returns: branch name
    """
    ls_remote_out = git('ls-remote', git_url, append_stderr=False)
    branches_list = \
        (l.split() for l in ls_remote_out.splitlines())

    return next(
        refspec for git_hash, refspec in branches_list
        if git_hash == commit_sha
    )


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

    stderr = (STDOUT if kwargs['append_stderr'] else None)
    LOGGER.info("Executing command: "
                "{command}".format(command=' '.join(git_command)))
    std_out = check_output(git_command, stderr=stderr)
    for log_line in std_out.splitlines():
        LOGGER.info(log_line)

    return std_out


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
        LOGGER.info('File {file_name} cannot be opened or is not a'
                    ' valid yaml'.format(file_name=file_name))
        return None


if __name__ == '__main__':
    main()
