#!/usr/bin/env python
"""usrc.py - A tool for handling upstream source dependencies
"""
from __future__ import absolute_import, print_function
import argparse
import sys
import os
from os.path import normpath, join, dirname, abspath
import logging
import logging.handlers
import yaml
from copy import copy
from hashlib import sha1, md5
from xdg.BaseDirectory import xdg_cache_home
from time import time
from socket import gethostbyname, gethostname
from subprocess import Popen, CalledProcessError, STDOUT, PIPE
from six import string_types, iteritems, viewkeys, itervalues
from six.moves import zip, reduce
from collections import Iterable, Mapping, Set, namedtuple, OrderedDict
from itertools import chain, tee
from traceback import format_exception
from textwrap import dedent
from pprint import pformat
from operator import or_
from functools import cmp_to_key, wraps
from contextlib import contextmanager
from collections import namedtuple
try:
    from stdci_tools.pusher import (
        DEFAULT_PUSH_MAP, read_push_details, add_key_to_known_hosts
    )
except ImportError as e:
    sys.path.append(dirname(dirname(abspath(normpath(__file__)))))
    try:
        from stdci_tools.pusher import (
            DEFAULT_PUSH_MAP, read_push_details, add_key_to_known_hosts
        )
    except (ImportError, ValueError):
        # avoid edge case
        DEFAULT_PUSH_MAP = \
            'THIS FEATURE IS DISABLED BECAUSE PUSHER WAS NOT IMPORTED'
try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO


def only_if_imported_any(*modules):
    """A decorator that disables functions if some module was not imported.

    This decorator can be used to disable and raise an exception if a function
    that requires a certain module to be imported was called but the module was
    not imported.

    :params str modules: The modules to check for being imported. If at least
                         one module of the provided ones was imported, we're ok
    """
    def original_or_error(func):
        @wraps(func)
        def error(*args, **kwargs):
            # print(sys.modules)
            print(sys.path)
            raise RuntimeError(
                '{fname} is disabled because none of {modules} were imported.'
                .format(fname=func.__name__, modules=modules)
            )
        if (not modules) or (set(modules) & set(sys.modules)):
            return func
        return error
    return original_or_error


UPSTREAM_SOURCES_FILE = 'upstream_sources.yaml'
UPSTREAM_SOURCES_FILE_LOOKUP_DIRS = ('', 'automation')
CACHE_NAME = 'usrc'
POLICIES = ('static', 'tagged', 'latest')
TagObject = namedtuple('TagObject', ['commit', 'annotated', 'name'])
# UpstreamSourcesConfigPath allows us to keep track of configs and where
# we found them
UpstreamSourcesConfigPath = namedtuple(
    'UpstreamSourcesConfigPath', ('stream', 'path')
)
logger = logging.getLogger(__name__)


class UnkownDestFormatError(Exception):
    pass


class UpstreamSourcesConfigNotFound(Exception):
    pass


@contextmanager
def upstream_sources_config(**kwargs):
    """Context manager to find the first upstream sources config. Currently,
    two config sources are supported:
    - filepath:   will load the config from the given filepath
    - git object: will load the config from the given filepath at the specified
                  commit.

    Supported named args:
    :param str commit: the commit to load the file from.
    :param str mode:   the mode to load the file at.

    If commit is specified, will use git object provider to lookup for the file
    Otherwise, will use filepath. If mode is ommited, will use 'r' as default.
    """
    config_provider = filepath_config_provider
    commit = kwargs.get('commit')
    if commit:
        config_provider = git_object_config_provider
    elif not kwargs.get('mode'):
        kwargs['mode'] = 'r'

    for lookup_dir in UPSTREAM_SOURCES_FILE_LOOKUP_DIRS:
        usrc_cfg = join(lookup_dir, UPSTREAM_SOURCES_FILE)
        try:
            with config_provider(usrc_cfg, **kwargs) as config_file:
                logger.debug('using upstream sources config: %s', usrc_cfg)
                yield UpstreamSourcesConfigPath(config_file, usrc_cfg)
            break
        except IOError as io_error:
            # errno 2 => file not found
            if io_error.errno != 2:
                raise
            logger.debug('not found upstream sources config at %s', usrc_cfg)
        except GitProcessError:
            logger.debug(
                'not found upstream sources config from commit %s at %s',
                commit, usrc_cfg
            )
    else:
        raise UpstreamSourcesConfigNotFound()


