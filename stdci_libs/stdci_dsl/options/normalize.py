#!/bin/env python

from __future__ import absolute_import
import os
import logging
import re
from tempfile import mkstemp
from datetime import timedelta
from collections import Mapping, Iterable, namedtuple
from hashlib import md5
from fnmatch import fnmatch
from itertools import product
from copy import copy
from six import string_types, iteritems, iterkeys
from yaml import safe_load
import py

from ..parser import stdci_load, ConfigurationNotFoundError
from ..options.defaults import DefaultValue
from ..options.defaults.values import (
    DEFAULT_REPORTING, DEFAULT_RUNTIME_REQUIREMENTS
)
from .base import ConfigurationSyntaxError, render_template
from ..syntax_utils import remove_case_and_signs
from .containers import Containers
from .podspecs import PodSpecs

from stdci_tools.usrc import get_modified_files


logger = logging.getLogger(__name__)
RepoConfig = namedtuple('RepoConfig', 'name,url')
MountConfig = namedtuple('MountConfig', 'src,dst')


class ConfigurationNotFound(Exception):
    pass


class UnknownFileSource(Exception):
    pass


def normalize(project, threads):
    """Resolve vectors options and set the proper values for every option.
    Threads that don't have script configured, will be filtered out of the list
    since they only configure an environment without functionality.

    This method is preparing the vectors for use by resolving path's, writing
    files and etc.

    :param str project:      Path to project directory
    :param Iterable vectors: Iterable of JobThread objects

    :rtype: Iterator
    :return: Returns iterator over a vector objects for the requested stage
    """
    project = py.path.local(project)
    for thread in threads:
        runif_cfg = thread.options.get('runif', None)
        if runif_cfg:
            if not _resolve_stdci_runif_conditions(project, thread, runif_cfg):
                continue
        # We need to render scripts_directory here because it takes effect
        # when resolving paths for option(s) configuration file(s).
        thread_options_with_scdir = render_template(
            thread, thread.options.get('scriptsdirectory', '')
        )
        thread_with_scdir = thread.with_modified(
            options=thread.options.update(thread_options_with_scdir)
        )
        script = _resolve_stdci_script(project, thread_with_scdir)
        if script is None:
            # We can't use threads with no functionality at all
            continue
        yumrepos = _resolve_stdci_yum_config(project, thread, 'yumrepos')
        environment = _resolve_stdci_yaml_config(project, thread, 'environment')
        mounts = _normalize_mounts_config(project, thread)
        repos = _normalize_repos_config(project, thread)
        packages = _resolve_stdci_list_config(project, thread, 'packages')
        reporting = _normalize_reporting_config(thread)
        timeout = _normalize_timeout(thread)
        runtime_requirements = _normalize_runtime_requirements(thread)
        normalized_options = copy(thread_with_scdir.options)
        normalized_options['script'] = script
        normalized_options['environment'] = environment
        normalized_options['yumrepos'] = yumrepos
        normalized_options['mounts'] = mounts
        normalized_options['repos'] = repos
        normalized_options['packages'] = packages
        normalized_options['reporting'] = reporting
        normalized_options['timeout'] = timeout
        normalized_options['runtimerequirements'] = runtime_requirements
        normalized_thread = thread_with_scdir.with_modified(
            options=normalized_options
        )

        option_classes = (Containers, PodSpecs)
        option_instances = (oc() for oc in option_classes)
        for opt in option_instances:
            normalized_thread = opt.normalize(normalized_thread)

        logger.debug(
            'Normalized thread options: %s', normalized_options
        )
        yield normalized_thread


def _normalize_mounts_config(project, thread):
    """Transform a list of mounts from the form ['source:destination']
    to a namedtuple of (source, target)

    :param list mounts: List of mounts

    :rtype: list
    :returns: List of namedtuples from the form (source, target)
    """
    mounts = _resolve_stdci_list_config(project, thread, 'mounts')
    all_mounts = []
    for mount in mounts:
        if not isinstance(mount, string_types):
            raise ConfigurationSyntaxError(
                'Mount configuration must be a dots separated string from the'
                ' form: source:destination or source only.'
                ' Syntax error at: {0}'.format(str(mount))
            )
        mount_src, _, mount_dst = mount.partition(':')
        if mount_dst == '':
            # We received a mount with source only
            mount_dst = mount_src
        all_mounts.append(MountConfig(src=mount_src, dst=mount_dst))
    return all_mounts


