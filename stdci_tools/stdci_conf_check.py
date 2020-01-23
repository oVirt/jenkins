#!/bin/env python
'''Check stdci v2 configuration file

    --project, -p project_root_dir | default CWD
    --verbose, -v  use a long listing format | default False
'''

from __future__ import print_function
import argparse
import os
import sys
import logging
import yaml
import struct
from termios import TIOCGWINSZ
from fcntl import ioctl
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.stdci_dsl.api import get_formatted_threads
from scripts.stdci_dsl.parser import CONFIG_FILES
from scripts.stdci_logging import add_logging_args, setup_console_logging


STDCI_STAGES = ('check-patch', 'check-merged', 'build-artifacts',
                'poll-upstream-sources', 'gate')


logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Tool for checking STDCIv2 configuration files.')
    parser.add_argument(
        '-p', '--project', action='store', dest='project_dir',
        help=(
            'Path to project root directory. Default current directory.'
        ),
        default=os.getcwd(),
    )
    parser.add_argument(
        'stage', action='store', help='STDCIv2 stage'
    )
    add_logging_args(parser)
    return parser.parse_args()


def get_terminal_width():
    ''' Return terminal width

    default_terminal_width is used when we can't obtain the terminal width
    as it happens when invoked by pytest

    :rtype: int
    :returns: returns terminal width
    '''
    default_terminal_width = 80
    try:
        # create a buffer to obtain data from ioctl()
        buf = struct.pack('HHHH', 0, 0, 0, 0)
        '''
        termios.TIOCGWINSZ is a magic constant determined by the system
        (TIOCGWINSZ -> IOCtl to Get the WINdow SiZe)
        In combination with ioctl(), it serves to tell the Windows Size
        ioctl() - perform operation on file descriptor, here 0 (stdin)
        '''
        win_size = ioctl(0, TIOCGWINSZ, buf)
        # decode the data received from ioctl()
        _, terminal_width, _, _ = struct.unpack('HHHH', win_size)
        return terminal_width
    except IOError:
        return default_terminal_width


def check_stage(stage):
    """Check for supported STDCI stage

    :param str stage: STDCI stage

    :rtype:           str
    :returns:         stage
    """
    if stage not in STDCI_STAGES:
        logger.error(
            'ERROR: Invalid STDCI stage %s. Valid STDCI stages are "%s"',
            stage, ', '.join(STDCI_STAGES)
        )
        sys.exit(1)
    return stage


def check_path_exists(path):
    """Check path to project directory

    :param str path: path to project directory

    :rtype:          str
    :returns:        path
    """
    if not os.path.isdir(path):
        logger.error(
            'ERROR: Project directory %s does not exist', args.project_dir)
        sys.exit(1)
    return path


def set_formatter(verbose):
    """Set formatter

    Choose between terse and verbose formatter based on parameter
    provided by the user and add terminal width to it

    :param bool verbose: set verbose or terse output
    :rtype:              str
    :returns:            forrmatter's name + teplate data
    """
    if verbose:
        frmtr_name='conf_checker_verbose'
    else:
        frmtr_name='conf_checker_terse'
    return '{0}:{1}'.format(frmtr_name, get_terminal_width())


def find_stdciv2_config(project_dir):
    """Find STDCIv2 config file(s)

    :param str project_dir: project directory
    :returns:               None
    """
    all_conf_files = []
    for fname in CONFIG_FILES:
        if os.path.exists(os.path.join(project_dir, fname)):
            all_conf_files.append(fname)
    if not all_conf_files:
        logger.info(
            'INFO: No STDCIv2 configuration file found under %s.'
            ' The defaults will be used.', project_dir)
    if len(all_conf_files) > 1:
        logger.info(
            'INFO: %d configuration files (%s) found. %s will be used.',
            len(all_conf_files), ', '.join(all_conf_files), all_conf_files[0])


def main():
    args = parse_args()
    setup_console_logging(args, logger)
    stdci_stage = check_stage(args.stage)
    project_dir = check_path_exists(args.project_dir)
    formatter = set_formatter(args.verbose)
    find_stdciv2_config(project_dir)

    try:
        formatter_out = get_formatted_threads(
            formatter, project_dir, stdci_stage, ignore_conditions=True)
    except yaml.parser.ParserError as e:
        logger.error('ERROR %s, %s%s', e.context, e.problem, e.problem_mark)
        sys.exit(1)
    except Exception as e:
        logger.error('ERROR: %s', e.args[0])
        sys.exit(1)
    if not formatter_out:
        print('No jobs for stage {0}'.format(stdci_stage))
    else:
        print(formatter_out)

if __name__ == '__main__':
    main()