@contextmanager
def filepath_config_provider(path, mode, **kwargs):
    """Load a file from the given path with the requested mode.

    This context manager is a shim to allow single interface between all config
    providers.

    :param str path:    path to the file we want to load
    :param str mode:    mode to open the file with
    :param dict kwargs: it's here just to fulfull the interface
    """
    with open(path, mode) as usrc_config:
        yield usrc_config


@contextmanager
def git_object_config_provider(path, commit, **kwargs):
    """Load a file from the given path at the given commit

    This context manager is a shim to allow single interface between all config
    providers.

    :param str path:    path to the file we want to load
    :param str mode:    mode to open the file with
    :param dict kwargs: it's here just to fulfull the interface

    Raises:
        GitProcessError: if for any reason we failed to process the git object
    """
    # To avoid edge cases in the general config provider context manager,
    # we always yield a TextIO-like object.
    file_from_commit = StringIO(git_read_file(path, commit))
    try:
        yield file_from_commit
    finally:
        file_from_commit.close()


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
    subparsers = parser.add_subparsers(dest='COMMAND')
    subparsers.required = True
    get_parser = subparsers.add_parser(
        'get', help='Download upstream sources',
        description=(
            'Download upstream sources as listed in upstream_sources.yaml'
            ' and merge them into the local directory'
        ),
    )
    get_parser.set_defaults(handler=get_main)
    get_parser.add_argument(
        '--push-map', default=DEFAULT_PUSH_MAP,
        help=(
            'Path to a push map YAML file that specifies details about how'
            ' to connect to the remote SCM servers and push changes.'
        ),
    )
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
    modify_entries_parser = subparsers.add_parser(
        'modify-entries',
        help='Update or create new upstream source entries',
        description=(
            'Specify multiple, IFS separated, upstream source entries in a'
            ' form of JSON or YAML. If an upstream source with the same repo'
            ' url and branch exists, it will be replaced in place with the new'
            ' one. Otherwise, the new entries will be appeneded in the same'
            ' order as they were specified at the end of the config.'
        ),
    )
    modify_entries_parser.add_argument(
        'entries', type=str, nargs='+',
        help='IFS separated upstream source entries'
    )
    modify_entries_parser.set_defaults(handler=modify_entries_main)
    modify_entries_parser.add_argument(
        '--commit', action='store_true',
        help=(
            'Commit the upstream_sources.yaml change locally.'
            ' This will create a branch called "commit_branch" and commit'
            ' the upstream_sources.yaml change into it. The branch will be'
            ' overwritten if it already exists'
        )
    )
    changed_files_parser = subparsers.add_parser(
        'changed-files', help='List files changed between commits',
        description=(
            'List all the files that were changed between commits to the'
            ' source code in $PWD, including changes that were actually made'
            ' to upstream sources'
        )
    )
    changed_files_parser.add_argument(
        'new_commit', nargs='?', default='HEAD',
        help='The commit to look for changed files in, defaults to HEAD'
    )
    changed_files_parser.add_argument(
        'old_commit', nargs='?', default=None,
        help=(
            'The commit to look for changed files from, defaults to the'
            ' commit before the one given in NEW_COMMIT'
        )
    )
    changed_files_parser.add_argument(
        '--resolve-links', '-l', action='store_true', default=False,
        help=(
            'If specifed, will treat symlinks in \'new_commit\' that links'
            ' to a modified files as a modfieid file.'
        )
    )
    changed_files_parser.set_defaults(handler=changed_files_main)
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
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s:%(funcName)s'
        ))
    else:
        file_handler = logging.handlers.WatchedFileHandler(args.log)
        file_handler.setFormatter(ExceptionSpreader(
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s:%(funcName)s'
        ))
        file_handler.setLevel(1)  # Set lowest possible level
        stderr_handler.setLevel(level)
        logger.setLevel(1)  # Set lowest possible level
        logger.addHandler(file_handler)


def get_main(args):
    get_upstream_sources(args.push_map)


def update_main(args):
    updates, config_path = update_upstream_sources()
    if args.commit:
        commit_upstream_sources_update(updates, config_path)