def _normalize_repos_config(project, thread):
    """Transform a list of repos from the form ['repo_name,repo_url'] into a
    list of namedtuples from the form: (repo_name, repo_url)

    :param list repos: List of repos. Every repo must be a string from the form
                       'repo name, repo url'.

    :rtype: list
    :returns: List of namedtuples from the form (repo_name, repo_url)
    """
    repos = _resolve_stdci_list_config(project, thread, 'repos')
    all_repos = []
    for repo in repos:
        if not isinstance(repo, string_types):
            raise ConfigurationSyntaxError(
                'Repo configuration must be a comma separated string from the'
                ' form: repo_name,repo_url or repo_url only.'
                ' Syntax error at: {0}'.format(str(repo))
            )
        repo_name, _, repo_url = repo.partition(',')
        if repo_url == '':
            # we received a repo with url only
            repo_url = repo_name
            repo_name = 'repo-{0}'.format(
                md5(repo_url.encode('utf-8')).hexdigest()
            )
        all_repos.append(RepoConfig(name=repo_name, url=repo_url))
    return all_repos


_RUNTIME_REQUIREMENTS_TRANSLATONS = {
    'isolationlevel': {
        'container': 'container',
        'containarized': 'container',
        'virtual': 'virtual',
        'vm': 'virtual',
        'virtualmachine': 'virtual',
        'physical': 'physical',
        'bm': 'physical',
        'baremetal': 'physical',
    },
    'hostdistro': {
        'same': 'same',
        'newer': 'newer',
        'better': 'newer',
    },
    'supportnestinglevel': {
        '0': 0,
        '1': 1,
        'vm': 1,
        'vms': 1,
        'virtualmachine': 1,
        'virtualmachines': 1,
        '2': 2,
        'nestedvm': 2,
        'nestedvms': 2,
        'nestedvirtualmachine': 2,
        'nestedvirtualmachines': 2,
        'vmonvm': 2,
        'vmsonvms': 2,
        'virtualmachineonvirtualmachine': 2,
        'virtualmachinesonvirtualmachines': 2,
    },
    'sriovnic': {
        1: True,
        '1': True,
        'true': True,
        True: True,
        0: False,
        '0': False,
        'false': False,
        False: False,
    }
}


def _normalize_runtime_requirements(thread):
    """Normalize the configuratiom in the runtime requirements option

    :param job_thread.JobThread thread: JobThread to resolve script for

    :returns: Normalized runtime requirements configuration
    :rtype: dict
    """
    rtr = thread.options['runtimerequirements']
    if not isinstance(rtr, Mapping):
        raise ConfigurationSyntaxError(
            'Runtime requirements must be a map. Not {0}'.format(type(rtr))
        )

    normalized = {}
    for config, translations in iteritems(_RUNTIME_REQUIREMENTS_TRANSLATONS):
        normalized[config] = translations.get(
            remove_case_and_signs(str(rtr.get(config, ''))),
            DEFAULT_RUNTIME_REQUIREMENTS[config]
        )
    if 'projectspecificnode' in rtr:
        normalized['projectspecificnode'] = rtr['projectspecificnode']
    return normalized


_TIMEOUT_UNIT_TRANSLATIONS = {
    'seconds': 's',
    'second': 's',
    'sec': 's',
    'minutes': 'm',
    'minute': 'm',
    'hours': 'h',
    'hour': 'h',
    'min': 'm',
    'h': 'h',
    'm': 'm',
    's': 's',
}


