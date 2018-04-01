#!/bin/env python
"""docker_cleanup.py - Safely remove Docker images with a whitelist filter"""

import logging
import argparse
import sys
import re
from copy import copy
from functools import partial
from six import iterkeys, iteritems

try:
    import docker
except ImportError:
    print('Could not import docker. Is python-docker-py installed? Exiting.')
    sys.exit(0)

try:
    from docker.errors import NotFound as ImageNotFoundException
except ImportError:
    from docker.errors import ImageNotFound as ImageNotFoundException


logger = logging.getLogger(__name__)


def main():
    args = parse_args()
    setup_console_logging(args, logger)
    client = _get_client(args)
    stop_all_running_containers(client)
    whitelisted_repos = _get_whitelisted_repos(args)
    safe_image_cleanup(client, whitelisted_repos)
    logger.info('Docker image cleanup is done.')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Safe cleanup of Docker images with whitelist filter'
    )
    parser.add_argument(
        '-c', '--client',
        help=(
            'Pocal path or base URL to docker socket.'
            ' If not specified, will try from env as Docker\'s CLI.'
        ),
        nargs=1, type=str, default='from-env', action='store'
    )
    parser.add_argument(
        '-w', '--whitelist',
        help=(
            'Whitelisted repositories: images from those repositories will not'
            ' be deleted'
        ),
        nargs="+"
    )
    add_logging_args(parser)
    return parser.parse_args()


def _get_client(args):
    """Get Docker client

    :param argparse.Namespace args: Argument parsing results

    :rtype: docker.DockerClient
    :returns: A client for communicating with a Docker server.
    """
    if args.client != 'from-env':
        return docker.DockerClient(base_url=args)
    return docker.from_env()


def _get_whitelisted_repos(args):
    """Get whitelist param from args and construct a set from the given list

    :param argparse.Namespace args: Argument parsing results

    :rtype: set
    :returns: A set with the whitelisted repositories are provided by the user.
    """
    whitelisted_repos = set(args.whitelist)
    if whitelisted_repos:
        logger.debug('Whitelisted repos: %s', whitelisted_repos)
    return whitelisted_repos


def safe_image_cleanup(client, whitelisted_repos):
    """Remove images which are not whitelisted.

    :param docker.DockerClient client: A client for communicating with a Docker
                                       server.
    :param set whitelisted_repos:      A set of whitelisted repos
    """
    parent_to_child_map = _get_parent_to_child_map(client, whitelisted_repos)
    while parent_to_child_map:
        parents = set(iterkeys(parent_to_child_map))
        for parent in parents:
            if parent_to_child_map[parent] & parents:
                # Skip grandparents
                continue
            _safe_rm(client, parent)
            parent_to_child_map.pop(parent)


def stop_all_running_containers(client):
    """Stop all running containers.

    :param docker.DockerClient client: A client for communicating with a Docker
                                       server.
    """
    logger.info('Stopping and removing all running containers')
    try:
        containers = client.containers.list()
    except AttributeError:
        containers = client.containers()
    for container in containers:
        logger.debug(
            'Stopping and removing name=%s, id=%s',
            _get_container_name(container), _get_container_id(container)
        )
        _remove_container(client, container)


def _get_container_name(container):
    if hasattr(container, 'name'):
        return container.name
    return container['Labels'].get('name', 'unnamed')


def _get_container_id(container):
    if hasattr(container, 'id'):
        return container.id
    return container['Id']


def _remove_container(client, container):
    """Stop and remove a container giving it the default 10sec timeout

    :param docker.DockerClient client: A client for communicating with a Docker
                                       server.
    :param container:                  A container represenation as returned by
                                       docker.containers
    """
    if hasattr(container, 'stop'):
        container.stop()
        container.remove(force=True)
        return
    client.stop(container)
    client.remove_container(container, force=True)


