#!/bin/bash -xe
echo "shell-scripts/standard_check_merge.sh"
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# distro
#     Distribution it should create the rpms for (usually el6, el7, fc19 or
#     fc20)
#
# arch
#     Architecture to build the packages for
#
# extra-packages
#     List of packages to install, should be empty as it should use the .req
#     files instead
#
# extra-repos
#     List of extra repositories to use when building, in a space separated list
#     of name,url pairs
#
# extra-env
#     Extra environment variables

distro="{distro}"
arch="{arch}"
project="{project}"
extra_packages=({extra-packages})
extra_repos=({extra-repos})
extra_env=({extra-env})
WORKSPACE=$PWD
script="automation/check-merged.sh"


### Generate the mock configuration
pushd "$WORKSPACE"/jenkins/mock_configs
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
    --try-proxy \
    --option="basedir=$WORKSPACE/mock/" \
    "${{mock_repos[@]}}" \
> "$mock_conf.cfg"
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz &>/dev/null || :
cat "$mock_conf.cfg"
popd

## prepare the command line
my_mock="/usr/bin/mock"
my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
my_mock+=" --root=$mock_conf"
my_mock+=" --resultdir=$WORKSPACE/exported-artifacts"

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

### Install any extra packages if needed
## from config
if [[ -n "$extra_packages" ]]; then
    echo "##### Installing extra dependencies: $extra_packages"
    $my_mock \
        --no-clean \
        --install "${{extra_packages[@]}}"
fi
## from project requirements file
build_deps_file="$project/automation/check-merged.req.${{distro}}"
[[ -f "$build_deps_file" ]] \
|| build_deps_file="$project/automation/check-merged.req"
if [[ -f  "$build_deps_file" ]]; then
    echo "##### Installing extra dependencies from $build_deps_file"
    packages=($(cat "$build_deps_file"))
    $my_mock \
        --no-clean \
        --install "${{packages[@]}}"
fi

## Needed when running yum inside the chroot on different distro than the host,
## because rpmdb is first generated with the host yum when creating the chroot
## and sometimes is not compatible with the chroot installed yum version
$my_mock \
    --no-clean \
    --shell <<EOF
rm -f /var/lib/rpm/__db*
rpm --rebuilddb
EOF

### Mount the current workspace in the chroot
$my_mock \
    --no-clean \
    --shell <<EOFMAKINGTHISHARDTOMATCH
mkdir -p /tmp/run
EOFMAKINGTHISHARDTOMATCH

# Adding the workspace mount to the config
pushd "$WORKSPACE"/jenkins/mock_configs
echo "#### Generating mock configuration with workspace mounted"
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --try-proxy \
    --option="basedir=$WORKSPACE/mock/" \
    --option="resultdir=$WORKSPACE/exported-artifacts" \
    --option="plugin_conf.bind_mount_enable=True" \
    --option='plugin_conf.bind_mount_opts.dirs=[
        ["'"$WORKSPACE"'", "/tmp/run"]
    ]' \
    "${{mock_repos[@]}}" \
> "$mock_conf.cfg"
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz &>/dev/null || :
cat "$mock_conf.cfg"
popd

### Run the script
echo "##### Running $SCRIPT inside mock"
$my_mock \
    --no-clean \
    --shell <<EOFMAKINGTHISHARDTOMATCH
set -e
SCRIPT="/tmp/run/$project/$script"
export HOME=/tmp/run
cd \$HOME/$project
chmod +x \$SCRIPT
\$SCRIPT
echo -e "\n\n"
[[ -d exported-artifacts  ]] && ls -la exported-artifacts
echo "Finished running the script"
EOFMAKINGTHISHARDTOMATCH

mkdir -p "$WORKSPACE"/exported-artifacts
sudo chown -R $USER:$USER "$WORKSPACE/exported-artifacts"
if ls "$WORKSPACE/$project/exported-artifacts/"* &>/dev/null; then
    sudo mv "$WORKSPACE/$project/exported-artifacts/"* \
            "$WORKSPACE/exported-artifacts/"
    sudo rmdir "$WORKSPACE/$project/exported-artifacts/"
fi
exit 0