def changed_files_main(args):
    for file_name in get_modified_files(
        args.new_commit, args.old_commit, args.resolve_links
    ):
        print(file_name)


def modify_entries_main(args):
    usrc, config_path = load_upstream_sources()
    usrc_to_set = (
        GitUpstreamSource.from_yaml_struct(yaml.safe_load(entry))
        for entry in args.entries
    )
    modified_entries = set_upstream_source_entries(usrc, usrc_to_set)
    save_upstream_sources(modified_entries, config_path)
    if args.commit:
        commit_upstream_sources_update(modified_entries, config_path)


def set_upstream_source_entries(usrc_orig, usrc_to_set):
    """Set upstream source entries in the upstream_sources config

    :param Iterable usrc_orig: The original GitUpstreamSource objects. Objects
                               in this iterable will be overwritten by those
                               provided to set.
    :param Iterable usrc_to_set: GitUpstreamSource objects to set. If one
                                 exists already in `usrc`, it will be replaced.
                                 Otherwise, it will be appended to the end of
                                 the list.

    :returns: Tuple of the modified GitUpstreamSource objects.
    """
    def usrc_to_key(usrc):
        return (usrc.url, usrc.branch)

    try:
        sources_to_set = OrderedDict(
            (usrc_to_key(usrc), usrc) for usrc in usrc_to_set
        )
    except yaml.parser.ParserError as parser_error:
        raise yaml.parser.ParserError(
            'Exception while trying parse one of the upstream sources:\n'
            '{details}'.format(details=str(parser_error))
        )
    modified_sources = tuple(
        sources_to_set.pop(usrc_to_key(usrc), usrc) for usrc in usrc_orig
    )
    new_sources = tuple(sources_to_set.values())
    return modified_sources + new_sources


