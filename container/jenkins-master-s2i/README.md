Jenkins master container image for STDCI
========================================

This directory contains files form building the Jenkins master container
images used for STDCI container-based masters.

The files here are mean to be used with [S2I][1] or the [OpenShift
source build strategy][2] while using the [OpenShift jenkins image][3]
as the build base image.

[1]: https://github.com/openshift/source-to-image
[2]: https://docs.okd.io/latest/architecture/core_concepts/builds_and_image_streams.html#source-build
[3]: https://github.com/openshift/jenkins

Jenkins CLI over SSH access
---------------------------
This image is configured to allow using the Jenkins CLI over SSH. The
CLI access is only possible from inside the container as the SSH port is
not exposed outside of it.

Assuming you have access to the OpenShift instance and namespace the
master is running in you can reach the CLI via `oc exec` like so:

    oc exec $MASTER_POD_NAME -- ssh -p 2222 admin@localhost

Where `$MASTER_POD_NAME` is the name of the pod running the container.

When starting the master for the 1st time, it is required to fix the
file permissions of the SSH key stored in the image with a command like
the following:

    oc exec $MASTER_POD_NAME -- \
        chmod -v 600 /var/lib/jenkins/.ssh/id_rsa

Failing to do the above would yield SSH connectivity errors when trying
to use the CLI as shown above.
