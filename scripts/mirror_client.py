#!/usr/bin/env python
"""mirror_client.py - Clinet for oVirt CI transactional mirrors
"""
from six.moves import StringIO, range
from six.moves.configparser import RawConfigParser
import requests
from requests.exceptions import ConnectionError, Timeout
from os import environ
import glob
import logging

HTTP_TIMEOUT = 30
HTTP_RETRIES = 3

logger = logging.getLogger(__name__)


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
    logger.info('Injected mirrors into: {0}'.format(file_name))


def inject_yum_mirrors_file_by_pattern(
    mirrors, file_pattern, allow_proxy=False
):
    """Inject yum mirrors into the given yum configuration file

    :param Mapping mirrors:  A mapping of mirror names to URLs
    :param str file_pattern: YUM configuration file glob pattern to adjust
    :param bool allow_proxy: Wether to allow accessing the mirrors via HTTP
                             proxies (defaults to False)
    :returns: None
    """
    for file_name in glob.glob(file_pattern):
        inject_yum_mirrors_file(mirrors, file_name, allow_proxy)


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
        for attempt in range(0, HTTP_RETRIES):
            try:
                resp = requests.get(url, proxies=proxies, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json().get(json_varname, dict())
                else:
                    return dict()
            except ValueError:
                # When JSON parsing fails we get a ValueError
                pass
            logger.warn('Encountered error getting data from mirrors server' +
                        ' in attempt {0}/{1}'.format(attempt, HTTP_RETRIES))
        else:
            raise
    except ConnectionError:
        logger.warn('Failed to connect to mirrors server')
        return dict()
    except Timeout:
        logger.warn('Timed out connecting to mirrors server')
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


def setupLogging(level=logging.INFO):
    """Basic logging setup for users of this script who don't what to bother
    with it

    :param int level: The logging level to setup (set to consts from the
                      logging module, default is INFO)
    """
    logging.basicConfig()
    logging.getLogger().level = logging.INFO
