import builtins
import os
from subprocess import CalledProcessError
from textwrap import dedent

import dockerfile_parse
import pytest
from dockerfile_parse import constants as dfp_constants
from unittest.mock import MagicMock, call, sentinel

from stdci_tools import dockerfile_utils
from stdci_tools.dockerfile_utils import (
    DecoratedCmd, Decorator, FailedToGetLatestVersionError,
    FailedToParseDecoratorError, ImageAndFloatingRef, UpdateAction,
    get_decorated_commands, get_decorator, get_dfps,
    get_nvr_tag_from_inspect_struct, get_old_images_and_floating_refs,
    get_update, update, main, run_command, add_registry_if_needed,
    get_latest_image_by_sha
)


@pytest.mark.parametrize('inspect, flat, expected', [
    (
        {
            'Labels': {
                'name': 'virt-api',
                'version': 'v2.1.0',
                'release': '1',
            }
        },
        False,
        'virt-api:v2.1.0-1'
    ),
    (
        {
            'Labels': {
                'name': 'cnv/virt-api',
                'version': 'v2.1.0',
                'release': '1',
            }
        },
        False,
        'cnv/virt-api:v2.1.0-1'
    ),
    (
        {
            'Labels': {
                'name': 'cnv/virt-api',
                'version': 'v2.1.0',
                'release': '1',
            }
        },
        True,
        'cnv-virt-api:v2.1.0-1'
    )
])
def test_get_nvr_tag_from_inspect_struct(inspect, flat, expected):
    assert get_nvr_tag_from_inspect_struct(inspect, flat) == expected


@pytest.mark.parametrize('struct', [
    {},
    {'Labels': {'version': 'a'}},
    {'Labels': {'release': 'b'}},
    {'Labels': {}},
    {'Labels': None},
    {'Labels': []}
])
def test_get_latest_image_from_inspect_struct_should_raise(struct):
    with pytest.raises(FailedToGetLatestVersionError):
        get_nvr_tag_from_inspect_struct(struct)


def test_get_dfps(monkeypatch):
    dockerfiles = ['a', 'b']
    fds = [MagicMock(name=x) for x in dockerfiles]
    open_mock = MagicMock(side_effect=fds)
    dfp_mock = MagicMock()

    monkeypatch.setattr(builtins, 'open', open_mock)
    monkeypatch.setattr(dockerfile_utils, 'DockerfileParser', dfp_mock)

    with get_dfps(dockerfiles):
        pass

    open_mock.assert_has_calls([call(x, mode='r+b') for x in dockerfiles])
    dfp_mock.assert_has_calls([(call(fileobj=x)) for x in fds])
    for fd in fds:
        fd.close.assert_called_once()


def test_get_dfps_close_fds(monkeypatch):
    good_file = MagicMock()
    open_mock = MagicMock(side_effect=[good_file, OSError()])
    monkeypatch.setattr(builtins, 'open', open_mock)

    with pytest.raises(OSError), get_dfps(['a', 'b']):
        pass

    good_file.close.assert_called_once()


def get_instruction(instruction, value):
    return {
        'instruction': instruction,
        'value': value
    }


def get_comment(value):
    return get_instruction(
        dfp_constants.COMMENT_INSTRUCTION,
        value
    )


@pytest.mark.parametrize('commands, expected', [
    (
        [
            get_comment('@1()'),
            get_instruction('A', 'a'),
            get_instruction('B', 'b'),
            get_comment('@2()'),
            get_comment('@3()'),
            get_instruction('C', 'c')
        ],
        [
            DecoratedCmd(
                get_instruction('A', 'a'),
                [Decorator('1', '')]
            ),
            DecoratedCmd(
                get_instruction('B', 'b'),
                []
            ),
            DecoratedCmd(
                get_instruction('C', 'c'),
                [
                    Decorator('2', ''),
                    Decorator('3', '')
                ]
            )
        ]
    ),
    (
        [
            get_comment('@1(bla)'),
            get_instruction('A', 'a'),
            get_comment('@2()'),
        ],
        [
            DecoratedCmd(
                get_instruction('A', 'a'),
                [Decorator('1', 'bla')]
            ),
        ]
    ),
    (
        [
            get_instruction('A', 'a'),
            get_comment('@1()'),
            get_instruction('B', 'b')
        ],
        [
            DecoratedCmd(
                get_instruction('A', 'a'),
                []
            ),
            DecoratedCmd(
                get_instruction('B', 'b'),
                [Decorator('1', '')]
            )
        ]
    ),
    ([], []),
    ([get_comment('@1()')], []),
    (
        [
            get_instruction('A', 'a'),
            get_instruction('B', 'b'),
            get_instruction('C', 'c'),
        ],
        [
            DecoratedCmd(get_instruction('A', 'a'), []),
            DecoratedCmd(get_instruction('B', 'b'), []),
            DecoratedCmd(get_instruction('C', 'c'), [])
        ]
    )
])
def test_get_decorated_commands(commands, expected):
    assert get_decorated_commands(commands) == expected


