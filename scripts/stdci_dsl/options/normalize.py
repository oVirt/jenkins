#!/bin/env python

from __future__ import absolute_import
import logging
from tempfile import mkstemp
from collections import Mapping
from copy import copy
from six import string_types
from jinja2.sandbox import SandboxedEnvironment
from yaml import safe_load
import py

from ..parser import stdci_load, ConfigurationNotFoundError
from ..options.defaults import DefaultValue


logger = logging.getLogger(__name__)


class ConfigurationSyntaxError(Exception):
    pass


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

    :param py.path.local project: Path to project directory
    :param Iterable vectors:      Iterable of JobThread objects

    :rtype: Iterator
    :return: Returns iterator over a vector objects for the requested stage
    """
    project = py.path.local(project)
    for thread in threads:
        # We need to render scripts_directory here because it takes effect
        # when resolving paths for option(s) configuration file(s).
        thread_options_with_scdir = _render_template(
            thread, thread.options.get('scripts_directory', '')
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
        mounts = _resolve_stdci_list_config(project, thread, 'mounts')
        repos = _resolve_stdci_list_config(project, thread, 'repos')
        packages = _resolve_stdci_list_config(project, thread, 'packages')
        normalized_options = copy(thread_with_scdir.options)
        normalized_options['script'] = script
        normalized_options['environment'] = environment
        normalized_options['yumrepos'] = yumrepos
        normalized_options['mounts'] = mounts
        normalized_options['repos'] = repos
        normalized_options['packages'] = packages
        normalized_thread = thread_with_scdir.with_modified(
            options=normalized_options
        )
        logger.debug(
            'Normalized thread_with_scdir options: %s', normalized_options
        )
        yield normalized_thread


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

    rendered_paths = (_render_template(thread, path) for path in script_paths)
    path_prefix = _get_path_prefix(thread, 'script')
    found_script = _get_first_file(project/path_prefix, rendered_paths)
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
        msg = \
            "Yum config must be specified inline or source file must be provided"
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)

    # validate and normalize the structure of 'fromfile' section
    yum_config_paths = yum_config.get('fromfile', None)
    if yum_config_paths is None:
        msg = "Wrong file source for yum config. Have you misspelled 'fromfile'?"
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
        _render_template(thread, path) for path in yum_config_paths
    )
    path_prefix = _get_path_prefix(thread, option)
    found_config = _get_first_file(project/path_prefix, rendered_paths)
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

    rendered_paths = (_render_template(thread, path) for path in config_paths)
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

    if not isinstance(yaml_config, Mapping):
        msg = '{0} must be a map not {1}'.format(option, type(option))
        logger.error(msg)
        raise ConfigurationSyntaxError(msg)

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
        _render_template(thread, template) for template in config_paths
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


def _render_template(thread, templates):
    """Render given iterable of templates in a sandboxed environment.

    :param JobThread thread:   JobThread instance the templates refer to
    :param template:           Template we need to render.
                               It can be a single template or an Iterable of
                               templates

    :returns: Rendered template(s)
    """
    sandbox = SandboxedEnvironment()
    rendered = (
        sandbox.from_string(templates).render(
            stage=thread.stage,
            substage=thread.substage,
            distro=thread.distro,
            arch=thread.arch
        )
    )
    if not isinstance(rendered, str):
        rendered = rendered.encode('ascii', 'ignore')
    return rendered


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
    If scripts_directory was specified, then use it as prefix
    If user explicitly specified the option, then set prefix to nothing ('')
    Otherwise, set prefix to automation/

    :param JobThread thread: JobThread instance that the option we extract
                             path prefix for belongs to.
    :param str option:       Name of the option to get path prefix for

    :rtype: str
    :returns: Path to option's configuration file(s) relative to project's root
    """
    scripts_directory = thread.options.get('scripts_directory', None)
    if scripts_directory:
        return scripts_directory
    if DefaultValue in thread.options[option]:
        return 'automation'
    return ''


def _get_first_file(search_dir, filenames):
    """Search the given directory for the first existing file from filenames

    :param py.path.local search_dir: The directory where we search the files in
    :param Iterable filenames:       Iterable of filenames to search

    :rtype: py.path.local
    :return: The first existing file from 'filenames' in 'search_dir'
              None is returned if file could not be found
    """
    search_dir = py.path.local(search_dir)
    if isinstance(filenames, string_types):
        filenames = [filenames]
    logger.debug('Searching files in: %s', str(search_dir))
    found = next(
        (search_dir/f for f in filenames if (search_dir/f).check(file=True)),
        None
    )
    if found is None:
        logger.debug('Could not find a valid file in: %s', filenames)
    else:
        logger.debug('Found a valid file: %s', found)
    return found
