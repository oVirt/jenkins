#!/usr/bin/env python
"""ovirt_build_resolver.py - Map between oVirt patches
and their candidate release branches.
"""
from __future__ import absolute_import, print_function
from collections import namedtuple
import os
import logging
from xdg.BaseDirectory import xdg_cache_home
from scripts.git_utils import git
from scripts.stdci_dsl.api import get_threads_with_globals
from scripts.jenkins_objects import JobRunSpec
from hashlib import sha1
from six import itervalues, iteritems, string_types
from functools import partial

CACHE_NAME = 'gate_cache'
logger = logging.getLogger(__name__)
patch_object = namedtuple(
    'patch_object', ['name', 'refspec', 'branch', 'url', 'sha']
)


def create_patch_threads(sources_table):
    """Get sources_table info from given str and build jobs threads from it.

    :param str sources_table: patches info seperated by url refspec branch
    :rtype: dict
    :returns: a dict of lists per projects organized by their ovirt release.
    """
    patches_list = parse_sources_table(sources_table)
    patch_to_release = unique_patches_per_release(patches_list)
    jrs_list = [
        (
            create_job_spec(patch_object),
            release,
            create_pipeline_thread_name(patch_object)
        )
        for patch_object, release in patch_to_release
    ]
    return jrs_list


def parse_sources_table(sources_table):
    """Parse each patch and yield it's data
    :params: sources_table str: sources_table input
    :rtype: tuple
    :returns: returns patch data and it's ovirt releases.
    """
    for patch in sources_table.splitlines():
        patch_data = create_patch_object(patch)
        releases = get_release_branches(patch_data)
        yield (patch_data, releases)


def create_patch_object(patch):
    """per single patch, create it's data.
    :params str: patch.
    :rtype: patch_object.
    :returns: instance of patch object.
    """
    url, branch, refspec = patch.split()
    name = get_project_name(url)
    sha = get_patch_sha(url, refspec)
    return patch_object(name, refspec, branch, url, sha)


def get_project_name(project_url):
    """Retrives project name from a given URL.
    :params str: project_url
    :rtype     : str
    :returns   : project's name
    """
    project_name = project_url.split('/')[-1]
    if '.git' in project_name:
        project_name = project_name.split('.git')[0]
    return project_name


def clone_project(url, refspec):
    """Clone project, fetch, and checkout the refspec in order to read later
       the stdci.yaml configuration.
    :params str url: url of the remote git repo.
    :params str refspec: the commit to check with.
    :params str branch: the branch associated with the commit to get the
    releases from.
    :rtype: str/list
    :returns: returns a string for a single ovirt release, or a list for
    multiple releases.
    """
    cache_dir_name = sha1(url.encode('utf-8')).hexdigest()
    cache_dir_path = os.path.join(xdg_cache_home, CACHE_NAME, cache_dir_name)
    cache_git_dir = os.path.join(cache_dir_path, '.git')
    logger.debug("Cache git dir is: {0}".format(cache_git_dir))
    git('init', cache_dir_path)
    rgit = partial(
        git, '--git-dir=' + cache_git_dir,
        '--work-tree=' + cache_dir_path
    )
    rgit('fetch', '-u', url, '+{0}:myhead'.format(refspec))
    rgit('checkout', 'myhead')
    rgit('reset', '--hard', 'HEAD')
    rgit('clean', '-fdx')
    return cache_dir_path


def get_patch_sha(url, refspec):
    project_dir = clone_project(url, refspec)
    project_git_dir = os.path.join(project_dir, '.git')
    sha = git('--git-dir={0}'.format(project_git_dir), 'rev-parse', 'HEAD')
    return sha


def get_release_branches(patch_object):
    """Returns release branches per project's branch.

    :params patch_object: object containing patch data.
    :rtype: list
    :returns: returns a list of releases, None if there is no release.
    """
    project_dir = clone_project(patch_object.url, patch_object.refspec)
    _, gopts = get_threads_with_globals(project_dir, 'build-artifacts')
    rb = gopts.get('releasebranches', {})
    releases = rb.get(patch_object.branch, [])
    if isinstance(releases, string_types):
        return [releases]
    return releases


def create_job_spec(project):
    """create a job for specific project
    :params project: project specification.
    :rtype: JobRunSpec
    :returns: JobRunSpec instance for a given project.
    """
    return JobRunSpec(
        job_name=project.name + "_standard-builder",
        params=dict(
            STD_CI_REFSPEC=project.refspec,
            STD_CI_CLONE_URL=project.url
        )
    ).as_pipeline_build_step()


def create_pipeline_thread_name(patch):
    """Generating parallel thread name for the patch.
    :params: patch object
    :rtype: str
    :returns: thread name for the parallel build
    """
    job_name = "-".join([patch.name, patch.sha[0:7]])
    return job_name


def unique_patches_per_release(patches):
    """
    :params: list of patches
    :rtype: dict
    :returns: dict of mapping between patches to releases.
    """
    release_to_patches = dict()
    for patch_object, releases in patches:
        for release in releases:
            release_to_patches.setdefault(
                release, {})[patch_object.name] = patch_object
    patches_to_releases = dict()
    for release, patch_dict in iteritems(release_to_patches):
        for patch_obj in itervalues(patch_dict):
            patches_to_releases.setdefault(patch_obj, []).append(release)

    return iteritems(patches_to_releases)
