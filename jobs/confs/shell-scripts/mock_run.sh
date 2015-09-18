#!/bin/bash -xe
echo "shell-scripts/mock_run.sh"
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# distro
#     Distribution it should create the rpms for
#     (usually el<version>, fc<version>)
#
# arch
#     Architecture to build the packages for
#
# extra-packages
#     List of packages to install
#
# extra-repos
#     List of extra repositories to use when building, in a space separated
#     list of name,url pairs
#
# env
#     Extra environment variables
#
# script
#     Script to run inside mock, with the jenkins/jobs/confs/shell-scripts as
#     basepath
#
# copy_dirs
#     Directories to copy inside the chroot

distro="{distro}"
arch="{arch}"
copy_dirs=({copy-dirs})
project="{project}"
extra_packages=({extra-packages})
extra_repos=({extra-repos})
extra_env="{env}"
script="{script}"


# Generate the mock configuration
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
# Careful here, json is very sensitive to trailing commas in lists
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    --option="plugin_conf.bind_mount_enable=True" \
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

# prepare the command line
my_mock="/usr/bin/mock"
my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
my_mock+=" --root=$mock_conf"
my_mock+=" --resultdir=$WORKSPACE/exported-artifacts"

# init the chroot
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


# Install any extra packages if needed
if [[ -n "$extra_packages" ]]; then
    echo "##### Installing extra dependencies: $extra_packages"
    $my_mock \
        --no-clean \
        --install "${{extra_packages[@]}}"
fi

# Make sure that the destination home dir exists
$my_mock \
    --no-clean \
    --shell <<EOFMAKINGTHISHARDTOMATCH
mkdir -p /tmp/run
EOFMAKINGTHISHARDTOMATCH

# Copy workspace code to the chroot
[[ "$copy_dirs" ]] \
&& {{
    for dir in "${{copy_dirs[@]}}"; do
        $my_mock \
            --no-clean \
            --copyin "$dir" /tmp/run/"$dir"
    done
}}
# Copy also the jenkins dir
$my_mock \
    --no-clean \
    --copyin "jenkins" /tmp/run/jenkins

# Needed when running a yum installed inside the chroot, as it might be a
# different version than the one running on the host
$my_mock \
    --no-clean \
    --shell <<EOF
rm -f /var/lib/rpm/__db*
rpm --rebuilddb
EOF

# Run the script
echo "##### Running inside mock"
pushd "$WORKSPACE"/jenkins/mock_configs
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    --option="plugin_conf.bind_mount_enable=True" \
    --option='plugin_conf.bind_mount_opts.dirs=[
        ["/dev", "/dev/"],
        ["/sys", "/sys/"],
        ["/lib/modules", "/lib/modules/"]
    ]' \
    "${{mock_repos[@]}}" \
> "$mock_conf.cfg"
cat "$mock_conf.cfg"
popd

$my_mock \
    --no-clean \
    --shell <<EOFMAKINGTHISHARDTOMATCH
SCRIPT="/tmp/run/jenkins/jobs/confs/shell-scripts/{script}"
export HOME=/tmp/run
cd
chmod +x \$SCRIPT
\$SCRIPT
EOFMAKINGTHISHARDTOMATCH
