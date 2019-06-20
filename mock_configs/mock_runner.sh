#!/usr/bin/env bash

shopt -s extglob nullglob

DEFAULT_SCRIPT=automation/build-artifacts.sh
RUN_SHELL="false"
CLEANUP="true"
MOCK_CONF_DIR="$(dirname "$(command -v "$0")")"
MOCK="mock"
MOUNT_POINT="$PWD"
FINAL_LOGS_DIR="exported-artifacts/mock_logs"
TRY_PROXY="false"
TRY_MIRRORS=""
PACKAGES=()
DEFAULT_MOCK_ENV=el7

# Environment variables set by authentication systems, that point to files that
# need to be made available inside the mock environment to enable authentication
# inheritance
readonly AUTH_ENV_VARS=(KRB5CCNAME SSH_AUTH_SOCK)
# Hardwired env vars we always copy into the mock env
readonly HW_ENV_VARS=(
    GIT_COMMITTER_{NAME,EMAIL} "${AUTH_ENV_VARS[@]}" SSH_AUTH_USER
    BUILD_{NUMBER,ID,DISPLAY_NAME,TAG,URL} JOB_{{,BASE_}NAME,URL}
    NODE_{NAME,LABELS} WORKSPACE JENKINS_URL
)
# Directories and files we always mount into the mock env
readonly HW_MNTS=(/etc/krb5.conf{,.d} /var/lib/sss/pubconf/krb5.include.d)
# Directories and files we mount from the CI source repo into the chroot
# (specified as 'src:dst' pairs where src is relative to the repo and
# dst is in the chroot
readonly CODE_MNTS=(
    scripts/ci_toolbox:/var/lib/ci_toolbox
    data/ssh_files:/var/lib/ci_ssh_files
    scripts/mock_runner_profile.sh:/etc/profile.d/mock_runner_profile.sh
)

# Generate temp dir to be used by any method in mock_runner
# This dir is removed recursively in `finalize`
readonly MR_TEMP_DIR=$(mktemp --tmpdir -d "tmp.mock_runner.XXX")
readonly LOGS_DIR="$(mktemp --tmpdir -d -t mock_logs.XXXXXXXX)"
trap finalize EXIT


