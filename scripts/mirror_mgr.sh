#!/bin/bash -xe
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
# The snapshots are built to be primarily compatible with DNF. To make them
# also work with yum, the following rewrite rules need to be configured for the
# HTTPD server sharing the mirrors
#
#   RewriteEngine On
#   RewriteCond "%{DOCUMENT_ROOT}/$0" !-f
#   RewriteRule "^/repos/yum/([^/]+)/([0-9-]+)/repodata/(.*)$" "/repos/yum/$1/base/repodata/$3" [R]
#
MIRRORS_MP_BASE="${MIRRORS_MP_BASE:-/var/www/html/repos}"
MIRRORS_HTTP_BASE="${MIRRORS_HTTP_BASE:-http://mirrors.phx.ovirt.org/repos}"
MIRRORS_CACHE="${MIRRORS_CACHE:-$HOME/mirrors_cache}"
YUM_PATH="/yum/"
MIRRORS_BASE_PREFIX="${MIRRORS_MP_BASE}${YUM_PATH}"
REPOQUERY_HTTP_BASE="${MIRRORS_HTTP_BASE}${YUM_PATH}"

MAX_LOCK_ATTEMPTS=120
LOCK_WAIT_INTERVAL=5
LOCK_BASE="$HOME"

OLD_MD_TO_KEEP=100
MAX_AGE=14

HTTP_SELINUX_TYPE="httpd_sys_content_t"
HTTP_FILE_MODE=644

main() {
    # Launch the command function according to the command given on the
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

    local sync_needed

    mkdir -p "$MIRRORS_CACHE"

    verify_repo_fs "$repo_name" yum

    modify_reposync_conf "$repo_name" "$reposync_conf"

    check_yum_sync_needed \
        "$repo_name" "$repo_archs" "$reposync_conf" sync_needed

    if [[ $sync_needed ]]; then
        mirror_cleanup "$repo_name"
        install_repo_pubkey "$repo_name" "$reposync_conf"
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
    sudo install -o "$USER" -d "$snapshot_mp" "$snapshot_mp/repodata"
    cp -a "$repo_mp/repodata/repomd.xml" "$snapshot_mp/repodata"

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
    local fifo format_fifos=() format_pids=()
    local list_pid

    wait_for_lock "$lock_name"
    echo "Writing latest index files for $repo_type repos"
    # Start formatter processes in the background with named fifos for input
    for format in yaml json py html; do
        fifo="$(mktemp -u)"; mkfifo "$fifo"
        format_fifos+=("$fifo")
        latest_format_$format "$varname" < "$fifo" | \
            atomic_write "${list_file_path}.${format}" \
                "$HTTP_FILE_MODE" "$HTTP_SELINUX_TYPE" &
        format_pids+=($!)
    done
    # write latest repos to all named fifos in parallel. Start it in the BG so
    # we can use the loop below to check return value
    list_latest "$repo_type" | tee "${format_fifos[@]}" > /dev/null &
    list_pid=$!
    # Wait for all background processes, return failure if anyone fails
    for pid in $list_pid ${format_pids[@]}; do
        wait $pid && continue
        # Lines below only run if a process fails:
        wait
        rm -f "${format_fifos[@]}"
        release_lock "$lock_name"
        return 1
    done
    rm -f "${format_fifos[@]}"
    release_lock "$lock_name"
}

verify_repo_fs() {
    local repo_name="${1:?}"
    local repo_type="${2:?}"

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
    # Delete cached yum metadata to ensure we get new metadata from upstream
    # repo
    rm -rf "$MIRRORS_CACHE/$repo_name"
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

install_repo_pubkey() {
    local repo_name="${1:?}"
    local reposync_conf="${2:?}"
    local gpg_key_file

    gpg_key_file="$(
        sed -nr \
            -e '/\['"$repo_name"']/{
                :loop;
                    s#^gpgkey\s*=\s*file://(.*)$#\1#p;
                    n;
                    /^\[.*\]$/q ;
                b loop
            }' \
            "$reposync_conf"
    )"
    if [[ -n $gpg_key_file && -r "$gpg_key_file" ]]; then
        sudo /usr/bin/rpmkeys --import "$gpg_key_file"
    fi
}

