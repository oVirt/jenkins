#!/usr/bin/env python
"""pusher.py - A tool for automated pushing of patches to SCMs
"""
from __future__ import absolute_import, print_function
import sys
import argparse
import logging
import logging.handlers
import os
import re
import yaml
import json
from copy import copy
from collections import namedtuple, Iterable, Mapping
from itertools import chain
from six import iteritems, string_types
from traceback import format_exception
from subprocess import Popen, CalledProcessError, STDOUT, PIPE


logger = logging.getLogger(__name__)

DEFAULT_PUSH_MAP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    'data', 'git-push-url-map.yaml'
)

PushDetails = namedtuple('Push_details', 'push_url host_key')


class PushMapError(Exception):
    pass


class PushMapIOError(PushMapError):
    pass


class PushMapSyntaxError(PushMapError):
    pass


class PushMapMatchError(PushMapError):
    pass


def main():
    args = parse_args()
    try:
        setup_console_logging(args, logger)
        args.handler(args)
        return 0
    except IOError as e:
        logger.exception('%s: %s', e.strerror, e.filename)
    except Exception as e:
        logger.exception("%s", e.message)
    return 1


def parse_args():
    parser = argparse.ArgumentParser(
        description='Tool for automated pushing of patches to SCMs'
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers()
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
    return parser.parse_args()


def add_logging_args(parser):
    """Add logging-related command line argumenets

    :param ArgumentParser parser: An argument parser to add the parameters to
    """
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='provide verbose output'
    )
    parser.add_argument(
        '-d', '--debug', action='store_true', help='provide debugging output'
    )
    parser.add_argument(
        '--log', nargs='?', const=sys.stderr, help=(
            'Log to the specified file. If no filename is specified, output'
            ' the regular output messages to STDERR in full log format.'
        )
    )


def setup_console_logging(args, logger=None):
    """Configure logging for when running as a console app

    :param argparse.Namespace args: Argument parsing results for an
                                    ArgumentParser object to which
                                    add_logging_args had been applied.
    :param logging.Logger logger:   (Optional) A logger to apply configuration
                                    to. If unspecified, configuration will be
                                    applied to the root logger.
    """
    if logger is None:
        logger = logging.getLogger()
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = logging.WARN
    logger.setLevel(level)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(ExceptionHider('%(message)s'))
    logger.addHandler(stderr_handler)
    if args.log is None:
        pass
    elif args.log == sys.stderr:
        stderr_handler.setFormatter(ExceptionSpreader(
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s'
        ))
    else:
        file_handler = logging.handlers.WatchedFileHandler(args.log)
        file_handler.setFormatter(ExceptionSpreader(
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s'
        ))
        file_handler.setLevel(1)  # Set lowest possible level
        stderr_handler.setLevel(level)
        logger.setLevel(1)  # Set lowest possible level
        logger.addHandler(file_handler)


def push_main(args):
    push_to_scm(
        dst_branch=args.branch,
        push_map=args.push_map,
        if_not_exists=args.if_not_exists,
        unless_hash=args.unless_hash,
    )


