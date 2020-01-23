#!/usr/bin/env python3
"""Utilities for managing Dockerfiles"""

import argparse
import json
import logging
import os
import re
from collections import namedtuple
from collections.abc import Mapping
from contextlib import contextmanager
from os.path import join
from subprocess import PIPE, CalledProcessError, run
from textwrap import dedent
from uuid import uuid4

from dockerfile_parse import DockerfileParser
from dockerfile_parse import constants as dfp_constants

try:
    from scripts.stdci_logging import add_logging_args, setup_console_logging
except ImportError:
    from stdci_logging import add_logging_args, setup_console_logging

logger = logging.getLogger(__name__)

Decorator = namedtuple('Decorator', ('name', 'args'))
"""Parsed decorator

    :param str name
    :param str args

    e.g: @follow_tag(ubi8-minimal:8-released)

    name = follow_tag
    args = ubi8-minimal:8-released
"""

DecoratedCmd = namedtuple('DecoratedCmd', ('cmd_dict', 'decorators'))
"""Binding between a dockerfile command and its decorators

    :param dict cmd_dict: The decorated command
    :param: decorators list of `Decorator`: The decorators that
        decorates command. The last decorator in the list, is the closest one
        to the command
"""

ImageAndFloatingRef = namedtuple(
    'ImageAndFloatingRef', ('image', 'floating_ref')
)
"""Binding between an image reference and the floating reference it follows

    :param: str image: The reference that appears in the FROM command
    :param: str floating_ref: The reference that appears in the decorator
"""


class UpdateAction(
    namedtuple('UpdateAction', ('idx', 'old_image', 'new_image'))
):

    """Represents an update to a FROM command in a Dockerfile
        :param: int idx: The index of the FROM command,
            respective to the other
            FROM commands (used for multistage Dockerfiles)
        :param: str old_image: The reference to the image before the update
        :param: str new_image: The reference to the image after the update
    """
    def __str__(self):
        return 'Index {}: {} -> {}'.format(*self)


class FailedToGetLatestVersionError(Exception):
    pass


class FailedToParseDecoratorError(Exception):
    pass


def main(args=None):
    args = parse_args(args)
    try:
        setup_console_logging(args)
        args.handler(args)
        return 0
    except IOError as e:
        logger.exception('%s: %s', e.strerror, e.filename)
    except CalledProcessError as e:
        logger.exception(
            'Msg: %s\nSTDOUT: %s\nSTDERR: %s',
            e.stdout, e.stderr, e.message
        )
    except Exception as e:
        logger.exception("%s", str(e))
        raise
    return 1


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description='Utilities for managing Dockerfiles'
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers(title='Subcommands')
    parent_image_update_parser = subparsers.add_parser(
        'parent-image-update',
        help='Update the parent image reference based on a floating tag',
        description=dedent(
            """
                Dockerfile syntax:

                #@follow_tag(ubi8-minimal:8-released)
                FROM ubi8-minimal:8-released
                ...

                The image in the FROM instruction will be replaced
                by the NVR of the current image that is tagged with the tag in
                the follow_tag decorator.
            """
        )
    )
    parent_image_update_parser.set_defaults(handler=parent_image_update_main)
    parent_image_update_parser.add_argument(
        'dockerfiles', metavar='DOCKERFILE', nargs='+'
    )
    parent_image_update_parser.add_argument(
        '--lookup-registry',
        default='',
        help='The registery that will be used when looking up for new images'

    )
    parent_image_update_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Do not update anything, just print what will be updated'
    )

    return parser.parse_args(args=args)


def parent_image_update_main(args):
    if args.lookup_registry:
        logger.debug('Using %s as the default registry', args.lookup_registry)

    with get_dfps(args.dockerfiles) as dfps:
        print(
            update_dockerfiles(
                dfps,
                args.lookup_registry,
                args.dry_run
            )
        )


def update_dockerfiles(dfps, lookup_registry='', dry_run=False):
    """Update the parent images in a Dockerfile

    The overall flow:

        - For each dockerfile parser (which represents a Dockerfile),
          get the images in the FROM insructions and the tag that they
          should follow.

        - Create a generator of all the floating tags

        - For each images reference, find out what is the NVR tag of the
          latest images that was tagged into it.

        - Replace the image reference in the decorated FROM instructions (
          with the matching NVR tag that we have found),
          and report what was replaced.

    :param list of `DockerfileParser` dfps: Will be used to update
        the Dockerfiles
    :param str lookup_registry: If specified, this registry will be used when
        pulling image information.
    :param bool dry_run: If true, don't update the Dockerfiles,
        just return what will be updated
    :return:
    """
    dfp_to_oiaft = {
        dfp: get_old_images_and_floating_refs(
            dfp.parent_images,
            get_decorated_commands(dfp.structure)
        )
        for dfp in dfps
    }

    all_floating_refs = (
        entry.floating_ref
        for oiafts in dfp_to_oiaft.values()
        for entry in oiafts
    )

    latest_images = get_latest_images(all_floating_refs, lookup_registry)

    results = [
        update(dfp, update_plan, latest_images, dry_run)
        for dfp, update_plan in dfp_to_oiaft.items()
    ]

    return report(results)


