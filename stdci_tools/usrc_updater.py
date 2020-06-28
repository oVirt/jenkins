#!/bin/env python3
"""usrc_updater.py: run the upstream source update process

The update process includes updating the commit pointer on the upstream sources
configuration file and pushing the changes to the requested branch.
"""

import os
import logging
from typing import Callable

import click

from stdci_libs.git_utils import prep_git_repo, get_name_from_repo_url
from stdci_libs.common_cli import cli_with_logging_from_logger
from stdci_libs.actuators.updaters import updater_cli
from stdci_tools.usrc import update_main as update_upstream_sources
from stdci_tools.pusher import push_to_scm as push_upstream_sources
from stdci_libs import file_utils


logger = logging.getLogger()


@click.command()
@cli_with_logging_from_logger(logger)
@updater_cli
def updater_main_cli(
        repo_url: str, refspec: str, target_branch: str, push_map: str,
):
    """run the upstream source update process

    The update process includes updating the commit reference on the upstream
    sources configuration file and pushing the changes to the requested branch.

    You can specify the positional arguments as environment variables or pass
    them as usual.
    """
    return updater_main(repo_url, refspec, target_branch, push_map)


def updater_main(
        repo_url: str, refspec: str, target_branch: str, push_map: str):
    """Run the actual logic to update the upstream source and push the changes

    :param repo_url: midstream repository URL
    :param refspec: refspec to fetch
    :param target_branch: branch to push the changes to
    :param push_map: path to pusher push map
    """
    repo_name = get_name_from_repo_url(repo_url)
    repo_root = os.path.join(os.getcwd(), repo_name)
    logger.info('adding repo url: %s', repo_url)
    git_func, fetch_sha = prep_git_repo(repo_root, repo_url, refspec, checkout=True)
    run_upstream_source_updater(repo_root)
    push_changes(
        repo_root=repo_root,
        repo_url=repo_url,
        push_branch=target_branch,
        unless_hash=fetch_sha,
        push_map=push_map)


def run_upstream_source_updater(repo_root: str):
    """Run the upstream source updater at the root of the repository

    :param repo_root: the root of the repository
    """
    with file_utils.workdir(repo_root):
        update_upstream_sources(commit=True)


def push_changes(
        repo_root: str, repo_url: str, push_branch: str, unless_hash: str,
        push_map: str, push_func: Callable = push_upstream_sources):
    """Push the any new commits in the repository

    :param repo_root: the root of the repository
    :param push_branch: the branch to push to
    :param unless_hash: skip push if the commit sha is the same as this
        parameter
    :param push_map: path to the push map
    :param push_func: the function to use to push the changes
    """
    with file_utils.workdir(repo_root):
        push_func(
            dst_branch=push_branch,
            push_map=push_map,
            if_not_exists=True,
            unless_hash=unless_hash)


if __name__ == '__main__':
    updater_main_cli()
