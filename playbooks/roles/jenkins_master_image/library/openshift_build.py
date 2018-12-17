#!/usr/bin/python

# Copyright: (c) 2018, Barak Korren <bkorren@redhat.com>
# GNU General Public License v3.0+
# (see https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: openshift_build

short_description: Configure and runa  build process in OpenShift

version_added: "2.7"

description:
    - Create all the OpenShift objects needed to run a build with the specified
      parameters
    - Optionally trigger the build if configuration changes were made

requirements:
    - The `oc` binary needs to be installed and configured in `$PATH`. This
      code had been tested with version v3.11.0+0cbc58b, but older versions
      should also work as long as they support the `--binary` option to the
      build commands.

options:
    name:
        description:
            - The name of the BuildConfig object to create
        required: true
    strategy:
        description:
            - The build strategy to use
            - Supported values: docker, pipeline, source
            - Default value: source
        required: false
    image_stream:
        description:
            - The image stream for use as a builder image
        required: false
    binary:
        description:
            - Set to `True` to run a binary build
        required: false
    to:
        description:
            - Image stream tag to upload build results into
        required: false
    start_build:
        description:
            - When to trigger the build
            - Supported valuse: never, on-change
            - Default value: never
        required: false
    from_dir:
        description:
            - for binary builds, the directory to upload sources from
        required: false

author:
    - Barak Korren (@bkorren)
'''

EXAMPLES = '''
# Build image 'the_image:latest' using the 'my_builder:latest' builder image
# and local source files
openshift_build:
    name: MyBuild
    strategy: source
    image_stream: my_builder:latest
    binary: True
    from: /path/to/source
    to: the_image:latest
    start_build: on-change
'''
from sh import oc, ErrorReturnCode_1
import time

from ansible.module_utils.basic import AnsibleModule


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        name=dict(type='str', required=True),
        strategy=dict(
            type='str',
            required=False,
            choices=('docker', 'pipeline', 'source'),
            default='source',
        ),
        image_stream=dict(type='str', required=False),
        binary=dict(type='bool', required=False, default=False),
        to=dict(type='str', required=False),
        start_build=dict(
            type='str',
            required=False,
            choices=('never', 'on-change'),
            default=('never'),
        ),
        from_dir=dict(type='str', required=False),
    )
    # TODO: Add cross-option checks such as ensuring from_dir is specified if
    # binary is True and start_build != never

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )

    # if module.check_mode:
    #    # TODO: Support check mode by verifying the BuildConfig and
    #    ImageStreamTag objects

    try:
        # Try to create a unique buildconfig for this source
        result = dict(changed=False, built=False)
        try:
            oc(
                'new-build',
                name=module.params['name'],
                strategy=module.params['strategy'],
                image_stream=module.params['image_stream'],
                binary=module.params['binary'],
                to=module.params['to'],
            )
        except ErrorReturnCode_1 as e:
            module.log("Failed to create buildconfig: %s with: %s" % (
                module.params['name'], str(e)
            ))
            if oc.get.buildconfig(
                module.params['name'], o="jsonpath=.", ignore_not_found=True
            ):
                # If the buildconfig we need is already there, we assume someone
                # else is building it and just skip the build
                module.log('buildconfig: %s exists, skipping build' % (
                    module.params['name']
                ))
            else:
                raise
        else:
            result['changed'] = True
            if module.params['start_build'] == 'on-change':
                result['built'] = True
                module.log('Running build for: {}'.format(module.params['to']))
                build_log = oc(
                    'start-build',
                    module.params['name'],
                    from_dir=module.params['from_dir'],
                    follow=True, wait=True
                )
                module.log('Build done successfully')
                result['build_stdout'] = build_log.stdout
                result['build_stderr'] = build_log.stderr
        if module.params['start_build'] == 'on-change':
            # If user asks for a build, return only if we verified the build
            # exists, even if we did not run it
            module.log('Waiting for built image to appear in registry')
            wait_for(oc, 'imagestreamtag', module.params['to'])
            module.log('Found image with tag %s', module.params['to'])
        module.exit_json(**result)
    except Exception as e:
        module.fail_json(
            msg=getattr(e, 'message', str(e))
        )


def wait_for(oc, object_type, object_name):
    for attempt in range(0, 70):
        if oc.get(
            object_type, object_name,
            o="jsonpath=.", ignore_not_found=True
        ):
            break
        sleep_time = min((2 ** ((attempt / 10) + 1), 64))
        time.sleep(sleep_time)
    else:
        raise RuntimeError("Timed out waitimg for {}: '{}'".format(
            object_type, object_name
        ))


def main():
    run_module()

if __name__ == '__main__':
    main()
