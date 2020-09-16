import builtins
import os
from subprocess import CalledProcessError
from textwrap import dedent

import dockerfile_parse
import pytest
from dockerfile_parse import constants as dfp_constants
from unittest.mock import MagicMock, call, sentinel, create_autospec

from stdci_tools import dockerfile_utils
from stdci_tools.dockerfile_utils import (
    DecoratedCmd, Decorator, FailedToGetLatestVersionError,
    FailedToParseDecoratorError, ImageAndFloatingRef, UpdateAction,
    get_decorated_commands, get_decorator, get_dfps,
    get_tag_from_inspect_struct, get_old_images_and_floating_refs,
    get_update, update, main, run_command, get_latest_image_by_sha,
    replace_tag_with_static_tag, replace_tag_with_sha, skopeo_inspect
)


@pytest.mark.parametrize('inspect, expected', [
    (
        {
            'Labels': {
                'version': 'v2.1.0',
                'release': '1',
            }
        },
        'v2.1.0-1'
    ),
])
def test_get_nvr_tag_from_inspect_struct(inspect, expected):
    assert get_tag_from_inspect_struct(inspect) == expected


@pytest.mark.parametrize('struct', [
    {},
    {'Labels': {'version': 'a'}},
    {'Labels': {'release': 'b'}},
    {'Labels': {}},
    {'Labels': None},
    {'Labels': []}
])
def test_get_get_tag_from_inspect_struct_should_raise(struct):
    with pytest.raises(FailedToGetLatestVersionError):
        get_tag_from_inspect_struct(struct)


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
        []
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
    ),
    (
        dedent(
            """
            #@follow_tag(registry.redhat.io/ubi8/ubi-minimal:8.2)
            FROM registry.redhat.io/ubi8/ubi-minimal:8.2
            RUN echo hi
            """
        ),
        dedent(
            """
            #@follow_tag(registry.redhat.io/ubi8/ubi-minimal:8.2)
            FROM registry.redhat.io/ubi8/ubi-minimal:8.2-345
            RUN echo hi
            """
        ),
        """
        {
            "Labels": {
                "release": "345",
                "version": "8.2"
            }
        }
        """,
        []
    ),
    (
        dedent(
            """
            #@follow_tag(registry.redhat.io/openshift4/ose-ansible-operator:v4.5.0)
            FROM registry.redhat.io/openshift4/ose-ansible-operator:v4.5.0
            RUN echo hi
            """
        ),
        dedent(
            """
            #@follow_tag(registry.redhat.io/openshift4/ose-ansible-operator:v4.5.0)
            FROM registry.redhat.io/openshift4/ose-ansible-operator:v4.5.0-202008100413.p0
            RUN echo hi
            """
        ),
        """
        {
            "Labels": {
                "release": "202008100413.p0",
                "version": "v4.5.0"
            }
        }
        """,
        []
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


@pytest.mark.parametrize('inspect_struct, expected', [
    (
        {
            'Name': 'registry.com/cnv-hco-bundle-registry',
            'Digest': 'sha256:123',
        },
        'sha256:123'
    )
])
def test_get_latest_image_by_sha(inspect_struct, expected):
    assert get_latest_image_by_sha(inspect_struct) == expected


@pytest.mark.parametrize('floating_ref, tag, expected', [
    (
        'registry.redhat.io/ubi8/ubi-minimal:8.2',
        '8.2-345',
        'registry.redhat.io/ubi8/ubi-minimal:8.2-345',
    ),
    (
        'registry.redhat.io/ubi8/ubi-minimal',
        '8.2-345',
        'registry.redhat.io/ubi8/ubi-minimal:8.2-345',
    )
])
def test_replace_tag_with_static_tag(floating_ref, tag, expected):
    assert replace_tag_with_static_tag(floating_ref, tag) == expected


@pytest.mark.parametrize('floating_ref, sha, expected', [
    (
        'registry.redhat.io/ubi8/ubi-minimal:8.2',
        'sha256:123',
        'registry.redhat.io/ubi8/ubi-minimal@sha256:123',
    ),
    (
        'registry.redhat.io/ubi8/ubi-minimal',
        'sha256:123',
        'registry.redhat.io/ubi8/ubi-minimal@sha256:123',
    )
])
def test_replace_tag_with_sha(floating_ref, sha, expected):
    assert replace_tag_with_sha(floating_ref, sha) == expected


@pytest.mark.parametrize('pull_url, kwargs, authfile, expected_command', [
    (
        'rhel:latest',
        {},
        None,
        [
            'skopeo',
            'inspect',
            '--tls-verify=false'
            'docker://rhel:latest',
        ],
    ),
    (
        'rhel:latest',
        {'tls_verify': True},
        None,
        [
            'skopeo',
            'inspect',
            'docker://rhel:latest',
        ],
    ),
    (
        'rhel:latest',
        {'tls_verify': True},
        '/mnt/auth.json',
        [
            'skopeo',
            'inspect',
            'docker://rhel:latest',
            '--authfile',
            '/mnt/auth.json',
        ],
    ),
])
def test_skopeo_inspect(
    pull_url,
    kwargs,
    authfile,
    expected_command,
    monkeypatch
):
    run_command_mock = create_autospec(run_command)
    monkeypatch.setattr(
        dockerfile_utils,
        'run_command',
        run_command_mock
    )
    if authfile is not None:
        monkeypatch.setenv('REGISTRY_AUTH_FILE', authfile)

    skopeo_inspect(pull_url, **kwargs)
    run_command_mock.assert_called_once()
