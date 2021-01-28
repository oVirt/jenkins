#!/usr/bin/env python3
"""inject_repos.py - CI secret repos injection.
"""
import yaml
from lxml import etree
from lxml.etree import ElementTree as ET
import argparse
from six import iteritems

def main():
    repos_file, beaker_file = parse_args()
    repos = load_secret_data(repos_file)
    inject_repos(repos, beaker_file)

def parse_args():
    description_msg = 'Resolve and filter secret data'
    parser = argparse.ArgumentParser(description=description_msg)
    parser.add_argument(
        "-f", "--secret-file", type=str,
        help=("Path to secret file.")
    )
    parser.add_argument(
        "-b", "--beaker-file", type=str,
        help=("Path to beaker file.")
    )
    args = parser.parse_args()
    return args.secret_file, args.beaker_file

def load_secret_data(file_to_load=None):
    """Load yaml file from a given location

    :param str file_to_load: (optional) Path to the file we need to load.

    :rtype: list
    :returns: A list with the file's data. An empty list if data was not found.
    """
    try:
        with open(file_to_load, 'r') as sf:
            return yaml.safe_load(sf)
    except IOError:
        return []

def inject_repos(repos, beaker_file):
    parser = etree.XMLParser(strip_cdata=False)
    tree = etree.parse(beaker_file, parser)
    root = tree.getroot()
    for repo_name, url in iteritems(repos):
        etree.SubElement(root[1][0][4], "repo",
            attrib={"name": repo_name, "url": url})
    tree.write(
        beaker_file, pretty_print=True,
        xml_declaration=True,   encoding="utf-8"
    )

if __name__ == "__main__":
    main()
