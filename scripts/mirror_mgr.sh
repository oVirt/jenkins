#!/bin/bash -e
# mirror_mgr.sh - Atomic mirror management script
#
# This script comtains various tools for managing oVirt CI package
# mirros the script is pribarily meant to be invoked from Jenkins.
#
# The basic syntax for running this script is:
#   mirror_mgr.sh COMMAND [COMMAND_ARGS..]
#
# Where COMMAND maps directly to a cmd_COMMAND function and the
# arguments are as needed by that function
#
# The main idea behind the CI package mirrors is to have atomic mirrors
# by using snapshots. Each time a mirror is updated, a snapshot of it is
# created. Clients are supposed to always use a snapshot so they can be
# guaranteed it will not change while they are using it.
# A 'latest.txt' file is created for each mirror to allow clients to
# determine which snapshot is the latest.
#
MIRRORS_VG="${MIRRORS_VG:-mirrors_vg}"
MIRRORS_TP="${MIRRORS_TP:-mirrors_tp}"
MIRRORS_LV="${MIRRORS_LV:-mirrors_lv}"
MIRRORS_FSTYPE="${MIRRORS_FSTYPE:-xfs}"
MIRRORS_MP_BASE="${MIRRORS_MP_BASE:-/var/www/html/repos}"
MIRRORS_HTTP_BASE="${MIRRORS_HTTP_BASE:-http://mirrors.phx.ovirt.org/repos}"
MIRRORS_CACHE="${MIRRORS_CACHE:-$HOME/mirrors_cache}"

MAX_LOCK_ATTEMPTS=120
LOCK_WAIT_INTERVAL=5
LOCK_BASE="$HOME"

main() {
    # Launch the command fuction according to the command given on the
    # command line
    local command="${1:?}"
    local command_args=("${@:2}")

    cmd_$command "${command_args[@]}"
}

cmd_resync_yum_mirror() {
    # Command for syncing a yum mirror.
    # This function will create a filesystem and a directory for storing
    # a mirror of the given repo, and then launch reposync to get
    # updates for the mirror.
    # If any updates were available for the mirror, this command wil
    # launch the cmd_snapshot_yum_mirror function to create a new mirror
    # snapshot
    #
    local repo_name="${1:?}"
    local repo_archs="${2:?}"
    local reposync_conf="${3:?}"

    local fs_was_created
    local sync_needed

    mkdir -p "$MIRRORS_CACHE"

    verify_repo_fs "$repo_name" yum fs_was_created

    if [[ $fs_was_created ]]; then
        sync_needed=true
    else
        check_yum_sync_needed \
            "$repo_name" "$repo_archs" "$reposync_conf" sync_needed
    fi

    if [[ $sync_needed ]]; then
        echo "Resyncing repo: $repo_name"
        perform_yum_sync "$repo_name" "$repo_archs" "$reposync_conf"
    else
        echo "Local mirror seems to be up to date"
    fi
    # failsafe - if we don't have a latest.txt file, create the snapshot
    # even if the mirror wasn't updated
    [[ $sync_needed || ! -f "$(latest_file $repo_name yum)" ]] &&
        cmd_snapshot_yum_mirror "$repo_name"
    echo done
}

cmd_snapshot_yum_mirror() {
    # Command for createing a yum mirror snapshot
    # Because yum is based around metadata index files, to create a
    # snapshot on a yum repository we don't actaully need to copy any
    # packag files. Instead, we just create a yum index file pointing to
    # a given state of the packages in the repo.
    # This way we alays have just one copy of a given package file so
    # that it can be easily cached in RAM of by HTTP caches.
    # The snpshot is made to contain only the latest version of each
    # package, that wat can can safely erase older packages without
    # worrying thy may be referenced by recent snapshots.
    #
    local repo_name="${1:?}"

    local snapshot_name
    local snapshot_mp
    local repo_mp
    local repo_comps
    local list_file

    repo_mp="$MIRRORS_MP_BASE/yum/$repo_name/base"
    [[ -d "$repo_mp" ]] || \
        die "Repo $repo_name doesn't seem to exist, did you sync it?"

    snapshot_name="$(date -u +%Y-%m-%d-%H-%M)"
    echo "Creating mirror snapshot: $snapshot_name"
    snapshot_mp="$MIRRORS_MP_BASE/yum/$repo_name/$snapshot_name"
    sudo install -o "$USER" -d "$snapshot_mp"

    [[ -f "$repo_mp/comps.xml" ]] && \
        repo_comps=("--groupfile=$repo_mp/comps.xml")
    list_file="$(mktemp)"
    echo "Creating snapshot package list" && \
        (
            cd "$repo_mp" && \
            repomanage --new --keep=1 --nocheck . > "$list_file"
        ) && \
        echo "Creating snapshot metadata" &&
        /bin/createrepo \
            --update --update-md-path="$repo_mp" \
            --baseurl="$(repo_url $repo_name yum base)" \
            --outputdir="$snapshot_mp" \
            --workers=8 \
            "${repo_comps[@]}" \
            --pkglist "$list_file" \
            "$repo_mp"
    rm -f "$list_file"
    echo "$snapshot_name" > "$(latest_file $repo_name yum)"
    /usr/sbin/restorecon -R "$snapshot_mp" "$(latest_file $repo_name yum)"
}