def report(results):
    """Report what was updated in a human readable way

    :param dict(str, list of UpdateAction) results:
        Maps between a Dockerfile path and the updated actions that
        were called on it.
    :rtype: str
    """
    def get_entry(dockerfile, update_actions):
        update_actions_str_lst = [
            '  - {}'.format(str(update_action))
            for update_action in update_actions
        ]
        return '{}:\n{}'.format(dockerfile, '\n'.join(update_actions_str_lst))

    update_entries = [
        get_entry(dockerfile, update_actions)
        for dockerfile, update_actions in results
        if update_actions
    ]

    header = dedent(
        """
        Dockerfile update summary
        --------------------------
        """
    )

    return '\n'.join(
        [header]
        + update_entries
        or ['No updates were found to any Dockerfile']
    )


def get_old_images_and_floating_refs(old_images, decorated_commands):
    """Create `ImageAndFloatingRef instances

    :param list of str old_images: The image references that appear in the FROM
        commands.
    :param list of `DecoratedCmd` decorated_commands: The commands that
        appears in the Dockerfiles and their decorators.
    :rtype: list of `ImageAndFloatingRef`
    """
    results = []

    from_cmds = (
        cmd for cmd in decorated_commands
        if cmd.cmd_dict['instruction'] == 'FROM'
    )

    for idx, cmd in enumerate(from_cmds):
        first_match = first_decorator('follow_tag', cmd.decorators)
        if first_match:
            floating_ref = first_match.args
        else:
            # From instruction without a decorator
            floating_ref = None

        results.append(ImageAndFloatingRef(
            old_images[idx],
            floating_ref
        ))

    return results


def get_decorated_commands(structure):
    """Group commands with their decorators

    :param list structure: List of commands as returned from
        `DockerfileParser.structure`
    :rtype: list of `DecoratedCmd`
    """
    decorators = []
    current_decorators = []

    for cmd in structure:
        if is_decorator(cmd['instruction'], cmd['value']):
            current_decorators.append(get_decorator(cmd['value']))
        else:
            decorators.append(DecoratedCmd(cmd, current_decorators))
            current_decorators = []

    return decorators


def is_comment(instruction):
    """Checks if a command from a docker file is a comment

    :param str instruction
    :rtype: bool
    """
    return instruction == dfp_constants.COMMENT_INSTRUCTION


def is_decorator(instruction, value):
    """Check if an instruction and its value represents a decorator

    :param str instruction:
    :param str value:
    :rtype: bool
    """
    return is_comment(instruction) and value.startswith('@')


def first_decorator(decorator_name, decorators):
    """Return the closest decorator to an instruction

    :param str decorator_name: The name of the requested decorator
    :param list of `Decorator`: A list of dicts, each dicts represents
        a decorator
    :rtype: `Decorator`
    """
    return next(
        (
            decorator for decorator in reversed(decorators)
            if decorator.name == decorator_name
        ),
        None
    )


def get_decorator(value):
    """Create a Decorator instance

    :param str value: The decorator as it appears in the Dockerfile
        (without the leading #)
    :rtype: `Decorator`
    """
    pattern = r'^@(?P<name>.+)\((?P<args>.*)\)$'
    match = re.match(pattern, value)

    if not match:
        raise FailedToParseDecoratorError(
            'Failed to parse decorator {}'.format(value)
        )

    return Decorator(
        **{
            k: v.strip() for k, v in match.groupdict().items()
        }
    )


def get_latest_images(all_floating_refs, lookup_registry=''):
    """Get the latest images for a list of floating tags

    :param iterable all_floating_refs:
    :param str lookup_registry: The registry that will be used for the lookup
        of images
    :rtype: dict
    """
    floating_refs = set(all_floating_refs)
    # Handle FROM commands without a follow_tag decorator
    floating_refs.discard(None)

    return {
        floating_ref: get_latest_image(floating_ref, lookup_registry)
        for floating_ref in floating_refs
    }