help() {
    cat <<EOH
    Usage: $0 [options] [mock_env]

    Will run the automation/* script specified in options on the mock
    environments, given by the command line argument. By default, it will
    run '$DEFAULT_SCRIPT' on the '$DEFAULT_MOCK_ENV' environment.

    A mock environment can be given as a shorthand name like 'el7' or 'fc27' or
    with a longer epression of the form 'ID:MOCK_CONF' where ID is the shorthand
    name and MOCK_CONF is the name of a mock configuration file used to setup
    the environment.

    A glob pattern can also be used to search against the known mock
    environments.

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
            the directoy where this script resides).

        -a|--add-package
            Add the given package to the mock env when installing, can be
            specified more than once

        -t|--timeout-duration
            Set timeout duration to the running script.
            DURATION is a floating point number with an optional suffix:
                's' for seconds (the default),
                'm' for minutes,
                'h' for hours or
                'd' for days.

        --secrets-file
            Path to secrets file
            (default is \${xdg_home}/ci_secrets_file.yaml)

    Example:

    To run the build script on the default environment:
    > $0 --build-only

    To run only the build artifacts script on fedora 27
    > $0 --build-only fc27

    To open a shell to debug the check-merged script on el7
    > $0 --merged-only --shell el7

EOH
    return 0
}


get_data_from_file() {
    local script="${1?}"
    local ftype="${2?}"
    local distro_suffix="${3?}"
    local source_file

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
    local proxy repo_url
    proxy="$(extract_proxy_from_mock_conf "$mock_conf_file")"
    repo_url="$(extract_repo_url_from_mock_conf "$mock_conf_file")"
    http_proxy="$proxy" \
        timeout 5 \
        curl \
            --silent \
            --fail \
            "$repo_url" \
    &>/dev/null
    return $?
}

rotate_logs_dir() {
    local logs_dir="${1?}"
    local dst_dir dir_num=0
    dst_dir="${logs_dir}.$(date +%Y%m%d)_0"
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
    makedir "$LOGS_DIR/init"
    init_chroot "${mock_chroot}" "${mock_dir}" 2>&1 \
        | tee -a "$LOGS_DIR/init/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    gen_mock_config "$base_chroot" "$dist_label" "$script" "user" \
        "${packages[@]}"
    return 0
}


get_base_conf() {
    local conf_dir="${1?}"
    local chroot="${2?}"

    base_conf="$conf_dir/$chroot.cfg"
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
        repo_opt \
        repo_name \
        repo_url \
        tmp_chroot \
        proxy \
        repos_md5 \
        last_gen_repo_name \
        ci_distro \
        ci_stage

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

# This alleviates the io of installing the chroot
config_opts["nosync"] = True
# we are not going to build cross-arch packages, we can force it
config_opts["nosync_force"] = True
EOH
    if [[ "$with_mounts" == 'user' ]]; then
        echo "Adding mount points" >&2
        get_mount_conf "$dist_label" "$script" >> "$tmp_conf"
    else
        echo "Skipping mount points" >&2
    fi

    repos=($(get_data_from_file "$script" repos "$dist_label"))
    # if we use custom repos, we don't want to mess with existing cached
    # chroots so we change the root param to have that info too
    if [[ "${#repos[@]}" -ne 0 || "${#packages[@]}" -ne 0 ]]; then
        repos_md5=($(echo "${repos[@]}" "${packages[@]}" | sort | md5sum ))
        tmp_chroot="${chroot}-${repos_md5[0]}"
    else
        tmp_chroot="$chroot"
    fi
    echo "Using chroot cache = /var/cache/mock/${tmp_chroot}" >&2
    echo "Using chroot dir = /var/lib/mock/${tmp_chroot}-$$" >&2
    {
        echo "config_opts['root'] = '${tmp_chroot}'"
        echo "config_opts['unique-ext'] = '$$'"
        sed -n \
            -e "/config_opts\[.root.\]/d" \
            -e "1,/\[[\"\']yum.conf[\"\']\]/p" \
            "$base_conf"
    } >> "$tmp_conf"

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
            last_gen_repo_name=$((last_gen_repo_name + 1))
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
    if [[ "${#packages[@]}" -ne 0 ]]; then
        cat  >> "$tmp_conf" <<EOC
config_opts['chroot_setup_cmd'] += ' ${packages[@]}'
EOC
    fi
    [[ "$TRY_MIRRORS" ]] && gen_mirrors_conf "$TRY_MIRRORS" >> "$tmp_conf"
    if [[ "$with_mounts" == 'user' ]]; then
        echo "Adding environment variables" >&2
        gen_environ_conf "$dist_label" "$script" >> "$tmp_conf"
    else
        echo "Skipping environment variables" >&2
    fi
    touch --date "yesterday" "$tmp_conf"
    echo "$tmp_conf"
    return 0
}

prepare_code_mnt() {
    local code_dir="${1:?}"
    local code_dir_name="${code_dir##*/}"
    local code_dir_orig="$MOCK_CONF_DIR/../$code_dir"
    local code_dir_copy
    code_dir_copy="$(mktemp -u "${MR_TEMP_DIR}/${code_dir_name}.XXXXX")"
    cp -rpL "$code_dir_orig" "$code_dir_copy"
    echo "$code_dir_copy"
}

get_mount_conf() {
    local dist_label="${1?}"
    local script="${2?}"

    local upstream_src_folder
    local upstream_dst_folder
    local mount_opt
    local src_mnt
    local dst_mnt

    echo "config_opts['plugin_conf']['bind_mount_enable']=True"
    echo "config_opts['chroothome'] = '$MOUNT_POINT'"
    echo "config_opts['plugin_conf']['bind_mount_opts']['dirs']=["
    echo "    # Mount the local dir to $MOUNT_POINT"
    echo "    [os.path.realpath(os.curdir), u'$MOUNT_POINT'],"

    # Mount code mounts
    for mount_opt in "${CODE_MNTS[@]}"; do
        src_mnt="${mount_opt%%:*}"
        dst_mnt="${mount_opt##*:}"
        echo "    [u'$(prepare_code_mnt "$src_mnt")', u'$dst_mnt'],"
    done
    # Mount hardwired mounts if they exist on the host
    for mount_opt in "${HW_MNTS[@]}"; do
        src_mnt="${mount_opt%%:*}"
        dst_mnt="${mount_opt##*:}"
        # shellcheck disable=2015
        [[ $src_mnt ]] && [[ -e $src_mnt ]] || continue
        echo "    [u'$src_mnt', u'$dst_mnt'],"
    done

    # Mount files indicated by authentication environment variables
    local evar_name evar_value
    for evar_name in "${AUTH_ENV_VARS[@]}"; do
        evar_value="${!evar_name}"
        # some env var values contain a prefix with ':' so strip it away to get
        # the actual path they point to
        src_mnt="${evar_value##*:}"
        # mount the path pointed be variable X in /tmp/X
        dst_mnt="/tmp/$evar_name"
        # skip mounting if the variable isn't defined or the pointed file does
        # not exist
        # shellcheck disable=2015
        [[ $evar_value ]] && [[ -e $src_mnt ]] || continue
        echo "    ['$src_mnt', '$dst_mnt'],"
        # make the var point to the internal mount point inside the mock env
        export "$evar_name=$dst_mnt"
    done

    upstream_src_folder="${PWD%/}._upstream"
    upstream_dst_folder="${MOUNT_POINT%/}._upstream"
    if [[ -d ${upstream_src_folder} ]]; then
        echo "['$upstream_src_folder', '$upstream_dst_folder'],"
    fi

    for mount_opt in $(get_data_from_file "$script" mounts "$dist_label"); do
        [[ "$mount_opt" == "" ]] && continue
        if [[ "$mount_opt" =~ ^([^:]*)(:(.*))?$ ]]; then
            src_mnt="${BASH_REMATCH[1]}"
            dst_mnt="${BASH_REMATCH[3]:-$src_mnt}"
            if [[ ! -e "$src_mnt" ]]; then
                mkdir -p "$src_mnt"
            fi
        fi
        echo "['$src_mnt', '$dst_mnt'],"
    done
    echo "]"
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
    echo "        locals().get('none_value', 'None'),"
    echo "    )"
    echo "finally:"
    echo "    sys.path.pop()"
}


