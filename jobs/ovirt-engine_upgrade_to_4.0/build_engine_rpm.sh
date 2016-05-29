#!/bin/bash -xe

## Copyright (C) 2014 Red Hat, Inc., Kiril Nesenko <knesenko@redhat.com>
### This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
(
    set +x
    echo ====================================================================
    echo == "$(basename "$0")"
)

shopt -s nullglob

help()
{
    rc="$1"
    msg="$2"
    cat << EOH
    USAGE:
        > $0 [-h|--help] -s SRC_DIR -d DST_DIR [-x MVN_SETTINGS]

    PARAMETERS:
        -s|--src-dir SRC_DIR
            Directory containing the engine sources

        -d|--dst-dir DST_DIR
            Directory where the built rpms will be put

    OPTIONS
        -h|--help
            Show this help and exit

        -x|--mvn-settings MVN_SETTINGS
            File with the maven settings to use
EOH
    if [[ -n $rc ]]; then
        [[ -n $msg ]] && echo "$msg"
        exit $rc
    fi
}


get_release_suffix()
{
    local src_ent="${1?}"
    local rel
    ## check if we have the git directory as source entity for the release
    if [[ -d "$src_ent"/.git ]]; then
        pushd "$src_ent" &>/dev/null
        rel=".git$(git rev-parse --short HEAD)"
    else
        echo "Unable to detect release from $src_ent"
        return 1
    fi
    echo "$rel"
    return 0
}


create_tarball()
{
    local src_dir="${1?}"
    local dst_dir="${2?}"
    pushd "$src_dir" &>/dev/null
    rm -f ovirt-engine-*.tar.gz
    make dist &> "$dst_dir/make_dist.log" \
    || return 1
    [[ -d "$dst_dir" ]] || mkdir -p "$dst_dir"
    tarball=(ovirt-engine-*.tar.gz)
    [[ -z $tarball ]] || ! [[ -e $tarball ]] \
    && {
        echo "No tarball created at $src_dir" >&2
        return 1
    }
    mv "$tarball" "$dst_dir/"
    echo "$dst_dir/$tarball"
    return 0
}


create_src_rpm()
{
    local tarball="${1?}"
    local dst_dir="${2?}"
    local workspace="${3:-$PWD}"
    local BUILD_JAVA_OPTS_MAVEN="\
    -XX:MaxPermSize=1G \
    -Dgwt.compiler.localWorkers=1 \
"
    local BUILD_JAVA_OPTS_GWT="\
    -XX:PermSize=512M \
    -XX:MaxPermSize=1G \
    -Xms1G \
    -Xmx6G \
"
    rm -f "$workspace"/ovirt-engine-*.src.rpm
    env BUILD_JAVA_OPTS_MAVEN="${BUILD_JAVA_OPTS_MAVEN}" \
        BUILD_JAVA_OPTS_GWT="${BUILD_JAVA_OPTS_GWT}" \
        rpmbuild \
                 -D "_srcrpmdir $workspace" \
                 -D "_specdir $workspace" \
                 -D "_sourcedir $workspace" \
                 -D "_rpmdir $workspace" \
                 -D "_builddir $workspace" \
                 -ts "$tarball" \
    &> "$dst_dir"/src_rpmbuild.log \
    || return 1
    src_rpm=("$workspace/"ovirt-engine-*.src.rpm)
    [[ -z $src_rpm ]] || ! [[ -e $src_rpm ]] \
    && {
        echo "No src rpm created at $workspace" >&2
        return 1
    }
    mv "$src_rpm" "$dst_dir"/
    echo "$dst_dir/${src_rpm##*/}"
    return 0
}


create_rpms()
{
    local src_rpm="${1?}"
    local dst_dir="${2?}"
    local release="${3?}"
    local workspace="${4:-$PWD}"
    local BUILD_JAVA_OPTS_MAVEN="\
    -XX:MaxPermSize=1G \
    -Dgwt.compiler.localWorkers=1 \
"
    local BUILD_JAVA_OPTS_GWT="\
    -XX:PermSize=512M \
    -XX:MaxPermSize=1G \
    -Xms1G \
    -Xmx6G \
"
    env BUILD_JAVA_OPTS_MAVEN="${BUILD_JAVA_OPTS_MAVEN}" \
        BUILD_JAVA_OPTS_GWT="${BUILD_JAVA_OPTS_GWT}" \
        rpmbuild \
                 -D "ovirt_build_minimal 1" \
                 -D "release_suffix $release" \
                 -D "ovirt_build_extra_flags -gs ${CI_MAVEN_SETTINGS}" \
                 -D "_srcrpmdir $dst_dir" \
                 -D "_specdir $dst_dir" \
                 -D "_sourcedir $dst_dir" \
                 -D "_rpmdir $dst_dir" \
                 -D "_builddir $dst_dir" \
                 --rebuild "$src_rpm" \
    &> "$dst_dir"/rpmbuild.log \
    || return 1
    return 0
}



###### MAIN
unset SRC_DIR DST_DIR MVN_SETTINGS
opts=$(getopt \
    -o 's:d:x:h' \
    -l 'src-dir:,dst-dir:,mvn-settings:,help' \
    -n "$0" \
    -- "$@")
[[ $? -eq 0 ]] ||  help 1;
eval set -- "$opts"
while true; do
    opt="$1"
    val="$2"
    shift 2 || :
    case $opt in
        -s|--src-dir)
            SRC_DIR="$val";;
        -d|--dst-dir)
            DST_DIR="$val";;
        -x|--mvn-settings)
            export CI_MAVEN_SETTINGS="$val";;
        -h|--help) help 0;;
        --) break;;
    esac
done

[[ -z $SRC_DIR ]] && help 1 "No --src-dir parameter passed"
[[ -z $DST_DIR ]] && help 1 "No --dst-dir parameter passed"
[[ -e $SRC_DIR ]] || help 1 "The source dir $SRC_DIR does not exist."
[[ -e $DST_DIR ]] || mkdir -p "$DST_DIR"

(set +x; echo CREATING ENGINE TARBALL)
tarball="$(create_tarball "$SRC_DIR" "$DST_DIR")"
(set +x; echo BUILDING ENGINE SRC RPM)
src_rpm="$(create_src_rpm "$tarball" "$DST_DIR")"
release="$(get_release_suffix "$SRC_DIR")"
(set +x; echo BUILDING ENGINE RPM)
create_rpms "$src_rpm" "$DST_DIR" "$release"
result=$?
if [[ $result -eq 0 ]]; then
    (set +x; echo ENGINE BUILD SUCCESSFUL)
else
    (set +x; echo ENGINE BUILD FAILED)
fi
(
    set +x
    echo listing built files
    find "$DST_DIR" -type f
)
exit $result
