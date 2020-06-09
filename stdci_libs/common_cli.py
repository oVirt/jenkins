"""Helpers for creating CLI applications"""

from functools import wraps
from logging import Logger
from typing import Any, Callable

from click import option

from stdci_libs.stdci_logging import setup_logging


def compose_decorators(*decorators) -> Callable:
    """Factory function for composing decorators

    The function gets a list of decorators and creates
    a decorator which applies them on the Callable it decorates.

    :param decorators: The decorators to compose
    """
    def decorate(func: Callable) -> Callable:
        """Decorate the given callable

        Decorate func with all the decorators given to `compose_decorators`

        :param func: The function that should be decorated
        """
        for decorator in reversed(decorators):
            func = decorator(func)

        return func
    return decorate


"""Log flag"""
log_opt = option(
    '--log', '-l', type=str, metavar='PATH',
    help=('If set, will log to the specified file.'
          ' Otherwise, log to stderr.'
    )
)


"""Debug flag"""
debug_opt = option(
    '--debug', '-d', help='Provide debugging output.',
    type=bool, is_flag=True, envvar='DEBUG'
)


"""Verbose flag"""
verbose_opt = option(
    '--verbose', '-v',
    help='Provide verbose output.', is_flag=True
)


"""Common CLI flags"""
cli_with_logging = compose_decorators(verbose_opt, debug_opt, log_opt)


def cli_with_logging_from_logger(logger: Logger) -> Callable:
    """Create a decorator which configures the logger from CLI flags

    :param logger: The logger that that needs to be configured
    """
    def cli_with_logging_wrapper(func: Callable) -> Callable:
        """Configure logging from CLI and run a command

        :param func: The command to run
        """
        @cli_with_logging
        @wraps(func)
        def run_cmd_with_logging(
            verbose: bool,
            debug: bool,
            log: str,
            **kwargs
        ) -> Any:
            """Configure logging from CLI and run a command

            :param verbose: If true the logger will run with verbose level
            :param debug: If true the logger will run with debug level
            :param log: If specified, the log will be written to this file
                instead of STDERR
            :param kwargs: Additional arguments to pass to `func`
            """
            setup_logging(
                debug=debug,
                verbose=verbose,
                log=log,
                logger=logger
            )
            return func(**kwargs)
        return run_cmd_with_logging
    return cli_with_logging_wrapper