gen_environ_conf() {
    local dist_label="${1?}"
    local script="${2?}"

    local base_dir scripts_path gdbm_db
    base_dir="$(dirname "$(which "$0")")/.."
    scripts_path="${base_dir}/scripts"
    gdbm_db=$(mktemp --tmpdir="$MR_TEMP_DIR" "gdbm_db.XXX")

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
    # shellcheck disable=2016
    echo "            '$gdbm_db', ${SECRETS_FILE:+'$SECRETS_FILE'}"
    echo "        )"

    local user_requests
    user_requests="$(resolve_file "$script" "environment.yaml" "$dist_label")"
    if [[ $user_requests ]]; then
        local user_requests_path
        user_requests_path="$(realpath "$user_requests")"
        echo "        with open('${user_requests_path}', 'r') as rf:"
        echo "            requests = safe_load(rf)"
        echo "        config_opts['environment'].update("
        echo "            gen_env_vars_from_requests(requests, providers)"
        echo "        )"
    fi

    echo "        _hw_vars = '${HW_ENV_VARS[*]}'.split()"
    echo "        _hw_requests = [{"
    echo "            'name': var,"
    echo "            'valueFrom': {'runtimeEnv': var},"
    echo "            'optional': True,"
    echo "        } for var in _hw_vars]"
    echo "        config_opts['environment'].update("
    echo "            gen_env_vars_from_requests(_hw_requests, providers)"
    echo "        )"

    echo "    finally:"
    echo "        sys.path.pop()"

    gen_ci_env_info_conf "$script" "$dist_label"
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
    echo "config_opts['environment']['MOCK_EXTERNAL_USER']=\"$USER\""
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
        --resultdir="$LOGS_DIR/init" \\
        --init
EOC
    $MOCK \
        --old-chroot \
        --configdir="$conf_dir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/init" \
        --init
    res=$?
    end="$(date +%s)"
    echo "Init took $((end - start)) seconds"
    echo "============================"
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
        --resultdir="$LOGS_DIR/scrub" \\
        --scrub=chroot
EOC
    $MOCK \
        --old-chroot \
        --configdir="$confdir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/scrub" \
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

    makedir "$LOGS_DIR/yumrepos"
    for file in "${target_yum_cfgs[@]}"; do
        cp "$file" "$LOGS_DIR/yumrepos/${file##*/}"
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
        --resultdir="$LOGS_DIR/shell" \\
        "${mock_enable_network[@]}" \\
        --shell '/bin/bash -l'
EOC
    $MOCK \
        --old-chroot \
        --configdir="$mock_dir" \
        --root="$mock_chroot" \
        --resultdir="$LOGS_DIR/shell" \
        "${mock_enable_network[@]}" \
        --shell '/bin/bash -l'
    res=$?

    if [[ "$cleanup" == "true" ]]; then
        scrub_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    return $res
}


