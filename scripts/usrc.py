#!/usr/bin/env python
"""usrc.py - A tool for handling upstream source dependencies
"""
from __future__ import absolute_import, print_function
import argparse
import sys
import os
import logging
import logging.handlers
import yaml
from copy import copy
from hashlib import sha1, md5
from xdg.BaseDirectory import xdg_cache_home
from time import time
from socket import gethostbyname, gethostname
from subprocess import Popen, CalledProcessError, STDOUT, PIPE
from six import string_types, iteritems
from six.moves import zip
from collections import Iterable, Mapping
from itertools import chain, tee
from traceback import format_exception
from textwrap import dedent
from pprint import pformat


UPSTREAM_SOURCES_FILE = 'upstream_sources.yaml'
UPSTREAM_SOURCES_PATH = os.path.join('automation', UPSTREAM_SOURCES_FILE)
CACHE_NAME = 'usrc'

logger = logging.getLogger(__name__)


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
        description='Upstream source dependency handling tool'
    )
    add_logging_args(parser)
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


def get_main(args):
    get_upstream_sources()


def update_main(args):
    updates = update_upstream_sources()
    if args.commit:
        commit_upstream_sources_update(updates)


class GitUpstreamSource(object):
    """A class representing Git-based upstream source dependencies
    """
    def __init__(self, url, branch, commit, automerge='no'):
        self.url, self.branch, self.commit = url, branch, commit
        if isinstance(automerge, string_types):
            if automerge.lower() in ('yes', 'true'):
                self.automerge = 'yes'
            elif automerge.lower() == 'never':
                self.automerge = 'never'
            else:
                self.automerge = 'no'
        else:
            self.automerge = 'yes' if automerge else 'no'
        cache_dir_name = sha1(url.encode('utf-8')).hexdigest()
        cache_dir = os.path.join(xdg_cache_home, CACHE_NAME, cache_dir_name)
        self._cache_dir = cache_dir
        self._cache_git_dir = os.path.join(cache_dir, '.git')
        logger.debug("Got upstream source: '%s'", self.url, extra={
            'blocks': pformat(self.to_yaml_struct())
        })

    def _cache_git(self, *args):
        return git('--git-dir=' + self._cache_git_dir, *args)

    def _init_cache(self):
        git('init', self._cache_dir)

    @classmethod
    def from_yaml_struct(cls, struct):
        """Initialise instance from a structure read from yaml

        :rtype: GitUpstreamSource
        """
        return cls(
            struct['url'],
            struct['branch'],
            struct['commit'],
            struct.get('automerge', 'no'),
        )

    def to_yaml_struct(self):
        """Return a structure representing this source that is safe for saving
        to YAML

        :rtype: dict
        """
        struct = dict(url=self.url, branch=self.branch, commit=self.commit)
        if self.automerge != 'no':
            struct['automerge'] = self.automerge
        return struct

    def get(self, dst_path):
        """Get the upstream source into the given path

        :param str dst_path: The path to get source into
        """
        # TODO: check if git_commit is already available locally and skip
        #       fetching
        self._fetch()
        self._cache_git(
            '--work-tree=' + dst_path,
            'checkout', self.commit, '-f',
        )

    def updated(self):
        """Look for the most up-to-date commit of the upstream source

        :returns: A new GitUpstreamSource instance representing the updated
            source. If self is already pointing to the most updated commit,
            returns self
        :rtype: GitUpstreamSource
        """
        self._fetch()
        latest_commit = self._cache_git(
            'rev-parse', 'refs/remotes/origin/{0}'.format(self.branch)
        ).strip()
        if not isinstance(latest_commit, str):
            # We normalize unicode output into an Ascii string because we know
            # git SHAs are only hex numbers and therefore only contain Ascii
            # characters.
            # We need to do this so we don't get strange unicode flags in YAML
            # we produce form Python2
            latest_commit = latest_commit.encode('ascii', 'ignore')
        if latest_commit == self.commit:
            return self
        logger.info(
            "Latest commit updated for branch '%s' in repo '%s'",
            self.branch, self.url
        )
        return self.__class__(
            self.url, self.branch, latest_commit, self.automerge
        )

    def _fetch(self):
        """Fetch the remote branch into the local cache
        """
        self._init_cache()
        self._cache_git(
            'fetch', '--tags', self.url,
            '+{0}:refs/remotes/origin/{0}'.format(self.branch)
        )

    @property
    def commit_title(self):
        """Return the title of the latest commit of the upstream source

        :rtype: str
        """
        self._fetch()
        ttl = self._cache_git('log', '-1', '--pretty=format:%s', self.commit)
        if not isinstance(ttl, str):
            ttl = ttl.encode('utf-8', 'ignore')
        return dedent(ttl)

    @property
    def commit_details(self):
        """Return a big string with details about the latest commit of the
        upstream source

        :rtype: str
        """
        self._fetch()
        git_format = dedent(
            '''
            Project: {0}
            Branch:  {1}
            Commit:  %H
            Author:  %an
            Date:    %ad

            %w(0,4,4)%s

            %w(0,4,4)%b
            '''
        ).strip().format(self.url, self.branch)
        msg = self._cache_git(
            'log', '-1', '--date=rfc',
            '--pretty=format:' + git_format, self.commit
        )
        if not isinstance(msg, str):
            msg = msg.encode('utf-8', 'ignore')
        return dedent(msg)


