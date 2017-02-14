#!/usr/bin/env python
"""mirror_client.py - Clinet for oVirt CI transactional mirrors
"""
from six.moves import StringIO
from six.moves.configparser import RawConfigParser
import requests
from requests.exceptions import ConnectionError
from os import environ


def inject_yum_mirrors(mirrors, yum_cfg, out_cfg, allow_proxy=False):
    """Inject yum mirrors into the given yum configuration

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param file yum_cfg:     YUM configuration file object to adjust
    :param file out_cfg:     File object to write adjusted configuration into
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    yum_cfg can be read-only, out_cfg should not be the same as yum_cfg.

    :returns: None
    """
    cfg = RawConfigParser()
    cfg.readfp(yum_cfg)
    for section in cfg.sections():
        if section not in mirrors:
            continue
        cfg.set(section, 'baseurl', mirrors[section])
        cfg.remove_option(section, 'mirrorlist')
        cfg.remove_option(section, 'metalink')
        if not allow_proxy:
            cfg.set(section, 'proxy', '_none_')
    cfg.write(out_cfg)


def inject_yum_mirrors_str(mirrors, yum_cfg_str, allow_proxy=False):
    """Inject yum mirrors into the given yum configuration string

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str yum_cfg:      YUM configuration string to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :rtype: str
    :returns: A string of the adjusted configuration
    """
    out_cfg = StringIO()
    inject_yum_mirrors(mirrors, StringIO(yum_cfg_str), out_cfg, allow_proxy)
    out_cfg.seek(0)
    return out_cfg.read()


def inject_yum_mirrors_file(mirrors, file_name, allow_proxy=False):
    """Inject yum mirrors into the given yum configuration file

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str file_name:    YUM configuration file to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :returns: None
    """
    with open(file_name, 'r') as rf:
        with open(file_name, 'r+') as wf:
            inject_yum_mirrors(mirrors, rf, wf, allow_proxy)
            wf.truncate()


def mirrors_from_http(
    url='http://mirrors.phx.ovirt.org/repos/yum/all_latest.json',
    json_varname='latest_ci_repos',
    allow_proxy=False,
):
    """Load mirrors from given URL

    :param str url:          Where to find mirrors JSON file
    :param str json_varname: The variable in the file pointing to the mirror
                             dictionary
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)

    :rtype: dict
    :returns: Loaded mirros data or an empty dict if could not be loaded
    """
    if allow_proxy:
        proxies = dict()
    else:
        proxies = dict(http=None, https=None)
    try:
        resp = requests.get(url, proxies=proxies)
        if resp.status_code == 200:
            return resp.json().get(json_varname, dict())
        else:
            return dict()
    except ConnectionError:
        return dict()


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
    :returns: Loaded mirros data or an empty dict if could not be loaded or the
              environment variable was not defined
    """
    if env_varname not in environ:
        return dict()
    return mirrors_from_http(environ[env_varname], json_varname, allow_proxy)
