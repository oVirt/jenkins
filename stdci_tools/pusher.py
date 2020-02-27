#!/usr/bin/env python
"""pusher.py - A tool for automated pushing of patches to SCMs
"""
from __future__ import absolute_import, print_function
import argparse
import logging
import logging.handlers
import os
import re
import yaml
import json
from collections import Iterable, Mapping
from itertools import chain
from six import iteritems, string_types
from six.moves.urllib.parse import urlparse
from subprocess import Popen, CalledProcessError, PIPE
from stdci_libs.stdci_logging import add_logging_args, setup_console_logging
from stdci_libs.git_utils import git, GitProcessError, git_rev_parse


logger = logging.getLogger(__name__)

DEFAULT_PUSH_MAP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    'data', 'git-push-url-map.yaml'
)


class PushDetails(object):
    """Class to represent configuration details about SCM hosts we want to
    communicate with
    """

    def __init__(
        self, push_url, host_key=None, merge_flags=None,
        maintainer_groups=None, maintainers=None, anonymous_clone_url=None,
    ):
        if merge_flags is None:
            merge_flags = []
        if maintainer_groups is None:
            maintainer_groups = []
        if maintainers is None:
            maintainers = []
        if anonymous_clone_url is None:
            anonymous_clone_url = push_url
        self.push_url, self.host_key, self.merge_flags = \
            push_url, host_key, merge_flags
        self.maintainer_groups, self.maintainers = \
            maintainer_groups, maintainers
        self.anonymous_clone_url = anonymous_clone_url

    def __eq__(self, other):
        return (
            self.push_url, self.host_key, self.merge_flags,
            self.maintainer_groups, self.maintainers,
            self.anonymous_clone_url
        ) == (
            other.push_url, other.host_key, other.merge_flags,
            other.maintainer_groups, other.maintainers,
            other.anonymous_clone_url
        )

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return yaml.dump({
            'push_url': self.push_url,
            'host_key': self.host_key[:57] + (self.host_key[57:] and '...'),
            'merge_flags': self.merge_flags,
            'maintainer_groups': self.maintainer_groups,
            'maintainers:': self.maintainers,
            'anonymous_clone_url': self.anonymous_clone_url,
        }, width=70)


class PushMapError(Exception):
    pass


class PushMapIOError(PushMapError):
    pass


class PushMapSyntaxError(PushMapError):
    pass


class PushMapMatchError(PushMapError):
    pass


class PatchInfoError(Exception):
    pass


def main():
    args = parse_args()
    try:
        setup_console_logging(args)
        retval = args.handler(args)
        if retval is None:
            return 0
        else:
            return retval
    except IOError as e:
        logger.exception('%s: %s', e.strerror, e.filename)
    except Exception as e:
        logger.exception("%s", e.args[0])
    return 1


