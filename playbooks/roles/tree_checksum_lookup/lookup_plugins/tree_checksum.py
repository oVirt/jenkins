# python 3 headers, required if submitting to Ansible
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
    lookup: tree_checksun
    author: Barak Korren (bkorren@redhat.com)
    version_added: "2.7"
    short_description: Calculate checksum of a directory tree
    description:
        - This lookup returns the cumulative checksum of all files in a given
          directory tree
    options:
        _terms:
            description: path of files to read
            required: True
        digest_algo:
            description: The digest algorithm to use for calculating the
                         checksum
            required: False
            default: sha256
"""
import hashlib
import py
from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        ret = []
        for term in terms:
            display.debug("Tree checksum lookup term: %s" % term)

            try:
                digest_algo_name = variables.get('digest_algo', 'sha256')
                digest_algo = getattr(hashlib, digest_algo_name)
            except AttributeError:
                raise AnsibleError(
                    "Invalid digest algorithm: %s" % digest_algo_name
                )

            try:
                checksum = calculate_tree_checksum(term, digest_algo)
            except py.error.Error as e:
                raise AnsibleError(str(e))

            ret.append(checksum)

        return ret


def calculate_tree_checksum(tree_path, digest_algo=hashlib.sha256):
    """Calculate the cumulative checksum for a directory tree
    """
    digest = digest_algo()
    pth = py.path.local(tree_path)
    for sub_pth in pth.visit(sort=True):
        if not sub_pth.isfile():
            continue
        digest.update(pth.bestrelpath(sub_pth).encode())
        digest.update(sub_pth.read_binary())
    return digest.hexdigest()