def _normalize_timeout(thread):
    """Convert the specified timeout time to seconds

    :param JobThread thread: JobThread to resolve timeout for

    :rtype: The timeout time in seconds
    """
    timeout_cfg = thread.options.get('timeout', 'unlimited')
    timeout_str = remove_case_and_signs(timeout_cfg)
    timeout_str = re.sub(r'(\s+)', '', timeout_str)

    if timeout_str in ('unlimited', 'never', 'no', ''):
        return 'unlimited'

    def _is_not_empty(str_in):
        if not str_in or str_in == ' ':
            return False
        return True

    units = iterkeys(_TIMEOUT_UNIT_TRANSLATIONS)
    units_rgx = r'([0-9]+)({0})$'.format('|'.join(units))
    try:
        timeout, unit = filter(  # Remove padding added by the split function
            _is_not_empty,
            re.split(units_rgx, timeout_str, maxsplit=2))
        logger.debug('Timeout config found: {0}{1}'.format(timeout, unit))
    except ValueError:
        raise ConfigurationSyntaxError(
            'Error reading timeout. Check your configuration')
    unit_translation = _TIMEOUT_UNIT_TRANSLATIONS[unit]
    if unit_translation == 's':
        return int(timeout)
    elif unit_translation == 'm':
        time = timedelta(minutes=int(timeout))
    else:
        time = timedelta(hours=int(timeout))
    try:
        # The [:-2] trims the suffix .0 as returned from total_seconds()
        return int(time.total_seconds())
    except AttributeError:
        # We're probably running on python <= 2.6.6
        def td_total_seconds(td):
            """Total seconds in the duration."""
            return (
                td.microseconds + 0.0 +
                (td.seconds + td.days * 24 * 3600) * 10 ** 6
            ) / 10 ** 6
        return int(td_total_seconds(time))


_STYLE_VALUE_TRNASLATIONS = {
    'default': 'default',
    'classic': 'classic',
    'stdci': 'stdci',
    'standardci': 'stdci',
    'plain': 'plain',
    'plaintext': 'plain',
    'blueocean': 'blueocean',
}


def _normalize_reporting_config(thread):
    """Normalize the configuration in the reporting option

    :param JobThread thread:      JobThread to resolve script for

    :returns: Normalized reporting configuration
    :rtype: dict
    """
    reporting = thread.options.get('reporting', {})
    if not isinstance(reporting, Mapping):
        if isinstance(reporting, string_types):
            reporting = {'style': reporting, }
        else:
            reporting = {}
    reporting['style'] = _STYLE_VALUE_TRNASLATIONS.get(
        remove_case_and_signs(reporting.get('style', '')),
        DEFAULT_REPORTING['style'],
    )
    return reporting


def _resolve_stdci_runif_conditions(project, thread, config):
    """Parse conditional execution config and return the final decision

    :param Mapping config:          Conditional execution configuration
    :param Iterable modified_files: Iterable of modified files as returned from
                                    get_modified_files()

    :rtype: bool
    :returns: True if conditions are satisfied, False otherwise.
    """
    try:
        return any(
            CONDITION_RESOLVERS[operator](project, thread, argument)
            for operator, argument in iteritems(config)
        )
    except KeyError:
        raise ConfigurationSyntaxError(
            'Operator not found. Available operators: %s. Your config: %s',
            CONDITION_RESOLVERS.keys(), config
        )


def _resolve_runif_not_condition(project, thread, conditions):
    """Resolve runif conditions recoursively and return the opposite decision.

    :param py.path.local project: Local path to project's root dir.
    :param JobThread thread:      JobThread which we check conditions for.
    :param Iterable conditions:   Iterable of conditions.

    :rtype: bool
    :returns: False if all conditions been satisfied. otherwise.
    """
    return not _resolve_stdci_runif_conditions(project, thread, conditions)


def _resolve_runif_all_condition(project, thread, conditions):
    """Resolve runif conditions recoursively. If at least one condition returns
    with False, return False.

    :param py.path.local project: Local path to project's root dir.
    :param JobThread thread:      JobThread which we check conditions for.
    :param Iterable conditions:   Iterable of conditions.

    :rtype: bool
    :returns: True if all conditions been satisfied. False otherwise.
    """
    return all(
        _resolve_stdci_runif_conditions(project, thread, condition)
        for condition in conditions
    )


def _resolve_runif_any_condition(project, thread, conditions):
    """Resolve runif conditions recoursively. If at least one condition returns
    with True, return True.

    :param py.path.local project: Local path to project's root dir.
    :param JobThread thread:      JobThread which we check conditions for.
    :param Iterable conditions:   Iterable of conditions.

    :rtype: bool
    :returns: True if at least one condition has been satisfied.
              False otherwise.
    """
    return any(
        _resolve_stdci_runif_conditions(project, thread, condition)
        for condition in conditions
    )