def parse_args():
    parser = argparse.ArgumentParser(
        description='Tool for automated pushing of patches to SCMs'
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers(dest='COMMAND')
    subparsers.required = True
    push_parser = subparsers.add_parser(
        'push', help='Push commit in $CWD',
        description='Push the local commit into the appropriate remote SCM',
    )
    push_parser.set_defaults(handler=push_main)
    push_parser.add_argument(
        'branch', help='Which branch to push changes into',
    )
    push_parser.add_argument(
        '--push-map', default=DEFAULT_PUSH_MAP,
        help=(
            'Path to a push map YAML file that specifies details about how'
            ' to connect to the remote SCM servers and push changes.'
        ),
    )
    push_parser.add_argument(
        '--unless-hash',
        help=(
            'Push only if HEAD is different than the specified Git hash'
            'or commit reference'
        ),
    )
    push_parser.add_argument(
        '--if-not-exists', action='store_true',
        help='Avoid pushing if similar commit was already pushed',
    )
    can_merge_parser = subparsers.add_parser(
        'can_merge', help='Check if allowed to merge specified commit in $CWD',
        description=(
            'Check if the local commit is allowed to be automatically merged'
            ' into the appropriate remote SCM. For a commit to be auto merged,'
            ' a certain header must be set if specified, and the commit owner'
            ' must be one of the project maintainers.'
        ),
    )
    can_merge_parser.set_defaults(handler=can_merge_main)
    can_merge_parser.add_argument(
        'commit', help='A ref of the commit to merge. Defaults to HEAD',
        nargs='?', default='HEAD',
    )
    can_merge_parser.add_argument(
        '--push-map', default=DEFAULT_PUSH_MAP,
        help=(
            'Path to a push map YAML file that specifies details about how'
            ' to connect to the remote SCM servers and merge changes.'
        ),
    )
    can_merge_mxg = can_merge_parser.add_mutually_exclusive_group()
    can_merge_mxg.add_argument(
        '--check-header', nargs=1, default='automerge',
        help=(
            'Set the name of the commit message header to check in order to'
            ' confirm running a merge. If option is not specified, The'
            ' "automerge" header will be checked.'
        )
    )
    can_merge_mxg.add_argument(
        '--no-check-header', const=None, action='store_const',
        dest='check_header',
        help='Skip commit message header check.',
    )
    merge_parser = subparsers.add_parser(
        'merge', help='Merge specified commit in $CWD',
        description='Merge the local commit into the appropriate remote SCM',
    )
    merge_parser.set_defaults(handler=merge_main)
    merge_parser.add_argument(
        'commit', help='A ref of the commit to merge. Defaults to HEAD',
        nargs='?', default='HEAD',
    )
    merge_parser.add_argument(
        '--push-map', default=DEFAULT_PUSH_MAP,
        help=(
            'Path to a push map YAML file that specifies details about how'
            ' to connect to the remote SCM servers and merge changes.'
        ),
    )
    merge_mxg = merge_parser.add_mutually_exclusive_group()
    merge_mxg.add_argument(
        '--check-header', nargs=1, default='automerge',
        help=(
            'Set the name of the commit message header to check in order to'
            ' confirm running a merge. If option is not specified, The'
            ' "automerge" header will be checked.'
        )
    )
    merge_mxg.add_argument(
        '--no-check-header', const=None, action='store_const',
        dest='check_header',
        help='Skip commit message header check.',
    )
    get_header_parser = subparsers.add_parser(
        'get_header', help='Get commit message header value',
        description=(
            'Get commit message header value for a specified commit in $PWD'
        ),
    )
    get_header_parser.set_defaults(handler=get_header_main)
    get_header_parser.add_argument(
        'header', help='The header to get a value for'
    )
    get_header_parser.add_argument(
        'commit', help=(
            'A ref of the commit to get value from. Defaults to HEAD'
        ),
        nargs='?', default='HEAD',
    )
    get_header_parser.add_argument(
        '--default-value', default=None,
        help=(
            'A default value to return if the header was not specified in the'
            ' commit. If unspecified, the command will raise an error if the'
            ' header is missing'
        )
    )
    is_header_true_parser = subparsers.add_parser(
        'is_header_true', help='Check commit message header for truth',
        description=(
            'Check if commit message header value for a specified commit in '
            '$PWD is set to "true" or "on"'
        ),
    )
    is_header_true_parser.set_defaults(handler=is_header_true_main)
    is_header_true_parser.add_argument(
        'header', help='The header to check'
    )
    is_header_true_parser.add_argument(
        'commit', help=(
            'A ref of the commit to get header from. Defaults to HEAD'
        ),
        nargs='?', default='HEAD',
    )
    map_check_parser = subparsers.add_parser(
        'map_check', help='Check push map file',
        description=(
            'Check correctness of push map file'
        ),
    )
    map_check_parser.set_defaults(handler=map_check_main)
    map_check_parser.add_argument(
        'remote_url', help='The remote URL to lookup in the push map'
    )
    map_check_parser.add_argument(
        '--push-map', default=DEFAULT_PUSH_MAP,
        help=(
            'Path to a push map YAML file that specifies details about how'
            ' to connect to the remote SCM servers and merge changes.'
        ),
    )
    return parser.parse_args()


def push_main(args):
    push_to_scm(
        dst_branch=args.branch,
        push_map=args.push_map,
        if_not_exists=args.if_not_exists,
        unless_hash=args.unless_hash,
    )


def merge_main(args):
    merge_to_scm(
        push_map=args.push_map,
        commit=args.commit,
        check_header=args.check_header,
    )


def can_merge_main(args):
    if can_merge_to_scm(
        push_map=args.push_map,
        commit=args.commit,
        check_header=args.check_header,
    ):
        return 0
    else:
        return 100


def get_header_main(args):
    print(get_patch_header(args.header, args.default_value, args.commit))


def is_header_true_main(args):
    if patch_header_is_true(args.header, args.commit):
        return 0
    else:
        return 100


def map_check_main(args):
    push_map_data = read_push_map(args.push_map)
    push_details = get_push_details(push_map_data, args.remote_url)
    print(push_details)
    return 0


def push_to_scm(
    dst_branch, push_map, direct=False, if_not_exists=True, unless_hash=None
):
    """Push commits to the specified remote branch

    :param str dst_branch:    The target remote branch to push changes into.
                              What this means in practice depends on the type
                              of remote SCM server being pushed to.
    :param str push_map:      The path to a file containing information about
                              remote SCM servers that is needed to push changes
                              to them.
    :param bool direct:       If set to True, bypass review and directly merge
                              the patch.
    :param str if_not_exists: If set to 'True' (the default), check remote for
                              a similar patch before pushing, and don't push if
                              it exists.
    :param str unless_hash:   Given a Git hash value, or a commit ref, if HEAD
                              is equal to this commit, don't try to push it.
    """
    if unless_hash is not None:
        if get_patch_sha() == git_rev_parse(unless_hash):
            logger.info("HEAD commit is '%s', skipping push", unless_hash)
            return
    push_details = read_push_details(push_map)
    logger.info("Would push to: '%s'", push_details.push_url)
    if push_details.host_key:
        add_key_to_known_hosts(push_details.host_key)
    if if_not_exists and check_if_similar_patch_pushed(push_details, dst_branch):
        logger.info('Found similar patch in SCM server, not pushing')
        return
    if direct:
        dest_to_push_to = 'HEAD:refs/heads/{0}'.format(dst_branch)
    else:
        dest_to_push_to = 'HEAD:refs/for/{0}'.format(dst_branch)
    logger.info("Push to: '%s' at '%s'",
                push_details.push_url, dest_to_push_to)
    git('push', push_details.push_url, dest_to_push_to)


def merge_to_scm(push_map, commit='HEAD', check_header='automerge'):
    """Make a remote SCM merge a given commit

    :param str push_map:     The path to a file containing information about
                             remote SCM servers that is needed to push changes
                             to them.
    :param str commit:       (Optional) A ref to the commit to merge. The
                             default is HEAD
    :param str check_header: (Optional) The name of a commit header that should
                             be set to 'true' or 'yes' in order for the merge
                             to be attempted. Set to 'automerge' be default,
                             cat be set to None to skip header check.
    """
    if not can_merge_to_scm(push_map, commit, check_header):
        return
    commit_hash = git_rev_parse(commit)
    logger.info("Will merge commit: %s", commit_hash)
    push_details = read_push_details(push_map)
    logger.info("Would merge to: '%s'", push_details.push_url)
    gerrit_cli(
        push_details, 'review', commit_hash, '--submit',
        *push_details.merge_flags
    )


def can_merge_to_scm(push_map, commit='HEAD', check_header='automerge'):
    """Check if commit can be merged in remote SCM

    :param str push_map:     The path to a file containing information about
                             remote SCM servers that is needed to push changes
                             to them.
    :param str commit:       (Optional) A ref to the commit to merge. The
                             default is HEAD
    :param str check_header: (Optional) The name of a commit header that should
                             be set to 'true' or 'yes' in order for the merge
                             to be attempted. Set to 'automerge' be default,
                             cat be set to None to skip header check.
    :rtype: bool
    :returns: True if commit contains the proper commit message header, it is
              set to a truth value and the commit patch owner is a member of
              the project maintainers group as specified in the push_map
    """
    if check_header is not None:
        if not patch_header_is_true(check_header, commit):
            return False
    else:
        logger.info("Skipped patch header check")
    push_details = read_push_details(push_map)
    logger.info("Would check merging to: '%s'", push_details.push_url)
    if push_details.host_key:
        add_key_to_known_hosts(push_details.host_key)
    patch_owner = get_patch_owner(push_details, commit)
    if patch_owner is None:
        raise PatchInfoError(
            "Cannot detect who the ptch owner is,"
            " was the patch submitted to the SCM?"
        )
        return False
    logger.debug("Checking if '%s' is in push map file", patch_owner)
    if patch_owner in push_details.maintainers:
        logger.info("'%s' found in push map", patch_owner)
        return True
    logger.debug("Checking if '%s' is in maintainer groups", patch_owner)
    for group in push_details.maintainer_groups:
        logger.debug("Checking if '%s' is in group '%s'", patch_owner, group)
        if gerrit_user_in_group(push_details, patch_owner, group):
            logger.info("'%s' found in group '%s'", patch_owner, group)
            return True
    logger.info("'%s' is not allowed to automerge", patch_owner)
    return False


def read_push_map(push_map):
    """Read and parse the push map file

    :param str push_map: A path to where the push map file, that describes how
                         to push to various remote SCMs, can be found.

    :rtype: list
    :returns: Contents of the push map file
    """
    try:
        with open(os.path.expanduser(push_map), 'r') as stream:
            push_map_data = yaml.safe_load(stream)
    except IOError as e:
        raise PushMapIOError("Failed to read push map: '{0}'".format(e))
    except yaml.MarkedYAMLError as e:
        e.problem_mark.name = push_map
        raise PushMapSyntaxError("Failed to parse push map: '{0}'".format(e))
    except yaml.YAMLError as e:
        raise PushMapSyntaxError("Failed to parse push map: '{0}'".format(e))
    return push_map_data


def read_push_details(push_map, remote_url=None):
    """Read information about how to push commits to remote SCM server

    :param str push_map: A path to where the push map file, that describes how
                         to push to various remote SCMs, can be found.
    :param str remote_url: Specify remote url to read from the push map. If not
                           specified, will read the remote url from workspace.

    :rtype: PushDetails
    :returns: Details from the push_map file describing how to push commits
              made to the repo at $PWD
    """
    push_map_data = read_push_map(push_map)
    remote_url = remote_url or get_remote_url_from_ws()
    return get_push_details(push_map_data, remote_url)


def get_remote_url_from_ws():
    """
    Get git 'origin' remote url from $CWD using 'git remote' command

    :rtype: string
    :returns: The 'origin' remote url
    """
    remotes_lines = git('remote', '-v').splitlines()
    remotes_name_data = (l.split(None, 1) for l in remotes_lines)
    remotes = ([n] + d.rsplit(' ', 1) for n, d in remotes_name_data)
    try:
        return next(
            url for name, url, role in remotes
            if name == 'origin' and role == '(push)'
        )
    except StopIteration:
        raise ValueError(
            'No appropriate Git remote url defined in current directory'
        )


def get_push_details(push_map_data, remote_url):
    """Parse information about how to push commits to remote SCM server

    :param list push_map_data: Date from a push_map file - see below
    :param string remote_url:  The remote URL of the server we want to push
                               commits to, as configured in 'git remote'

    The push_map_data consists of a list of single-key Mappings, where the key
    is a regular expression and the value is another mapping with details about
    how to push commits.
    The value of the first mapping in the list whose key matches the given
    remote_url is converted into a PushDetails tuple and returned.

    The push_url fields of the push details mappings is a regex replacement
    expression that can contain match references for parts matched by the regex
    key pointing to it. Matching parts from the remote_url are expanded into
    the expression before it is returned in the PushDetails tuple.

    :rtype: PushDetails class
    :returns: push url and its host key
    """
    if not isinstance(push_map_data, Iterable):
        raise PushMapSyntaxError(
            'Sytax error in push map file.\n'
            'Push map file should contain a list of regex to details mappings.'
        )

    for clone_to_push_entry in push_map_data:
        if not isinstance(clone_to_push_entry, Mapping):
            raise PushMapSyntaxError(
                'Found an entry in the push map file that is not a mapping.\n'
                'The push map file should contain a list of single-key'
                ' mappings where the key is a regex matching remote URLs and'
                ' the value is a mapping of push details.'
            )
        if len(clone_to_push_entry) != 1:
            raise PushMapSyntaxError(
                'Fount an entry in the push map file with more or less then'
                ' one key.\n'
                'The push map file should contain a list of single-key'
                ' mappings where the key is a regex matching remote URLs and'
                ' the value is a mapping of push details.'
            )

        push_url_matcher, push_details_struct = \
            next(iteritems(clone_to_push_entry))

        match_obj = re.search(push_url_matcher, remote_url)
        if not match_obj:
            continue

        push_details = parse_push_details_struct(push_details_struct)
        push_details.push_url = match_obj.expand(push_details.push_url)
        push_details.maintainer_groups = \
            [match_obj.expand(expr) for expr in push_details.maintainer_groups]
        push_details.maintainers = \
            [match_obj.expand(expr) for expr in push_details.maintainers]
        push_details.anonymous_clone_url = \
            match_obj.expand(push_details.anonymous_clone_url)

        return push_details

    # If there was no match between remote and push,exit
    raise PushMapMatchError((
        "Can't find push details for remote URL: '{0}' in the push map file."
    ).format(remote_url))


def parse_push_details_struct(push_details_struct):
    """
    validate and parse push details struct

    :param dict push_details_struct: push url and possibly host key

    :rtype: PushDetails class
    :returns: push url matcher and host key
    """
    if not isinstance(push_details_struct, Mapping):
        raise PushMapSyntaxError(
            'Push details in a push map file must be given as a mapping'
        )
    if 'push_url' not in push_details_struct:
        raise PushMapSyntaxError(
            'Push details in a push map file must include the push_url key'
        )

    merge_flags = push_details_struct.get('merge_flags', [])
    if isinstance(merge_flags, Mapping):
        merge_flags = sorted([
            '{0}={1}'.format(k, v) for k, v in iteritems(merge_flags)
        ])
    else:
        merge_flags = parse_yaml_to_list(merge_flags)

    return PushDetails(
        push_url=push_details_struct['push_url'],
        host_key=push_details_struct.get('host_key', None),
        merge_flags=merge_flags,
        maintainer_groups=parse_yaml_to_list(
            push_details_struct.get('maintainer_groups', [])
        ),
        maintainers=parse_yaml_to_list(
            push_details_struct.get('maintainers', [])
        ),
        anonymous_clone_url=push_details_struct.get('anonymous_clone_url'),
    )


def parse_yaml_to_list(yaml_object):
    """Read a YAML section into a list

    :param object yaml_object: A value that is read from YAML

    Lists can be represented in YAML as YAML lists, as whitespace-separated
    strings or as lists of such strings. If a Mapping is given, the keys will
    be sorted and used as the values in the list.

    :rtype: list
    :returns: A list generated from the YAML object.
    """
    if isinstance(yaml_object, Mapping):
        yaml_object = sorted(yaml_object)
    elif isinstance(yaml_object, string_types):
        yaml_object = [yaml_object]
    elif isinstance(yaml_object, Iterable):
        pass
    else:
        yaml_object = [str(yaml_object)]
    return list(chain.from_iterable(str(x).split() for x in yaml_object))


def check_if_similar_patch_pushed(push_details, branch):
    """
    Check if same patch has already been pushed

    :param PushDetails push_details: Details about where we're pushing the
                                     patch to

    :param: str branch: The branch that the change would be pushed to.
        Required since the same change, which will produce the same checksum,
        can be sent to multiple branches.

    Avoiding push of patches that had already been pushed and hadn't been
    merged yet.  These patches has a md5 checksum hash in the commit message.
    It'll check whether the current sources file md5 hash is part of commit
    message of a patch that had already been pushed to branch.

    :rtype: boolean
    :returns: True if patch exists and false if not
    """
    checksum = get_patch_header('x-md5')
    project = \
        re.sub('^/?(.*?)(.git)?$', '\\1', urlparse(push_details.push_url).path)
    project_param = "project:{project}".format(project=project)
    msg_param = 'message:{checksum}'.format(checksum=checksum)
    branch_param = 'branch:{branch}'.format(branch=branch)
    output = gerrit_cli(
        push_details,
        'query', '--format=JSON', project_param, msg_param, branch_param
    )
    return (
        output
        and json.loads(output.splitlines()[-1]).get('rowCount', 0) >= 1
    )


def get_patch_owner(push_details, commit='HEAD'):
    """Get the Gerrit username for the owner of the given commit

    :param PushDetails push_details: Details about where we're pushing the
                                     patch to
    :param str commit:               (Optional) A commit ref for a commit in
                                     $PWD, Defaults to HEAD.
    :rtype: str
    :returns: The Gerrit username for the owner of the patchset that includes
              the given commit
    """
    git_hash = git_rev_parse(commit)
    change_json_lines = gerrit_cli(
        push_details, 'query', '--format=json', 'commit:' + git_hash
    ).splitlines()
    if len(change_json_lines) <= 1:
        return None
    change = json.loads(change_json_lines[0])
    return change['owner']['username']


def gerrit_user_in_group(push_details, user, group):
    """Returns True if given user is in given group in Gerrit

    :param PushDetails push_details: Details about where we're pushing the
                                     patch to
    :param str user:                 The name of the user to look for
    :param str group:                The name of the group to check

    :rtype: bool
    :returns: True if the user is a member of the given group
    """
    lsm_out = gerrit_cli(push_details, 'ls-members', '--recursive', group)
    lsm_out = lsm_out.splitlines()
    if len(lsm_out) <= 1:
        # Empty or non-existant group
        return False
    lsm_out_table = (l.split('\t') for l in lsm_out)
    next(lsm_out_table)
    member_usernames = (username for _, username, _, _ in lsm_out_table)
    member_usernames = set(member_usernames)
    return user in member_usernames


def gerrit_cli(push_details, *cli_args):
    """
    Run Gerrit CLI commands

    :param PushDetails push_details: Details about the Gerrit host to talk to
    :param list cli_args:            Arguments to the Gerrit CLI

    :rtype: str
    :returns: The output of the invoked command. A CalledProcessError exception
              will be raised if the command fails
    """
    server, _, port = urlparse(push_details.push_url).netloc.rpartition(':')
    if not port:
        port = '29418'
    cmd_list = ('ssh', '-p', port, server, 'gerrit') + cli_args
    logger.debug("executing: %s" % ' '.join(cmd_list))
    process = Popen(cmd_list, stdout=PIPE, stderr=PIPE)
    output, error = process.communicate()
    output = output.decode('utf-8')
    retcode = process.poll()
    logger.debug("'ssh' exited with status: %d", retcode, extra={'blocks': (
        ('stderr', error.decode('utf-8')), ('stdout', output)
    )},)
    if retcode:
        raise CalledProcessError(retcode, cmd_list)
    return output


def get_patch_header(header, default=None, commit='HEAD'):
    """Get the value of a given header in the given commit in $PWD

    :param str header:  The name of the header which value we want to get
    :param str default: A default value to return if the give header is not
                        found. If this is not set, an KeyError exception will
                        be thrown instead of returning a value.
    :param str commit:  (Optional) The commit to look for headers in. Defaults
                        to HEAD.

    :rtype: str
    :returns: The value of the given header if specified in the commit message
              of the HEAD commit in $CWD
    """
    try:
        msg_lines = git('log', '-1', '--pretty=format:%b', commit).splitlines()
    except GitProcessError:
        raise KeyError("Commit ref '{0}' not found".format(commit))
    header_value = next((
        line[len(header) + 2:] for line in msg_lines
        if line.startswith(header + ': ')
    ), None)
    if header_value is None:
        if default is None:
            raise KeyError(
                "Header: '{0}' not found in ref: '{1}'".format(header, commit)
            )
        else:
            return default
    return header_value


def patch_header_is_true(header, commit='HEAD'):
    """Check if given commit message header of given commit is set to true

    :param str header:  The name of the header which value we want to check
    :param str commit:  (Optional) The commit to look for headers in. Defaults
                        to HEAD.
    :rtype: bool
    :returns: True if the header exists and is set to 'true' or 'on' (case
              insensitive)
    """
    hdr_val = get_patch_header(header, 'no', commit).lower()
    logger.info("Header: '%s' resolved to '%s'", header, hdr_val)
    return hdr_val in ['true', 'yes']


def get_patch_sha():
    """Get the hash of HEAD in $PWD

    :rtype: str
    """
    return git('log', '-1', '--pretty=format:%H')


def add_key_to_known_hosts(key):
    """
    Add a given host key to known_hosts if its not there already

    :param string key: ssh host key for known_hosts file
    """
    ssh_folder = os.path.expanduser('~/.ssh/')
    if not os.path.exists(ssh_folder):
        logger.debug("Creating directory: '%s'", ssh_folder)
        os.mkdir(ssh_folder, 0o766)

    known_hosts_file = os.path.join(ssh_folder, 'known_hosts')
    with open(known_hosts_file, 'a+') as known_hosts:
        known_hosts.seek(0)
        if key in (line.rstrip() for line in known_hosts.readlines()):
            logger.debug(
                "SSH host key for '%s' already in '%s'",
                key.split(None, 1)[0], known_hosts_file
            )
            return

        logger.info(
            "Adding SSH host key for '%s' to '%s'",
            key.split(None, 1)[0], known_hosts_file
        )
        known_hosts.write("{0}\n".format(key))


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it

    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = level


if __name__ == '__main__':
    exit(main())