class GitUpstreamSource(object):
    """A class representing Git-based upstream source dependencies

    :params : dict dest_formats - destination formats.
    :params : update_policy - the latest or tagged policy to be updated.
    :params : tag_filter - used to filter to specific tags you like.
    :params : annotated_tag_only - used to pick only annotated tags.
    """

    _dest_fmt_default = {'files': None}

    def __init__(
        self, url, branch, commit, automerge='no', dest_formats=None,
        files_dest_dir='', update_policy=None, tag_filter=None,
        annotated_tag_only=None
    ):
        self.url, self.branch, self.commit = url, branch, commit
        self.dest_formats = dest_formats or self._dest_fmt_default
        self._validate_dst_fmt_exists()
        self.files_dest_dir = files_dest_dir
        if update_policy:
            self.update_policy = update_policy
        else:
            self.update_policy = ('latest')
        self.tag_filter = tag_filter

        if isinstance(annotated_tag_only, string_types):
            self.annotated_tag_only = (annotated_tag_only == 'yes')
        elif isinstance(annotated_tag_only, bool):
            self.annotated_tag_only = annotated_tag_only
        elif annotated_tag_only is None:
            self.annotated_tag_only = False
        else:
            raise ConfigError(
                'annotated_tag_only field should contain a string or a boolean'
            )

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
            struct.get('dest_formats'),
            struct.get('files_dest_dir', ''),
            struct.get('update_policy', ('latest')),
            struct.get('tag_filter', None),
            struct.get('annotated_tag_only', 'no'),
        )

    def to_yaml_struct(self):
        """Return a structure representing this source that is safe for saving
        to YAML

        :rtype: dict
        """
        struct = dict(url=self.url, branch=self.branch, commit=self.commit)
        if self.automerge != 'no':
            struct['automerge'] = self.automerge
        if self.dest_formats != self._dest_fmt_default:
            struct['dest_formats'] = self.dest_formats
        if self.files_dest_dir != '':
            struct['files_dest_dir'] = self.files_dest_dir
        if self.update_policy != ('latest'):
            struct['update_policy'] = self.update_policy
        if self.tag_filter is not None:
            struct['tag_filter'] = self.tag_filter
        if self.annotated_tag_only:
            struct['annotated_tag_only'] = 'yes'
        return struct

    def _files_format_handler(self, dst_path, files_dest_dir=None, **kwargs):
        """Get the upstream source into the given path
        """
        dst_dir = files_dest_dir or self.files_dest_dir
        if dst_dir != '':
            dst_path = os.path.join(dst_path, dst_dir)
            try:
                os.makedirs(dst_path)
            except OSError:
                pass
        self._cache_git(
            '--work-tree=' + dst_path,
            'checkout', self.commit, '-f',
        )

    @only_if_imported_any('pusher', 'stdci_tools.pusher')
    def _branch_format_handler(self, push_map, **kwargs):
        """Get the upstream source to branch

        :param str push_map: The path to a file containing information
                             about remote SCM servers that is needed to
                             push changes to them.
        :param str push_url: Choose a push url to use from the push_map.
        :param bool gen_source_repos: If set to True, after pushed sources to
                                      a remote branch, propogate the call to
                                      _source_repos_format_handler.
        """
        dst_branch = '_upstream_' + self.branch + '_' + self.commit[0:7]
        push_details = read_push_details(push_map, kwargs.get('push_url'))
        logger.info("Would push to: '%s'", push_details.push_url)
        if push_details.host_key:
            add_key_to_known_hosts(push_details.host_key)
        self._cache_git(
            'push', push_details.push_url,
            '{0}:refs/heads/{1}'.format(self.commit, dst_branch)
        )
        if kwargs.get('gen_source_repos'):
            self._source_repos_format_handler(push_map, **kwargs)

    def _source_repos_format_handler(
        self, push_map, dst_path, files_dest_dir=None, src_repos_file=None,
        **kwargs
    ):
        """Write a source-repos file. If the file already exists, will append to
        it's end.

        :param str push_map:       The path to a file containing information
                                   about remote SCM servers that is needed to
                                   push changes to them.
        :param str dst_path:       Path where the tool was called from.
        :param str files_dest_dir: Destination directory where to place the
                                   source-repos file. If not specified, falls
                                   back to global files_dest_dir and then to
                                   dst_path. Can be used in conjunction with
                                   src_repos_file.
        :param str src_repos_file: Where to write source-repos file. Path must
                                   be is relative to repo's root. Default's
                                   to files_dest_dir. If used in conjunction
                                   with files_dest_dir, files_dest_dir will
                                   prefix the path specified in src_repos_file.
        :param str push_url:       Choose a push url to use from the push_map.


        """
        src_repos_file = src_repos_file or 'source-repos'
        files_dest_dir = files_dest_dir or self.files_dest_dir
        src_repos_file = os.path.join(dst_path, files_dest_dir, src_repos_file)
        self._assert_path_under_root(dst_path, src_repos_file)
        source_repos_dirname = os.path.dirname(src_repos_file)
        try:
            if source_repos_dirname:
                os.makedirs(source_repos_dirname)
        except OSError as os_error:
            if os_error.errno != 17:
                raise  # Directory already exist
        url = read_push_details(
            push_map, kwargs.get('push_url')
        ).anonymous_clone_url
        with open(src_repos_file, 'a') as source_repos:
            source_repos.write(
                '{url} {commit}\n'.format(url=url, commit=self.commit)
            )

    @staticmethod
    def _assert_path_under_root(root_path, file_path):
        """Ensure that the given path is under repo's root

        Due to security reasons, we do not allow writing files outside of the
        project's source dir.

        :param str root_path: Root reference path
        :param str file_path: Path to check is under root
        :raises ConfigError: if the path is not under repo's root
        """
        root_abspath = os.path.abspath(root_path)
        file_abspath = os.path.abspath(file_path)
        if file_abspath.startswith(root_abspath):
            return
        raise ConfigError('{file_path} is not under {root_path}'.format(
            file_path=file_path, root_path=root_path
        ))

    def get(self, dst_path, push_map):
        """Fetch the upstream source and call to the formatters

        :param str dst_path: The path to get source into
        :param str push_map: The path to a file containing information about
                             remote SCM servers that is needed to push changes
                             to them.
        """
        # TODO: check if git_commit is already available locally and skip
        #       fetching
        self._fetch()
        self._call_format_handlers(dst_path, push_map)

    def _call_format_handlers(self, dst_path, push_map):
        """Call all the format handlers as the user specified in the config

        Each format handler get's all the params so it is expected to accept
        **kwargs as a param. The formatter is free to ignore or use whatever
        arguments it needs. The arguments the user specified under the formatter
        will be passed to the handler.

        :param str dst_path: The path to get source into
        :param str push_map: The path to a file containing information about
                             remote SCM servers that is needed to push changes
                             to them.
        """
        for handler_name, handler_params in iteritems(self.dest_formats):
            params = handler_params or {}  # avoid edge case
            formatter = '_{fmt}_format_handler'.format(fmt=handler_name)
            handler = getattr(self, formatter)
            handler(dst_path=dst_path, push_map=push_map, **params)

    def _validate_dst_fmt_exists(self):
        """Validate that all the requested dest formatters exists. If there is a
        missing formatter, will raise an UnknownDestFormatError.
        """
        missing_formatters = [
            fmt for fmt in self.dest_formats
            if not hasattr(self, '_{fmt}_format_handler'.format(fmt=fmt))
        ]
        if not missing_formatters:
            return
        raise UnkownDestFormatError(
            "Unknown destination formatters {missing}.".format(
                missing=missing_formatters))

    def updated(self):
        """Look for the most up-to-date commit or tag of the upstream source
           depending on the user request.

        Currently supported policies:

            - 'latest': will update to the latest HEAD in the referenced branch
            - 'tagged': will updated to the latest tagged commit in the
                        referenced branch. When combined with 'tag_filter',
                        can follow tags of a specified glob pattern.
            - 'static': disable auto update.

        :returns: A new GitUpstreamSource instance representing the updated
            source. If self is already pointing to the most updated commit
            or tag, returns self
        :rtype: GitUpstreamSource
        """
        self._fetch()
        for policy in POLICIES:
            if policy not in self.update_policy:
                continue
            latest_commit = getattr(self, "_update_policy_" + policy)()
            if latest_commit != self.commit:
                logger.info(
                    "Latest {0} commit updated for branch {1} in repo"
                    "{2}".format(policy, self.branch, self.url)
                )
                return self.__class__(
                    self.url, self.branch, latest_commit, self.automerge,
                    self.dest_formats, self.files_dest_dir, self.update_policy,
                    self.tag_filter, self.annotated_tag_only
                )
        return self

    def _update_policy_static(self):
        """Just return the current commit.

        :returns: the current referenced commit.
        :rtype: str
        """
        return self.commit

    def _update_policy_latest(self):
        """Look for the most up-to-date commit of the upstream source

        :returns: latest commit in the upstream source branch.
        :rtype: str
        """
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
        return latest_commit

    def _update_policy_tagged(self):
        """Look for latest tagged of the upstream source

        :returns:   returns the latest tagged commit or self
                    if it is same or newer commit.
        :rtype: str
        """
        tags = self._get_tags()
        # Filtering non-annotated tags if specified.
        if self.annotated_tag_only:
            tags = (tag for tag in tags if 'tag' == tag.annotated)
        # Filtering tagged commits for branch
        tags = [tag for tag in tags if self._tag_in_branch(tag)]
        # The filters filtered all the possible tags, keep the same commit
        if not tags:
            return self.commit
        # Getting latest tagged commit.
        latest_tag = max(tags, key=cmp_to_key(self._commit_cmp))
        # Checking wether the tag is older than the current commit.
        if self._commit_cmp(latest_tag.commit, self.commit) <= 0:
            return self.commit
        return latest_tag.commit

    def _get_raw_tags(self):
        """Return a list of tag details from the cached git repo

        The returned string is in a yaml format.

        :rtype: str
        """
        out = self._cache_git(
            'for-each-ref',
            'refs/tags/' + (self.tag_filter if self.tag_filter else ""),
            '--format',
            '- {"commit": "%(objectname)",'
            '"annotated": "%(objecttype)", "name": "%(refname:short)"}'
        ).strip()

        if not isinstance(out, str):
            return out.encode('ascii', 'ignore')

        return out

    def _get_tags_gen(self, tags_yaml_struct):
        """Create a generator of TagObjects

        :param tags_yaml_struct: A structure that was generated by loading
            a yaml file
        :rtype: gen expr
        """
        return (
            TagObject(
                self._rev_parse(tag['commit']), tag['annotated'], tag['name']
            )
            for tag in tags_yaml_struct
        )

    def _get_tags(self):
        """Create a tagged gen expression to iterate over.

        :returns: returns a gen expr containing the tagged objects.
        :rtype  : gen expr or an empty list if no tags were found
        """
        # _get_raw_tags can return an empty string if no tags were found
        raw_tags = self._get_raw_tags()
        if not raw_tags:
            return []

        return self._get_tags_gen(yaml.safe_load(raw_tags))

    def _tag_in_branch(self, tag):
        """checks wether a tag is in branch meaning they have ancestor commit.

        returns : Returns True/False if tag is in branch.
        rtype   : bool
        """
        return \
            self._merge_base(tag.commit, 'origin/' + self.branch) == tag.commit

    def _commit_cmp(self, a, b):
        """Check if tag_a is newer or older than tag_b.

        :param a: TagStruct object or commit.
        :param b: TagStruct object or commit.
        :returns: 1 if tag_a is newer,
            0 if they are pointing on same commit,
            -1 if tag_a is older than tag_b.
        rtype: int
        """
        commit_a = getattr(a, 'commit', a)
        commit_b = getattr(b, 'commit', b)
        if commit_a == commit_b:
            return 0
        elif self._merge_base(commit_a, commit_b) == commit_a:
            return -1
        return 1

    def _fetch(self):
        """Fetch the remote branch into the local cache
        """
        self._init_cache()
        self._cache_git(
            'fetch', '--tags', self.url,
            '+{0}:refs/remotes/origin/{0}'.format(self.branch)
        )

    def _merge_base(self, object_a, object_b):
        """Returns the ancestor commit between 2 commits.

        :returns : returns the older commit.
        :rtype: str
        """
        if not isinstance(object_a, str):
            object_a = object_a.encode('ascii', 'ignore').rstrip()
        if not isinstance(object_b, str):
            object_b = object_b.encode('ascii', 'ignore').rstrip()
        return self._cache_git(
            'merge-base', object_a, object_b).rstrip()

    def _rev_parse(self, ref):
        """
        Returns a commit sha from a given reference.

        :params  : self - class instance.
        :params  : ref - reference to parse.
        :returns : returns sha of a given ref.
        :rtype   : str
        """
        out = self._cache_git(
            'rev-parse', "{0}^{{commit}}".format(ref)
        ).rstrip()
        if not isinstance(out, str):
            return out.encode('ascii', 'ignore')

        return out

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

    def ls_files(self):
        """Lists the files provided by this upstream source

        :rtype: dict
        :returns: A mapping from file names to tuples of file mode and file
                  checksum
        """
        self._fetch()
        return git_ls_files(self.commit, git_func=self._cache_git)


