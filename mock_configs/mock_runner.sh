#!/usr/bin/env bash

shopt -s extglob nullglob

SCRIPTS=()
RUN_SHELL="false"
CLEANUP="true"
MOCK_CONF_DIR="/etc/mock"
MOCK="mock"
MOUNT_POINT="$PWD"
FINAL_LOGS_DIR="exported-artifacts/mock_logs"
TRY_PROXY="false"
TRY_MIRRORS=""
PACKAGES=()

# Generate temp dir to be used by any method in mock_runner
# This dir is removed recursively in `finalize`
readonly MR_TEMP_DIR=$(mktemp --tmpdir -d "tmp.mock_runner.XXX")
readonly LOGS_DIR="$(mktemp -d -p "." -t mock_logs.XXXXXXXX)"
trap finalize EXIT


help() {
    cat <<EOH
    Usage: $0 [options] [mock_env [mock_env [...]]]

    Will run the automation/* scripts on mock environments, by default, it will
    run check-patch, check-merged and build-artifacts in that order, on the
    mock environments: ${MOCKS[@]}

    A mock environment must be passed as a ':' separated tuple of:
        ID:MOCK_CONF

    Where the ID is the name used for it on the requirements file (usually in
    the style fc19, el6 or similar) and MOCK_CONF is the mock configuration
    name as passed to the mock -r option (usually, the configuration name
    without extension, for example fedora-23-x86_64)

    Options:
        -h|--help
            Show this help

        -v|--verbose
            Verbose

        -s|--shell chroot
            Prepare the given chroot and start an interactive session but
            don't run any scripts

        -p|--patch-only
            Run/Prepare for the check-patch script only

        -m|--merged-only
            Run/Prepare for the check-merged script only

        -b|--build-only
            Run/Prepare for the build-artifacts script only

        -e|--execute-script path/to/script.sh
            Run/Prepare for the given script

        -n|--no-cleanup
            If set, will not cleanup/scrub the generated chroot at the end,
            allowing you to access it (usually under /var/lib/mock/)

        -P|--try-proxy
            If set, will try to use the proxied config and set the proxy inside
            the mock env

        -M|--try-mirrors MIRRORS_URL
            Try to download a mirror list JSON file from MIRRORS_URL for use
            instead of given yum repos

        -C|--mock-confs-dir
            Directory where the base mock configs are located (default is
            /etc/mock).

        -a|--add-package
            Add the given package to the mock env when installing, can be
            specified more than once

        --secrets-file
            Path to secrets file
            (default is \${xdg_home}/ci_secrets_file.yaml)

    Parameters:
        mock_env
            Name of the mock chroot to use, if none passed all of the defaults
            will be used: ${MOCKS[@]}

            If you pass only one of the elements separated by ':' it will use
            the first one from that contains the passed string

    Example:

    To run the build script on all the chroots:
    > $0 --build-only

    To run only the build artifacts script on fedoras 23 and 24
    > $0 --build-only fc23:fedora-23-x86_64 fc24:fedora-24-x86_64

    To open a shell to debug the check-merged script on el7
    > $0 --merged-only --shell el7:epel-7-x86_64

EOH
    return 0
}


get_data_from_file() {
    local script="${1?}"
    local ftype="${2?}"
    local distro_suffix="${3?}"
    local source_file \
        sfile

    source_file="$(resolve_file "${script}" "$ftype" "$distro_suffix")"
    if [[ "$?" != "0" ]]; then
        return 0
    fi
    grep -v -e '^\#' "$source_file" \
    | grep -v -e '^\s*$'
    return 0
}


extract_proxy_from_mock_conf() {
    local conf_file="${1?}"
    grep -oP '(?<=^proxy=).*$' "$conf_file"
}

extract_repo_url_from_mock_conf() {
    local conf_file="${1?}"
    grep -oP '(?<=^baseurl=).*$' "$conf_file" | head -n1
}

try_proxy() {
    local mock_conf_file="${1?}"
    local proxy="$(extract_proxy_from_mock_conf "$mock_conf_file")"
    local repo_url="$(extract_repo_url_from_mock_conf "$mock_conf_file")"
    http_proxy="$proxy" \
        timeout 5 \
        wget \
            -q \
            "$repo_url" \
            -O - \
    &>/dev/null
    return $?
}

rotate_logs_dir() {
    local logs_dir="${1?}"
    local dst_dir="${logs_dir}.$(date +%Y%m%d)_0"
    local dir_num=0
    [[ -d "$logs_dir" ]] || return 0
    while [[ -e "$dst_dir" ]]; do
        dir_num=$((dir_num + 1))
        dst_dir="${dst_dir%_*}_$dir_num"
    done
    mv "$logs_dir" "$dst_dir"
    return $?
}


makedir() {
    dir_path="${1?}"
    [[ -e "$dir_path" ]] \
    || mkdir -p "$dir_path"
    chgrp mock "$dir_path"
    chmod g+rwx "$dir_path"
}

prepare_chroot() {
    local base_chroot="${1?}"
    local dist_label="${2?}"
    local script="${3?}"
    local cleanup="${4:-false}"
    local base_conf \
        tmp_conf \
        mock_conf \
        mock_chroot \
        mock_dir \
        mock_conf_with_mounts \
        packages

    packages=(
        $(get_data_from_file "$script" req "$dist_label")
        $(get_data_from_file "$script" packages "$dist_label")
        "${PACKAGES[@]}"
    )
    mock_conf="$(
        gen_mock_config "$base_chroot" "$dist_label" "$script" no \
            "${packages[@]}"
    )"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"
    mock_dir="${mock_conf%/*}"
    makedir "$LOGS_DIR/${mock_chroot}.init"
    init_chroot "${mock_chroot}" "${mock_dir}" \
        | tee -a "$LOGS_DIR/${mock_chroot}.init/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    makedir "$LOGS_DIR/${mock_chroot}.populate_mock"
    populate_mock "$mock_chroot" "$mock_dir" \
        | tee -a "$LOGS_DIR/${mock_chroot}.populate_mock/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    mock_conf_with_mounts="$(
        gen_mock_config "$base_chroot" "$dist_label" "$script" "with_mounts" \
            "${packages[@]}"
    )"
    return 0
}


get_base_conf() {
    local conf_dir="${1?}"
    local chroot="${2?}"

    base_conf="$MOCK_CONF_DIR/$chroot.cfg"
    if ! [[ -e "$base_conf" ]]; then
        echo "Unable to find base mock conf $base_conf" >&2
        return 1
    fi
    echo "$base_conf"
    return 0
}


get_temp_conf() {
    local chroot="${1?}"
    local dist_label="${2?}"
    echo "$PWD/mocker-${chroot//:/_}.${dist_label}.cfg"
}


gen_mock_config() {
    local chroot="${1?}"
    local dist_label="${2?}"
    local script="${3?}"
    local with_mounts="${4:-no}"
    local packages=("${@:5}")
    local base_conf \
        tmp_conf \
        mount_opt \
        repo_opt \
        src_mnt \
        dst_mnt \
        repo_name \
        repo_url \
        tmp_chroot \
        proxy \
        repos_md5 \
        last_gen_repo_name \
        chroot_setup_cmd \
        ci_distro \
        ci_stage \
        ci_reposfile \
        upstream_src_folder \
        upstream_dst_folder \
        env_req

    base_conf="$(get_base_conf "$MOCK_CONF_DIR" "$chroot")"
    tmp_conf="$(get_temp_conf "$chroot" "$dist_label")"
    if [[ "$TRY_PROXY" == "true" ]]; then
        proxified_conf="${base_conf%.*}_proxied.cfg"
        if [[ -r "$proxified_conf" ]]; then
            if try_proxy "$proxified_conf"; then
                echo "Using proxified config $proxified_conf" >&2
                base_conf="$proxified_conf"
            else
                proxy="$(extract_proxy_from_mock_conf "$proxified_conf")"
                echo "Failed to contact proxy $proxy, falling back to" \
                    "non-proxied config" \
                    >&2
            fi
        else
            echo "No proxified config file found $proxified_conf," \
                "falling back to non-proxied config" \
                >&2
        fi
    fi
    echo "Generating temporary mock conf ${tmp_conf%.*}" >&2
    cat >"$tmp_conf" <<EOH
import os
import platform

# Needed when running on dnf systems
distro_maj = int(platform.linux_distribution()[1].split('.', 1)[0])
if int(distro_maj) >= 23:
    config_opts['yum_command'] = '/usr/bin/yum-deprecated'

# This alleviates the io of installing the chroot
config_opts["nosync"] = True
# we are not going to build cross-arch packages, we can force it
config_opts["nosync_force"] = True
EOH
    if [[ "$with_mounts" != 'no' ]]; then
        echo "Adding mount points" >&2
        cat >>"$tmp_conf" <<EOH
config_opts["plugin_conf"]["bind_mount_enable"]='True'
config_opts['chroothome'] = '$MOUNT_POINT'
config_opts["plugin_conf"]["bind_mount_opts"]["dirs"]=[
    # Mount the local dir to $MOUNT_POINT
    [os.path.realpath(os.curdir), u'$MOUNT_POINT'],
EOH
        upstream_src_folder="${PWD%/}._upstream"
        upstream_dst_folder="${MOUNT_POINT%/}._upstream"
        if [[ -d ${upstream_src_folder} ]]; then
            echo "['$upstream_src_folder', '$upstream_dst_folder']," >> "$tmp_conf"
        fi

        for mount_opt in $(get_data_from_file "$script" mounts "$dist_label"); do
            [[ "$mount_opt" == "" ]] && continue
            if [[ "$mount_opt" =~ ^([^:]*)(:(.*))?$ ]]; then
                src_mnt="${BASH_REMATCH[1]}"
                dst_mnt="${BASH_REMATCH[3]:-$src_mnt}"
                if [[ ! -e "$src_mnt" ]]; then
                    echo "Creating destination folder before mounting"
                    mkdir -p $src_mnt
                fi
            fi
            echo "['$src_mnt', '$dst_mnt']," >> "$tmp_conf"
        done
        echo "]" >> "$tmp_conf"
    else
        echo "Skipping mount points" >&2
    fi

    repos=($(get_data_from_file "$script" repos "$dist_label"))
    # if we use custom repos, we don't want to mess with existing cached
    # chroots so we change the root param to have that info too
    if [[ "$repos" != "" || "$packages" != "" ]]; then
        repos_md5=($(echo "${repos[@]}" "${packages[@]}" | sort | md5sum ))
        tmp_chroot="${chroot}-${repos_md5[0]}"
    else
        tmp_chroot="$chroot"
    fi
    echo "Using chroot cache = /var/cache/mock/${tmp_chroot}" >&2
    echo "Using chroot dir = /var/lib/mock/${tmp_chroot}-$$" >&2
    echo "config_opts['root'] = '${tmp_chroot}'" >> "$tmp_conf"
    echo "config_opts['unique-ext'] = '$$'" >> "$tmp_conf"
    sed -n \
        -e "/config_opts\[.root.\]/d" \
        -e "1,/\[[\"\']yum.conf[\"\']\]/p" \
        "$base_conf" >> "$tmp_conf"

    last_gen_repo_name=0
    for repo_opt in "${repos[@]}"; do
        [[ "$repo_opt" == "" ]] && continue
        if [[ "$repo_opt" =~ ^([^,]*)(,(.*))?$ ]]; then
            repo_name="${BASH_REMATCH[1]}"
            repo_url="${BASH_REMATCH[3]}"
        fi
        if [[ "$repo_url" == "" ]]; then
            repo_url="$repo_name"
            repo_name="repo-$last_gen_repo_name"
            last_gen_repo_name=$(($last_gen_repo_name + 1))
        fi
        # this is here because for the init we can't use /etc/yum/vars or
        # something, as it's not there yet
        repo_url="${repo_url//\$distro/$dist_label}"
        echo "Adding repo $repo_name -> $repo_url" >&2
        cat >>"$tmp_conf" <<EOR
[$repo_name]
enabled=1
gpgcheck=0
baseurl=$repo_url
name="Custom $repo_name"

EOR
    done
    sed -n -e '/\[main\]/,$p' "$base_conf" >> "$tmp_conf"
    if [[ "$packages" != "" ]]; then
        cat  >> "$tmp_conf" <<EOC
config_opts['chroot_setup_cmd'] += ' ${packages[@]}'
EOC
    fi
    [[ "$TRY_MIRRORS" ]] && gen_mirrors_conf "$TRY_MIRRORS" >> "$tmp_conf"
    gen_ci_env_info_conf "$script" "$dist_label" >> "$tmp_conf"
    env_req=($(resolve_file "$script" "environment.yaml" "$dist_label"))
    [[ -e "$env_req" ]] && \
        gen_environ_conf "$env_req" >> "$tmp_conf"
    touch --date "yesterday" "$tmp_conf"
    echo "$tmp_conf"
    return 0
}


gen_mirrors_conf() {
    local mirrors_url="${1?}"
    local scripts_path
    scripts_path="$(dirname "$(which "$0")")/../scripts"

    echo "import sys"
    echo "sys.path.append('$scripts_path')"
    echo "try:"
    echo "    from mirror_client import mirrors_from_uri, \\"
    echo "        inject_yum_mirrors_str"
    echo "    config_opts['yum.conf'] = inject_yum_mirrors_str("
    echo "        mirrors_from_uri('$mirrors_url'),"
    echo "        config_opts['yum.conf'],"
    echo "    )"
    echo "finally:"
    echo "    sys.path.pop()"
}


gen_environ_conf() {
    local user_requests="${1:?}"
    local user_requests_path="$(realpath "$user_requests")"
    local base_dir="$(dirname "$(which "$0")")/.."
    local scripts_path="${base_dir}/scripts"
    local gdbm_db=$(mktemp --tmpdir="$MR_TEMP_DIR" "gdbm_db.XXX")

    # Generate GDBM database from `$env`
    python "${scripts_path}/gdbm_db_resolvers.py" "${gdbm_db}"

    echo "from os.path import isfile"
    echo "if isfile('$gdbm_db'):"
    echo "    import sys"
    echo "    from yaml import safe_load"
    echo "    sys.path.append('$base_dir')"
    echo "    try:"
    echo "        from scripts.ci_env_client import ("
    echo "            load_providers, gen_env_vars_from_requests"
    echo "        )"
    echo "        providers = load_providers("
    echo "            '$gdbm_db', ${SECRETS_FILE:+'$SECRETS_FILE'}"
    echo "        )"
    echo "        with open('${user_requests_path}', 'r') as rf:"
    echo "            requests = safe_load(rf)"
    echo "        config_opts['environment'].update("
    echo "            gen_env_vars_from_requests(requests, providers)"
    echo "        )"
    echo "    finally:"
    echo "        sys.path.pop()"
}


gen_ci_env_info_conf() {
    local path_to_script="${1:?}"
    local ci_distro="${2:?}"
    local script_name="${path_to_script##*/}"
    local ci_stage="${script_name%%.*}"
    local ci_reposfiles

    ci_reposfiles=($(resolve_multiple_files "$path_to_script" "yumrepos" "$dist_label"))

    echo "config_opts['environment']['STD_CI_DISTRO'] = \"$ci_distro\""
    echo "config_opts['environment']['STD_CI_STAGE'] = \"$ci_stage\""
    # Since 'resolve_multiple_files' returns an array of matches, we need only
    # the first match.
    echo "config_opts['environment']['STD_CI_YUMREPOS']=\"${ci_reposfiles[0]}\""
}