def _is_repo_whitelisted(tags, whitelisted_repos):
    """Check if image is from a whitelisted repo

    :param string_types image_repo_tag: Full image repo tag
    :param set whitelisted_repos:       Set of whitelisted repos

    :rtype: bool
    :returns: True if image is whitelisted and False otherwise.
    """
    image_repo_regex = re.compile(r'docker.io/(.+)[:/](.*)')
    if not tags:
        return False
    match = image_repo_regex.match(tags[0])
    if not match:
        return False
    elif match.group(1) in whitelisted_repos:
        return True
    return False


def _get_parent_to_child_map(client, whitelisted_repos):
    """Generate a map from a parent image to it's childs.

    :param docker.DockerClient client: A client for communicating with a Docker
                                       server.
    :param set whitelisted_repos:      Set of whitelisted repositories

    :rtype: Mapping
    :returns: Map from parent image to it's childs where all whitelisted
              (if any) parents are excluded.
    """
    whitelisted_images = set()
    parent_to_child_map = {}
    try:
        images = client.images.list(all=True)
    except AttributeError:
        images = client.images(all=True)
    for image in images:
        image_id = _get_image_id(image)
        parent_id = _get_image_parent_id(image)
        image_repo_tags = _get_image_repo_tags(image)
        if _is_repo_whitelisted(image_repo_tags, whitelisted_repos):
            logger.debug('Image %s is from a whitelisted repo.', image_id)
            whitelisted_images.add(image_id)
        parent_to_child_map.setdefault(image_id, set())
        if parent_id:
            logger.debug('%s is parent of %s', parent_id, image_id)
            parent_to_child_map.setdefault(parent_id, set()).add(image_id)
    _exclude_whitelisted_parents(whitelisted_images, parent_to_child_map)
    return parent_to_child_map


def _get_image_repo_tags(image):
    return getattr(image, 'attrs', image)['RepoTags']


def _get_image_id(image):
    if hasattr(image, 'id'):
        return image.id
    return image['Id']


def _get_image_parent_id(image):
    if hasattr(image, 'attrs'):
        return image.attrs['Parent']
    return image['ParentId']


def _exclude_whitelisted_parents(whitelist, parent_to_child_map):
    """Remove whitelisted parents from parent_to_child_map.
    Whitelisted parents are whitelisted images or parents of whitelisted images

    :param set whitelist:               Set of whitelisted image IDs.
    :param Mapping parent_to_child_map: Map from parent to child from which we
                                        remove whitelisted parents (keys).

    :rtype: set
    :returns: A set of whitelisted parents
    """
    whitelist = copy(whitelist)
    logger.info('Excluding whitelisted parent from parent to child map.')
    while True:
        # Get parents of whitelisted childs or whitelisted parents
        whitelisted_parents = set(
            parent for (parent, childs) in iteritems(parent_to_child_map)
            if childs & whitelist or parent in whitelist
        )
        if not whitelisted_parents:
            logger.info('All whitelisted parents are exluded.')
            return whitelist
        logger.debug(
            'Found whitelisted parents. Will exclude: %s', whitelisted_parents
        )
        for parent in whitelisted_parents:
            # Remove whitelisted parents
            logger.debug('Excluding %s', parent)
            parent_to_child_map.pop(parent)
            whitelist.add(parent)


def _safe_rm(client, image_id, force=None):
    """Safely try to remove the given image id. If the image was already
    removed, skip.

    :param docker.DockerClient client: A client for communicating with a Docker
                                       server.
    :param str image_id: Image ID to remove.
    :param bool force:   Force removal of the image. The default is true.
    """
    if not force:
        force = True
    try:
        logger.info('Removing image: %s, force=%s', image_id, str(force))
        if hasattr(client.images, 'remove'):
            client.images.remove(image_id, force=force)
            return
        client.remove_image(image_id, force=force)
    except ImageNotFoundException:
        logger.debug('Image was already removed.')
        pass


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
