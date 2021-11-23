#!/usr/bin/env python
"""mirror_client.py - Clinet for oVirt CI transactional mirrors
"""
from six.moves import StringIO, range
from six.moves.configparser import RawConfigParser
from six.moves.urllib.parse import urlparse, urljoin
from six import MAXSIZE, iteritems, string_types
import requests
from requests.exceptions import ConnectionError, Timeout
from os import environ
import glob
import logging
import yaml
import re
from collections import Mapping
from time import sleep
import argparse
from base64 import b64decode
import json

HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
HTTP_RETRY_DELAY_SEC = 0.2

logger = logging.getLogger(__name__)


def main():
    (mirrors_uri, configs, allow_proxy) = parse_args()
    mirrors_data = mirrors_from_uri(mirrors_uri)
    for conf in configs:
        inject_yum_mirrors_file(mirrors_data, conf, allow_proxy)


def parse_args():
    """Parse positional arguments and return their values"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mirrors",
        help="Path or URL to a mirrors file."
    )
    parser.add_argument(
        "configs", nargs='+',
        help="A list of yum configs to modify."
    )
    parser.add_argument(
        "-p", "--proxy", action='store_true', default=False,
        help="If not specified, proxy will be set to None."
    )
    args = parser.parse_args()
    return args.mirrors, args.configs, args.proxy


def inject_yum_mirrors(
    mirrors, yum_cfg, out_cfg, allow_proxy=False, none_value=None
):
    """Inject yum mirrors into the given yum configuration

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param file yum_cfg:     YUM configuration file object to adjust
    :param file out_cfg:     File object to write adjusted configuration into
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)
    :param str none_value:   Specify what is the value to set to the 'proxy'
                             configuration option for disabling proxy use. This
                             is '_none_' for older (< fc29) distros, and 'None'
                             for newer ones. If None (the default) is passed,
                             the value will be decided by the repo name suffix

    yum_cfg can be read-only, out_cfg should not be the same as yum_cfg.

    :returns: None
    """
    oldcfg = RawConfigParser()
    newcfg = RawConfigParser()
    _readfp(oldcfg, yum_cfg)
    for section in oldcfg.sections():
        for repoid, baseurl in mirrors.get('before:' + section, []):
            mk_injected_section(
                oldcfg, newcfg, repoid, baseurl, allow_proxy, none_value
            )
        if section not in mirrors:
            copy_section(oldcfg, newcfg, section)
        else:
            mk_injected_section(
                oldcfg, newcfg, section, mirrors[section], allow_proxy,
                none_value
            )
    newcfg.write(out_cfg)


def copy_section(oldcfg, newcfg, section):
    """Copy a configuration section between RawConfigParser objects

    :param RawConfigParser oldcfg: RawConfigParser to read from
    :param RawConfigParser newcfg: RawConfigParser to write to
    :param str section:            The name of the section to copy
    """
    if not oldcfg.has_section(section):
        return
    if not newcfg.has_section(section):
        newcfg.add_section(section)
    for option, value in oldcfg.items(section):
        newcfg.set(section, option, value)


def mk_injected_section(
    oldcfg, newcfg, section, baseurl, allow_proxy=False, none_value=None
):
    """Make a configuration section with injected mirror URL

    :param RawConfigParser oldcfg: RawConfigParser to take existing
                                   configuration values from
    :param RawConfigParser newcfg: RawConfigParser to write configuration
                                   section into
    :param str section:            The name of the configuration section to
                                   make
    :param str baseurl:            The mirror URL to inject
    :param bool allow_proxy:       Wether to allow accessing the mirrors via
                                   HTTP proxies (defaults to False)
    :param str none_value:         Specify the 'no-proxy' value - see docstring
                                   for inject_yum_mirrors for full explanation
    """
    copy_section(oldcfg, newcfg, section)
    if not newcfg.has_section(section):
        newcfg.add_section(section)
    if none_value is None:
        none_value_str = none_value_by_repo_name(section)
    else:
        none_value_str = str(none_value)
    newcfg.set(section, 'baseurl', baseurl)
    newcfg.remove_option(section, 'mirrorlist')
    newcfg.remove_option(section, 'metalink')
    if not allow_proxy:
        newcfg.set(section, 'proxy', none_value_str)


def _readfp(cp, fp, filename=None):
    """Fix Python 3.2+ compatibility

    RawConfigParser.readfp had been renamed to read_file in Python 3.2
    """
    if hasattr(cp, 'read_file'):
        return cp.read_file(fp, filename)
    else:
        return cp.readfp(fp, filename)


def none_value_by_repo_name(repo_name):
    """Auto-detect the no-proxy value from the repo name

    :param str repo_name: The name of the repo as appears in square brackets in
                          the yum configuration file

    :rtype: str
    :returns: If the name of the repo ends witha distro suffix for a distro
              older then fc29, returns '_none_', otherwise returns 'None'
    """
    m = re.search('-(?P<distro>fc|el)(?P<version>[0-9]+)$', repo_name)
    if not m:
        return 'None'
    newer_distros = {'fc': 29}
    if newer_distros.get(m.group('distro'), MAXSIZE) <= int(m.group('version')):
        return 'None'
    else:
        return '_none_'


def inject_yum_mirrors_str(
    mirrors, yum_cfg_str, allow_proxy=False, none_value=None
):
    """Inject yum mirrors into the given yum configuration string

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str yum_cfg:      YUM configuration string to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)
    :param str none_value:   Specify the 'no-proxy' value - see docstring for
                             inject_yum_mirrors for full explanation
    :rtype: str
    :returns: A string of the adjusted configuration
    """
    out_cfg = StringIO()
    inject_yum_mirrors(
        mirrors, StringIO(yum_cfg_str), out_cfg, allow_proxy, none_value
    )
    out_cfg.seek(0)
    return out_cfg.read()


def inject_yum_mirrors_file(
    mirrors, file_name, allow_proxy=False, none_value=None
):
    """Inject yum mirrors into the given yum configuration file

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str file_name:    YUM configuration file to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :param str none_value:   Specify the 'no-proxy' value - see docstring for
                             inject_yum_mirrors for full explanation
    :returns: None
    """
    with open(file_name, 'r') as rf:
        with open(file_name, 'r+') as wf:
            inject_yum_mirrors(mirrors, rf, wf, allow_proxy, none_value)
            wf.truncate()
    logger.info('Injected mirrors into: {0}'.format(file_name))


def inject_yum_mirrors_file_by_pattern(
    mirrors, file_pattern, allow_proxy=False, none_value=None
):
    """Inject yum mirrors into the given yum configuration file

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str file_pattern: YUM configuration file glob pattern to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)
    :param str none_value:   Specify the 'no-proxy' value - see docstring for
                             inject_yum_mirrors for full explanation
    :returns: None
    """
    for file_name in glob.glob(file_pattern):
        inject_yum_mirrors_file(mirrors, file_name, allow_proxy, none_value)


def mirrors_from_http(
    url='http://mirrors-wdc.ovirt.org/repos/yum/all_latest.json',
    json_varname='latest_ci_repos',
    allow_proxy=False,
    none_value=None
):
    """Load mirrors from given URL

    :param str url:          Where to find mirrors JSON file
    :param str json_varname: The variable in the file pointing to the mirror
                             dictionary
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :rtype: dict
    :returns: Loaded mirrors data or an empty dict if could not be loaded
    """
    if allow_proxy:
        proxies = dict()
    else:
        proxies = dict(http=None, https=None)
    try:
        loop_exception = None
        for attempt in range(0, HTTP_RETRIES):
            try:
                resp = requests.get(url, proxies=proxies, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json().get(json_varname, dict())
                else:
                    return dict()
            except ValueError as e:
                # When JSON parsing fails we get a ValueError
                loop_exception = e
            logger.warning(
                'Encountered error getting data from mirrors server' +
                ' in attempt {0}/{1}'.format(attempt, HTTP_RETRIES)
            )
            # Sleep a short while to let server sort its issues
            sleep(HTTP_RETRY_DELAY_SEC)
        else:
            raise loop_exception
    except ConnectionError:
        logger.warning('Failed to connect to mirrors server')
        return dict()
    except Timeout:
        logger.warning('Timed out connecting to mirrors server')
        return dict()


def mirrors_from_file(file_name):
    """Load mirrors from a local file

    :param str filename: The file to load mirrors from

    The file can be JNOS or YAML formatted

    :rtype: dict
    """
    data = None
    with open(file_name, 'r') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, Mapping):
        raise ValueError("Invalid mirrors data in '{0}'".format(file_name))
    return data


def mirrors_from_data_url(url):
    """Load mirrors from a data URL

    :param str url: The data URL to get mirrors from

    Accepted data URLs have the following syntax:

        data:application/json[;base64],<json data>

    Where if `;base64` is present the data would be base64 encoded, otherwise
    it would be in plain text.

    :rtype: dict
    :returs: The mirror data embedded in the URL
    """
    PREFIX = 'data:application/json'
    PLAIN_PREFIX = PREFIX + ','
    B64_PREFIX = PREFIX + ';base64,'
    if url.startswith(PLAIN_PREFIX):
        js = url[len(PLAIN_PREFIX):]
    elif url.startswith(B64_PREFIX):
        js = b64decode(url[len(B64_PREFIX):])
    else:
        return {}
    return json.loads(js)


def mirrors_from_uri(uri, json_varname='latest_ci_repos', allow_proxy=False):
    """Load mirrors from URI

    :param str uri: The URI to mirrors JSON file
    :param str json_varname: The variable in the file pointing to the mirror
                             dictionary
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :rtype: dict
    :returns: Loaded mirrors data or an empty dict if could not be loaded
    """
    parsed = urlparse(uri)
    if parsed.scheme == 'http' or parsed.scheme == 'https':
        mirrors = mirrors_from_http(parsed.geturl(), json_varname, allow_proxy)
    elif parsed.scheme == '' or parsed.scheme == 'file':
        mirrors = mirrors_from_file(parsed.path)
    elif parsed.scheme == 'data':
        mirrors = mirrors_from_data_url(uri)
    mirrors = normalize_mirror_urls(mirrors, uri)
    mirrors = parse_mirror_includes(mirrors, json_varname, allow_proxy)
    return mirrors


def parse_mirror_includes(
    mirrors, json_varname='latest_ci_repos', allow_proxy=False
):
    """Parse and implement includes in the mirrors data

    :param Mapping mirrors: Mirrors data with or without includes
    :param str json_varname: The variable in the file pointing to the mirror
                             dictionary
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    Includes can be specified in mirrors data in two ways:
    1. Adding an 'include:' key that points to list of URLs. Data is read from
       Each one of the URLs in the list and merged into the resulting mirrors
       data
    2. Adding an 'include:before:' key that points to a list of name-url pairs.
       The data will be read from the URLs and then converted to insertion
       statements before the repos that start with `name`.

    :rtype: dict
    :returns: copy of the data in `mirrors` with all includes converted to
              included data
    """
    parsed = {
        k: v for k, v in iteritems(mirrors) if not k.startswith('include:')
    }
    for uri in mirrors.get('include:', []):
        parsed = merge_mirrors(
            parsed, mirrors_from_uri(uri, json_varname, allow_proxy)
        )
    for repo_name, uri in mirrors.get('include:before:', []):
        parsed = merge_mirrors(parsed, mirrors_to_inserts(
            mirrors_from_uri(uri, json_varname, allow_proxy), repo_name
        ))
    return parsed


def merge_mirrors(a, b):
    """Merge mirror data

    Merge the mirror data in b into the data in a so that:
    - A repo that is defined both in 'a' and 'b' remains with the URL defined
      in 'a'
    - When insertions to the same repo exist both in 'a' and 'b', the
      insertions from 'b' are added after the insertions from 'a'

    :rtype: dict
    """
    merged = dict(a)
    for repo_name, repo_url in iteritems(b):
        if repo_name not in merged:
            merged[repo_name] = repo_url
            continue
        if ':' in repo_name:
            merged[repo_name].extend(repo_url)
    return merged


def mirrors_from_environ(
    env_varname='CI_MIRRORS_URL',
    json_varname='latest_ci_repos',
    allow_proxy=False,
):
    """Load mirrors from URL given in an environment variable

    :param str env_varname:  The environment variable containing URL to mirrors
                             JSON file
    :param str json_varname: The variable in the file pointing to the mirror
                             dictionary
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :rtype: dict
    :returns: Loaded mirrors data or an empty dict if could not be loaded or
              the environment variable was not defined
    """
    if env_varname not in environ:
        return dict()
    return mirrors_from_uri(environ[env_varname])


def normalize_mirror_urls(mirrors, base_uri):
    """Turn relative URLs in mirrors to absolute ones

    :param Mapping mirrors: Mirror information map
    :param str base_uri:    Base URI to add to relative URLs, usually the URI
                            whee the mirrors JSON file was obtained from

    :rtype: dict
    :returns: The mirror information given in `mirrors` with all the relative
              URLs turned into absolute ones
    """
    return {
        repo_name: (
            urljoin(base_uri, uri) if isinstance(uri, string_types)
            else [
                urljoin(base_uri, inc_uri) for inc_uri in uri
            ] if repo_name == 'include:'
            else [
                [ins_repo_name, urljoin(base_uri, ins_uri)]
                for ins_repo_name, ins_uri in uri
            ]
        )
        for repo_name, uri in iteritems(mirrors)
    }


def mirrors_to_inserts(mirrors, ins_repo_prefix, ins_type='before'):
    """Convert mirrors map into a set of repo insertions

    :param Mapping mirrors:     Mirrors information map
    :param str ins_repo_prefix: The prefix for names of repos that the repos
                                will be inserted with relation to
    :param str ins_type:        (Optional) The type of insertion to create,
                                currently, only 'before' is supported

    :rtype: dict
    :returns: A new mirror map where the repos in `mirrors` had been converted
              to insertion requests in the following way:
              - The last part of the repo name will be treated as a distro id,
                for example, for a repo called `foo-el7` the distro id would be
                `el7`.
              - The repo will become an insertion with relation to a repo with
                the prefix given in `ins_repo_prefix` and the same distro id.
                For example, if `ins_repo_prefix` is `bar`, a repo called
                `foo-el7` would be inserted in relation to `bar-el7`.
              - Existing insertion statements in `mirrors` are generally left
                as-is, but repos could be added into them.
              - In case there are multiple insertions with relation to the same
                repo, they would be ordered alphabetically according to repo
                name
    """
    inserts = {k: v for k, v in iteritems(mirrors) if ':' in k}
    for repo_name, repo_url in sorted(iteritems(mirrors)):
        if ':' in repo_name:
            continue
        distro = repo_name.rsplit('-', 1)[-1]
        ins_key = u'{}:{}-{}'.format(ins_type, ins_repo_prefix, distro)
        inserts.setdefault(ins_key, []).append([repo_name, repo_url])
    return inserts


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it

    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = logging.INFO


def ovirt_tested_as_mirrors(
    ovirt_release,
    distributions=('el7', 'fc24', 'fc25', 'fc26'),
    repos_base='http://resources.ovirt.org/repos/ovirt/tested',
):
    """Generate a mirrors dict that points to the oVirt tested repos

    :param str ovirt_release:      The oVirt release which tested repos we want
    :param Iterable distributions: (optional) the list of distributions oVirt
                                   is released for
    :param str repos_base:         (optional) the base URL for the 'tested'
                                   repos

    The list passed to 'distributions' does not have to be accurate. The
    resulting dict is used in mirror injection (one of the inject_* functions
    above) so for a repo to be used, someone needs to ask for it by including a
    repo with the correct repo id in a yum configuration file. Therefore it is
    quite safe to include non-existent distros here, and it is also safe to
    omit some exiting distros as long as they are not asked for.

    :rtype: dict
    :returns: A mirrors dict that will cause the URLs for tested repos to be
              injected for repos called 'ovirt-<version>-<distro>'
    """
    return dict(
        (
            'ovirt-{0}-{1}'.format(ovirt_release, distribution),
            '{0}/{1}/rpm/{2}/'.format(repos_base, ovirt_release, distribution)
        ) for distribution in distributions
    )


if __name__ == "__main__":
    main()
