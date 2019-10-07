#!/bin/env python
"""threads.py - Set of data formatters for stdci threads"""

from __future__ import division
import logging
import os
from yaml import safe_dump


_formatters = {}
logger = logging.getLogger(__name__)


CONTINUATION_STRING = '...'
COLUMN_SEPARATOR = '  '


class FormatterNotFoundError(Exception):
    pass


class TrimFunctionValueError(Exception):
    pass


def trim_zero(string, max_len=0, continuation_string=None):
    """Gimmick trim string function
    Returns unmodified string received as parameter. max_len parameter and
    continuation_string have no effect. They were added for having the same
    interface as rest trim functions.

    :param str string:              string
    :param int max_len:             does not have effect
    :param str continuation_string: does not have effect

    :rtype:   str
    :returns: string
    """
    return string


def trim_str(string, max_len=0, continuation_string=CONTINUATION_STRING):
    """Trim string
    If max_len is not provided, return the first character of the string and
    continuation string or the first character if the string is of length one.
    e.g string=performance_suite_master -> p...

    If max_len is provided:
    e.g string=performance_suite_master max_len=15 -> performance_...
    e.g string=performance_suite_master max_len=2 -> pe

    :param str string:              string
    :param int max_len:             max length to truncate to
    :param str continuation_string: suffix for truncated pathnames

    :rtype:   str
    :returns: truncated string
    """
    if max_len < 0:
        raise TrimFunctionValueError("String max_len can't be negative")
    if not max_len:
        return string[0] + continuation_string if len(string) > 1 else string
    trimmed_str = (
        string[:max_len - len(continuation_string)] + continuation_string
    )
    return (
        trimmed_str if len(string) > max_len else string
    )[:max_len]


def trim_str_end(string, max_len=0, continuation_string=CONTINUATION_STRING):
    """Trim string
    If max_len is not provided, return continuation string followed by the
    last characted of the string. If len(str) == 1, return str.
    e.g string=performance_suite_master -> '...r'

    If max_len is provided:
    e.g string=performance_suite_master max_len=15 -> '...suite_master'
    If max_len <= len(continuation_string), return str[:max_len]
    e.g string=performance_suite_master max_len=2 -> 'er'

    :param str string:              string
    :param int max_len:             max length to truncate to
    :param str continuation_string: suffix for truncated pathnames

    :rtype:   str
    :returns: truncated string
    """
    if max_len < 0:
        raise TrimFunctionValueError("String max_len can't be negative")
    if not max_len:
        return continuation_string + string[-1] if len(string) > 1 else string
    trimmed_str = (continuation_string +
        string[-max_len + len(continuation_string):]
    )
    return (
        trimmed_str if len(string) > max_len else string
    )[-max_len:]


def trim_path(pathname, max_len=0, continuation_string=CONTINUATION_STRING):
    """Trim path
    If max_len is not provided, return continuation string followed by the last
    character of the pathname basedir followed by a slash followed by the first
    character of the pathname basename followed by continuation string,
    e.g pathname=automation/check-patch.sh -> ...n/c...

    If max_len is provided, return the string if len(pathname) is less or equal
    to max_len. Otherwise return truncated pathname. How pathname is truncated:
    pathname=automation/check-patch.sh and max_len=10 -> check-patc...
    pathname=automation/check-patch.sh and max_len=15 -> check-patch.sh
    pathname=automation/check-patch.sh and max_len=20 -> ...on/check-patch.sh

    :param str pathname:            pathname
    :param int max_len:             max length to truncate to
    :param str continuation_string: suffix for truncated pathnames

    :rtype:   str
    :returns: truncated path
    """
    if max_len < 0:
        raise TrimFunctionValueError("Pathname max_len can't be negative")
    dirpath, filename = os.path.split(pathname)
    if not max_len:
        if not dirpath:
            return trim_str(filename)
        return trim_str_end(dirpath) + '/' + trim_str(filename)
    if not dirpath or \
        len(filename) >= max_len - len(continuation_string + '/') - 1:
        return trim_str(filename, max_len)
    max_dir_len = max_len - len('/' + filename)
    return trim_str_end(dirpath, max_dir_len) + '/' + filename


