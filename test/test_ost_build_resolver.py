#!/usr/bin/env python
"""test_ovirt_build_resolver - Tests for ovirt_build_resolver
"""
import pytest
from scripts.ost_build_resolver import (
    get_project_name, get_release_branches,
    create_patch_threads, unique_patches_per_release, patch_object,
    create_job_spec, get_patch_sha, create_patch_object,
    create_pipeline_thread_name,
)
from scripts.jenkins_objects import JobRunSpec


@pytest.fixture(scope='function')
def stdci_project_dir(gitrepo, git_branch, git_tag):
    repo = gitrepo(
        'stdci_project_dir',
        {
            'msg': 'stdci yaml commit',
            'files': {
                'stdci.yaml': (
                    'stage: build-artifacts\n'
                    'release_branches:\n'
                    '  master: master\n'
                )
            },
        },
    )
    git_tag('stdci_project_dir', 'master_first_commit')
    with git_branch('stdci_project_dir', 'test-release-branch'):
        gitrepo(
            'stdci_project_dir',
            {
                'msg': 'New release branch',
                'files': {
                    'stdci.yaml': (
                        'stage:\n'
                        '  - build-artifacts\n'
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


@pytest.mark.parametrize('refspec,branch,expected', [
    ('master', 'master', ['master']),
    ('test-release-branch', 'test-release-branch', ['test-release'])
])
def test_get_release_branches(refspec, branch, expected, stdci_project_dir):
    patch = patch_object(
        url=str(stdci_project_dir), refspec=refspec, branch=branch,
        sha='HEAD', name='stdci_project_dir'
    )
    result = get_release_branches(patch)
    assert result == expected


def test_unique_patches_per_release(stdci_project_dir, gitrepo, git_branch):
    patchList = [
        (patch_object('prj1', 'refspec1', 'br1', 'url1', 'sha1'), ['rb1']),
        (patch_object('prj1', 'refspec2', 'br1', 'url1', 'sha2'), ['rb1'])
    ]
    expected = 1  # 1 patch will stay.
    output = unique_patches_per_release(patchList)
    output = list(output)
    assert len(output) == expected


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


def test_create_patch_threads(stdci_project_dir, gitrepo, git_branch):
    url = str(stdci_project_dir)
    with git_branch('stdci_project_dir', 'master'):
        gitrepo(
            'stdci_project_dir',
            {
                'msg': 'New file',
                'files': {
                    'file.txt': 'Some text'
                },
            },
        )
    branch = 'master'
    project1 = " ".join([url, branch, 'master_first_commit'])
    project2 = " ".join([url, branch, 'HEAD'])
    projects = "\n".join([project1, project2])
    projects_list = create_patch_threads(projects)
    projects_list = list(projects_list)
    assert len(projects_list) == 1
