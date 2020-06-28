"""Tools for writing actuators of type updater"""


from stdci_libs.actuators.common import (
    repo_url_arg,
    refspec_arg,
    target_branch_arg,
    push_map_arg
)
from stdci_libs.common_cli import compose_decorators


"""Common CLI for updater scripts"""
updater_cli = compose_decorators(
    repo_url_arg,
    refspec_arg,
    target_branch_arg,
    push_map_arg,
)
