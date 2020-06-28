#!/bin/env python3
"""usrc_updater.py: run the upstream source update process

The update process includes updating the commit pointer on the upstream sources
configuration file and pushing the changes to the requested branch.
"""


from functools import partial
import logging
from typing import Callable


import click


from stdci_libs.common_cli import cli_with_logging_from_logger
from stdci_libs.actuators.updaters import updater_cli, committing_updater
from stdci_tools.usrc import update_main as update_upstream_sources


logger = logging.getLogger()


@click.command()
@cli_with_logging_from_logger(logger)
@updater_cli
@committing_updater
def updater_main_cli(committing_updater_func: Callable):
    """run the upstream source update process

    The update process includes updating the commit reference on the upstream
    sources configuration file and pushing the changes to the requested branch.

    You can specify the positional arguments as environment variables or pass
    them as usual.
    """
    return committing_updater_func(
        updater_func=partial(update_upstream_sources, commit=True),
        logger=logger
    )


if __name__ == '__main__':
    updater_main_cli()