run_script_in_mock() {
    local mock_conf="${1?}"
    local mock_env="${2?}"
    local script="${3?}"
    local base_chroot \
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
    local logs_dir logs_xfr_dir
    logs_dir="$LOGS_DIR/script"
    logs_xfr_dir="$(mktemp --tmpdir=. -u -d -t mock_logs.XXXXXXXX)"
    mkdir -p "$logs_dir"
    local mock_shell_cmd
    read -r -d '' mock_shell_cmd <<EOF
        logdir="\$(mktemp --tmpdir -d -t mock_logs.XXXXXXXX)"
        mkdir -p "\$logdir"
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
            groupadd --gid "\$runner_GID" "\$runner_GROUP"
        fi
        if [[ "$script" == /* ]]; then
            script_path="$script"
        else
            script_path="./$script"
        fi

        exec 98>&1 99>&2 &> >(tee \$logdir/stdout_stderr.log)
        echo "========== Running the shellscript $script"
        start="\$(date +%s)"
        if [[ "$TIMEOUT_DURATION" ]]; then
            # _STDCI_TIMEOUT_CMD should be configured in mock_config
            _STDCI_TIMEOUT_CMD="\${_STDCI_TIMEOUT_CMD:-timeout --kill-after 5m}"
            echo "Timeout set to script: $TIMEOUT_DURATION"
            \${_STDCI_TIMEOUT_CMD} "$TIMEOUT_DURATION" "\$script_path" < /dev/null
        else
            "\$script_path" < /dev/null
        fi
        res=\$?
        end="\$(date +%s)"
        if [[ \$res -eq 124 && "$TIMEOUT_DURATION" ]]; then
            echo "Timed out after \$((end - start)) seconds"
        else
            echo "Took \$((end - start)) seconds"
        fi
        echo "==================================="
        exec 1>&98 2>&99

        mv "\$logdir" "$logs_xfr_dir"
        if [[ "\$(find . -uid 0 -print -quit)" != '' ]]; then
            chown -R "$UID:\$runner_GID" .
        fi
        exit \$res
EOF
    cat <<EOF
    $MOCK \
        --old-chroot \
        --root="${mock_chroot}" \
        --configdir="$mock_dir" \
        --no-clean \
        --resultdir="$logs_dir" \
        "${mock_enable_network[@]}" \
        --shell '/bin/bash -l' <<< "$mock_shell_cmd"
EOF
    $MOCK \
        --old-chroot \
        --root="${mock_chroot}" \
        --configdir="$mock_dir" \
        --no-clean \
        --resultdir="$logs_dir" \
        "${mock_enable_network[@]}" \
        --shell '/bin/bash -l' <<< "$mock_shell_cmd"
    local res=$?
    mv "$logs_xfr_dir"/* "$logs_dir" || :
    rmdir "$logs_xfr_dir"
    return $res
}

# Runs a set of scripts each on its own chroot
run_script() {
    local mock_env="${1?}"
    local cleanup="${2?}"
    local script="${3?}"
    local distro_id \
        mock_conf \
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
    run_script_in_mock "$mock_conf" "$mock_env" "$exec_script"
    res=$?
    end="$(date +%s)"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    echo "@@ $(date) $exec_script chroot finished"
    echo "@@      took $((end - start)) seconds"
    echo "@@      rc = $res"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    if [[ "$cleanup" == "true" ]]; then
        scrub_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    return $res
}


finalize() {
    local logs
    logs="$(find "$LOGS_DIR" -mindepth 1 -maxdepth 1)"
    if [[ -n "$logs" ]]; then
        rotate_logs_dir "$PWD/$FINAL_LOGS_DIR"
        makedir "$FINAL_LOGS_DIR"
        echo "Collecting mock logs"
        sync
        xargs -r mv -v -t "$FINAL_LOGS_DIR" <<<"$logs"
        echo "##########################################################"
    fi
    rmdir "$LOGS_DIR"
    rm -rf "$MR_TEMP_DIR"
}


#### MAIN

if ! [[ "$0" =~ ^.*/bash$ ]]; then
    script="$DEFAULT_SCRIPT"

    long_opts="shell"
    short_opts="s"

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

    long_opts+=",timeout-duration:"
    short_opts+=",t:"

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
                shift
                RUN_SHELL="true"
            ;;
            -p|--patch-only)
                shift
                script=automation/check-patch.sh
            ;;
            -m|--merged-only)
                shift
                script=automation/check-merged.sh
            ;;
            -b|--build-only)
                shift
                script=automation/build-artifacts.sh
            ;;
            -e|--execute-script)
                script="$2"
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
            -t|--timeout-duration)
                TIMEOUT_DURATION="$2"
                shift 2
            ;;
            --)
                # end of options
                shift
                break
            ;;
        esac
    done

    mock_env="$(resolve_mock "${1:-$DEFAULT_MOCK_ENV}" "$MOCK_CONF_DIR")" \
    || {
        echo "Unable to find mock env $mock_env" >&2
        exit 1
    }


    if [[ "$RUN_SHELL" == "true" ]]; then
        run_shell \
            "${mock_env:?}" \
            "$script" \
            "$CLEANUP"
        res=$?
    else
        start="$(date +%s)"
        echo "##########################################################"
        echo "##########################################################"
        echo "## $(date) Running env: $mock_env"
        echo "##########################################################"
        run_script "$mock_env" "$CLEANUP" "$script"
        res="$?"
        end="$(date +%s)"
        echo "##########################################################"
        echo "## $(date) Finished env: $mock_env"
        echo "##      took $((end - start)) seconds"
        echo "##      rc = $res"
        echo "##########################################################"
        if [[ "$res" != "0" ]]; then
            lastlog="$( \
                find "$LOGS_DIR" -iname \*.log -print0 \
                | xargs -0 ls -lt \
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
    fi
    exit $res
fi
