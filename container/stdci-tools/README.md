STDCI tools container
=====================

This directory contains files for building a container that provides access to
the STDCI tools.

Build requirements
------------------
This container is built using the [s2i][1] tool and the [RHEL8 UBI Python
3.6][2] base image.

[1]: https://github.com/openshift/source-to-image
[2]: https://access.redhat.com/containers/?get-method=registry-tokens#/registry.access.redhat.com/ubi8/python-36

To use the *s2i* tool you must first have Docker installed and then you can
download a release from the [GitHub releases page][3] and extract it so the
included `s2i` binary is in `$PATH`.

[3]: https://github.com/openshift/source-to-image/releases

To obtain access to the RHEL UBI image you must create an account on
[redhat.com][4] (You can create a free developer account if you don't have one
already) and then go to [this page][5] to create a registry service account.
After you've created the service account you will get access to instruction
about how to login to the registry with various tools. Follow the instructions
for `docker login`.

[4]: https://www.redhat.com
[5]: https://access.redhat.com/terms-based-registry/

Building this container
-----------------------
Once you have the necessary tools installed, the container itself can be build
with the following command (Running from the same directory where this
`README.md` file is found):

    s2i build . registry.redhat.io/ubi8/python-36 quay.io/ovirtci/stdci-tools
