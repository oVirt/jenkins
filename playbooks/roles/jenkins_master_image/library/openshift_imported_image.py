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
module: openshift_imported_image

short_description: Import images from 3rd party registries into OpenShift

version_added: "2.7"

description:
    - Imports a container image from an external registry into OpenShift
    - The container image is imported as an ImageStreamTag

options:
    source_image:
        description:
            - The external container image to import
        required: true
    dest_imagestream:
        description:
            - The ImageStreamTag that is going to be created
        required: true

author:
    - Barak Korren (@bkorren)
'''

EXAMPLES = '''
# Import the 'openshift/jenkins-2-centos7:v3.11' image from DockerHub into the
# jenkins-2-centos7:latest ImageStreamTag
openshift_imported_image:
    source_image: 'openshift/jenkins-2-centos7:v3.11'
    dest_imagestream: 'jenkins-2-centos7:latest'
'''

RETURN = '''
container_sha:
    description: The checksum of the image that was imported
    type: str
'''
from sh import oc
import time

from ansible.module_utils.basic import AnsibleModule


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        source_image=dict(type='str', required=True),
        dest_imagestream=dict(type='str', required=False, default=False)
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )

    # if module.check_mode:
    #    # TODO: Support check mode by using skopio to check what is the SHA
    #    # of the image in the source repo and compart with the one in
    #    # OpenShift
    #    return result

    try:
        current_container_sha = \
            get_current_image_sha(oc, module.params['dest_imagestream'])
        do_image_import(
            oc,
            module.params['source_image'],
            module.params['dest_imagestream'],
        )
        new_container_sha = \
            get_current_image_sha(oc, module.params['dest_imagestream'])
        module.exit_json(
            changed=(current_container_sha != new_container_sha),
            container_sha=new_container_sha,
        )
    except Exception as e:
        module.fail_json(
            msg=getattr(e, 'message', str(e))
        )


def get_current_image_sha(oc, dest_imagestream):
    return oc.get.imagestreamtag(
        dest_imagestream, o='jsonpath={.image.dockerImageMetadata.Container}',
        ignore_not_found=True
    ).strip()


def do_image_import(oc, source_image, dest_imagestream):
    oc.tag(
        source_image,
        dest_imagestream,
        source='docker',
        reference_policy='local',
    )
    wait_for(oc, 'imagestreamtag', dest_imagestream)


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
