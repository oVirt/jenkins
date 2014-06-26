#!/bin/bash -xe
# shell-scripts/build_mock_srcrpm_releng.sh
# PARAMETERS
#
# subproject
#     Internal subproject in releng repo to build
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
# extra-build-packages
#     space separated list of extra packages to install, as you would pass to
#     yum
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
subproject="{subproject}"
extra_packages=({extra-build-packages})
extra_rpmbuild_options=({extra-rpmbuild-options})
extra_repos=({extra-repos})
extra_env="{env}"
WORKSPACE=$PWD


### Generate the mock configuration
rpmbuild_options=("-D" "release_suffix ${{suffix}}")
mock_build_options=("--define" "release_suffix ${{suffix}}")
for option in $extra_rpmbuild_options; do
    rpmbuild_options+=("-D" "${{option//=/ }}")
    mock_build_options+=("--define" "${{option//=/ }}")
done
pushd "$WORKSPACE"/jenkins/mock_configs
arch="{arch}"
case $distro in
    fc*) distribution="fedora-${{distro#fc}}";;
    el*) distribution="epel-${{distro#el}}";;
    *) echo "Unknown distro $distro"; exit 1;;
esac
mock_conf="${{distribution}}-$arch-custom"
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

### Build the srpms
echo "##### Copying repo into chroot"
$my_mock \
    --no-clean \
    --copyin "$WORKSPACE"/$project/specs/$subproject /tmp/$subproject

echo "##### Building the srpms"
$my_mock \
    --no-clean \
    --shell <<EOF
cd /tmp/$subproject
./build.sh "${{extra_build_options[@]}}"
mkdir /tmp/SRCRPMS
mv *src.rpm /tmp/SRCRPMS/
EOF

echo "#### Archiving the results"
$my_mock \
    --no-clean \
    --copyout /tmp/SRCRPMS ./SRCRPMS
mv ./SRCRPMS/* "$WORKSPACE"/exported-artifacts/
rm -Rf ./SRCRPMS