MODIFIED_FILES = {}


def _resolve_changed_files(project, thread, conditions):
    """Check if any modified file matches at least one condition.

    :param string_types project: Path to project's root dir
    :param list modified_files:  List of modified file names (str)
    :param list conditions:      List of conditions to match against modified
                                 files. Condition is Unix shell-style wildcard.

    :rtype: bool
    :returns: True if any file from the modified files matches at least one
              condition.
    """
    logger.debug('Resolving conditions: %s', conditions)
    if not isinstance(conditions, Iterable) \
            or isinstance(conditions, Mapping):
        raise ConfigurationSyntaxError(
            'At: {0} run-if conditions must be a string or a list of strings.'
            ' not {1}.'.format(conditions, type(conditions))
        )
    elif isinstance(conditions, string_types):
        conditions = [conditions]
    conditions = _verify_render_conditions(thread, conditions)
    if logger.level <= logging.DEBUG:
        # Since conditions can be a generator expression we need transform it
        # into a list before printing to debug log.
        conditions = list(conditions)
        logger.debug("Conditions: %s", conditions)
    # MODIFIED_FILES is global that stores per-project cache of modified files.
    global MODIFIED_FILES
    if project not in MODIFIED_FILES:
        # Call get_modified_files only if cache doesn't exists
        with py.path.local(project).as_cwd():
            logger.debug('No cached changes for %s. Generating cache', project)
            MODIFIED_FILES[project] = set(
                get_modified_files(resolve_links=True)
            )
    logger.debug('Modified files: %s', MODIFIED_FILES[project])
    res = any(
        fnmatch(name, pat)
        for (name, pat) in product(MODIFIED_FILES[project], conditions)
    )
    logger.debug('Result: %s', res)
    return res


def _verify_render_conditions(thread, conditions):
    for condition in conditions:
        if not isinstance(condition, string_types):
            raise ConfigurationSyntaxError(
                'At: {0}. Condition must be a string! Not {1}'
                .format(condition, type(condition))
            )
        yield render_template(thread, condition)


CONDITION_RESOLVERS = {
    'any': _resolve_runif_any_condition,
    'all': _resolve_runif_all_condition,
    'not': _resolve_runif_not_condition,
    'filechanged': _resolve_changed_files,
}


