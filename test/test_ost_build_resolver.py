#!/usr/bin/env python
"""test_ovirt_build_resolver - Tests for ovirt_build_resolver
"""
import pytest
from scripts.ost_build_resolver import (
    get_project_name, get_release_queues,
    create_build_jobs, unique_patches_per_release, patch_object,
    create_job_spec, get_patch_sha, create_patch_object,
    create_pipeline_thread_name,
)
from scripts import ost_build_resolver
from scripts.jenkins_objects import JobRunSpec


@pytest.fixture(scope='function')
def stdci_project_dir(gitrepo, git_branch, git_tag):
    repo = gitrepo(
        'stdci_project_dir',
        {
            'msg': 'stdci yaml commit',
            'files': {
                'stdci.yaml': (
                    'release_branches:\n'
                    '  master: master\n'
                )
            },
        },
    )
    git_tag('stdci_project_dir', 'master_first_commit')
    with git_branch('stdci_project_dir', 'multi-rel-branch'):
        gitrepo(
            'stdci_project_dir',
            {
                'msg': 'New release branch',
                'files': {
                    'stdci.yaml': (
                        'release_branches:\n'
                        '  multi-rel-branch: [test-1, test-2, r-3]'
                    )
                },
            },
        )
    with git_branch('stdci_project_dir', 'test-release-branch'):
        gitrepo(
            'stdci_project_dir',
            {
                'msg': 'New release branch',
                'files': {
                    'stdci.yaml': (
                        'release_branches:\n'
                        '  test-release-branch: test-release'
                    )
                },
            },
        )
    return repo


@pytest.mark.parametrize('input,expected', [
    ("url/dummy_project", "dummy_project"),
    ("https://dummy-url/dummy-project", "dummy-project"),
    ("https://dummy-url-with-git-suffix/dummy-project.git", "dummy-project"),
    ("ssh://user@scmserver/project.git", "project"),
    ("dummy_string_without_slashes", "dummy_string_without_slashes"),
])
def test_get_project_name(input, expected):
    projects = get_project_name(input)
    assert projects == expected


@pytest.mark.parametrize('refspec,branch,qp,expected', [
    ('master', 'master', None, 'master'),
    ('test-release-branch', 'test-release-branch', None, 'test-release'),
    ('multi-rel-branch', 'multi-rel-branch', None, 'test-1 test-2 r-3'),
    ('multi-rel-branch', 'multi-rel-branch', 'test', '1 2'),
])
def test_get_release_queues(refspec, branch, qp, expected, stdci_project_dir):
    expected = expected.split()
    patch = patch_object(
        url=str(stdci_project_dir), refspec=refspec, branch=branch,
        sha='HEAD', name='stdci_project_dir'
    )
    result = get_release_queues(patch, qp)
    assert result == expected


def test_unique_patches_per_release():
    patchList = [
        (patch_object('pr1', 'ref1a', 'br1', 'url1', 'sha1a'), ['r1']),
        (patch_object('pr1', 'ref1b', 'br1', 'url1', 'sha1b'), ['r1']),
        (patch_object('pr2', 'ref2a', 'br2', 'url2', 'sha2a'), ['r2', 'r3']),
        (patch_object('pr2', 'ref2b', 'br2', 'url2', 'sha2b'), ['r2']),
        (patch_object('pr3', 'ref3a', 'br3', 'url3', 'sha3a'), ['r2']),
        (patch_object('pr3', 'ref3b', 'br3', 'url3', 'sha3b'), ['r2', 'r3']),
        (patch_object('pr4', 'ref4a', 'br4', 'url4', 'sha4a'), ['r1']),
        (patch_object('pr4', 'ref4b', 'br4', 'url4', 'sha4b'), ['r2', 'r3']),
    ]
    expected = [
        (patch_object('pr1', 'ref1b', 'br1', 'url1', 'sha1b'), ['r1']),
        (patch_object('pr2', 'ref2a', 'br2', 'url2', 'sha2a'), ['r3']),
        (patch_object('pr2', 'ref2b', 'br2', 'url2', 'sha2b'), ['r2']),
        (patch_object('pr3', 'ref3b', 'br3', 'url3', 'sha3b'), ['r2', 'r3']),
        (patch_object('pr4', 'ref4a', 'br4', 'url4', 'sha4a'), ['r1']),
        (patch_object('pr4', 'ref4b', 'br4', 'url4', 'sha4b'), ['r2', 'r3']),
    ]
    output = unique_patches_per_release(patchList)
    output = list(output)
    assert sorted(output) == sorted(expected)


@pytest.mark.parametrize('input,expected', [
    (
        patch_object(name='a', refspec='b', branch='c', url='u', sha='d'),
        JobRunSpec(job_name='a_standard-builder', params=dict(
            STD_CI_REFSPEC='b', STD_CI_CLONE_URL='u'
        )).as_pipeline_build_step()
    ),
])
def test_create_job_spec(input, expected):
    output = create_job_spec(input)
    assert output == expected


def test_get_patch_sha(stdci_project_dir, git):
    url = str(stdci_project_dir)
    gitdir = url + '/.git'
    sha = git('--git-dir={0}'.format(gitdir), 'rev-parse', 'HEAD')
    assert sha == get_patch_sha(url, 'HEAD')


@pytest.mark.parametrize('input,expected', [
    (
        patch_object(name='a', refspec='b', branch='c', url='u', sha='d'),
        "a-d"
    )
])
def test_create_job_name_for_thread(input, expected, stdci_project_dir):
    assert create_pipeline_thread_name(input) == expected


def test_create_patch_object(stdci_project_dir, git):
    url = str(stdci_project_dir)
    name = 'stdci_project_dir'
    gitdir = url + '/.git'
    refspec = 'HEAD'
    sha = git('--git-dir={0}'.format(gitdir), 'rev-parse', refspec)
    branch = 'master'
    expected = patch_object(name, refspec, branch, url, sha)
    project = " ".join([url, branch, refspec])
    assert expected == create_patch_object(project)


def test_create_build_jobs(monkeypatch):
    sources_list = [
        (patch_object('pr1', 'ref1a', 'br1', 'u1', 'sh1a'), ['r1']),
        (patch_object('pr1', 'ref1b', 'br1', 'u1', 'sh1b'), ['r1', 'r2']),
        (patch_object('pr1', 'ref1c', 'br1', 'u1', 'sh1c'), ['r1', 'r2']),
        (patch_object('pr2', 'ref2a', 'br2', 'u2', 'sh2a'), ['r1']),
    ]
    expected = [
        ('jspec:ref1c', ['r1', 'r2'], 'pr1-sh1c'),
        ('jspec:ref2a', ['r1'], 'pr2-sh2a'),
    ]
    monkeypatch.setattr(
        ost_build_resolver, 'create_job_spec', lambda x: "jspec:" + x.refspec
    )
    out = create_build_jobs(sources_list)
    out = list(out)
    assert out == expected
