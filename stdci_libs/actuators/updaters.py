"""Tools for writing actuators of type updater"""


from functools import wraps, partial
from logging import Logger
import os
from typing import Callable


from stdci_libs.git_utils import prep_git_repo, get_name_from_repo_url, commit_files
from stdci_tools.pusher import push_to_scm as push_upstream_sources
from stdci_libs import file_utils

from stdci_libs.actuators.common import (
    repo_url_arg,
    refspec_arg,
    target_branch_arg,
    push_map_arg,
)
from stdci_libs.common_cli import compose_decorators


"""Common CLI for updater scripts"""
updater_cli = compose_decorators(
    repo_url_arg,
    refspec_arg,
    target_branch_arg,
    push_map_arg,
)


def committing_updater(func: Callable) -> Callable:
    """Injects a callable that contains a common updater logic

    The purpose of this decorator is to remove the boilerplate code
    that pass the common arguments to updater_main

    :param func: The callable to wrap
    """
    @wraps(func)
    def committing_updater_func(
        repo_url: str,
        refspec: str,
        target_branch: str,
        push_map: str,
        **kwargs
    ):
        """
        For the description about the arguments please look at
        `updater_main`.
        """
        updater_main_with_args = partial(
            updater_main,
            repo_url=repo_url,
            refspec=refspec,
            target_branch=target_branch,
            push_map=push_map
        )
        return func(
            committing_updater_func=updater_main_with_args,
            **kwargs
        )

    return committing_updater_func


def updater_main(
    repo_url: str,
    refspec: str,
    target_branch: str,
    push_map: str,
    updater_func: Callable[[], None],
    logger: Logger,
    execute_commit: bool = False,
    automerge: bool = False
):
    """Run the actual logic to update the upstream source and push the changes

    :param repo_url: midstream repository URL
    :param refspec: refspec to fetch
    :param target_branch: branch to push the changes to
    :param push_map: path to pusher push map
    :param updater_func: A callable that is called with the root of the
        repository as the first argument and run the actual update.
    :param logger: logger instance that will be used to log messages
    :param execute_commit: Apply commit after running the updater func
    :param automerge: Enable automerge in commit message (applicable only
        when execute_commit is set to true).
    """
    repo_name = get_name_from_repo_url(repo_url)
    repo_root = os.path.join(os.getcwd(), repo_name)
    logger.info('adding repo url: %s', repo_url)
    _, fetch_sha = prep_git_repo(repo_root, repo_url, refspec, checkout=True)
    with file_utils.workdir(repo_root):
        ret = updater_func()
        if execute_commit:
            add_headers = {}
            if automerge:
                add_headers["automerge"] = "yes"
            commit_files(
                ["."],
                change_id_headers=["x-md5"],
                add_headers=add_headers
            )
        push_upstream_sources(
            dst_branch=target_branch,
            push_map=push_map,
            if_not_exists=True,
            unless_hash=fetch_sha
        )

    return ret
