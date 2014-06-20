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
#
# extra-autogen-options
#     extra options to pass to autogen
#
# extra-rpmbuild-options
#     extra options to pass to rpmbuild as defines, as a spaceseparated list
#     of key=value pairs
#
# extra-repos
#     List of extra repositories to use when building, in a space separated list
#     of name,url pairs
#
# env
#     extra env variables to set when building

distro="{distro}"
arch="{arch}"
project="{project}"
extra_packages=({extra-packages})
extra_configure_options=({extra-configure-options})
extra_autogen_options=({extra-autogen-options})
extra_rpmbuild_options=({extra-rpmbuild-options})
extra_repos=({extra-repos})
extra_env="{env}"

WORKSPACE=$PWD


# Build the src_rpms
# Get the release suffix
pushd "$WORKSPACE/$project"
suffix=".$(date -u +%Y%m%d%H%M%S).git$(git rev-parse --short HEAD)"

# make sure it's properly clean
git clean -dxf
# build tarballs
./autogen.sh --system "${{extra_autogen_options[@]}}"
./configure "${{extra_configure_options[@]}}"
make dist
mv *.tar.gz "$WORKSPACE"/exported-artifacts/
popd

## build src.rpm
rpmbuild_options=("-D" "release_suffix ${{suffix}}")
mock_build_options=("--define" "release_suffix ${{suffix}}")
for option in $extra_rpmbuild_options; do
    rpmbuild_options+=("-D" "${{option//=/ }}")
    mock_build_options+=("--define" "${{option//=/ }}")
done
rpmbuild \
    -D "_topdir $WORKSPACE/rpmbuild"  \
    -D "_srcrpmdir $WORKSPACE/exported-artifacts"  \
    "${{rpmbuild_options[@]}}" \
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
mock_repos=''
for mock_repo in "${{extra_repos[@]}}"; do
    mock_repos+=" --repo=$mock_repo"
done
echo "#### Generating mock configuration"
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    $mock_repos \
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
	--install "${{extra_packages[@]}}"
fi

### Set any extra env vars if any
if [[ -n $extra_env ]]; then
    echo "Configuring custom env variables"
    $my_mock \
	--no-clean \
	--shell <<EOF
        echo "export $extra_env" >> /etc/profile
EOF
fi

### Build the rpms
echo "##### Building the rpms"
$my_mock \
    "${{mock_build_options[@]}}" \
    --rebuild \
    --no-clean \
    --resultdir=$WORKSPACE/exported-artifacts \
    "$WORKSPACE"/exported-artifacts/*.src.rpm
