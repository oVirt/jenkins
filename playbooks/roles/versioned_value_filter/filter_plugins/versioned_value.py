#!/usr/bin/python

from ansible import errors
from ansible.plugins.test.core import version_compare

DOCUMENTATION = '''
---
filter: versioned_value

short_description: Returns the value per a version key

version_added: "2.7"

description:
    - Input: Dict variable, version keys.
    - Valid input: non empty dict, version key should be equal or higher
      any other key in the dict, in the format of vx.y.z. For example: v.3.6.0
    - Ouput: The value of the dict key. If key doesn't exist return the
             value of the nearest lower version value

suggested usage is:

  vars:
    dict_var:
      version1: 'value1'
      version2: 'value2'

  tasks:
  - name: value will result in - value1
    set_fact:
        value: "{{ dict_var | versioned_value('version1') }}"
  - name: value will result in - value2
    set_fact:
        value: "{{ dict_var | versioned_value('version2') }}"
  - name: name: value will result in - value2 if version3>version2
    set_fact:
        value: "{{ dict_var | versioned_value('version3') }}"

author:
    - Liora Milbaum (@lioramilbaum)
'''


def versioned_value(a, version):
    if not isinstance(a, dict) or not a:
        raise errors.AnsibleFilterError(
            "versioned_value expects to filter on not empty dict")
    if version in a:
        return a[version]
    temp = 'v0.0.0'
    for key in a:
        if (version_compare(key, version, 'lt', False) and
                version_compare(key, temp, 'gt', False)):
            temp = key
    if temp == 'v0.0.0':
        raise errors.AnsibleFilterError("version should be in dict or greater")
    else:
        return a[temp]


class FilterModule(object):
    def filters(self):
        return {
            'versioned_value': versioned_value
        }