def _resolve_stdci_script(project, thread):
    """Resolve STDCI script.
    If script was specified inline, write it to tempfile
    If path to script was specified, _resolve the path

    :param py.path.local project: Path to project directory
    :param JobThread thread:      JobThread to resolve script for

    :rtype: py.path.local
    :returns: Path to resolved/created script file
    """
    script_config = thread.options['script']

    if isinstance(script_config, string_types):
        # Script was specified inline
        found_script = _write_to_tmpfile(script_config, '.sh')
        logger.debug('Script was written to: %s', str(found_script))
        return found_script
    if not isinstance(script_config, Mapping):
        # Script must be specified inline or source must be specified
        msg = "Script must be specified inline or source file must be provided"
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)

    # validate and normalize the structure of 'fromfile' section
    script_paths = script_config.get('fromfile', None)
    if script_paths is None:
        msg = "Wrong file source for script. Have you misspelled 'fromfile'?"
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if not isinstance(script_paths, (string_types, list)):
        # Path must be a single path or a list of paths
        msg = (
            'Path to script file must be string or list of strings! Not {0}'
            .format(type(script_paths))
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if isinstance(script_paths, string_types):
        script_paths = [script_paths]

    rendered_paths = (render_template(thread, path) for path in script_paths)
    path_prefix = _get_path_prefix(thread, 'script')
    found_script = _get_first_file(project, path_prefix, rendered_paths)
    if not (found_script or thread.options['ignore_if_missing_script']):
        # User specified path to script file and we couldn't resolve the path
        msg = (
            "Could not find script for thread:\n"
            "stage: {stage},\n"
            "substage: {substage},\n"
            "distro: {distro}\n"
            "arch: {arch}"
            .format(stage=thread.stage, substage=thread.substage,
                    distro=thread.distro, arch=thread.arch)
        )
        logger.error(msg)
        raise ConfigurationNotFound(msg)
    return found_script


def _resolve_stdci_yum_config(project, thread, option):
    """Resolve STDCI yum config style cofigurtions.
    If config was specified inline, write it to tempfile
    If path to config was specifeid, resovle the path

    :param py.path.local project: Path to project directory
    :param dict options:          Options configurations from JobThread object

    :rtype: py.path.local
    :returns: Path to _resolved/created script file
    """
    yum_config = thread.options[option]

    if isinstance(yum_config, string_types):
        # yum config was specified inline
        found_config = _write_to_tmpfile(yum_config, '.yumrepos')
        logger.debug('Config was written to: %s', str(found_config))
        return found_config
    if not isinstance(yum_config, Mapping):
        # Yum config must be specified inline or source must be specified
        msg = (
            "Yum config must be specified inline or source file must be"
            " provided"
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)

    # validate and normalize the structure of 'fromfile' section
    yum_config_paths = yum_config.get('fromfile', None)
    if yum_config_paths is None:
        msg = \
            "Wrong file source for yum config. Have you misspelled 'fromfile'?"
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if not isinstance(yum_config_paths, (string_types, list)):
        msg = (
            'Path to yum config must be string or list of strings! Not {0}'
            .format(type(yum_config_paths))
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if isinstance(yum_config_paths, string_types):
        yum_config_paths = [yum_config_paths]

    rendered_paths = (
        render_template(thread, path) for path in yum_config_paths
    )
    path_prefix = _get_path_prefix(thread, option)
    found_config = _get_first_file(project, path_prefix, rendered_paths)
    default_value = DefaultValue in yum_config
    if not (found_config or default_value):
        # User specified path to config file and we couldn't resolve the path
        msg = (
            "Could not find yum config for thread:\n"
            "stage: {stage},\n"
            "substage: {substage},\n"
            "distro: {distro}\n"
            "arch: {arch}"
            .format(stage=thread.stage, substage=thread.substage,
                    distro=thread.distro, arch=thread.arch)
        )
        logger.error(msg)
        raise ConfigurationNotFound(msg)
    return found_config


def _resolve_stdci_list_config(project, thread, option):
    """Resolve STDCI list config file.
    If list config was specified inline, generate config object.
    If paths to list config were specified, _resolve the first existing one and
    load it's data to config object.

    :param py.path.local project: Path to project directory
    :param dict options:          Options configurations from JobThread object
    :param str option:            Option to _resolve list config for
    :param str source:            File source type for the option
                                  Default is 'fromlistfile' but for some configs
                                  we use 'fromfile'

    :rtype: list
    :returns: List object representing the list config file
    """
    list_config = thread.options[option]

    if isinstance(list_config, string_types):
        # Single element specified inline
        return [list_config]
    elif isinstance(list_config, list):
        # List specified inline
        return list_config
    elif not isinstance(list_config, Mapping):
        msg = "List config must be specified inline or config must be provided"
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)

    # validate and normalize the structure of 'fromlistfile' section
    config_paths = list_config.get('fromlistfile', None)
    if config_paths is None:
        msg = (
            'You must specify file srouce "fromlistfile" for {0},'
            ' or specify it inline.'.format(option)
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if not isinstance(config_paths, (string_types, list)):
        msg = (
            'Path to config file must be string or list of strings! Not {0}'
            .format(type(config_paths))
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if isinstance(config_paths, string_types):
        config_paths = [config_paths]

    rendered_paths = (render_template(thread, path) for path in config_paths)
    path_prefix = _get_path_prefix(thread, option)
    try:
        with stdci_load(str(project/path_prefix), rendered_paths) as f:
            return f.read().splitlines()
    except ConfigurationNotFoundError:
        default_value = DefaultValue in list_config
        if not default_value:
            # User specified configuration file and we could not find it
            msg = "Could not find config file for {0}".format(option)
            logger.error(msg)
            raise ConfigurationNotFound(msg)
        # We couldn't find the config but it was default value.
        return []


def _resolve_stdci_yaml_config(project, thread, option):
    """Resolve STDCI yaml config file.
    If yaml config was specified inline, generate config object.
    If paths to yaml config were specified, _resolve the first existing one and
    load it's data to config object.

    :param py.path.local project: Path to project directory
    :param dict options:          Options configurations from JobThread object
    :param str option:            Option to _resolve list config for

    :rtype: dict
    :returns: Dict object representing the yaml config file
    """
    yaml_config = thread.options[option]

    if not isinstance(yaml_config, (Mapping, Iterable)):
        msg = '{0} must be a Map or an Iterable not {1}'.format(
            option, type(option)
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if (
        isinstance(yaml_config, Iterable)
        and not isinstance(yaml_config, Mapping)
    ):
        # inline specified
        return yaml_config

    # validate and normalize the structure of 'fromfile' section
    config_paths = yaml_config.get('fromfile', None)
    if config_paths is None:
        # Yaml config was specified inline
        logger.debug(
            'Config for %s was specified inline: %s', option, yaml_config
        )
        return yaml_config
    if not isinstance(config_paths, (string_types, list)):
        msg = (
            'Path to config file must be string or list of strings! Not {0}'
            .format(type(config_paths))
        )
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)
    if isinstance(config_paths, string_types):
        config_paths = [config_paths]

    rendered_paths = (
        render_template(thread, template) for template in config_paths
    )
    path_prefix = _get_path_prefix(thread, option)
    try:
        with stdci_load(str(project/path_prefix), rendered_paths) as cfg:
            config_data = safe_load(cfg)
            logger.debug('Loaded config data for %s: %s', option, config_data)
            return config_data
    except ConfigurationNotFoundError:
        default_value = DefaultValue in yaml_config
        if not default_value:
            # User specified configuration file and we could not find it
            msg = "Could not find config file for {0}".format(option)
            logger.error(msg)
            raise ConfigurationNotFound(msg)
        # We couldn't find the config but it was default value.
        return {}


def _write_to_tmpfile(string, suffix=''):
    """Write given string to a temporary file

    :param str string: String to be written to temporary file
    :param str suffix: Suffix to the name of the temporary file

    :rtype: str
    :returns: Path to generated temporary file
    """
    tmp_file = mkstemp(suffix, 'stdci-tmp.', dir='.', text=True)
    try:
        with open(tmp_file[1], 'w') as wf:
            wf.write(string)
    except IOError as e:
        logger.error("Could not open file for writing: %s\n%s", tmp_file[1], e)
        raise e
    logger.info("Script was written to: %s", tmp_file)
    return tmp_file[1]


def _get_path_prefix(thread, option):
    """Get path prefix with the following logic:
    If scriptsdirectory was specified, then use it as prefix
    If user explicitly specified the option, then set prefix to nothing ('')
    Otherwise, set prefix to automation/

    :param JobThread thread: JobThread instance that the option we extract
                             path prefix for belongs to.
    :param str option:       Name of the option to get path prefix for

    :rtype: str
    :returns: Path to option's configuration file(s) relative to project's root
    """
    scriptsdirectory = thread.options.get('scriptsdirectory', None)
    if scriptsdirectory:
        return scriptsdirectory
    if DefaultValue in thread.options[option]:
        return 'automation'
    return ''


def _get_first_file(project, search_dir, filenames):
    """Search the given directory for the first existing file from filenames

    :param py.path.local search_dir: The directory where we search the files in
    :param Iterable filenames:       Iterable of filenames to search

    :rtype: py.path.local
    :return: The first existing file from 'filenames' in 'search_dir'
              None is returned if file could not be found
    """
    project = py.path.local(project)
    if isinstance(filenames, string_types):
        filenames = [filenames]
    logger.debug('Searching files in: %s', str(search_dir))
    if logger.level <= logging.DEBUG:
        # Filenames might be a generator expression so in order to print it
        # we need to transform it into a list.
        filenames = list(filenames)
    found = next(
        (os.path.join(search_dir, f) for f in filenames
         if (project/search_dir/f).check(file=True)),
        None
    )
    if found is None:
        logger.debug('Could not find a valid file in: %s', filenames)
    else:
        logger.debug('Found a valid file: %s', found)
    return found