cmd_list_latest() {
    # List the latest repo URLs for all repos of the given type
    # An optional 2rd parameter specifies the listing format, and causes the
    # list to be passed through the latest_format_$format function, all other
    # parametrs will be passed to the formatting funtion as well
    #
    local repo_type="${1:?}"
    local formatter="latest_format_${2:-plain}"
    local formatter_params=("${@:3}")

    list_latest "$repo_type" | $formatter "${formatter_params[@]}"
}

cmd_write_latest_lists() {
    local repo_type="${1:?}"
    local varname="${2:-latest_ci_repos}"

    local list_file_path="$MIRRORS_MP_BASE/$repo_type/all_latest"
    local lock_name="latest_lists_$repo_type"

    wait_for_lock "$lock_name"
    echo "Writing lates index files for $repo_type repos"
    list_latest "$repo_type" | tee > /dev/null \
        >(latest_format_yaml "$varname" > "${list_file_path}.yaml") \
        >(latest_format_json "$varname" > "${list_file_path}.json") \
        >(latest_format_python "$varname" > "${list_file_path}.py")
    release_lock "$lock_name"
}

verify_repo_fs() {
    local repo_name="${1:?}"
    local repo_type="${2:?}"
    local p_fs_was_created="${3:?}"
    local repo_dev_name
    local repo_mp

    sudo vgs --noheadings -o 'vg_name' "$MIRRORS_VG" | \
        grep -q "$MIRRORS_VG" || \
        die "Cannot find volume group $MIRRORS_VG"

    if ! sudo lvs --noheadings -o 'lv_name' "$MIRRORS_VG/$MIRRORS_TP" | \
        grep -q "$MIRRORS_TP"
    then
        echo "Creating mirros thin pool: $MIRRORS_TP"
        sudo lvcreate \
            --name "$MIRRORS_TP" \
            --type thin-pool \
            --extents=50%VG \
            "$MIRRORS_VG"
    fi

    repo_dev_name="/dev/$MIRRORS_VG/$MIRRORS_LV"
    if [[ ! -b "$repo_dev_name" ]]; then
        echo "Createing mirrors base volume: $MIRRORS_LV"
        sudo lvcreate \
            --name "$repo_name" \
            --thin \
            --virtualsize=100G \
            --thinpool "$MIRRORS_TP" \
            "$MIRRORS_VG"
        eval $p_fs_was_created=true
    fi
    if ! sudo blkid -p -n "$MIRRORS_FSTYPE" -s '' "$repo_dev_name"; then
        echo "Createing mirror base $MIRRORS_FSTYPE at: $repo_dev_name"
        sudo mkfs -t xfs "$repo_dev_name"
        eval $p_fs_was_created=true
    fi
    ensure_mount "$repo_dev_name" "$MIRRORS_MP_BASE" rw $p_fs_was_created

    sudo install -o "$USER" -d \
        "$MIRRORS_MP_BASE/$repo_type" \
        "$MIRRORS_MP_BASE/$repo_type/$repo_name" \
        "$MIRRORS_MP_BASE/$repo_type/$repo_name/base"
}

check_yum_sync_needed() {
    local repo_name="${1:?}"
    local repo_archs="${2:?}"
    local reposync_conf="${3:?}"
    local p_sync_needed="${4:?}"
    local reposync_out

    echo "Checking if mirror needs a resync"
    for arch in $(IFS=,; echo $repo_archs) ; do
        reposync_out="$(
            run_reposync "$repo_name" "$arch" "$reposync_conf" --urls --quiet
        )"
        if [[ $reposync_out ]]; then
            eval $p_sync_needed=true
            return
        fi
    done
}

