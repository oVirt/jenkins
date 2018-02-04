#!/bin/env python
"""values.py - Default values for options"""


DefaultValue = object()


def _default_templates_with_substage(ftype, from_=None):
    if from_ in ('fromfile', 'fromlistfile'):
        return {
            from_: [
                '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' %
                ftype,
                '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
                '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
                '{{ stage }}.{{ substage }}.%s' % ftype,
            ],
            DefaultValue: True,
        }
    return {
        'fromlistfile': [
            '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s' % ftype,
        ],
        'fromfile': [
            '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s' % ftype,
        ],
        DefaultValue: True,
    }


def _default_templates_without_substage(ftype, from_=None):
    if from_ in ('fromfile', 'fromlistfile'):
        return {
            from_: [
                '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' %
                ftype,
                '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
                '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
                '{{ stage }}.{{ substage }}.%s' % ftype,
                '{{ stage }}.%s.{{ distro }}.{{ arch }}' % ftype,
                '{{ stage }}.%s.{{ distro }}' % ftype,
                '{{ stage }}.%s.{{ arch }}' % ftype,
                '{{ stage }}.%s' % ftype,
            ],
            DefaultValue: True,
        }
    return {
        'fromlistfile': [
            '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s' % ftype,
            '{{ stage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.%s' % ftype,
        ],
        'fromfile': [
            '{{ stage }}.{{ substage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.{{ substage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.{{ substage }}.%s' % ftype,
            '{{ stage }}.%s.{{ distro }}.{{ arch }}' % ftype,
            '{{ stage }}.%s.{{ distro }}' % ftype,
            '{{ stage }}.%s.{{ arch }}' % ftype,
            '{{ stage }}.%s' % ftype,
        ],
        DefaultValue: True,
    }


DEFAULT_VALUES = {
    'user_specified_substage':
    {
        'release_branches': {},
        'upstream_sources': {},
        'runtime_requirements':
        {
            'support_nesting_level': 0,
            'host_distro': 'el7',
            'host_arch': 'x86_64'
        },
        'environment': \
            _default_templates_with_substage('environment.yaml', 'fromfile'),
        'packages': \
            _default_templates_with_substage('packages', 'fromlistfile'),
        'yumrepos': _default_templates_with_substage('yumrepos', 'fromfile'),
        'repos': _default_templates_with_substage('repos', 'fromlistfile'),
        'mounts': _default_templates_with_substage('mounts', 'fromlistfile'),
        'script': _default_templates_with_substage('sh', 'fromfile')
    },
    'default_substage':
    {
        'release_branches': {},
        'upstream_sources': {},
        'runtime_requirements':
        {
            'support_nesting_level': 0,
            'host_distro': 'el7',
            'host_arch': 'x86_64'
        },
        'environment': \
            _default_templates_without_substage('environment.yaml', 'fromfile'),
        'packages': \
            _default_templates_without_substage('packages', 'fromlistfile'),
        'yumrepos': _default_templates_without_substage('yumrepos', 'fromfile'),
        'repos': _default_templates_without_substage('repos', 'fromlistfile'),
        'mounts': _default_templates_without_substage('mounts', 'fromlistfile'),
        'script': _default_templates_without_substage('sh', 'fromfile')
    }
}
