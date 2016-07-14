#!/bin/bash -xe
echo "shell-scripts/build_local_srcrpm.sh"
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# extra-configure-options
#     extra options to pass to configure
#
# extra-autogen-options
#     extra options to pass to autogen
#
# extra-rpmbuild-options
#     extra options to pass to rpmbuild as defines, as a spaceseparated list
#     of key=value pairs
#
# env
#     extra env variables to set when building

project="{project}"
extra_configure_options=({extra-configure-options})
extra_autogen_options=({extra-autogen-options})
extra_rpmbuild_options=({extra-rpmbuild-options})
extra_env="{env}"
WORKSPACE=$PWD


# Build the src_rpms
# Get the release suffix
pushd "$WORKSPACE/$project"
suffix=".$(date -u +%Y%m%d%H%M%S).git$(git rev-parse --short HEAD)"
# We store the suffix so it can be used on other scripts
echo "suffix='${{suffix}}'" > "${{WORKSPACE}}/tmp/rpm_suffix.inc"

# make sure it's properly clean
git clean -dxf
# build tarballs
if [[ -x autogen.sh ]]; then
    yum install -y autoconf automake
    ./autogen.sh --system "${{extra_autogen_options[@]}}"
elif [[ -e configure.ac ]]; then
    autoreconf -ivf
fi

if [[ -x configure ]]; then
    ./configure ${{extra_configure_options[@]}}
fi
make dist
mv *.tar.gz "$WORKSPACE"/exported-artifacts/
popd

## build src.rpm
rpmbuild_options=("-D" "release_suffix ${{suffix}}")
for option in "${{extra_rpmbuild_options[@]}}"; do
    rpmbuild_options+=("-D" "${{option//=/ }}")
done
# not using -D "_srcrpmdir $WORKSPACE/exported-artifacts"
# avoiding duplicate src.rpms
rpmbuild \
    -D "_topdir $WORKSPACE/rpmbuild"  \
    -D "_srcrpmdir $WORKSPACE"  \
    "${{rpmbuild_options[@]}}" \
    -ts exported-artifacts/*.gz
## we don't need the rpmbuild dir no more
rm -Rf "$WORKSPACE"/rpmbuild