@pytest.mark.parametrize('value, expected', [
    (
        '@follow_tag(ubi8-minimal:8-released)',
        Decorator(
            'follow_tag',
            'ubi8-minimal:8-released'
        )
    ),
    (
        '@follow_tag(ubi8-minimal:8-released  )',
        Decorator(
            'follow_tag',
            'ubi8-minimal:8-released'
        )
    ),
])
def test_get_decorator(value, expected):
    assert get_decorator(value) == expected


def test_get_decorator_should_raise():
    with pytest.raises(FailedToParseDecoratorError):
        get_decorator('blabla')


@pytest.mark.parametrize('old_images, decorated_commands, expected', [
    (
        [
            'image_a:v1',
            'image_b:latest'
        ],
        [
            DecoratedCmd(
                {'instruction': 'FROM'},
                []
            ),
            DecoratedCmd(
                {'instruction': 'RUN'},
                []
            ),
            DecoratedCmd(
                {'instruction': 'FROM'},
                [
                    Decorator('follow_tag', 'some_other_tag'),
                    Decorator('follow_tag', 'some_tag')
                ]
            ),
        ],
        [
            ImageAndFloatingRef('image_a:v1', None),
            ImageAndFloatingRef('image_b:latest', 'some_tag')
        ]
    )
])
def test_get_old_images_and_floating_refs(
    old_images,
    decorated_commands,
    expected
):
    result = get_old_images_and_floating_refs(
        old_images,
        decorated_commands
    )

    assert result == expected


@pytest.mark.parametrize(
    'get_old_images_and_floating_tags, latest_images, ex_parent_images, ex_update_actions',
    [
        (
            [
                ImageAndFloatingRef('image_a:v1', 'image_a:latest'),
                ImageAndFloatingRef('image_b:v1', 'image_b:latest')
            ],
            {
                'image_a:latest': 'image_a:v1',
                'image_b:latest': 'image_b:v2'
            },
            [
                'image_a:v1',
                'image_b:v2'
            ],
            [
                UpdateAction(
                    1,
                    'image_b:v1',
                    'image_b:v2'
                )
            ]
        ),
        (
                [
                    ImageAndFloatingRef('image_a:v1', None),
                    ImageAndFloatingRef('image_b:v1', 'image_b:latest')
                ],
                {
                    'image_b:latest': 'image_b:v2'
                },
                [
                    'image_a:v1',
                    'image_b:v2'
                ],
                [
                    UpdateAction(
                        1,
                        'image_b:v1',
                        'image_b:v2'
                    )
                ]
        ),
        (
                [
                    ImageAndFloatingRef('image_a:v1', 'image_a:latest'),
                    ImageAndFloatingRef('image_b:v1', 'image_b:latest')
                ],
                {
                    'image_a:latest': 'image_a:v1',
                    'image_b:latest': 'image_b:v1'
                },
                [
                    'image_a:v1',
                    'image_b:v1'
                ],
                []
        )
    ]
)
def test_get_update(
    get_old_images_and_floating_tags,
    latest_images,
    ex_parent_images,
    ex_update_actions
):
    parent_images, update_actions = get_update(
        get_old_images_and_floating_tags,
        latest_images
    )

    assert parent_images == ex_parent_images
    assert update_actions == ex_update_actions


def test_update_dry_run():
    dfp = MagicMock()
    old_parent_images = sentinel.old_parent_images
    dfp.parent_images = old_parent_images
    update(dfp, {}, {}, True)

    assert dfp.parent_images == old_parent_images


