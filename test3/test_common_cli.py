from functools import partial
from unittest.mock import create_autospec, sentinel

import pytest
from click import argument, command

from stdci_libs import common_cli
from stdci_libs.common_cli import (cli_with_logging_from_logger,
                                   compose_decorators, option, setup_logging)


@pytest.mark.parametrize('should_raise', [
    False, True
])
def test_cli_with_logging_from_logger(should_raise, monkeypatch):
    fake_logger = sentinel.fake_logger

    @command()
    @argument('extra-argument')
    @option('--extra-option')
    @cli_with_logging_from_logger(fake_logger)
    def fake_main(extra_option, extra_argument):
        if should_raise:
            raise RuntimeError()
        else:
            return extra_option, extra_argument

    setup_logging_mock = create_autospec(setup_logging)
    monkeypatch.setattr(
        common_cli, 'setup_logging', setup_logging_mock
    )
    fake_extra_option = 'x'
    fake_extra_argument = 'y'
    fake_log = 'path_to_log'

    fake_cmd_with_args = partial(
        fake_main,
        [
            '-v', '-d', '-l', fake_log,
            '--extra-option', fake_extra_option, fake_extra_argument
        ],
        standalone_mode=False
    )
    if should_raise:
        with pytest.raises(RuntimeError):
            fake_cmd_with_args()
    else:
        ret = fake_cmd_with_args()
        assert ret == (fake_extra_option, fake_extra_argument)

    setup_logging_mock.assert_called_once_with(
        debug=True,
        verbose=True,
        log=fake_log,
        logger=fake_logger
    )


def test_compose_decorators():
    first_arg = sentinel.first_arg
    second_arg = sentinel.second_arg

    def first_decorator(func):
        return partial(func, first_arg)

    def second_decorator(func):
        return partial(func, second_arg)

    # Using reverse order, so it would look the same as if
    # the decorators were applied directly on a function
    decorators = (
        second_decorator,
        first_decorator
    )

    dummy_common_cli = compose_decorators(*decorators)

    @dummy_common_cli
    def func_to_decorate(first, second):
        assert first is first_arg
        assert second is second_arg

    func_to_decorate()
