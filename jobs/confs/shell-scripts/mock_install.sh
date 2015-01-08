#!/bin/bash -xe
echo "shell-scripts/mock_install.sh"
# Do some black magic
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# distro
#     Distribution it should create the rpms for (usually el6, el7, fc20 or
#     fc21)
#
# arch
#     Architecture to build the packages for
#
# packages
#     List of paths to the packages to install
#
# extra-repos
#     List of extra repositories to use when building, in a space separated list
#     of name,url pairs
#
# env
#     Extra environment variables
#

distro="{distro}"
arch="{arch}"
project="{project}"
packages=({packages})
extra_repos=({extra-repos})
extra_env="{env}"


### Generate the mock configuration
pushd "$WORKSPACE"/jenkins/mock_configs
arch="{arch}"
case $distro in
    fc*) distribution="fedora-${{distro#fc}}";;
    el*) distribution="epel-${{distro#el}}";;
    *) echo "Unknown distro $distro"; exit 1;;
esac
mock_conf="${{distribution}}-$arch-ovirt-snapshot"
mock_repos=()
for mock_repo in "${{extra_repos[@]}}"; do
    mock_repos+=("--repo" "$mock_repo")
done
echo "#### Generating mock configuration"
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    "${{mock_repos[@]}}" \
> "$mock_conf.cfg"
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz || :
cat "$mock_conf.cfg"
popd

pkg_array=()
for package in "${{packages[@]}}"; do
    [[ -f "$package" ]] \
    || {{
        echo "ERROR: Package $package not found!"
        exit 1
    }}
done

echo "Will install the packages:"
echo "    ${{packages[@]}}"

## prepare the command line
my_mock="/usr/bin/mock"
my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
my_mock+=" --root=$mock_conf"

## init the chroot
$my_mock \
    --init

### Configure extra yum vars
echo "Configuring custom env variables for repo urls"
$my_mock \
    --no-clean \
    --shell <<EOF
        mkdir -p /etc/yum/vars
        echo "$distro" > /etc/yum/vars/distro
EOF

## Needed when running shell on different arch than the host, because rpmdb is
## copied from it when creating the chroot and x86_64 rpmdb is not compatible on
## i686
$my_mock \
    --no-clean \
    --shell <<EOF
rm -f /var/lib/rpm/__db*
rpm --rebuilddb
EOF

### Copy the packages to the chroot
$my_mock \
    --no-clean \
    --copyin "${{packages[@]}}" /tmp/

### Install yum
$my_mock \
    --no-clean \
    --install \
        yum

### Install the packages
echo "##### Installing ${{packages[@]}}"
$my_mock \
    --no-clean \
    --shell <<EOF
yum localinstall -y /tmp/*rpm
EOF
