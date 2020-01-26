#!/usr/bin/env python
"""secrets_resolvers.py - CI secrets resolvers library
"""
import yaml
import argparse
from re import match
from xdg.BaseDirectory import xdg_config_home


try:
    from resolver_base import ResolverKeyError
except ImportError:
    from stdci_libs.resolver_base import ResolverKeyError


def main():
    parse_args()


def parse_args():
    description_msg = 'Resolve and filter secret data'
    parser = argparse.ArgumentParser(description=description_msg)
    parser.add_argument(
        "-f", "--secret-file", type=str,
        help=(
            "Path to secret file. if not specified"
            "will use default at xdg_home/ci_secret_file.yaml"
        )
    )
    subparsers = parser.add_subparsers()

    # subparser for resolve functionality
    parser_resolve = subparsers.add_parser(
        'resolve', help="Resolve secrets file",
        description=(
            "Resolve secrets file and return requested secret"
            "if resolve is used, the first argument to resolve should be the"
            "key which should be resolved."
            "secrets_resolvers.py resolve key"
        )
    )
    parser_resolve.add_argument("key", type=str,
                                help="Name of the secret to resolve")
    parser_resolve.set_defaults(func=main_resolve)

    # subparser for filter functionality
    parser_filter = subparsers.add_parser(
        'filter', help="Filter secrets file",
        description=(
            "Filter secrets file and return filtered data."
            "The file is being filtered by project and branch."
        )
    )
    parser_filter.add_argument(
        "project", type=str, help="Project by which secrets will be filtered"
    )
    parser_filter.add_argument(
        "branch", type=str, help="Branch by which secrets will be filtered"
    )
    parser_filter.set_defaults(func=main_filter_data)
    args = parser.parse_args()
    args.func(args)


def main_filter_data(args):
    print(
        yaml.dump(
            list(filter_secret_data(
                args.project, args.branch, load_secret_data(args.secret_file))),
            default_flow_style=False
        )
    )


def main_resolve(args):
    print(
        yaml.dump(
            ci_secrets_file_resolver(
                load_secret_data(args.secret_file), args.key
            ),
            default_flow_style=False
        )
    )


def ci_secrets_file_resolver(secret_data, req_secret_name):
    """Resolve CI secret - extrat the data field

    :param list secret_data: A list representing the yaml config of the secrets
                              file.
    :param str req_secret_name:   The name of the requested secret.

    :rtype: dict
    :returns: A dict containing the requested keys and values
    """
    try:
        return next(secret['secret_data'] for secret in secret_data
                    if match(secret.get('name', '.*'), req_secret_name))
    except StopIteration:
        raise ResolverKeyError(
            "Could not find matching secret for {0}".format(req_secret_name)
        )


def filter_secret_data(project, branch, secret_data):
    """Filter secrets file by project and branch.

    :param list secret_data:           Secrets data to filter
    :param str project:                To which project the secret relates to
    :param str branch:                 To Which branch the secret relates to

    :rtype: list
    :returns: Filtered secrets data
    """
    for data in secret_data:
        if (
            match(data.get('project', '.*'), project)
            and match(data.get('branch', '.*'), branch)
        ):
            yield data


def load_secret_data(file_to_load=None):
    """Load yaml file from a given location

    :param str file_to_load: (optional) Path to the file we need to load
                             If not specified, will use default file at
                             $xdg_config_home/ci_secrets_file.yaml

    :rtype: list
    :returns: A list with the file's data. An empty list if data was not found.
    """
    if file_to_load is None:
        file_to_load = xdg_config_home + "/ci_secrets_file.yaml"
    try:
        with open(file_to_load, 'r') as sf:
            return yaml.safe_load(sf)
    except IOError:
        return []


if __name__ == "__main__":
    main()
