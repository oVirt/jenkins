#!/usr/bin/env python3

"""usrc_data_extractor.py - A tool to extract data from upstream_sources.yaml
"""

import re
import argparse
from itertools import chain

from yaml import safe_load
import sys

try:
    from stdci_tools.usrc import upstream_sources_config, UpstreamSourcesConfigNotFound
except ImportError:
    from usrc import upstream_sources_config, UpstreamSourcesConfigNotFound


def main():
    args = parse_args()
    try:
        usrc_yaml = load_upstream_sources_yaml(args.usrc_yaml)
    except UpstreamSourcesConfigNotFound as e:
        if args.usrc_yaml:
            raise e
        else:
            print(str(e), file=sys.stderr)
            return 0
    environment_file = generate_environment_file(usrc_yaml)
    print(environment_file)


def parse_args():
    parser = argparse.ArgumentParser(description=(
        'Generate environment file from upstream source entries in an '
        'upstream_sources.yaml config. Each upstream source environment '
        'variable is composed out of an upstream source project name is '
        'being capitalized, all hyphens "-" and dots "." are being replaced '
        'with underscores "_", and a suffix of {BRANCH,COMMIT,URL} is added.'
    ))
    parser.add_argument(
        '--usrc-yaml',
        help=(
            'Specify a path to upstream_sources.yaml config. '
            f'If not specified the tool will try to lookup the config'
        )
    )
    return parser.parse_args()


def load_upstream_sources_yaml(usrc_yaml: str = None) -> dict:
    """Load upstream sources yaml

    :param str usrc_yaml:  A path where the config should be loaded from.
    If not specified, the config will be searched in the default
    paths defined by usrc.
    """
    usrc_yaml = [usrc_yaml] if usrc_yaml else []
    with upstream_sources_config(*usrc_yaml, mode='r') as config:
        return safe_load(config.stream)


def generate_environment_file(usrc_config: dict) -> str:
    """Given a upstream sources config, generate an environment file.

    Every upstream source entry in the config yields 4 environment variables:
    CI_{US_PROJECT_NAME}_UPSTREAM_{COMMIT|SHORT_COMMIT|BRANCH|URL}. Also, for
    backward compatability with older version of similar automation, for the
    first upstream source entry in the list, generate 4 legacy environment
    variables: CI_UPSTREAM_{COMMIT|SHORT_COMMIT|BRANCH|URL} (w/o project name).

    :param dict usrc_config: upstream sources config
    :returns: a string representation of an environment file
    """
    if not isinstance(usrc_config, dict):
        cfg_type = type(usrc_config)
        raise TypeError(
            f'upstream sources config should be a dict, not {cfg_type}'
        )
    try:
        git_config_entries = usrc_config['git']
    except KeyError:
        raise KeyError('Missing `git` config entry in upstream_sources.yaml.')
    environment_file_entries = (
        generate_entry_for_upstream_source(idx, usrc_entry)
        for idx, usrc_entry in enumerate(git_config_entries)
    )
    # Some of our users already have automation set for a single upstream
    # source so we also create vars with the legacy CI prefix for the first
    # entry in the config to support them.
    legacy_environment_file_entries = generate_entry_for_upstream_source(
        entry_index=0,
        usrc_entry=git_config_entries[0],
        legacy_name=True
    )
    return ''.join(chain(
        environment_file_entries, (legacy_environment_file_entries,)
    ))


def generate_entry_for_upstream_source(
    entry_index: int, usrc_entry: dict, legacy_name: bool = False
) -> str:
    """Given an upstream source entry, generate string entry for the
    environment file.

    :param dict usrc_entry:  upstream source entry from upstream_sources.yaml
    :param int entry_index:  the index of the upstream source entry in the list
    :param bool legacy_name: set to True to maintain compatability with legacy
                             var names from old version of the automation.
                             If True, ommits the project name from the var name
    :returns: a string entry for the environment file
    """
    try:
        branch = usrc_entry['branch']
        commit = usrc_entry['commit']
        url = usrc_entry['url']
    except KeyError as key_error:
        missing_entry = key_error.args[0]
        raise KeyError(
            f'Missing {missing_entry} in upstream source entry #{entry_index}.'
        )
    if legacy_name:
        var_name = ''
    else:
        var_name = project_name_from_repo_url(url) + '_'
    return (
        f'CI_{var_name}UPSTREAM_BRANCH={branch}\n'
        f'CI_{var_name}UPSTREAM_COMMIT={commit}\n'
        f'CI_{var_name}UPSTREAM_SHORT_COMMIT={commit[0:7]}\n'
        f'CI_{var_name}UPSTREAM_URL={url}\n'
    )


def project_name_from_repo_url(repo_url: str) -> str:
    """Given a repo url, return the name of the project where all letters are
    in upper-case and all hyphens and dots are replaced with underscores.

    :param str repo_url: a full repo url
    :returns: the project name in upper-case and underscores
    """
    pattern = re.compile(r'(.*/)?(.+?)(\.git)?$')
    match = pattern.match(repo_url)
    if match is None:
        raise ValueError(
            "Failed to extract project name from repo URL. "
            "Repo URL can't be empty"
        )
    project_name = match.group(2)
    project_name = project_name.upper().replace('-', '_').replace('.', '_')
    return project_name


if __name__ == '__main__':
    main()