def load_upstream_sources(commit=None):
    """Load upstream source objects from configuration file

    :param str commit: (Optional) The commit to load the configuration from. If
                       unspecified, will load from $PWD even if uncommitted
    :rtype: tuple
    """
    try:
        with upstream_sources_config(commit=commit) as config_path:
            return (
                parse_upstream_sources(config_path.stream, config_path.path),
                config_path.path
            )
    except UpstreamSourcesConfigNotFound:
        # Non existent upstream sources config is not considered an error while
        # an empty config can't be parsed and we consider it as an error.
        return tuple(), ''


class ConfigError(Exception):
    pass


def parse_upstream_sources(stream, context):
    """Parse a given text stream and return upstream sources

    :param object stream: A string or a file object containing YAML text or
                          upstream sources confoguration
    :param str context:   (Optional) The place we read the stream from, this is
                          used for adding detail to error messages.
    :rtype: tuple
    :returns: A tuple of GitUpstreamSource objects
    """
    try:
        sources_doc = yaml.safe_load(stream)
    except yaml.ScannerError:
        raise ConfigError("Invalid YAML in '%2'", context)
    return tuple(
        GitUpstreamSource.from_yaml_struct(obj)
        for obj in sources_doc.get('git', [])
    )


def save_upstream_sources(upstream_sources, config_path):
    """Save upstream objects to YAML

    :param Iterable upstream_sources: A collection of upstream source objects
    :param str config_path:           Path to the upstream sources config
    """
    sources_doc = dict(
        git=[usrc.to_yaml_struct() for usrc in upstream_sources]
    )
    with open(config_path, 'w') as usrc_config:
        yaml.safe_dump(sources_doc, usrc_config, default_flow_style=False)