def format_table(table, trim_funcs, headers, term_width,
        column_separation=COLUMN_SEPARATOR):
    """Create table presentation of data

    table: list of list, each list is a row of data
    trim_funcs: list of functions to trim the fields in a row
    headers: list of strings, table headers
    term_width: int terminal width
    column_separation: string to separate table columns

    :rtype:   str
    :returns: table presentation of data
    """
    if not table:
        return ''
    if not len(table[0]) == len(trim_funcs) == len(headers):
        raise ValueError('table, trim_funcs and headers parameters must be'
            ' of the same length')
    column_separation_all = (len(table[0]) - 1) * len(column_separation)
    sum_values = [0] * len(table[0])
    max_min_values = [0] * len(table[0])
    max_values = [0] * len(table[0])
    # find greatest value per column, the greatest of the minimum values per
    # column and the sum of all values per column (needed to calculate average)
    for row in table:
        row_fields_len = [len(field) for field in row]
        max_values = [max(val) for val in zip(max_values, row_fields_len)]
        sum_values = (sum(val) for val in zip(sum_values, row_fields_len))
        max_min_values_row = (len(func(val))
            for func, val in zip(trim_funcs, row))
        max_min_values = [max(val)
            for val in zip(max_min_values, max_min_values_row)]
    # calculate smallest width we can create table for
    min_table_width = sum(max_min_values) + column_separation_all + 1 #\n
    # width with all fields at original length (not trimmed)
    max_table_width = sum(max_values) + column_separation_all + 1
    if min_table_width > term_width:
        raise ValueError('Not enough terminal width to draw table. Use -v.')
    if max_table_width <= term_width:
        trim_values = max_values
    else:
        extra_space = term_width - min_table_width
        values_average = (val//len(table) for val in sum_values)
        # if the average value per column is bigger than greatest minimum value
        # we extend the space for that column using the extra space
        extra_values_fields = [
            av_val if av_val > mm_val else 0
            for mm_val, av_val in zip(max_min_values, values_average)
        ]
        sum_extra_values = sum(extra_values_fields)
        # calculate the portions of extra space per column
        extra_values = [
            int(round(extra_val*extra_space/sum_extra_values))
            for extra_val in extra_values_fields]
        # extend the columns width
        trim_values = [sum(vals) for vals in zip(max_min_values, extra_values)]

    table_header = column_separation.join(
        (header[:trim_val] + ' ' * (trim_val - len(header[:trim_val]))
        for header, trim_val in zip(headers, trim_values))) + '\n'

    table_header_separator = '-'*(len(table_header) - 1) + '\n'

    # zip(trim_funcs, row, trim_values) generates tuples of function and two
    # parameters provided to that function to create custom field.
    # Here table_data is generator of generators where inner generator
    # generates the fileds per row and the outper generator generates the rows.
    table_data = (
        (ffv[0](ffv[1], ffv[2]).ljust(ffv[2]) + column_separation
        for ffv in zip(trim_funcs, row, trim_values)
        )
        for row in table
    )
    table_formatted = '\n'.join(
        ''.join(row)[:-len(column_separation)] for row in table_data)

    return table_header + table_header_separator + table_formatted


def get_formatter(formatter_name):
    """Given formatter name, return formatter function

    :param str formatter_name: Name of the required formatter

    :rtype:   function
    :returns: Formatter function
    """
    formatter_ = _formatters.get(formatter_name, None)
    if formatter_ is None:
        raise FormatterNotFoundError(
            'Could not find formatter_: {0}'.format(formatter_name)
        )
    return formatter_


def formatter(name):
    """Decorator function for formatter registration"""
    def wrapper(function):
        _formatters[name] = function
        logger.debug('Registered threads data formatter: %s', name)
        return function
    return wrapper


@formatter('pipeline_dict')
def _pipeline_dict_formatter(threads, global_options, template=None):
    """Format vectors data into pipeline dict

    :param Iterable vectors:     Iterable of JobThread objects
    :param dict global_options : Global options config
    :param str template:     Format template
                             (currently unused in this formatter)

    :rtype: str
    :returns: yaml config with vectors data from $vectors
    """
    data = {}
    data['global_config'] = {
        'upstream_sources': global_options['upstreamsources'],
        'release_branches': global_options['releasebranches']
    }
    data['jobs'] = [
        {
            'stage': thread.stage,
            'substage': thread.substage,
            'distro': thread.distro,
            'arch': thread.arch,
            'script': str(thread.options['script']),
            'runtime_reqs': thread.options['runtimerequirements'],
            'release_branches': thread.options['releasebranches'],
            'reporting': thread.options['reporting'],
            'timeout': thread.options['timeout'],
            'containers': thread.options['containers'],
        } for thread in threads
    ]
    return safe_dump(data, default_flow_style=False)


@formatter('conf_checker_terse')
def _conf_checker_terse_formatter(threads, global_options, template=None):
    """Format vectors data into job tabulated data

    :param Iterable vectors:     Iterable of JobThread objects
    :param dict global_options:  Global options config
    :param str template:         Number representing terminal width

    :rtype:   str
    :returns: tabulated config with vectors data from $vectors
    """

    terminal_width = int(template)

    all_jobs = []
    stage = ''
    for thread in threads:
        if not stage:
            stage = thread.stage
        job = [thread.substage, thread.distro, thread.arch,
            str(thread.options['script'])]
        if 'ignore_runif' in thread.options:
            job.append('* ')    # extra space for 'If' header
        else:
            job.append('  ')
        all_jobs.append(job)

    if not all_jobs:
        return ''

    trim_functions = [trim_str, trim_zero, trim_zero, trim_path, trim_zero]
    table_headers = ['Substage', 'Distro', 'Arch', 'Script', 'If']
    return 'Stage: {0}\n{1}'.format(stage, format_table(
        all_jobs, trim_functions, table_headers, terminal_width))


@formatter('conf_checker_verbose')
def _conf_checker_verbose_formatter(threads, global_options, template=None):
    """Format vectors data into list of jobs

    :param Iterable vectors:     Iterable of JobThread objects
    :param dict global_options : Global options config
    :param str template:         Number representing terminal width

    :rtype:   str
    :returns: list jobs with vectors data from $vectors
    """
    header_sep = '-'
    terminal_width = int(template)
    job_separator = header_sep * terminal_width + '\n'

    formatted_jobs = ''
    for thread in threads:
        formatted_jobs += ('stage: {0}\nsubstage: {1}\ndistro: {2}\n'
            'arch: {3}\nscript: {4}\n'.format(
                 thread.stage, thread.substage, thread.distro,
                 thread.arch, str(thread.options['script']))
        )
        if 'ignore_runif' in thread.options:
            formatted_jobs += '{0}\n'.format(' *Conditional')
        formatted_jobs += job_separator

    if formatted_jobs:
        formatted_jobs = job_separator + formatted_jobs

    return formatted_jobs