init_chroot() {
    local chroot="${1?}"
    local conf_dir="${2?}"
    local start \
        end
    start="$(date +%s)"
    echo "========== Initializing chroot"
    cat <<EOC
    $MOCK \\
        --old-chroot \\
        --configdir="$conf_dir" \\
        --root="$chroot" \\
        --resultdir="$LOGS_DIR/${chroot}.init" \\
        --init
EOC
    $MOCK \
        --old-chroot \
        --configdir="$conf_dir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/${chroot}.init" \
        --init
    res=$?
    end="$(date +%s)"
    echo "Init took $((end - start)) seconds"
    echo "============================"
    return $res
}


populate_mock() {
    local chroot="${1?}"
    local conf_dir="${2?}"
    local start \
        end \
        src_mnt \
        dst_mnt \
        file_mount_points \
        file_mount_point_dirs
    start="$(date +%s)"
    echo "========== Populating mock environment"
    file_mount_points=()
    file_mount_point_dirs=()
    for mount_opt in $(get_data_from_file "$script" mounts "$dist_label"); do
        [[ "$mount_opt" == "" ]] && continue
        if [[ "$mount_opt" =~ ^([^:]*)(:(.*))?$ ]]; then
            src_mnt="${BASH_REMATCH[1]}"
            dst_mnt="${BASH_REMATCH[3]:-$src_mnt}"
            if [[ -e "$src_mnt" && ! -d "$src_mnt" ]]; then
                echo "Will create mount point for file: $src_mnt" >&2
                file_mount_points+=("'$dst_mnt'")
                file_mount_point_dirs+=("'$(dirname $dst_mnt)'")
            fi
        fi
    done
    $MOCK \
        --old-chroot \
        --configdir="$conf_dir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/${chroot}.populate_mock" \
        --shell <<EOC
            set -e
            logdir="$MOUNT_POINT/$LOGS_DIR/${chroot}.populate_mock"
            [[ -d \$logdir ]] \\
            || mkdir -p "\$logdir"
            # Fix that allows using yum inside the chroot on dnf enabled
            # distros
            [[ -d /etc/dnf ]] && [[ -e /etc/yum/yum.conf ]] && cat /etc/yum/yum.conf > /etc/dnf/dnf.conf
            rm -Rf /var/lib/rpm/__* &>\$logdir/rpmbuild.log
            rpm --rebuilddb &>>\$logdir/rpmbuild.log
            [[ -z "${file_mount_point_dirs[@]}" ]] || mkdir -p ${file_mount_point_dirs[@]}
            [[ -z "${file_mount_points[@]}" ]] || touch ${file_mount_points[@]}
EOC
    res=$?
    end="$(date +%s)"
    echo "Populating mock took $((end - start)) seconds"
    echo "================================"
    return $res
}