def load_upstream_sources():
    """Load upstream source objects from configuration file

    :rtype: tuple
    """
    sources_doc = read_yaml_to_obj(UPSTREAM_SOURCES_PATH)
    if not sources_doc:
        return tuple()

    return tuple(
        GitUpstreamSource.from_yaml_struct(obj)
        for obj in sources_doc.get('git', [])
    )


def save_upstream_sources(upstream_sources):
    """Save upstream objects to YAML

    :param Iterable upstream_sources: A collection of upstream source objects
    """
    sources_doc = dict(
        git=[usrc.to_yaml_struct() for usrc in upstream_sources]
    )
    with open(UPSTREAM_SOURCES_PATH, 'w') as stream:
        yaml.dump(sources_doc, stream, default_flow_style=False)


def get_upstream_sources():
    """Download the US sources listed in upstream_sources.yaml
    """
    upstream_sources = load_upstream_sources()
    dst_path = os.getcwd()

    for usrc in upstream_sources:
        usrc.get(dst_path)

    # the below code will 'prefer' ds changes over us ones
    git(
        '--git-dir=' + os.path.join(dst_path, '.git'),
        '--work-tree=' + dst_path,
        "reset", "--hard",
    )


def update_upstream_sources():
    """Update the commit hashes for US sources listed in upstream_sources.yaml
    """
    upstream_sources = load_upstream_sources()

    updated_sources, us2 = tee(usrc.updated() for usrc in upstream_sources)
    modified_sources, ms2 = tee(
        new for new, old in zip(us2, upstream_sources) if new != old
    )
    has_changed = next((True for ms in ms2), False)
    if not has_changed:
        return modified_sources

    save_upstream_sources(updated_sources)
    return modified_sources


def commit_upstream_sources_update(updates):
    """Commit updates made to the upstream_sources.yaml file

    :param Iterable updates: Iterator over upstream source objects representing
                             sources that were updated
    """
    updates = list(updates)
    if not updates:
        # Skip committing if upstream_sources.yaml not changed
        return
    if check_if_branch_exists('commit_branch'):
        git('branch', '-D', 'commit_branch')
    git('checkout', '-b', 'commit_branch')
    with open(UPSTREAM_SOURCES_PATH, 'r') as stream:
        checksum = md5(stream.read().encode('utf-8')).hexdigest()
    git('add', UPSTREAM_SOURCES_PATH)
    commit_message = generate_update_commit_message(updates)
    commit_message = generate_gerrit_message(commit_message, checksum)
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


def generate_update_commit_message(updates):
    """Generate the commit message for an update commit

    :param Iterable updates: Iterator over upstream source objects representing
                             sources that were updated
    :rtype: str
    :returns: commit message with update information
    """
    updates = list(updates)
    if len(updates) == 1:
        message = dedent(
            '''
            Updated US source to: {commit_hash:.7} {commit_title}

            Updated upstream source commit.
            Commit details follow:

            {commit_details}

            '''
        ).lstrip().format(
            commit_hash=updates[0].commit,
            commit_title=updates[0].commit_title,
            commit_details=updates[0].commit_details,
        )
    else:
        message = dedent(
            '''
            Updated {count} upstream sources

            Updated upstream source commits.
            Updated commit details follow:

            {commit_details}

            '''
        ).lstrip().format(
            count=len(updates),
            commit_details="\n\n".join(u.commit_details for u in updates),
        )
    print('checking AM')
    print([u.automerge for u in updates])
    if any(True for update in updates if update.automerge == 'yes'):
        print('found yes')
        if all(update.automerge != 'never' for update in updates):
            print('not found never')
            message += 'automerge: yes\n'

    return message


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
    message_template = '{message}x-md5: {md5}\nChange-Id: I{change_id}'

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
        """Returns an iterator over any text blocks added to a log record

        :param object blocks: An object representing text blocks, may be a
                              single string, a Mapping an Iterable or any other
                              object that can be converted into a string.
        :rtype: Iterator
        :returns: An iterator over blocks where each block my be either
                  a string or a pair if a title string and a text string.
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


if __name__ == '__main__':
    exit(main())
