#!/bin/bash -xe
# Do some black magic
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# distro
#     Distribution it should cre%ate the repms for (usually el6, el7, fc19 or
#     fc20)
#
# arch
#     Architecture to build the packages for
#
# extra-packages
#     space separated list of extra packages to install, as you would pass to
#     yum
#
# extra-configure-options
#     extra options to pass to configure

distro="{distro}"
arch="{arch}"
project="{project}"
extra_packages="{extra-packages}"
extra_configure_options="{extra-configure-options}"

WORKSPACE=$PWD

# Build the src_rpms
# Get the release suffix
pushd "$WORKSPACE/$project"
suffix=".$(date -u +%Y%m%d%H%M%S).git$(git rev-parse --short HEAD)"

# make sure it's properly clean
git clean -dxf
# build tarballs
./autogen.sh --system
./configure $extra_configure_options
make dist
mv *.tar.gz "$WORKSPACE"/exported-artifacts/
popd

## build src.rpm
rpmbuild \
    -D "_topdir $WORKSPACE/rpmbuild"  \
    -D "_srcrpmdir $WORKSPACE/exported-artifacts"  \
    -D "release_suffix ${{suffix}}"\
    -ts exported-artifacts/*.gz
## we don't need the rpmbuild dir no more
rm -Rf "$WORKSPACE"/rpmbuild

### Generate the mock configuration
pushd "$WORKSPACE"/jenkins/mock_configs
arch="{arch}"
case $distro in
    fc*) distribution="fedora-${{distro#fc}}";;
    el*) distribution="epel-${{distro#el}}";;
    *) echo "Unknown distro $distro"; exit 1;;
esac
mock_conf="${{distribution}}-$arch-ovirt-snapshot"
echo "#### Generating mock configuration"
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    --repo="ovirt-master-snapshot,http://resources.ovirt.org/pub/ovirt-master-snapshot/rpm/$distro" \
    --repo="ovirt-master-snapshot-static,http://resources.ovirt.org/pub/ovirt-master-snapshot-static/rpm/$distro" \
> "$mock_conf.cfg"
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz || :
cat "$mock_conf.cfg"
popd

## prepare the command line
my_mock="/usr/bin/mock"
my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
my_mock+=" --root=$mock_conf"

## init the chroot
echo "##### Initializing chroot"
$my_mock --init

### Install any extra packages if needed
if [[ -n "$extra_packages" ]]; then
    echo "##### Installing extra dependencies: $extra_packages"
    $my_mock \
	--no-clean \
	--install "$extra_packages"
fi

### Build the rpms
echo "##### Building the rpms"
$my_mock \
    --define="release_suffix $suffix" \
    --rebuild \
    --no-clean \
    --resultdir=$WORKSPACE/exported-artifacts \
    "$WORKSPACE"/exported-artifacts/*.src.rpm
