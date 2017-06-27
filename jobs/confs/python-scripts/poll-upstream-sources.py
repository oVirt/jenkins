#!/usr/bin/env python
"""
poll-upstream-sources.py
The below is a build step for the poll std-ci
stage that'll update the upstream_sources yaml
with the latest upstream commit SHA for each
branch
"""

import os
import yaml
import json
import time
import socket
import logging
import hashlib
from subprocess import check_output, STDOUT
from os.path import expanduser
from stat import S_IRWXU, S_IRGRP, S_IXGRP, S_IROTH, S_IXOTH
from urlparse import urlparse

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger('poll-upstream-sources')


def main():
    """
    Parse yaml, seprate it to sections and call the
    relevant util function
    """
    git_flags = {}
    yaml_paths = {}
    workspace = os.environ['WORKSPACE']
    project = os.environ['PROJECT']
    dst_path = os.path.join(workspace, project)
    git_flags['work_folder_cmd'] = \
        '--git-dir={dst_path}/.git'.format(dst_path=dst_path)
    git_flags['work_tree_cmd'] = \
        '--work-tree={dst_path}'.format(dst_path=dst_path)
    yaml_paths['relative'] = 'automation/upstream_sources.yaml'
    yaml_paths['full'] = os.path.join(dst_path, yaml_paths['relative'])
    sources_doc = read_yaml_to_obj(yaml_paths['full'])
    if not sources_doc:
        return

    push_yaml = 'jenkins/data/git-push-url-map.yaml'
    path_to_push_yaml = os.path.join(workspace, push_yaml)
    push_doc = read_yaml_to_obj(path_to_push_yaml)
    if not push_doc:
        return

    push_details = get_push_details(push_doc, dst_path,
                                    git_flags['work_folder_cmd'])
    if not push_details[0]:
        return

    has_changed = update_git_sha_in_yaml(sources_doc.get('git', []))

    if has_changed:
        update_yaml_and_push(yaml_paths, sources_doc, push_details, git_flags)


def read_yaml_to_obj(file_name):
    """
    Opens a yaml file and returns an object

    :param string file_name: string, yaml file path

    :rtype: dictionary
    :returns: an object out of the yaml
    """
    try:
        with open(file_name, 'r') as stream:
            return yaml.safe_load(stream)
    except IOError:
        LOGGER.error('File {file_name} cannot be '
                     'opened'.format(file_name=file_name))
        raise
    except yaml.YAMLError:
        LOGGER.error('File {file_name} is not a valid '
                     'yaml'.format(file_name=file_name))
        raise

    return None


def update_git_sha_in_yaml(git_section):
    """
    update upstream sources yaml with newer commits SHA1

    :param list git_section: list of git upstream repos, branchs and SHA1s

    :rtype: boolean
    :returns: whether the yaml doc has been updates or not
    """
    has_changed = False

    for index, repo in enumerate(git_section):
        latest_commit = get_latest_commit(repo['branch'], repo['url'])
        if not latest_commit:
            LOGGER.error("Could not find latest commit for branch: "
                         "{branch}".format(branch=repo['branch']))
            continue

        if latest_commit != repo['commit']:
            has_changed = True
            git_section[index]['commit'] = latest_commit

    return has_changed


def check_if_similar_patch_pushed(url, checksum):
    """
    check if same patch has already been pushed

    :param string url:      git repo url
    :param string checksum: sources file checksum

    Avoiding push of patches that had
    already been pushed and hadn't been merged yet.
    These patches has a md5 checksum hash in the commit
    message. It'll check wether the current sources file
    md5 hash is part of commit message of a patch that
    had already been pushed

    :rtype: boolean
    :returns: True if patch exists and false if not
    """
    url_list = url.split('/')
    server_url = url_list[2].split(':')[0]
    project = "/".join(url_list[3:]).replace('.git', '')
    project_param = "project:{project}".format(project=project)
    msg_param = 'message:{checksum}'.format(checksum=checksum)
    cmd_list = ['ssh', '-p', '29418', server_url, 'gerrit', 'query',
                '--format=JSON', 'status:open', project_param, msg_param]
    LOGGER.info("executing: %s" % str(cmd_list))
    res = check_output(['ssh', '-p', '29418', server_url, 'gerrit', 'query',
                        '--format=JSON', 'status:open', project, msg_param])

    LOGGER.info(res)

    if res and json.loads(res.splitlines()[-1]).get('rowCount', 0) >= 1:
        return True
    else:
        return False


def get_latest_commit(branch, git_url):
    """
    Get latest commit of a branch from remote repository

    :param string branch:  git branch
    :param string git_url: git repository url

    :rtype: string
    :returns: last commit of a branch
    """
    branches_and_refs = git('ls-remote', git_url, branch,
                            append_stderr=False).splitlines()
    if len(branches_and_refs) == 1:
        return branches_and_refs[0].split()[0]

    return ''


def commit_changes(sources_yaml, git_flags, checksum):
    """
    Checkout to a temporary branch, add changes
    and commit them

    :param string sources_yaml:  relative path to sources_upstream
                                 yaml for git add command (for some
                                 reason cannot work with full path)
    :param dictionary git_flags: special commandline arguments for git
    :param string checksum:      sources file checksum
    """
    if check_if_branch_exists('commit_branch', git_flags['work_folder_cmd']):
        git(git_flags['work_folder_cmd'], 'branch', '-D', 'commit_branch',
            append_stderr=True)
    git(git_flags['work_folder_cmd'], 'checkout', '-b', 'commit_branch',
        append_stderr=True)
    git(git_flags['work_folder_cmd'], git_flags['work_tree_cmd'], 'add',
        sources_yaml, append_stderr=True)

    commit_message = generate_gerrit_message('Changed commit SHA1', checksum,
                                             git_flags['work_folder_cmd'])
    git(git_flags['work_folder_cmd'], 'commit', '-m', commit_message,
        append_stderr=True)