def get_upstream_sources(push_map):
    """Download the US sources listed in upstream_sources.yaml

    :param str push_map: The path to a file containing information about remote
                         SCM servers that is needed to push changes to them.
    """
    upstream_sources, _ = load_upstream_sources()
    dst_path = os.getcwd()

    for usrc in upstream_sources:
        usrc.get(dst_path, push_map)

    # the below code will 'prefer' ds changes over us ones
    git(
        '--git-dir=' + os.path.join(dst_path, '.git'),
        '--work-tree=' + dst_path,
        "reset", "--hard",
    )


def update_upstream_sources():
    """Update the commit hashes for US sources listed in upstream_sources.yaml

    :returns: Generator upstream_sources: A collection of upstream source
        objects
    :returns: str config_path: Path to the upstream sources config
    """
    upstream_sources, config_path = load_upstream_sources()
    updated_sources, us2 = tee(usrc.updated() for usrc in upstream_sources)
    modified_sources, ms2 = tee(
        new for new, old in zip(us2, upstream_sources) if new != old
    )
    has_changed = next((True for ms in ms2), False)
    if not has_changed:
        return modified_sources, config_path

    save_upstream_sources(updated_sources, config_path)
    return modified_sources, config_path


def get_modified_files(new_commit=None, old_commit=None, resolve_links=None):
    """Gets the list of files modified locally or in upstreams between commits

    :param str new_commit:     (Optional) The commit to look for modified files
                               in.
                               Defaults to HEAD
    :param str old_commit:     (Optional) The older commit to compare with.
                               Defaults to one before the one which is given in
                               'new_commit'.
    :param bool resolve_links: (Optional) If set to True will resolve symlinks
                               to modfied files and treat them as modified
                               files. Symlinks are taken from 'new_commit'.
                               Defaults to False.

    :rtype: Iterable
    :returns: Iterator over modified file paths
    """
    if new_commit is None:
        new_commit = 'HEAD'
    if old_commit is None:
        old_commit = new_commit + '^'
    logger.info(
        'Looking for files changed between %s and %s', old_commit, new_commit
    )
    old_files = ls_all_files(old_commit)
    new_files = ls_all_files(new_commit)
    changed_files = files_diff(old_files, new_files)
    if not resolve_links:
        return changed_files
    logger.info('Resolving symlinks to changed files')
    changed_files = set(changed_files)
    links_map = get_files_to_links_map(new_files, new_commit)
    link_sets_to_changed_files = (
        get_links_to_file(f, links_map) for f in changed_files
    )
    return iter(reduce(or_, link_sets_to_changed_files, changed_files))