@pytest.mark.parametrize(
    'input_dockerfile_content, expected_dockerfile_content, '
    'skopeo_inspect_output, args', [
    (
        dedent(
            """
            FROM ubi8-minimal:8-released AS builder
            RUN echo hello

            #@follow_tag(ubi8-minimal:8-released)
            FROM ubi8-minimal:8-released
            RUN echo hi

            #@follow_tag(quay.io/rh-osbs/ubi8-minimal:8-released)
            FROM ubi8-minimal:8-released

            RUN echo hello
            """
        ),
        dedent(
            """
            FROM ubi8-minimal:8-released AS builder
            RUN echo hello

            #@follow_tag(ubi8-minimal:8-released)
            FROM ubi8-minimal:8.0-204
            RUN echo hi

            #@follow_tag(quay.io/rh-osbs/ubi8-minimal:8-released)
            FROM quay.io/rh-osbs/ubi8-minimal:8.0-204

            RUN echo hello
            """
        ),
        """
        {
            "Labels": {
                "name": "ubi8-minimal",
                "release": "204",
                "version": "8.0"
            }
        }
        """,
        []
    ),
    (
        dedent(
            """
            #@follow_tag(registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0)
            FROM registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0
            RUN echo hi
            """
        ),
        dedent(
            """
            #@follow_tag(registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0)
            FROM registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0-100
            RUN echo hi
            """
        ),
        """
        {
            "Labels": {
                "name": "cnv/hco-bundle-registry",
                "release": "100",
                "version": "v2.2.0"
            }
        }
        """,
        [
            '--flat-nested-repositories'
        ]
    ),
    (
        dedent(
            """
            #@follow_tag(cnv-hco-bundle-registry:v2.2.0)
            FROM cnv-hco-bundle-registry:v2.2.0
            RUN echo hi
            """
        ),
        dedent(
            """
            #@follow_tag(cnv-hco-bundle-registry:v2.2.0)
            FROM cnv-hco-bundle-registry@sha256:123
            RUN echo hi
            """
        ),
        """
        {
            "Name": "registry.com/rh-osbs/cnv-hco-bundle-registry",
            "Digest": "sha256:123"
        }
        """,
        [
            '--use-sha'
        ]
    )
])
def test_base_image_update_full_run(
    input_dockerfile_content,
    expected_dockerfile_content,
    skopeo_inspect_output,
    args,
    monkeypatch,
    tmpdir
):
    input_dockerfile_path = tmpdir.join('Dockerfile')
    input_dockerfile_path.write(input_dockerfile_content)
    skopeo_inspect_mock = MagicMock(return_value=skopeo_inspect_output)
    monkeypatch.setattr(
        dockerfile_utils, 'skopeo_inspect', skopeo_inspect_mock
    )

    main(['parent-image-update', str(input_dockerfile_path)] + args)
    assert input_dockerfile_path.read() == expected_dockerfile_content


def test_run_command_which_fails_should_raise():
    with pytest.raises(CalledProcessError):
        run_command(['false'])


@pytest.mark.parametrize('floating_ref, nvr_tag, expected', [
    (
        'registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0',
        'cnv-hco-bundle-registry:v2.2.0-274',
        'registry.com/rh-osbs/cnv-hco-bundle-registry:v2.2.0-274'
    ),
    (
        'cnv-hco-bundle-registry:v2.2.0',
        'cnv-hco-bundle-registry:v2.2.0-274',
        'cnv-hco-bundle-registry:v2.2.0-274'
    ),
    (
        'registry.com/cnv-hco-bundle-registry:v2.2.0',
        'cnv-hco-bundle-registry:v2.2.0-274',
        'registry.com/cnv-hco-bundle-registry:v2.2.0-274'
    )
])
def test_add_registry_if_needed(floating_ref, nvr_tag, expected):
    assert add_registry_if_needed(floating_ref, nvr_tag) == expected


@pytest.mark.parametrize('inspect_struct, expected', [
    (
        {
            'Name': 'registry.com/cnv-hco-bundle-registry',
            'Digest': 'sha256:123',
        },
        'cnv-hco-bundle-registry@sha256:123'
    )
])
def test_get_latest_image_by_sha(inspect_struct, expected):
    assert get_latest_image_by_sha(inspect_struct) == expected