perform_yum_sync() {
    local repo_name="${1:?}"
    local repo_archs="${2:?}"
    local reposync_conf="${3:?}"
    local repo_mp
    local repo_comps

    repo_mp="$MIRRORS_MP_BASE/yum/$repo_name/base"
    for arch in $(IFS=,; echo $repo_archs) ; do
        echo "Syncing yum repo $repo_name for arch: $arch"
        run_reposync "$repo_name" "$arch" "$reposync_conf" \
            --downloadcomps --gpgcheck
    done
    [[ -f "$repo_mp/comps.xml" ]] && \
        repo_comps=("--groupfile=$repo_mp/comps.xml")
    echo "Generating yum repo metadata for: $repo_name"
    /bin/createrepo --update --workers=8 "${repo_comps[@]}" "$repo_mp"
    /usr/sbin/restorecon -R "$repo_mp"
}

ensure_mount() {
    local device="${1:?}"
    local mount_point="${2:?}"
    local opts="${3:-rw},noatime"
    local p_was_mounted="${4:?}"

    local fstab_line

    sudo mkdir -p "$mount_point"
    fstab_line="$device $mount_point $MIRRORS_FSTYPE $opts 0 0"
    if ! grep -qF "$fstab_line" /etc/fstab; then
        sudo sed -i -e $'$a\\\n'"$fstab_line" /etc/fstab
        eval $p_was_mounted=true
    fi
    if ! grep -q " $mount_point " /proc/mounts ; then
        sudo mount $mount_point
        eval $p_was_mounted=true
    fi
}

run_reposync() {
    local repo_name="${1:?}"
    local repo_arch="${2:?}"
    local reposync_conf="${3:?}"
    local extra_args=("${@:4}")

    reposync \
        --config="$reposync_conf" \
        --repoid="$repo_name" \
        --arch="$repo_arch" \
        --cachedir="$MIRRORS_CACHE" \
        --download_path="$MIRRORS_MP_BASE/yum/$repo_name/base" \
        --norepopath --newest-only \
        "${extra_args[@]}"
}

list_latest() {
    local repo_type="${1:?}"
    local lf repo_name

    for lf in $(latest_file '*' "$repo_type"); do
        [[ "$lf" =~ ^$(latest_file '(.*)' "$repo_type")$ ]] || continue
        repo_name="${BASH_REMATCH[1]}"
        # If we get a '*' as the repo name it probably just means we got our
        # pattern back instead of matches, so we just break out of the loop
        [[ "$repo_name" = "*" ]] && break
        echo "$repo_name $(repo_url "$repo_name" "$repo_type" "$(cat $lf)")"
    done
}

latest_format_plain() { cat; }

latest_format_yaml() {
    local varname="${1:-latest_ci_repos}"
    echo $'---\n'"${varname}:"
    while read repo_name repo_url; do
        echo "  $repo_name: '$repo_url'"
    done
}

latest_format_json() {
    local varname="${1:-latest_ci_repos}"
    local json
    echo "{ \"${varname}\": {"
    json="$(
        while read repo_name repo_url; do
            echo "  \"$repo_name\": \"$repo_url\","
        done
    )"
    echo "${json%%,}"
    echo "} }"
}

latest_format_python() {
    local varname="${1:-latest_ci_repos}"
    local indention="${2:-}"
    echo "${indention}${varname} = {"
    while read repo_name repo_url; do
        echo "${indention}    '$repo_name': '$repo_url',"
    done
    echo "${indention}}"
}

latest_file() {
    local repo_name="${1:?}"
    local repo_type="${2:?}"
    echo "$MIRRORS_MP_BASE/$repo_type/$repo_name/latest.txt"
}

repo_url() {
    local repo_name="${1:?}"
    local repo_type="${2:?}"
    local snapshot="${3:-base}"

    echo "$MIRRORS_HTTP_BASE/$repo_type/$repo_name/$snapshot"
}

wait_for_lock() {
    local lock_name="${1:?}"
    local max_lock_attempts="${2:-$MAX_LOCK_ATTEMPTS}"
    local lock_wait_interval="${3:-$LOCK_WAIT_INTERVAL}"
    local lock_path="$LOCK_BASE/${lock_name}.lock"

    for ((i = 0; i < $max_lock_attempts; i++)); do
        if (set -o noclobber; > $lock_path) 2> /dev/null; then
            echo "Acquired lock: $lock_name"
            trap "release_lock '$lock_name'" EXIT
            return
        fi
        sleep $lock_wait_interval
    done
    echo "Timed out waiting for lock: $lock_name" >&2
    exit 1
}

release_lock() {
    local lock_name="${1:?}"
    local lock_path="$LOCK_BASE/${lock_name}.lock"
    if [[ -e "$lock_path" ]]; then
        rm -f "$lock_path"
        echo "Released lock: $lock_name"
    fi
}

die() {
    echo "$@" >&2
    exit 1
}

main "$@"