def get_links_to_file(file, links_map):
    """Recursively get symlinks to a given file

    :param str file:          Normalized path to a file to lookup in links_map
    :param Mapping links_map: Mapping between files and links to the files
                              as returned from get_files_to_links_map()

    :rtype: set
    :returns: A set of symlinks to file including indirect symlinks (those who
              point indirectly through other symlinks)
    """
    logger.info('Recursively resolving links for file [{0}]'.format(file))
    if file not in links_map:
        return set()
    links = links_map[file]
    # Recursively get links to links to file
    links_to_links = (get_links_to_file(link, links_map) for link in links)
    links_to_file = reduce(or_, links_to_links, links)
    logger.debug(
        'Links to file [{0}]: {1}'.format(file, pformat(links_to_file))
    )
    return links_to_file


def get_files_to_links_map(files, commit=None):
    """Gets a map of of files and a set of symlinks to them

    :param Iterable files: All files in the repositoy formatted to:
                           {filename: (file-type, hash)}
                           as returned from ls_all_files()

    :rtype: dict
    :returns: A dict mapping files and a set of symlinks to them
    """
    logger.info('Generating file to links map')
    links_map = dict(
        (f.path, normpath(join(dirname(f.path), f.read_file())))
        for f in itervalues(files) if f.file_type == 0o120000
    )
    file_to_links = dict()
    logger.debug('Generating file to links map')
    for link, dst in iteritems(links_map):
        file_to_links.setdefault(dst, set()).add(link)
    logger.debug('Full file to links map: {0}'.format(pformat(file_to_links)))
    return file_to_links