def push_to_scm(dst_branch, push_map, if_not_exists=True, unless_hash=None):
    """Push commits to the specified remote branch

    :param str dst_branch:    The target remote branch to push changes into.
                              What this means in practice depends on the type
                              of remote SCM server being pushed to.
    :param str push_map:      The path to a file containing information about
                              remote SCM servers that is needed to push changes
                              to them.
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
    if if_not_exists and check_if_similar_patch_pushed(push_details):
        logger.info('Found similar patch in SCM server, not pushing')
        return
    dest_to_push_to = 'HEAD:refs/for/{0}'.format(dst_branch)
    logger.info("Push to: '%s' at '%s'", push_details.push_url, dest_to_push_to)
    git('push', push_details.push_url, dest_to_push_to)


def read_push_details(push_map):
    """Read information about how to push commits to remote SCM server

    :param str push_map: A path to where the push map file, that describes how
                         to push to various remote SCMs, can be found.

    :rtype: PushDetails
    :returns: Details from the push_map file describing how to push commits
              made to the repo at $PWD
    """
    try:
        with open(push_map, 'r') as stream:
            push_map_data = yaml.safe_load(stream)
    except IOError as e:
        raise PushMapIOError("Failed to read push map: '{0}'".format(e))
    except yaml.MarkedYAMLError as e:
        e.problem_mark.name = push_map
        raise PushMapSyntaxError("Failed to parse push map: '{0}'".format(e))
    except yaml.YAMLError as e:
        raise PushMapSyntaxError("Failed to parse push map: '{0}'".format(e))
    remote_url = get_remote_url_from_ws()
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

        return PushDetails(match_obj.expand(push_details.push_url),
                           push_details.host_key)

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

    host_key = push_details_struct.get('host_key', '')

    return PushDetails(push_details_struct['push_url'], host_key)


def check_if_similar_patch_pushed(push_details):
    """
    Check if same patch has already been pushed

    :param PushDetails push_details: Details about where we're pushing the
                                     patch to

    Avoiding push of patches that had already been pushed and hadn't been
    merged yet.  These patches has a md5 checksum hash in the commit message.
    It'll check wether the current sources file md5 hash is part of commit
    message of a patch that had already been pushed

    :rtype: boolean
    :returns: True if patch exists and false if not
    """
    checksum = get_patch_header('x-md5')
    url = push_details.push_url
    url_list = url.split('/')
    server_url = url_list[2].split(':')[0]
    project = "/".join(url_list[3:]).replace('.git', '')
    project_param = "project:{project}".format(project=project)
    msg_param = 'message:{checksum}'.format(checksum=checksum)
    cmd_list = ['ssh', '-p', '29418', server_url, 'gerrit', 'query',
                '--format=JSON', 'status:open', project_param, msg_param]
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

    return (
        output
        and json.loads(output.splitlines()[-1]).get('rowCount', 0) >= 1
    )


def get_patch_header(header, default=None):
    """Get the value of a given header in the topmost patch in $PWD

    :param str header:  The name of the header which value we want to get
    :param str default: A default value to return if the give header is not
                        found. If this is not set, an KeyError excepction will
                        be thrown instead of returning a value.

    :rtype: str
    :returns: The value of the given header if specified in the commit message
              of the HEAD commit in $CWD
    """
    msg_lines = git('log', '-1', '--pretty=format:%b').splitlines()
    header_value = next((
        line[len(header) + 2:] for line in msg_lines
        if line.startswith(header + ': ')
    ), None)
    if header_value is None:
        if default is None:
            raise KeyError(
                "Header: '{0}' not found in HEAD commit".format(header)
            )
        else:
            return default
    return header_value


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
    logger.debug("Executing command: '%s'", ' '.join(git_command))
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


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it

    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = level


class BlockFormatter(logging.Formatter):
    """A log formatter that knows how to handle text blocks that are embedded
    in the log object
    """
    def format(self, record):
        """Called by the logging.Handler object to do the actual log formatting

        :param logging.LogRecord record: The log record to be formatted

        This format generates extra log lines to display text blocks embedded
        in the log object as indented text

        :rtype: str
        :returns: The string to be written to the log
        """
        blocks = getattr(record, 'blocks', None)
        if blocks is None:
            return super(BlockFormatter, self).format(record)
        out_rec = copy(record)
        exc_info = out_rec.exc_info
        out_rec.exc_info = None
        out = [super(BlockFormatter, self).format(out_rec)]
        for block in self._iter_blocks(blocks):
            if isinstance(block, string_types):
                title, text = None, block
            elif isinstance(block, Iterable) and len(block) == 2:
                title, text = block
            else:
                title, text = None, block
            if title is not None:
                out.append(self._log_line(out_rec, '  ---- %s ----', title))
            for line in text.splitlines():
                out.append(self._log_line(out_rec, '    %s', line))
        if exc_info:
            out.append(self.formatException(exc_info))
        return '\n'.join(out)

    def _iter_blocks(self, blocks):
        """Returns an iterator over any text blocks added to a log record

        :param object blocks: An object representing text blocks, may be a
                              single string, a Mapping an Iterable or any other
                              object that can be converted into a string.
        :rtype: Iterator
        :returns: An iterator over blocks where each block my be either
                  a string or a pair if a title string and a text string.
        """
        if isinstance(blocks, string_types):
            return iter((blocks,))
        elif isinstance(blocks, Mapping):
            return iteritems(blocks)
        elif isinstance(blocks, Iterable):
            return blocks
        else:
            return iter((str(blocks),))

    def _log_line(self, mut_rec, msg, line):
        """format a single log line using the superclass formatter

        :param logrecord mut_rec: a logrecord object that is allowed to be
                                  mutated and contains the extra data about the
                                  message we're logging
        :param str msg:           a logger format string for the line to format
        :param str line:          the log line to format
        :type: str
        :returns: a formatted log line
        """
        mut_rec.msg = msg
        mut_rec.args = (line,)
        return super(BlockFormatter, self).format(mut_rec)


class ExceptionSpreader(BlockFormatter):
    """A log formatter that takes care of properly formatting exception objects
    if they are attached to logs
    """
    def format(self, record):
        """Called by the logging.Handler object to do the actual log formatting

        :param logging.LogRecord record: The log record to be formatted

        This formatter converts the embedded excpetion opbject into a text
        block and the uses the BlockFormatter to display it

        :rtype: str
        :returns: The string to be written to the log
        """
        if record.exc_info is None:
            return super(ExceptionSpreader, self).format(record)
        out_rec = copy(record)
        out_rec.exc_info = None
        if getattr(out_rec, 'blocks', None) is None:
            out_rec.blocks = format_exception(*record.exc_info)
        else:
            out_rec.blocks = chain(
                self._iter_blocks(out_rec.blocks),
                (('excpetion', ''.join(format_exception(*record.exc_info))),)
            )
        return super(ExceptionSpreader, self).format(out_rec)


class ExceptionHider(BlockFormatter):
    """A log formatter that ensures that exception objects are not dumped into
    the logs
    """
    def format(self, record):
        """Called by the logging.Handler object to do the actual log formatting

        :param logging.LogRecord record: The log record to be formatted

        This formatter essentially strips away any embedded exception objects
        from the record objects.

        :rtype: str
        :returns: The string to be written to the log
        """
        if record.exc_info is None:
            return super(ExceptionHider, self).format(record)
        out_rec = copy(record)
        out_rec.exc_info = None
        return super(ExceptionHider, self).format(out_rec)


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
        return git('rev-parse', ref).rstrip()
    except GitProcessError as e:
        if e.returncode == 128:
            raise InvalidGitRef(
                "Invalid Git ref given: '{0}'".format(ref), ref
            )
        else:
            raise


if __name__ == '__main__':
    exit(main())