get_modulesmd_path() {
    # parse repomd.xml to verify if it has a modules section
    # if found - print out the file location
    # otherwise - print a non-existing path
    local repo_name="${1:?}"
    # the below one-liner does the following actions to extract the file name:
    #   sed     - remove xmlns schema definition to make the next step work
    #   xmllint - prints out the path in the xml file
    #   grep    - only matches symbols allowed in file names (alphanumeric, dash, underscore, dot)
    filename=$(sed -e 's/xmlns=".*"//g' $MIRRORS_CACHE/$repo_name/repomd.xml |\
        xmllint --xpath 'string(/repomd/data[@type="modules"]/location/@href)' - |\
        grep -o [[:alnum:]_.-]*$)
    if [[ -z "$filename" ]]; then
        false
    else
        echo "$MIRRORS_CACHE/$repo_name/$filename"
    fi
}

perform_yum_sync() {
    local repo_name="${1:?}"
    local repo_archs="${2:?}"
    local reposync_conf="${3:?}"
    local repo_mp
    local repo_comps
    local sync_newest_only

    repo_mp="$MIRRORS_MP_BASE/yum/$repo_name/base"
    # Get the modules metadata path. If empty - only sync latest package version
    # Otherwisw sync all packages since modular repos expect multiple versions to exist
    if [ -z "$(get_modulesmd_path $repo_name)" ]; then
        sync_newest_only="--newest-only"
    else
        echo "Module information found, will fetch all package versions"
    fi
    # run reposync
    for arch in $(IFS=,; echo $repo_archs) ; do
        echo "Syncing yum repo $repo_name for arch: $arch"
        run_reposync "$repo_name" "$arch" "$reposync_conf" \
            --downloadcomps --gpgcheck --download-metadata $sync_newest_only
    done
    [[ -f "$repo_mp/comps.xml" ]] && \
        repo_comps=("--groupfile=$repo_mp/comps.xml")
    echo "Generating yum repo metadata for: $repo_name"
    # Repo meta data is created in a way that older repomd.xml files can be
    # copied and moved around
    /bin/createrepo \
        --update \
        --workers=8 \
        --baseurl="$(repo_url $repo_name yum base)" \
        --retain-old-md="$OLD_MD_TO_KEEP" \
        "${repo_comps[@]}" \
        "$repo_mp"
    # inject modules.yaml.gz into newly generated metadata if they exist
    if [[ -f "$(get_modulesmd_path $repo_name)" ]]; then
        echo "Module information found, updating metadata"
        /bin/modifyrepo \
            --mdtype=modules \
            "$(get_modulesmd_path $repo_name)" \
            "$repo_mp/repodata"
    fi
    /usr/sbin/restorecon -R "$repo_mp"
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
        --norepopath \
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

latest_format_py() {
    local varname="${1:-latest_ci_repos}"
    local indention="${2:-}"
    echo "${indention}${varname} = {"
    while read repo_name repo_url; do
        echo "${indention}    '$repo_name': '$repo_url',"
    done
    echo "${indention}}"
}

latest_format_html() {
    echo "<html><head>Latest repo snapshots</head><body>"
    echo "<table border=1>"
    echo "<tr><td><b>Repo Name</b></td><td><b>Repo URL</b></td></tr>"
    while read repo_name repo_url; do
        echo \<tr\>
        echo \<td\>$repo_name\<\/td\> \<td\>$repo_url\<\/td\>
        echo \<\/tr\>
    done
    echo "</table>"
    echo "</body></html>"
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

atomic_write() {
    local final_file="${1:?}"
    local mode="${2:?}"
    local selinux_type="${3:?}"
    local tmp_file

    tmp_file="$(mktemp)" && \
        chcon -t "$selinux_type" "$tmp_file" && \
        chmod "$mode" "$tmp_file" && \
        cat > "$tmp_file" && \
        mv -f "$tmp_file" "$final_file"
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

mirror_cleanup() {
    # Main flow of mirrors cleanup.
    # At first, the snapshots to-be-kept are located, including the hardcoded
    # ones. Then repoquery is being run against each snapshot, and an
    # associative array is being filled with the packages that should be kept.
    # After that, packages which are not referenced by any snapshot are
    # deleted, and lastly old snapshots are deleted as well.
    #
    local repo="${1:?}"
    local pkgs_file="referenced_pkgs.txt"
    recent_snapshots=$(find_recent_snapshots "${MIRRORS_BASE_PREFIX}${repo}")
    hardcoded_snapshot=$(get_repo_slaves_snapshots "$repo")
    if [[ ! "${recent_snapshots}" == *"$hardcoded_snapshot"* ]]; then
        recent_snapshots+="$hardcoded_snapshot"
    fi
    if [ -z "$recent_snapshots" ]; then
        echo "No snapshots were found, skipping cleanup"
        return 0
    fi
    find_referenced_pkgs "$recent_snapshots" "$pkgs_file"
    rm_unreferenced_pkgs "${MIRRORS_BASE_PREFIX}${repo}" "$pkgs_file"
    rm_old_snapshots "${MIRRORS_BASE_PREFIX}${repo}" "$recent_snapshots"
    rm "$pkgs_file"
}

get_repo_slaves_snapshots() {
    # Extracting the hardcoded snapshots from the files
    # under data/slave-repos
    #
    local repo_name="${1:?}"
    git_grep_output=$(git --git-dir=jenkins/.git --work-tree=jenkins/ \
        grep ${REPOQUERY_HTTP_BASE})
    for line in ${git_grep_output}; do
        if [[ $line == *"$repo_name"* ]]; then
            suffix="${line##*yum/}"
            snapshot="${MIRRORS_BASE_PREFIX}${suffix}"
            break
        fi
    done
    echo $'\n'${snapshot}

}

rm_old_snapshots() {
    # Removing the snapshots that were not added to
    # the list of snapshots we want to keep
    #
    local repo_dir="${1:?}"
    local p_recent_snapshots="${2:?}"
    local all_snapshots=($(find ${repo_dir} -mindepth 1 -maxdepth 1 -type d ! \
        \( -name "base" -o -name ".*" \)))
    for snapshot in "${all_snapshots[@]}"; do
        if [[ ! "$p_recent_snapshots" == *"$snapshot"* ]]; then
            rm -rf "$snapshot"
        fi
    done
}

rm_unreferenced_pkgs() {
    # Removing the unreferenced packages.
    # In this function, packages that are not referenced by one or more of the
    # to-be-kept snapshots (and are not found in repoquery's results),
    # would get deleted
    #
    local repo_dir="${1:?}"
    local rpms_file="${2:?}"
    local all_rpms_file="all_pkgs.txt"
    local for_removal="pkgs_for_removal.txt"
    find "${repo_dir}/base" -name "*.rpm" > "$all_rpms_file"
    if grep -F -w -v -f \
    <(cat "$rpms_file") <(cat "$all_rpms_file") > "$for_removal"; then
        cat "$for_removal" | xargs rm
    fi
    rm "$all_rpms_file" "$for_removal"
}

find_recent_snapshots() {
    # Find snapshots that should be kept, according to the following:
    # 1. All snapshots that are younger than ${MAX_AGE} days, should be saved
    # 2. If there are no snapshots matching the first criteria, then
    #    the most recent one is taken.
    #
    local repo="${1:?}"
    local fresh_snapshots=$(find ${repo} -mindepth 1 -maxdepth 1 -type d \
        -mtime -${MAX_AGE} ! \( -name "base" -o -name ".*" \))
    if [[ -z "$fresh_snapshots" ]]; then
        local all_snapshots=($(find ${repo} -mindepth 1 -maxdepth 1 -type d \
            ! \( -name "base" -o -name ".*" \)))
        IFS=$'\n'
        sorted=($(sort <<<"${all_snapshots[*]}"))
        unset IFS
        fresh_snapshots=${sorted[-1]}
    fi

    echo "$fresh_snapshots"
}

find_referenced_pkgs() {
    # Once the should-be-kept snapshots are found,
    # run repoquery against each one of them, to capture all
    # the referenced packages.
    # An associative array is used to make sure there are no
    # duplicate packages in the referenced pakcages array.
    #
    local recent_snapshots_list="${1:?}"
    local ref_pkgs="${2:?}"
    local repoquery_result="repoquery_result.txt"
    local exists=1
    for snapshot in ${recent_snapshots_list}; do
        local snapshot_suffix=${snapshot#$MIRRORS_BASE_PREFIX}
        local repoquery_cmd="repoquery \
            --repofrompath=this,${REPOQUERY_HTTP_BASE}${snapshot_suffix} \
            --repoid=this -a --qf %{relativepath} \
            --archlist=s390x,s390,ppc64le,ppc64,x86_64,i686,noarch"
        $repoquery_cmd >> "$repoquery_result" || continue

    done
    cat "$repoquery_result" | sort -u | xargs -n1 > "$ref_pkgs"
    rm "$repoquery_result"
}

modify_reposync_conf() {
    # Extract data from reposync.conf which is relevant
    # only for the current repo.
    #
    local repo_name="${1:?}"
    local reposync_conf="${2:?}"
    local tmp_file="reposync.tmp"
    awk -v RS='' -v ORS='\n\n' /"main"/ "$reposync_conf" > "$tmp_file"
    awk -v RS='' -v ORS='\n\n' /"$repo_name"/ "$reposync_conf" >> "$tmp_file"
    mv "$tmp_file" "$reposync_conf"
}

main "$@"