def get_latest_image(floating_ref, lookup_registry=''):
    """Get the latest nvr from a floating ref

    :param str floating_ref
    :param str lookup_registry: The registry that will be used
        for the lookup.
    :return:
    """
    logger.info('Getting the latest version of %s', floating_ref)
    inspect = skopeo_inspect(join(lookup_registry, floating_ref))

    return get_nvr_tag_from_inspect_struct(json.loads(inspect))


def get_nvr_tag_from_inspect_struct(struct):
    """Get the nvr tag of a component from it's inspect struct

    An inspect struct is the parsed output of 'skopeo inspect'
    Generally it's a dict that contains a 'Labels' key that maps
    to a dict.

    A nvr tag is an image refrence that is composed from it's
    nvr.

    e.g:

    nvr -> ubi8-minimal-8.1-279
    nvr tag -> ubi8-minimal:8.1-279

    :param dict struct: Information about a container image
    :rtype: str
    """
    labels = struct.get('Labels')
    if not isinstance(labels, Mapping):
        raise FailedToGetLatestVersionError(
            'Labels dict was not found in {}'
            .format(struct)
        )

    required_labels = {}
    missing_labels = []
    for label in ('name', 'version', 'release'):
        if labels.get(label):
            required_labels[label] = labels[label]
        else:
            missing_labels.append(label)

    if missing_labels:
        raise FailedToGetLatestVersionError(
            'The following labels, for image {}, were not set or empty'
            .format(missing_labels)
        )

    return '{name}:{version}-{release}'.format(**required_labels)


@contextmanager
def get_dfps(dockerfiles):
    """Load DockerfileParser object from a list of Dockerfiles

    The file like objects that are being used by the parser
    objects will be closed when this context manager exists.

    :param list of str dockerfiles: Paths to the Dockerfiles
    :yeilds: list of `DockerfileParser` objects
    """
    fds = []
    try:
        for dockerfile in dockerfiles:
            fds.append(open(dockerfile, mode='r+b'))
        yield [DockerfileParser(fileobj=fd) for fd in fds]
    finally:
        for fd in fds:
            fd.close()


def skopeo_inspect(pull_url, transport='docker://', tls_verify=False):
    return run_command([
        'skopeo',
        'inspect',
        '' if tls_verify else '--tls-verify=false',
        '{}{}'.format(transport, pull_url)
    ])


def update(
    dfp,
    old_images_and_floating_refs,
    latest_images,
    dry_run
):
    """Update a dockerfile and report what was updated

    The return value is a tuple which contains the path
    to the Dockerfile that was updated, and a list of `UpdateActions`
    which describe what was updated.

    :param list of `OldImageAndFloatingTag` old_images_and_floating_refs:
    :param dict latest_images: A mapping between a floating tag to
        its latest image
    :param bool dry_run: If true, don't update the Dockerfiles,
        just return what will be updated
    :rtype: tuple (str, list of `UpdateAction`)
    """
    logger.debug('Updating %s', dfp.fileobj.name)
    new_images, update_actions = get_update(
        old_images_and_floating_refs,
        latest_images
    )

    if not dry_run:
        dfp.parent_images = new_images

    return dfp.fileobj.name, update_actions


def get_update(old_images_and_floating_refs, latest_images):
    """Update a dockerfile and report what was updated

    :param list of `OldImageAndFloatingTag` old_images_and_floating_refs:
    :param dict latest_images: A mapping between a floating tag to
        its latest image
    :param bool dry_run: If true, don't update the Dockerfiles,
        just return what will be updated
    :rtype: tuple  (list of str, list of `UpdateAction`)
    """
    new_images = []
    update_actions = []
    idx = 0
    for old_image, floating_ref in old_images_and_floating_refs:
        if floating_ref:
            latest_image = latest_images[floating_ref]
            new_images.append(latest_image)
            if old_image != latest_image:
                logger.debug(
                    'Updating %s to %s at index %s',
                    old_image,
                    latest_image,
                    idx
                )
                update_actions.append(UpdateAction(
                    idx,
                    old_image,
                    latest_image)
                )
            else:
                logger.debug('image %s is up to date', old_image)
        else:
            new_images.append(old_image)

        idx += 1

    return new_images, update_actions


def run_command(cmd):
    """Run command in a subprocess and return its stdout

    :param list cmd
    :rtype: str
    """
    uuid = uuid4()
    logger.debug(
        'Running command: %s with id: %s',
        ' '.join(cmd),
        uuid
    )

    out = run(cmd, stdout=PIPE, stderr=PIPE, encoding='utf-8', check=True)
    logger.debug(
        'Command %s\n STDOUT: %s\n STDERR: %s\n',
        uuid,
        out.stdout,
        out.stderr
    )

    return out.stdout


if __name__ == '__main__':
    exit(main())