def generate_gerrit_message(message, checksum, work_folder_cmd):
    """
    Generate commit message

    :param string message:         git commit message
    :param string checksum:        sources file checksum
    :param string work_folder_cmd: git-dir parameter to git commands

    generate change ID hash for the commit message
    so gerrit will be able to create a new patch.
    Moreover, for patch duplication, add checksum
    so the next poll run will be able to check whether
    the same patch has already been merged or not

    :rtype: string
    :returns: commit message with change ID and checksum
    """
    message_template = '{message}\n\nChange-Id: I{change_id}\n\n\nx-md5: {md5}'

    with open('change_id_data', 'w') as cid:
        cid.write("tree {tree}".format(tree=git(work_folder_cmd, 'write-tree',
                                                append_stderr=False)))
        parent = git(work_folder_cmd, 'rev-parse', 'HEAD^0',
                     append_stderr=False)
        if parent:
            cid.write("parent {parent}".format(parent=parent))
        cid.write(str(time.time()))
        cid.write(os.uname()[1])
        cid.write(socket.gethostbyname(socket.gethostname()))
        cid.write(message)

    change_id = git(work_folder_cmd, 'hash-object', '-t', 'commit',
                    'change_id_data', append_stderr=False)

    return message_template.format(message=message, change_id=change_id,
                                   md5=checksum)


def push_changes(push_remote, work_folder_cmd):
    """
    Push changes to git remote repository

    :param string push_remote:     url to remote repo
    :param string work_folder_cmd: git-dir parameter to git commands
    """
    gerrit_branch = os.environ['GERRIT_BRANCH']
    if not push_remote:
        LOGGER.error("No push URL")
        return
    dest_to_push_to = \
        'HEAD:refs/for/{branch}'.format(branch=gerrit_branch.split('/')[-1])
    git(work_folder_cmd, 'push', push_remote, dest_to_push_to,
        append_stderr=True)


def get_push_details(push_doc, dst_path, work_folder_cmd):
    """
    return the push remote url so git push will be possible

    :param push_doc:        dictionary for mapping git clone
    urls to git push urls
    :param string dst_path: destination folder path
    :param string work_folder_cmd: git-dir parameter to git commands

    :rtype: tuple
    :returns: push url and its host key

    """
    remotes = git(work_folder_cmd, 'remote', '-v', append_stderr=False)
    remote = [line.split() for line in remotes.splitlines()
              if line.split()[0] == 'origin' and line.split()[-1] == '(push)']
    if not remote:
        return '', ''

    project_suffix = urlparse(remote[0][1]).path
    base_url = remote[0][1].replace(project_suffix, '')
    push_details = push_doc[base_url]
    if 'host_key' not in push_details:
        return '', ''
    if 'push_url' not in push_details or not push_details['push_url']:
        push_details['push_url'] = base_url
    git_push_url = \
        "{push_url}{project}".format(push_url=push_details['push_url'],
                                     project=project_suffix)

    return git_push_url, push_details['host_key']


def add_private_key_to_known_hosts(key):
    """
    Add host key to known_hosts

    :param string key: ssh host key for known_hosts file

    Adding private key to known_hosts file so
    git push will be available
    """
    home = expanduser('~')
    ssh_folder = '{home}/.ssh/'.format(home=home)
    if not os.path.exists(ssh_folder):
        os.mkdir(ssh_folder, S_IRWXU | S_IRGRP | S_IXGRP | S_IROTH | S_IXOTH)

    known_hosts_file = '{ssh_folder}/known_hosts'.format(ssh_folder=ssh_folder)
    with open(known_hosts_file, 'w+') as known_hosts:
        for key in known_hosts.readlines():
            return

        known_hosts.write("{key}\n".format(key=key))


def check_if_branch_exists(branch_to_check, work_folder_cmd):
    """
    Checks if a local branch already exists

    :param string branch_to_check: branch to check if already exists
    :param string work_folder_cmd: git-dir parameter to git commands

    :rtype: boolean
    :returns: whether a branch exists or not
    """
    branches = git(work_folder_cmd, 'branch', append_stderr=False).splitlines()
    for branch in branches:
        if branch.strip() == branch_to_check:
            return True

    return False


def update_yaml_and_push(yaml_paths, sources_doc, push_details, git_flags):
    """
    dump the data into the yaml, make sure know_hosts file
    is updated properly, check if this commit hadn't already
    been pushed, commit and push

    :param dictionary yaml_paths:  full and relative paths to sources yaml
    :param dictionary sources_doc: dictionary of sources_upstream
    :param string push_details:    url to remote repo and ssh host_key
    :param dictionary git_flags:   special commandline arguments for git
    """
    with open(yaml_paths['full'], 'w') as stream:
        yaml.dump(sources_doc, stream, default_flow_style=False)

    checksum = hashlib.md5(yaml.dump(sources_doc,
                                     default_flow_style=False)).hexdigest()
    add_private_key_to_known_hosts(push_details[1])
    if not check_if_similar_patch_pushed(push_details[0], checksum):
        commit_changes(yaml_paths['relative'], git_flags, checksum)
        push_changes(push_details[0], git_flags['work_folder_cmd'])


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


if __name__ == '__main__':
    main()
