#!/bin/bash -xe
echo "shell-scripts/build_mock_srcrpm.sh"
# PARAMETERS
#
# project
#     Name of the project it runs on, specifically the dir where the code
#     has been cloned
#
# distro
#     Distribution it should create the rpms for (usually el6, el7, fcXX)
#
# arch
#     Architecture to build the packages for
#
# extra-build-packages
#     space separated list of extra packages to install, as you would pass to
#     yum
#
# extra-build-options
#     space separated list of extra options to pass to the build.sh script
#
# extra-configure-options
#     space separated list of extra options to pass to the configure script
#
# extra-autogen-options
#     space separated list of extra options to pass to the autogen.sh script
#
# extra-rpmbuild-options
#     extra options to pass to rpmbuild as defines, as a spaceseparated list
#     of key=value pairs
#
# extra-repos
#     List of extra repositories to use when building, in a space separated list
#     of name,url pairs
#
# extra-env
#     extra env variables to set when building
#
# cherry-pick
#     List of refspecs to cherry-pick before creating the src.rpm
#
# extra-make-targets
#     extra make targets to be built
#

distro="{distro}"
arch="{arch}"
project="{project}"
extra_build_options=({extra-build-options})
extra_configure_options=({extra-configure-options})
extra_autogen_options=({extra-autogen-options})
extra_rpmbuild_options=({extra-rpmbuild-options})
extra_build_packages=(
    autoconf
    make
    {extra-build-packages}
)
extra_repos=({extra-repos})
extra_env=({extra-env})
to_cherry_pick=({cherry-pick})
make_targets=(dist {extra-make-targets})
WORKSPACE=$PWD

# Get the release suffix
pushd "$WORKSPACE/$project"

# Cherry pick now all the required patches
for patch in "${{to_cherry_pick[@]}}"; do
    git fetch origin "$patch"
    git cherry-pick FETCH_HEAD
done

suffix=".$(date -u +%Y%m%d%H%M%S).git$(git rev-parse --short HEAD)"
echo "suffix='${{suffix}}'" > "$WORKSPACE/tmp/rpm_suffix.inc"

### Generate the mock configuration
rpmbuild_options=("-D" "release_suffix ${{suffix}}")
mock_build_options=("--define" "release_suffix ${{suffix}}")
for option in "${{extra_rpmbuild_options[@]}}"; do
    rpmbuild_options+=("-D" "${{option//=/ }}")
    mock_build_options+=("--define" "${{option//=/ }}")
done
pushd "$WORKSPACE"/jenkins/mock_configs
case $distro in
    fc*) distribution="fedora-${{distro#fc}}";;
    el*) distribution="epel-${{distro#el}}";;
    *) echo "Unknown distro $distro"; exit 1;;
esac
mock_conf="${{distribution}}-$arch-custom"
mock_repos=()
for mock_repo in "${{extra_repos[@]}}"; do
    mock_repos+=("--repo=$mock_repo")
done
### Set any extra env vars if any
mock_envs=()
for env_opt in "${{extra_env[@]}}"; do
    mock_envs+=("--option=environment.$env_opt")
done
echo "#### Generating mock configuration"
./mock_genconfig \
    --name="$mock_conf" \
    --base="$distribution-$arch.cfg" \
    --option="basedir=$WORKSPACE/mock/" \
    --try-proxy \
    "${{mock_repos[@]}}" \
    "${{mock_envs[@]}}" \
> "$mock_conf.cfg"
sudo touch /var/cache/mock/*/root_cache/cache.tar.gz || :
cat "$mock_conf.cfg"
popd

## prepare the command line
my_mock="/usr/bin/mock"
my_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
my_mock+=" --root=$mock_conf"
my_mock+=" --resultdir=$WORKSPACE"

## init the chroot
echo "##### Initializing chroot"
$my_mock --init
$my_mock \
    --no-clean \
    --scrub=yum-cache

### Configure extra yum vars
echo "Configuring custom env variables for repo urls"
$my_mock \
    --no-clean \
    --shell <<EOF
        mkdir -p /etc/yum/vars
        echo "$distro" > /etc/yum/vars/distro
EOF

### Install any extra packages if needed
if [[ -n "$extra_build_packages" ]]; then
    echo "##### Installing extra dependencies: $extra_packages"
    $my_mock \
        --no-clean \
        --install "${{extra_build_packages[@]}}"
fi


### Set custom dist from mock config into rpmmacros for manual builds
rpm_dist="$(grep 'config_opts\["dist"\]' \
            $WORKSPACE/jenkins/mock_configs/$mock_conf.cfg)"
rpm_dist="${{rpm_dist//[\'\"]/}}"
rpm_dist=.${{rpm_dist#*=}}
$my_mock \
    --no-clean \
    --shell <<EOF
        echo "%dist $rpm_dist" > ~/.rpmmacros
EOF

### Build the srpms
echo "##### Copying repo into chroot"

# Build the src_rpms
# Get the release suffix
pushd "$WORKSPACE/$project"
suffix=".$(date -u +%Y%m%d%H%M%S).git$(git rev-parse --short HEAD)"

# make sure it's properly clean
git clean -dxf
popd


$my_mock \
    --no-clean \
    --copyin "$WORKSPACE"/$project /tmp/$project

echo "##### Building the srpms"
$my_mock \
    --no-clean \
    --shell <<EOF
        set -e
        cd /tmp/$project
        if [[ -x autogen.sh ]]; then
            ./autogen.sh --system "${{extra_autogen_options[@]}}"
        elif [[ -e configure.ac ]]; then
            autoreconf -ivf
        fi
        [[ -x configure  ]] &&
            ./configure ${{extra_configure_options[@]}}
        # Build extra make targets, like offline-tarball for ovirt-host-deploy
        make ${{make_targets[@]}}

        if [[ -n ${{suffix}} ]]; then
            rpmbuild_options=("-D" "release_suffix ${{suffix}}")
        else
            rpmbuild_options=()
        fi
        for option in "${{extra_rpmbuild_options[@]}}"; do
            rpmbuild_options+=("-D" "${{option//=/ }}")
        done

        shopt -s nullglob
        # build src.rpm
        rpmbuild \
            -D "_srcrpmdir ."  \
            "\${{rpmbuild_options[@]}}" \
            -ts *.gz *.bz2

        mkdir /tmp/SRCRPMS
        mv *.tar.gz *.tar.bz2 /tmp/SRCRPMS/
        mv *src.rpm /tmp/SRCRPMS/
EOF

echo "#### Archiving the results"
$my_mock \
    --no-clean \
    --copyout /tmp/SRCRPMS ./SRCRPMS
mv ./SRCRPMS/* "$WORKSPACE"/
rm -Rf ./SRCRPMS
