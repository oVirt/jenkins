#!/bin/env python
"""options/base.py - Base classes for DSL options and some utility functions
"""
from six import iteritems

from jinja2.sandbox import SandboxedEnvironment

from scripts.struct_normalizer import (
    normalize_value, scalar, DataNormalizationError, normalize_option
)


class ConfigurationSyntaxError(Exception):
    pass


def render_template(thread, template):
    """Render given iterable of templates in a sandboxed environment.

    :param JobThread thread:   JobThread instance the templates refer to
    :param template:           Template we need to render.

    :returns: Rendered template(s)
    """
    sandbox = SandboxedEnvironment()
    rendered = (
        sandbox.from_string(template).render(
            stage=thread.stage,
            substage=thread.substage,
            distro=thread.distro,
            arch=thread.arch
        )
    )
    if not isinstance(rendered, str):
        # Throw away unicode on Py2 since making it work properly is more
        # trouble then its worth
        rendered = rendered.encode('ascii', 'ignore')
    return rendered


def template_string(else_='Invalid value for template string'):
    """A normalization function generator for strings that are Jinja templates

    :param str else_: Optional error message to raise if value is not a string

    :rtype: function
    :returns: A function that accepts a JobThread and a value and converts the
              value to a string, or raises the given error message in a
              DataNormalizationError exception if that cannot be done. The
              string is then used as a Jinja2 template to generate the returned
              value.
    """
    def normalizer(thread, value):
        tmpl = normalize_value(thread, value, to=scalar(type=str, else_=else_))
        if tmpl:
            return render_template(thread, tmpl)
        else:
            raise DataNormalizationError(else_)
    return normalizer


def normalize_thread_options(thread, **kwargs):
    """A helper function for normalizing thread options

    :param JobThread thread: A thread object to normalize options for

    :rtype: JobThread
    :returns: A thread object where for each given kwarg, the option named by
              the key had been normalized with the normalizer function given
              by the value
    """
    for key, nrmfun in iteritems(kwargs):
        update_dict = normalize_option(thread, thread.options, key, to=nrmfun)
        if not update_dict:
            continue
        new_options = thread.options.copy()
        new_options.update(update_dict)
        thread = thread.with_modified(options=new_options)
    return thread