def commit_upstream_sources_update(updates, config_path):
    """Commit updates made to the upstream_sources.yaml file

    :param Iterable updates: Iterator over upstream source objects representing
                             sources that were updated
    :param str config_path:  Path to the config to commit
    """
    updates = list(updates)
    if not updates:
        # Skip committing if upstream_sources.yaml not changed
        return
    if check_if_branch_exists('commit_branch'):
        git('branch', '-D', 'commit_branch')
    git('checkout', '-b', 'commit_branch')
    with open(config_path, 'r') as stream:
        checksum = md5(stream.read().encode('utf-8')).hexdigest()
    git('add', config_path)
    commit_message = generate_update_commit_message(updates)
    commit_message = generate_gerrit_message(commit_message, checksum)
    git('commit', '-m', commit_message)


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


def ls_all_files(commit=None):
    """List all files in repo in $PWD including those from upstream sources

    :param str commit:        (Optional) The commit to list files in. If
                              unspecified, HEAD is used.
    :rtype: dict
    :returns: A dict mapping file names to tuples containing the file mode and
              content checksum
    """
    if commit is None:
        commit = 'HEAD'
    upstream_sources, _ = load_upstream_sources(commit)
    files = dict()
    for usrc in upstream_sources:
        files.update(usrc.ls_files())
    files.update(git_ls_files(commit))
    return files


def files_diff(old_files, new_files):
    """Returns which files changed between two file sets

    :param dict old_files: The list of older files as a mapping of file names
                           to tuples of file mode and checksum, as returned by
                           ls_all_files.
    :param dict new_files: The list of newer files, similarly as a mapping.

    :rtype: Iterable
    :returns: The set of files that changed between the state represented by
              old_files to the one represented by new_fils
    """
    old_file_paths = dict_keys_set(old_files)
    new_file_paths = dict_keys_set(new_files)
    for file_path in old_file_paths ^ new_file_paths:
        yield file_path
    for file_path in old_file_paths & new_file_paths:
        if old_files[file_path] != new_files[file_path]:
            yield file_path


def dict_keys_set(d):
    """Returns a read-only set of the keys in a given dict

    This is generally for Python <= 2.6 compatibility as dict.viewkeys is
    available in Python >= 2.7
    """
    if hasattr(d, 'viewkeys'):
        return viewkeys(d)
    keys = d.keys()
    if isinstance(keys, Set):
        # In python3 keys() returns a set view
        return keys
    return set(keys)


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


class GitFile(namedtuple('_GitFileData', 'file_type file_hash')):
    """
    Wrapper class for git file metadata (type and hash) as returned from git.
    It's used to bind the git_func that was used to read the upstream source
    to the data.
    """
    @classmethod
    def construct(cls, file_path, file_type, file_hash, git_func, commit):
        file_obj = cls(file_type, file_hash)
        file_obj.git_func = git_func
        file_obj.path = file_path
        file_obj.commit = commit
        return file_obj

    def read_file(self):
        return git_read_file(self.path, self.commit, self.git_func)


def git_ls_files(commit=None, git_func=None):
    """List the files in a given commit

    :param str commit:        (Optional) The commit to list files in. If
                              unspecified, HEAD is used.
    :param function git_func: (Optional) The function to use to run git,
                              defaults to 'git'
    :rtype: dict
    :returns: A dict mapping file names to tuples containing the file mode and
              content checksum
    """
    if commit is None:
        commit = 'HEAD'
    if git_func is None:
        git_func = git
    lines = git_func('ls-tree', '--full-tree', '-r', commit).splitlines()
    data_and_names = (line.split(u'\t') for line in lines)
    names_and_split_data = ((n, d.split(u' ')) for d, n in data_and_names)
    names_and_objects = (
        (n, GitFile.construct(n, int(m, base=8), h, git_func, commit))
        for n, (m, _, h) in names_and_split_data
    )
    return dict(names_and_objects)


def git_read_file(path, commit=None, git_func=None):
    """Read a specified file from a specific Git commit

    :param str path:          The path to the file to read, relative to the
                              repository root
    :param str commit:        (Optional) The commit to get the file from. If
                              unspecified, HEAD is used.
    :param function git_func: (Optional) The function to use to run git,
                              defaults to 'git'

    This function may raise a GitProcessError exception if the file or commit
    are not found

    :rtype: str
    :returns: The contents of the file
    """
    if commit is None:
        commit = 'HEAD'
    if git_func is None:
        git_func = git
    return git_func('cat-file', '-p', '{0}:{1}'.format(commit, path))


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
