#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Barak Korren <bkorren@redhat.com>
# GNU General Public License v3.0+
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: git_commit_files

short_description: Commit files int Git

version_added: "2.8"

author:
    - "Barak Korren <bkorren@redhat.com>"

description:
    - Commit a given set of files into Git
    - Can create a branch to commit into

options:
    files:
        description:
            - The list of files to commit
            - An alternative to specifying files directly in free form
            - This cannot be given of the free form is used and vice-versa
        required: yes
    repo_dir:
        description:
            - The directory where the Git repo resides
            - If unspecified, the directory where ansible is running the module
              from would be used
        required: no
    branch:
        description:
            - A branch that will be created and the commit added into
            - If the branch exists it will be destroyed
            - If unspecified the change will be committed to current branch
        required: no
        default: unspecified
    commit_message:
        description:
            - The commit message to set when committing changes
            - If not given a default message would be generated
        required: no
    add_change_id:
        description:
            - Set wither to add a 'Change-Id' header to the commit message
            - The change id value will consist of a checksum of the modified
              files
        required: no
        default: false
    change_id_headers:
        description:
            - The list of headers to place change checksum into
            - Setting 'add_change_id' effectively sets this to ['Change-Id']
        required: no
        default: []
    add_headers:
        description:
            - A dictionary of headers to add to the commit message
        required: no
        default: {}

requirements:
  - I(git) installed on the target host
  - The target work directory should already be a Git repo
'''

EXAMPLES = '''
- name: Commit a set of files
  git_commit_files:
    files:
      - file1.txt
      - file2.txt

- name: Commit with a custom message
  git_commit_files
    files: files1.txt
    commit_message: "file1.txt was updated"

- name: Commit with Change-Id and custom headers
  git_commit_files:
    files:
      - file1.txt
      - file2.txt
    add_change_id: true
    add_headers:
      Automerge: yes
'''

RETURN = '''
changed_files:
    description:
        - The list of files that were actually changed and committed
    returned: success
    type: dict
'''
import os
from six.moves import filter
from six import iteritems
from hashlib import sha1

from ansible.module_utils.basic import AnsibleModule, heuristic_log_sanitize


class GitProcessError(RuntimeError):
    def __init__(self, cmd, rc, stdout, stderr):
        self.cmd = cmd
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return 'Git command {} failed with {} exit code'.format(
            self.cmd, self.rc
        )

    def fail_json(self, module):
        msg = heuristic_log_sanitize(
            self.stderr.rstrip(), module.no_log_values
        )
        module.fail_json(
            git_cmd=module._clean_args(self.cmd),
            rc=self.rc,
            stdout=self.stdout,
            stderr=self.stderr,
            msg=msg
        )


class GitCommitFilesModule(AnsibleModule):
    def __init__(self, *args, **kwargs):
        kwargs['argument_spec'] = self.argspec
        kwargs['supports_check_mode'] = False
        AnsibleModule.__init__(self, *args, **kwargs)

    def execute_module(self):
        self._execute_module_w_args(**self.params)

    def _execute_module_w_args(
        self, files, repo_dir, branch, commit_message,
        add_change_id, change_id_headers, add_headers,
    ):
        if not files:
            self.fail_json(rc=256, msg='no files given')

        if repo_dir and repo_dir.strip():
            os.chdir(repo_dir.strip())

        change_id_headers = set(change_id_headers)
        if add_change_id:
            change_id_headers.add('Change-Id')

        try:
            commit_data = self._commit_files(
                files, branch, commit_message, change_id_headers, add_headers
            )
            self.exit_json(
                changed=bool(commit_data['changed_files']),
                **commit_data
            )
        except IOError as e:
            if e.errno == 2:
                self.fail_json(
                    msg=str(e),
                    file=e.filename,
                    cwd=os.getcwd(),
                )
            else:
                raise
        except GitProcessError as e:
            e.fail_json(self)

    @property
    def argspec(self):
        args = dict(
            files=dict(type='list', required=True),
            repo_dir=dict(type='path'),
            branch=dict(type='str'),
            commit_message=dict(type="str"),
            add_change_id=dict(type="bool", default=False),
            change_id_headers=dict(type="list", default=[]),
            add_headers=dict(type="dict", default={}),
        )
        return args

    def _commit_files(
        self, files, branch=None, commit_message=None,
        change_id_headers=None, extra_headers=None,
    ):
        # Clear git index before adding the requested files
        self._git('reset', 'HEAD')
        self._git('add', *filter(os.path.exists, files))
        changed_files = self._staged_files()
        if changed_files:
            if branch:
                self._git('checkout', '-B', branch)
            self._git('commit', '-m', self._commit_message(
                changed_files, commit_message, change_id_headers, extra_headers
            ))
        return {'changed_files': changed_files}

    def _staged_files(self):
        return self._git('diff', '--staged', '--name-only').splitlines()

    def _commit_message(
        self, changed_files, commit_message,
        change_id_headers=None, extra_headers=None
    ):
        if commit_message:
            commit_message = str(commit_message).strip()
        if not commit_message:
            commit_message = self._commit_title(changed_files)
            if len(changed_files) > 1:
                commit_message += '\n\nChanged files:\n'
                commit_message += '\n'.join(
                    '- ' + fil for fil in changed_files
                )
        headers = self._commit_headers(
            changed_files, change_id_headers, extra_headers
        )
        if headers:
            commit_message += '\n'
            commit_message += headers
        return commit_message

    def _commit_title(self, changed_files, max_title=60):
        if len(changed_files) != 1:
            return 'Changed {} files'.format(len(changed_files))
        title = 'Changed: {}'.format(changed_files[0])
        if len(title) <= max_title:
            return title
        title = 'Changed: {}'.format(os.path.basename(changed_files[0]))
        if len(title) <= max_title:
            return title
        return 'Changed one file'

    def _commit_headers(self, changed_files, change_id_headers, extra_headers):
        headers = ''
        if extra_headers:
            for hdr, val in sorted(iteritems(extra_headers)):
                headers += '\n{}: {}'.format(hdr, val)
        if changed_files and change_id_headers:
            change_id_set = False
            change_id = 'I' + self._files_checksum(changed_files)
            for hdr in sorted(set(change_id_headers)):
                if hdr == 'Change-Id':
                    change_id_set = True
                    continue
                headers += '\n{}: {}'.format(hdr, change_id)
            # Ensure that 'Change-Id' is the last header we set because Gerrit
            # needs it to be on the very last line of the commit message
            if change_id_set:
                headers += '\nChange-Id: {}'.format(change_id)
        return headers

    def _files_checksum(self, changed_files):
        digest = sha1()
        for fil in sorted(set(changed_files)):
            digest.update(fil.encode('utf-8'))
            with open(fil, 'rb') as f:
                digest.update(f.read())
        return digest.hexdigest()

    def _git(self, *args, **kwargs):
        rc_args = ['git']
        rc_args.extend(args)
        rc, stdout, stderr = self.run_command(rc_args, **kwargs)
        if rc != 0:
            raise GitProcessError(rc_args, rc, stdout, stderr)
        return stdout


def main():
    GitCommitFilesModule().execute_module()


if __name__ == '__main__':
    main()
