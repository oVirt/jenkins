from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
    lookup: jjb_jobs_xml
    author: Barak Korren (bkorren@redhat.com)
    version_added: "2.7"
    short_description: Use JJB to generate job XML
    description:
        - This lookup returns the list of jobs that Jenking Job Builder can
          generate from a diven directory of YAML files
    options:
        _terms:
            description:
                - The 1st term is a colon-separated list of paths of
                  directories to read JJB YAML from
                - Following terms are the names or glob patterns of jobs to
                  generate XML for
                - If only the 1st term is specified - generate all jobs
            required: True
        chdir:
            description: Directory to change into for running JJB
            required: False
            default: None
        allow_empty_variables:
            description: Wither to allow empty variables in the JJB YAML
            required: False
            default: False
        recursive:
            description: Set to True to scan YAML directories recursively
            required: False
            default: False
        plugin_info:
            description:
                - Plugin information data as retrieved by the
                  jenkins_ssh_cli_facts module.
            required: False
            default: None
"""
import subprocess
import os
from shutil import rmtree
from contextlib import contextmanager
from tempfile import mkdtemp, NamedTemporaryFile
import yaml

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        if not terms:
            raise AnsibleError(
                "lookup_plugin.jjb_jobs_xml: YAML directory not specified"
            )
        yaml_path = terms[0]
        job_patterns = terms[1:]

        display.debug("Generate JJB jobs in: %s" % yaml_path)

        out_dir = mkdtemp()
        try:
            self.run_jjb(yaml_path, job_patterns, o=out_dir, **kwargs)
            jobs = self.read_jjb_xml(out_dir)
        finally:
            rmtree(out_dir)

        return jobs

    def build_jjb_cmd(
        self, yaml_path, job_patterns, o, pif, chdir=None,
        allow_empty_variables=False, recursive=False
    ):
        jjb_cmd = ['jenkins-jobs', '--conf', '/dev/null']
        if allow_empty_variables:
            jjb_cmd.append('--allow-empty-variables')
        jjb_cmd.extend(
            ['test', '-o', o, '--plugin-info', pif, '--config-xml']
        )
        if recursive:
            jjb_cmd.append('--recursive')
        jjb_cmd.append(yaml_path)
        jjb_cmd.extend(job_patterns)
        return jjb_cmd

    def run_jjb(
        self, yaml_path, job_patterns, o, chdir=None,
        allow_empty_variables=False, recursive=False, plugin_info=None
    ):
        with self.plugin_info_file(plugin_info) as pif:
            jjb_cmd = self.build_jjb_cmd(
                yaml_path, job_patterns, o, pif, chdir, allow_empty_variables,
                recursive
            )

            p = subprocess.Popen(
                jjb_cmd,
                cwd=chdir or self._loader.get_basedir(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                raise AnsibleError(
                    "lookup_plugin.jjb_job_list returned %d; stderr: %s" %
                    (p.returncode, stderr.decode("utf-8"))
                )

    @contextmanager
    def plugin_info_file(self, plugin_info):
        with NamedTemporaryFile('w+') as pif:
            yaml.dump(plugin_info or [], pif)
            yield pif.name

    def read_jjb_xml(self, out_dir):
        if not out_dir.endswith('/'):
            out_dir = out_dir + '/'
        return {
            dirpath[len(out_dir):]: self.read_job_xml(dirpath)
            for dirpath, dirnames, filenames in os.walk(out_dir)
            if 'config.xml' in filenames
        }

    def read_job_xml(self, job_path):
        fname = os.path.join(job_path, 'config.xml')
        with open(fname, 'r') as f:
            return f.read()
