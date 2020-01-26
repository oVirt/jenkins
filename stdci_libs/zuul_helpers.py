#!/usr/bin/env python
# zuul_helpers.py - Helper functions for integrting STDCI with Zuul
#
import re
from six import iteritems, string_types
from collections import Mapping, Iterable
import os
from glob import glob
import yaml


def is_gated_project(
    project, project_name=None, gate_pipelines='^gate-patch$',
    gate_jobs='^(run-gate-job|.*-gate)$', gate_templates='^.*-gated-project$'
):
    """Determine is a project is gated by Zuul

    This function scans the project source code for Zuul configuration files
    and tries to determine if it is gated by Zuul according to values given in
    other parameters.

    :param str project:             The path to the project source code to be
                                    examined
    :param str project_name:        (Optional) The name of the project we
                                    examine.  Used to match Zuul YAML project
                                    entries. If not given, the last part of the
                                    path given in the `project` parameter would
                                    be used.
    :param str gate_pipelines:      (Optional) A regular expression the matches
                                    the names of the Zuul pipelines used for
                                    gating. Default value matches `gate-patch`.
    :param Iterable gate_jobs:      (Optional) A regular expression string
                                    that is expected to match the names of Zuul
                                    jobs used for gating.
    :param Iterable gate_templates: (Optional) A regular expression string that
                                    is expected to match the names of Zuul
                                    project templates that cause a project to
                                    be gated

    A project would be considered as gated if its either derived from a
    template that matches one of the expressions in `gate_templates` or if it
    includes a job that matches the expression in `gate_jobs` within a pipeline
    that matches `gate_pipelines`.

    :rtype: Boolean
    :returns: True if the project is deemed to be gated by Zuul
    """
    zfiles = ('zuul.yaml', 'zuul.d/*.yaml', '.zuul.yaml', '.zuul.d/*.yaml')
    project = str(project)
    if not project_name:
        project_name = os.path.basename(project)
    for zfile in zfiles:
        # Zuul defines that the files in the `*.d` directories need to be
        # processed in alphabetical order, so we sort glob`s output
        cfiles = sorted(glob(os.path.join(project, zfile)))
        if not cfiles:
            continue
        projects = []
        for cfile in cfiles:
            entries = []
            with open(cfile, 'r') as f:
                entries = yaml.safe_load(f)
            if not isinstance(entries, Iterable):
                continue
            projects.extend(
                ent['project'] for ent in entries
                if isinstance(ent, Mapping)
                and 'project' in ent
                and ent['project'].get('name', project_name) == project_name
            )
        if not projects:
            return False
        if len(projects) == 1:
            project = projects[0]
        else:
            project = merge_project_yaml(projects, gate_pipelines)
        return is_gated_project_entry(
            project, gate_pipelines, gate_jobs, gate_templates
        )


def merge_project_yaml(entries, gate_pipelines='^gate-patch$'):
    """Merge multiple project YAML entries together

    When using Zuul configuration directories, the project configuration can be
    spread across multiple files and needs to be merged together in a
    non-trivial way. Since we only care about project templates and gating
    jobs, this function includes a partial implementation of the Zuul merging
    algorithm that only deals with those.

    :param Iterable entries:   An iterable containing project entries to be
                               merged together.
    :param str gate_pipelines: (Optional) A regular expression the matches
                               the names of the Zuul pipelines used for gating.
                               Default value matches `gate-patch`. Only jobs
                               within pipeline entriess that match this
                               expression will be merged by this job, the rest
                               will be thrown away.

    This function will throw away all project information that is unrelated to
    gating including pipeline entries that do not match `gate_pipelines` and
    all other project properties other then `templates`.

    :rtype: dict
    :returns: A project entry that is the result of merging the given project
              entries
    """
    merged_entry = {}
    for entry in entries:
        for k, v in iteritems(entry):
            if k == 'templates' and v:
                merged_entry.setdefault('templates', []).extend(v)
                continue
            if re.search(gate_pipelines, k) and isinstance(v, Mapping):
                jobs = v.get('jobs')
                if jobs:
                    (
                        merged_entry.setdefault(k, {}).setdefault('jobs', [])
                    ).extend(jobs)
    return merged_entry


def is_gated_project_entry(
    entry, gate_pipelines='^gate-patch$', gate_jobs='^(run-gate-job|.*-gate)$',
    gate_templates='^.*-gated-project$'
):
    """Determine is a project entry is gated by Zuul

    Given a parsed amnd merged project Zuul YAML configuration, determine if it
    is gated or not.

    :param dict entry:              A Zuul project configuration entry to check
    :param str gate_pipelines:      (Optional) A regular expression the matches
                                    the names of the Zuul pipelines used for
                                    gating. Default value matches `gate-patch`.
    :param Iterable gate_jobs:      (Optional) A regular expression string
                                    that is expected to match the names of Zuul
                                    jobs used for gating.
    :param Iterable gate_templates: (Optional) A regular expression string that
                                    is expected to match the names of Zuul
                                    project templates that cause a project to
                                    be gated

    A project would be considered as gated if its either derived from a
    template that matches one of the expressions in `gate_templates` or if it
    includes a job that matches the expression in `gate_jobs` within a pipeline
    that matches `gate_pipelines`.

    This function will only inspect the project `templates` definition and the
    definitions of pipelines that match `gate_pipelines`, all other project
    setting will be ognored and therefore can be safely removed from the
    project entry before passing it to this function.

    :rtype: Boolean
    :returns: True if the project is deemed to be gated by Zuul
    """
    return (
        any(
            re.search(gate_templates, tmpl)
            for tmpl in entry.get('templates', [])
        )
        or any(
            (
                isinstance(pdef, Mapping)
                and re.search(gate_pipelines, pipeline)
                and any(
                    (
                        (
                            isinstance(job, string_types)
                            and re.search(gate_jobs, job)
                        )
                        or (
                            isinstance(job, Mapping)
                            and job
                            and re.search(gate_jobs, next(iter(job)))
                        )
                    )
                    for job in pdef.get('jobs', [])
                )
            )
            for pipeline, pdef in iteritems(entry)
        )
    )
