#!/bin/bash -xe
echo "shell-scripts/mock_build_onlyrpm.sh"
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
# extra-packages
#     space separated list of extra packages to install, as you would pass to
#     yum
#
# extra-rpmbuild-options
#     extra options to pass to rpmbuild as defines, as a space separated list
#     of key=value pairs
#
# extra-repos
#     List of extra repositories to use when building, in a space separated list
#     of name,url pairs
#
# extra-env
#     extra env variables to set when building
#
# copy-in
#     list of files to copy into the chroot before building the rpm
#
# copy-out
#     list of files to copy out of the chroot after building the rpm

distro="{distro}"
arch="{arch}"
project="{project}"
extra_packages=(vim-minimal {extra-packages})
extra_rpmbuild_options=({extra-rpmbuild-options})
extra_repos=({extra-repos})
extra_env=({extra-env})
copy_in=({copy-in})
copy_out=({copy-out})
WORKSPACE=$PWD

### Import the suffix if any
[[ -f "${{WORKSPACE}}/tmp/rpm_suffix.inc" ]] \
&& source "${{WORKSPACE}}/tmp/rpm_suffix.inc"

### Generate the mock configuration
rpmbuild_options=()
mock_build_options=()
if [[ -n $suffix ]]; then
    rpmbuild_options+=("-D" "release_suffix ${{suffix}}")
    mock_build_options+=("--define" "release_suffix ${{suffix}}")
fi
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
mock_conf="${{distribution}}-$arch-ovirt-snapshot"
### Set extra repos if any
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
build_mock="/usr/bin/mock"
build_mock+=" --configdir=$WORKSPACE/jenkins/mock_configs"
build_mock+=" --root=$mock_conf"
temp_mock="$build_mock --resultdir=$WORKSPACE"

### Build the rpms
echo "##### Building the rpms"
for srcrpm in "$WORKSPACE"/exported-artifacts/*.src.rpm; do

    ## init the chroot
    echo "##### Initializing chroot for ${{srcrpm##*/}}"
    $temp_mock \
        --init
    $temp_mock \
        --no-clean \
        --scrub=yum-cache

    ### Configure extra yum vars
    echo "Configuring custom env variables for repo urls for ${{srcrpm##*/}}"
    $temp_mock \
        --no-clean \
        --shell <<EOF
            mkdir -p /etc/yum/vars
            echo "$distro" > /etc/yum/vars/distro
EOF

    ### Install any extra packages if needed
    if [[ -n "$extra_packages" ]]; then
        echo "##### Installing extra dependencies: " \
             "$extra_packages for ${{srcrpm##*/}}"
        $temp_mock \
        --no-clean \
        --install "${{extra_packages[@]}}"
    fi

    ### Copy files if any
    for fname in "${{copy_in[@]}}"; do
        if [[ "$fname" =~ ^.*: ]]; then
            dest="${{fname#*:}}"
            fname="${{fname%:*}}"
        else
            dest="/root"
        fi
        fname="$PWD/$fname"
        if ! [[ -r "$fname" ]]; then
            echo "ERROR::Unable to read file $fname"
            exit 1
        fi
        $temp_mock \
            --no-clean \
            --copyin \
            "$fname" \
            "$dest"
    done

    ### Set custom dist from mock config into rpmmacros for manual builds
    rpm_dist="$(grep 'config_opts\["dist"\]' \
                $WORKSPACE/jenkins/mock_configs/$mock_conf.cfg)"
    rpm_dist="${{rpm_dist//[\'\"]/}}"
    rpm_dist=${{rpm_dist#*=}}
    [[ -n $rpm_dist ]] \
    && mock_build_options+=("--define" "dist .${{rpm_dist//\"/}}")

    echo "     Building $srcrpm"
    $build_mock \
        "${{mock_build_options[@]}}" \
        --rebuild \
        --no-clean \
        --no-cleanup-after \
        --resultdir=$WORKSPACE/exported-artifacts \
        "$srcrpm"

    ### Copy out files if any
    for fname in "${{copy_out[@]}}"; do
        if [[ "$fname" =~ ^.*: ]]; then
            dest="${{fname#*:}}"
            fname="${{fname%:*}}"
        else
            dest="$PWD/exported-artifacts"
        fi
        $temp_mock \
            --no-clean \
            --copyout \
            "$fname" \
            "$dest"
    done
done