scrub_chroot() {
    local chroot="${1?}"
    local confdir="${2?}"
    local start \
        end \
        res
    start="$(date +%s)"
    echo "========== Scrubbing chroot"
    cat <<EOC
    $MOCK \\
        --old-chroot \\
        --configdir="$confdir" \\
        --root="$chroot" \\
        --resultdir="$LOGS_DIR/${chroot}.scrub" \\
        --scrub=chroot
EOC
    $MOCK \
        --old-chroot \
        --configdir="$confdir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/${chroot}.scrub" \
        --scrub=chroot
    res=$?
    end="$(date +%s)"
    echo "Scrub chroot took $((end - start)) seconds"
    echo "============================"
    return $res
}


inject_ci_mirrors() {
    local path_to_script="${1?}"
    local mock_cfg_path="${2?}"
    local target_file_suffix="${3:-yumrepos}"
    local target_yum_cfgs \
        mock_cfg \
        mock_logs_dir \
        scripts_path \
        distro

    scripts_path="$(dirname "$(which "$0")")/../scripts"
    mock_cfg="${mock_cfg_path##*/}"
    mock_logs_dir="${mock_cfg%.*}"
    distro="${mock_logs_dir##*.}"

    target_yum_cfgs=($(
        resolve_multiple_files \
            "$path_to_script" \
            "$target_file_suffix" \
            "$distro"
    ))
    [[ ${#target_yum_cfgs[@]} -eq 0 ]] && return 0
    "${scripts_path}"/mirror_client.py "$TRY_MIRRORS" "${target_yum_cfgs[@]}"

    makedir "$LOGS_DIR/${mock_logs_dir}.yumrepos"
    for file in "${target_yum_cfgs[@]}"; do
        cp "$file" "$LOGS_DIR/${mock_logs_dir}.yumrepos/${file##*/}"
    done
}


resolve_multiple_files() {
    local path_to_script="${1?}"
    local suffix="${2?}"
    local distro="${3?}"
    local path_to_script_no_ext="${path_to_script%%.*}"
    local matches

    matches=($(
        printf "%s\n" "${path_to_script_no_ext}"?(.*)".${suffix}.${distro}" | \
            sort -r
        printf "%s\n" "${path_to_script_no_ext}"?(.*)".${suffix}" | sort -r
    ))
    echo "${matches[@]}"
}


resolve_file() {
    local basename="${1?}"
    local suffix="${2?}"
    local distro="${3?}"

    basename="${basename%.sh}.${suffix}"
    found="false"
    for pfile in "${basename}.$distro" "$basename"; do
        if ! [[ -f "$pfile" ]]; then
            continue
        fi
        found="true"
        break
    done
    if [[ "$found" == "false" ]]; then
        echo "WARN: Unable to find $suffix file" \
             "$basename or ${basename}.$distro, skipping $suffix" >&2
        return 1
    fi
    echo "$pfile"
    return 0
}


resolve_mock() {
    local mock="${1?}"
    local mock_dir="${2?}"
    local full_mock \
        mocks
    if [[ "${mock}" =~ ^.+:.+$ ]]; then
        echo "$mock"
        return 0
    fi

    mocks=($(cat /dev/null "${mock_dir}"/*.mrmap))
    for full_mock in "${mocks[@]}"; do
        if [[ "$full_mock" =~ $mock ]]; then
            echo "$full_mock"
            return 0
        fi
    done
    return 1
}


run_shell() {
    local mock_env="${1?}"
    local script="${2:-interactive}"
    local cleanup="${3:-false}"
    local distro_id \
        mock_conf \
        mock_dir \
        mock_chroot \
        base_chroot \
        mock_enable_network

    base_chroot="${mock_env#*:}"
    distro_id="${mock_env%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$base_chroot" ]]; then
        echo "ERROR: invalid mock environment passed: $mock_env" >&2
        return 1
    fi
    mock_conf="$(get_temp_conf "$base_chroot" "$distro_id")" \
    || return 1

    [[ -n "$TRY_MIRRORS" ]] && [[ -n "$script" ]] && \
        inject_ci_mirrors "$script" "$mock_conf"

    mock_dir="${mock_conf%/*}"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"

    # If mock supports the --enable-network option, we need to use it
    mock_enable_network=($(mock --help 2>&1 | grep -o -- --enable-network))

    echo "Using base mock conf $MOCK_CONF_DIR/${base_chroot}.cfg" >&2
    prepare_chroot "$base_chroot" "$distro_id" "$script" \
    || return 1
    echo "INFO The working directory is mounted at \$HOME, you can just run 'cd' to get there"
    cat <<EOC
    $MOCK \\
        --old-chroot \\
        --configdir="$mock_dir" \\
        --root="$mock_chroot" \\
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \\
        "${mock_enable_network[@]}" \\
        --shell
EOC
    $MOCK \
        --old-chroot \
        --configdir="$mock_dir" \
        --root="$mock_chroot" \
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \
        "${mock_enable_network[@]}" \
        --shell
    res=$?

    if [[ "$cleanup" == "true" ]]; then
        scrub_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    return $res
}


run_script() {
    local mock_conf="${1?}"
    local mock_env="${2?}"
    local script="${3?}"
    local base_chroot \
        configdir \
        custom_conf \
        distro_id \
        mock_enable_network

    base_chroot="${mock_env#*:}"
    distro_id="${mock_env%%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$base_chroot" ]]; then
        echo "ERROR: invalid mock environment passed: $mock_env" >&2
        return 1
    fi
    mock_conf="$(get_temp_conf "$base_chroot" "$distro_id")" \
    || return 1

    [[ -n "$TRY_MIRRORS" ]] && inject_ci_mirrors "$script" "$mock_conf"
    mock_dir="${mock_conf%/*}"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"

    # If mock supports the --enable-network option, we need to use it
    mock_enable_network=($(mock --help 2>&1 | grep -o -- --enable-network))

    echo "Using base mock conf $MOCK_CONF_DIR/${base_chroot}.cfg" >&2
    prepare_chroot "$base_chroot" "${mock_env%%:*}" "$script" \
    || return 1
    cat <<EOC
    $MOCK \\
        --old-chroot \\
        --root="${mock_chroot}" \\
        --configdir="$mock_dir" \\
        --no-clean \\
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \\
        "${mock_enable_network[@]}" \\
        --shell <<EOS
            set -e
            # Remove all system repos from the environment to ensure we're not
            # using any pakcge repos we didn't specify explicitly
            rpm -qf /etc/system-release \
                | xargs -r rpm -ql fedora-repos{,-rawhide} epel-release \
                | grep '/etc/yum\.repos\.d/.*\.repo' | xargs -r rm -fv
            logdir="$MOUNT_POINT/$LOGS_DIR/${mock_chroot}.${script##*/}"
            [[ -d "\\\$logdir" ]] \\
            || mkdir -p "\\\$logdir"
            export HOME=$MOUNT_POINT
            cd
            chmod +x $script
            runner_GID="$(id -g)"
            runner_GROUP="$(id -n -g)"
            # mock group is called mockbuild inside the chroot
            if [[ \\\$runner_GROUP == "mock" ]]; then
                runner_GROUP=mockbuild
            fi
            if ! getent group "\\\$runner_GID" &>/dev/null; then
                groupadd \\
                    --gid "\\\$runner_GID" \\
                    "\\\$runner_GROUP"
            fi
            start="\\\$(date +%s)"
            res=0
            echo "========== Running the shellscript $script" \\
                | tee -a \\\$logdir/${script##*/}.log
            ./$script 2>&1 | tee -a \\\$logdir/${script##*/}.log \\
            || res=\\\${PIPESTATUS[0]}
            end="\\\$(date +%s)"
            echo "Took \\\$((end - start)) seconds" \\
            | tee -a \\\$logdir/${script##*/}.log
            echo "===================================" \\
            | tee -a \\\$logdir/${script##*/}.log
            if [[ "\\\$(find . -uid 0 -print -quit)" != '' ]]; then
                chown -R "\$UID:\\\$runner_GID" .
            fi
            exit \\\$res
EOS
EOC
    $MOCK \
        --old-chroot \
        --root="${mock_chroot}" \
        --configdir="$mock_dir" \
        --no-clean \
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \
        "${mock_enable_network[@]}" \
        --shell <<EOS
            set -e
            # Remove all system repos from the environment to ensure we're not
            # using any pakcge repos we didn't specify explicitly
            rpm -qf /etc/system-release \
                | xargs -r rpm -ql fedora-repos{,-rawhide} epel-release \
                | grep '/etc/yum\.repos\.d/.*\.repo' | xargs -r rm -fv
            logdir="$MOUNT_POINT/$LOGS_DIR/${mock_chroot}.${script##*/}"
            [[ -d "\$logdir" ]] \\
            || mkdir -p "\$logdir"
            export HOME=$MOUNT_POINT
            cd
            chmod +x $script
            runner_GID="$(id -g)"
            runner_GROUP="$(id -n -g)"
            # mock group is called mockbuild inside the chroot
            if [[ \$runner_GROUP == "mock" ]]; then
                runner_GROUP=mockbuild
            fi
            if ! getent group "\$runner_GID" &>/dev/null; then
                groupadd \
                    --gid "\$runner_GID" \
                    "\$runner_GROUP"
            fi
            start="\$(date +%s)"
            res=0
            echo "========== Running the shellscript $script" \
                | tee -a \$logdir/${script##*/}.log
            # It turns out that on some scripts if the following is not all
            # in the same line, it never runs and returns with 0 (giving false
            # positives)
            ./$script 2>&1 | tee -a \$logdir/${script##*/}.log \
            && res=\${PIPESTATUS[0]}; \
            end="\$(date +%s)"; \
            echo "Took \$((end - start)) seconds" \
            | tee -a \$logdir/${script##*/}.log; \
            echo "===================================" \
            | tee -a \$logdir/${script##*/}.log; \
            if [[ "\$(find . -uid 0 -print -quit)" != '' ]]; then \
                chown -R "$UID:\$runner_GID" . ;\
            fi; \
            exit \$res
EOS
    return $?
}


# Runs a set of scripts each on its own chroot
run_scripts() {
    local mock_env="${1?}"
    local cleanup="${2?}"
    local scripts=("${@:3}")
    local distro_id \
        mock_conf \
        packages_file \
        packages \
        script \
        start \
        end \
        res \
        exec_script

    mock_conf="$(get_base_conf "$MOCK_CONF_DIR" "${mock_env#*:}")" \
    || return 1
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"
    mock_dir="${mock_conf%/*}"
    distro_id="${mock_env%%:*}"
    for script in "${scripts[@]}"; do
        exec_script="$(resolve_file "$script" "sh" "$distro_id")"
        [[ -r "$exec_script" ]] \
        || {
            echo "ERROR: Script $exec_script does not exist or is not readable."
            return 1
        }
        start="$(date +%s)"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@ $(date) Running chroot for script: $exec_script"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        run_script "$mock_conf" "$mock_env" "$exec_script"
        res=$?
        end="$(date +%s)"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@ $(date) $exec_script chroot finished"
        echo "@@      took $((end - start)) seconds"
        echo "@@      rc = $res"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        if [[ "$res" != "0" ]]; then
            break
        fi
    done
    if [[ "$cleanup" == "true" ]]; then
        scrub_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    return $res
}


finalize() {
    rotate_logs_dir "$PWD/$FINAL_LOGS_DIR"
    makedir "$FINAL_LOGS_DIR"
    echo "Collecting mock logs"
    mv -v "$LOGS_DIR"/* "$FINAL_LOGS_DIR"
    rmdir "$LOGS_DIR"
    rm -rf "$MR_TEMP_DIR"
    echo "##########################################################"
}


#### MAIN

if ! [[ "$0" =~ ^.*/bash$ ]]; then

    long_opts="shell:"
    short_opts="s:"

    long_opts+=",patch-only"
    short_opts+=",p"

    long_opts+=",merged-only"
    short_opts+=",m"

    long_opts+=",build-only"
    short_opts+=",b"

    long_opts+=",help"
    short_opts+=",h"

    long_opts+=",execute-script:"
    short_opts+=",e:"

    long_opts+=",verbose"
    short_opts+=",v"

    long_opts+=",no-cleanup"
    short_opts+=",n"

    long_opts+=",mock-confs-dir:"
    short_opts+=",C:"

    long_opts+=",try-proxy"
    short_opts+=",P"

    long_opts+=",try-mirrors:"
    short_opts+=",M:"

    long_opts+=",add-package:"
    short_opts+=",a:"

    long_opts+=",secrets-file:"

    # Parse options
    args="$( \
        getopt \
            -o "$short_opts" \
            -l "$long_opts" \
            -n "$0" \
            -- "$@" \
    )"
    # Bad arguments
    if [[ $? -ne 0 ]]; then
        help
        exit 1
    fi
    eval set -- "$args"
    while true; do
        case "$1" in
            -h|--help)
                help
                exit 0
            ;;
            -v|--verbose)
                shift
                set -x
            ;;
            -s|--shell)
                mock_env_regexp="$2"
                shift 2
                RUN_SHELL="true"
            ;;
            -p|--patch-only)
                shift
                SCRIPTS=( automation/check-patch.sh )
            ;;
            -m|--merged-only)
                shift
                SCRIPTS=( automation/check-merged.sh )
            ;;
            -b|--build-only)
                shift
                SCRIPTS=( automation/build-artifacts.sh )
            ;;
            -e|--execute-script)
                SCRIPTS=( "$2" )
                shift 2
            ;;
            -n|--no-cleanup)
                shift
                CLEANUP="false"
            ;;
            -C|--mock-confs-dir)
                MOCK_CONF_DIR="$2"
                shift 2
            ;;
            -P|--try-proxy)
                TRY_PROXY="true"
                shift
            ;;
            -P|--try-mirrors)
                TRY_MIRRORS="$2"
                shift 2
            ;;
            -a|--add-package)
                PACKAGES+=("$2")
                shift 2
            ;;
            --secrets-file)
                SECRETS_FILE="$2"
                shift 2
            ;;
            --)
                # end of options
                shift
                break
            ;;
        esac
    done

    if [ ! -z "$mock_env_regexp" ]; then
        mock_env="$(resolve_mock "$mock_env_regexp" "$MOCK_CONF_DIR")" \
        || {
            echo "Unable to find mock env $mock_env" >&2
            exit 1
        }
    fi


    if [[ "$RUN_SHELL" == "true" ]]; then
        run_shell \
            "${mock_env:?}" \
            "${SCRIPTS[0]}" \
            "$CLEANUP"
        res=$?
    else
        if [[ -n "$1" ]]; then
            mocks=("$@")
        else
            mocks=("${MOCKS[@]}")
        fi
        for mock_env in "${mocks[@]}"; do
            full_mock_env="$(resolve_mock "$mock_env" "$MOCK_CONF_DIR")" \
            || {
                echo "Unable to find mock env $mock_env" >&2
                exit 1
            }
            start="$(date +%s)"
            echo "##########################################################"
            echo "##########################################################"
            echo "## $(date) Running env: $full_mock_env"
            echo "##########################################################"
            run_scripts "$full_mock_env" "$CLEANUP" "${SCRIPTS[@]}"
            res="$?"
            end="$(date +%s)"
            echo "##########################################################"
            echo "## $(date) Finished env: $full_mock_env"
            echo "##      took $((end - start)) seconds"
            echo "##      rc = $res"
            echo "##########################################################"
            if [[ "$res" != "0" ]]; then
                lastlog="$( \
                    find "$LOGS_DIR" -iname \*.log \
                    | xargs ls -lt \
                    | head -n1\
                    | awk '{print $9}' \
                )"
                if [[ -r "$lastlog" ]]; then
                    echo '##! ERROR vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv'
                    echo '##! Last 20 log entries: '"$lastlog"
                    echo '##!'
                    tail -n 20 "$lastlog"
                    echo '##!'
                    echo '##! ERROR ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'
                else
                    echo "No log files found, check command output"
                fi
                echo '##!########################################################'
            else
                echo "## FINISHED SUCCESSFULLY"
                echo "##########################################################"
                res=0
            fi
        done
    fi
    exit $res
fi
