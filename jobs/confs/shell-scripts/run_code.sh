#!/bin/bash -e
shopt -s extglob nullglob
source "$(dirname "$(which "$0")")/../../../scripts/parse_yaml.sh"
MOCK_CONF_DIR="$(dirname "$(which "$0")")/../../../mock_configs"
PACKAGES=(
    firewalld  libvirt qemu-kvm
    libselinux-utils kmod rpm-plugin-selinux
)
TRY_MIRRORS=""
REPO_INSTALLER=""
REPO_CONF_FILE=""
# Hardwired env vars we always copy into the mock env
readonly HW_ENV_VARS=(
    GIT_COMMITTER_{NAME,EMAIL} BUILD_{NUMBER,ID,DISPLAY_NAME,TAG,URL}
    JOB_{{,BASE_}NAME,URL} NODE_{NAME,LABELS} WORKSPACE JENKINS_URL GERRIT_BRANCH
)
# Directories and files we mount from the CI source repo into the chroot
# (specified as 'src:dst' pairs where src is relative to the repo and
# dst is in the chroot
readonly CODE_MNTS=(
    scripts/ci_toolbox:/var/lib/ci_toolbox
    data/ssh_files:/var/lib/ci_ssh_files
    scripts/mock_runner_profile.sh:/etc/profile.d/mock_runner_profile.sh
)

readonly MR_TEMP_DIR=$(mktemp --tmpdir -d "tmp.code_run.XXX")
readonly LOGS_DIR="$(mktemp --tmpdir -d -t run_logs.XXXXXXXX)"
# trap finalize EXIT

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

verify_ipv6() {
    # check if any routes received via router advertisements are in place
    /sbin/sysctl net.ipv6.conf.all.accept_ra=2 || return 1
}

setup_qemu() {
    chmod o+x /root/workspace
    install -m 0644 -d /var/lib/lago
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

inject_repos() {
    local distro="${1?}"
    local script="${2?}"
    local packages=("${@:3}")
    local repos \
        base_conf \
        repo_opt \
        repo_name \
        repo_url \
        tmp_chroot \
        proxy \
        repos_md5 \
        last_gen_repo_name \
        mirror_conf \
        mirror_conf_file \
        user_conf \
        env_conf \
        env_conf_file \
        env_file \
        repo_conf \
        extra_user_repos \
        vars_list=()

    repos=($(get_data_from_file "$script" repos "$distro"))
    user_conf=$(mktemp "tmp.user_conf.XXX")
    mirror_conf_file=$(mktemp "tmp.mirror_conf.XXX")
    env_conf_file=$(mktemp "tmp.env_conf.XXX")
    # this is a key:value file to store the env vars.
    env_file=$(mktemp --tmpdir="$MR_TEMP_DIR" "env_file.XXX")
    if [[ "${#repos[@]}" -ne 0 || "${#packages[@]}" -ne 0 ]]; then
        repos_md5=($(echo "${repos[@]}" "${packages[@]}" | sort | md5sum ))
    fi

    env_conf=$(gen_environ_conf "$distro" "$script" "$env_file")
    echo "${env_conf}" >> "${env_conf_file}"
    python "${env_conf_file}"
    vars_list=$(parse_yaml "${env_file}")
    eval "${vars_list}"
    for var in vars_list; do
        export $var
    done
    # create_variables "${env_file}"
    # Overwrite the yum / dnf conf.
    if [[ $os =~ rhel7 ]] || [[ $os =~ centos7 ]]; then
        REPO_INSTALLER="yum"
        REPO_CONF_FILE="/etc/yum.conf"
    else
        REPO_CONF_FILE="/etc/dnf/dnf.conf"
        REPO_INSTALLER="dnf"
        if [[ $NAME =~ 'Stream' ]]; then
            dnf config-manager --set-enabled powertools
        else
            dnf config-manager --set-enabled PowerTools
        fi
    fi
    #Overwrite repo config file.
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
        cat >>"$user_conf" <<EOR
[$repo_name]
enabled=1
gpgcheck=0
baseurl=$repo_url
name="Custom $repo_name"
module_hotfixes=1

EOR
    done
    repo_conf=$(cat "${REPO_CONF_FILE}")
    extra_user_repos=$(cat "${user_conf}")
    echo -e "${repo_conf}\n${extra_user_repos}" > "/tmp/${REPO_CONF_FILE##*/}"
    cp "/tmp/${REPO_CONF_FILE##*/}" "${REPO_CONF_FILE}"
    # Install all user packages.
    "${REPO_INSTALLER}" install -y "${packages[@]}"

}

gen_environ_conf() {
    local dist_label="${1?}"
    local script="${2?}"
    local env_file="${3?}"
    local gdbm_db
    gdbm_db=$(mktemp --tmpdir="$MR_TEMP_DIR" "gdbm_db.XXX")
    # Generate GDBM database from `$env`
    python "${scripts_path}/gdbm_db_resolvers.py" "${gdbm_db}"
    echo "import os"
    echo "from six import iteritems"
    echo "from os.path import isfile"
    echo "if isfile('$gdbm_db'):"
    echo "    import sys"
    echo "    from yaml import safe_load"
    echo "    sys.path.append('$scripts_path')"
    echo "    try:"
    echo "        from ci_env_client import ("
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
        echo "        env_dict = gen_env_vars_from_requests(requests, providers)"
        echo "        with open('${env_file}', 'a') as wf:"
        echo "            for k,v in iteritems(env_dict):"
        echo "                wf.write('{0}:{1}\n'.format(k,v))"
    fi

    echo "        _hw_vars = '${HW_ENV_VARS[*]}'.split()"
    echo "        _hw_requests = [{"
    echo "            'name': var,"
    echo "            'valueFrom': {'runtimeEnv': var},"
    echo "            'optional': True,"
    echo "        } for var in _hw_vars]"
    echo "        hw_dict = gen_env_vars_from_requests(_hw_requests, providers)"
    echo "        with open('${env_file}', 'a') as wf:"
    echo "            for k,v in iteritems(hw_dict):"
    echo "                wf.write('{0}:{1}\n'.format(k,v))"
    echo "    finally:"
    echo "        sys.path.pop()"
    gen_ci_env_info_conf "$script" "$dist_label" "$env_file"
}


gen_ci_env_info_conf() {
    local path_to_script="${1:?}"
    local ci_distro="${2:?}"
    local env_file="${3:?}"
    local script_name="${path_to_script##*/}"
    local ci_stage="${script_name%%.*}"
    local ci_reposfiles

    ci_reposfiles=($(resolve_multiple_files "$path_to_script" "yumrepos" "$ci_distro"))
    echo "with open('${env_file}', 'a') as wf:"
    echo "    wf.write('"STD_CI_DISTRO = \"${ci_distro}\""\n')"
    echo "    wf.write('"STD_CI_STAGE = \"${ci_stage}\""\n')"
    # Since 'resolve_multiple_files' returns an array of matches, we need only
    # the first match.
    echo "    wf.write('"STD_CI_YUMREPOS = \"${ci_reposfiles[0]}\""\n')"
    # echo "os.environ['MOCK_EXTERNAL_USER'] = \"${USER}\""
}

gen_mirrors_conf() {
    local mirrors_url="${1?}"
    local yum_conf="/tmp/repo.conf"

    echo "import sys"
    echo "sys.path.append('$scripts_path')"
    echo "try:"
    echo "    from mirror_client import mirrors_from_uri, \\"
    echo "        inject_yum_mirrors_str"
    echo "    config_opts = dict()"
    echo "    config_opts['yum.conf'] = inject_yum_mirrors_str("
    echo "        mirrors_from_uri('$mirrors_url'),"
    echo "        config_opts['yum.conf'],"
    echo "        locals().get('none_value', 'None'),"
    echo "    )"
    echo "    with open('$yum_conf', 'w') as repo_file:"
    echo "        repo_file.write(config_opts['yum.conf'])"
    echo "finally:"
    echo "    sys.path.pop()"
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

inject_ci_mirrors() {
    local path_to_script="${1?}"
    local distro="${2?}"
    local target_file_suffix="${3:-yumrepos}"
    local target_yum_cfgs
    local new_repo_file

    target_yum_cfgs=($(
        resolve_multiple_files \
            "$path_to_script" \
            "$target_file_suffix" \
            "$distro"
    ))
    [[ ${#target_yum_cfgs[@]} -eq 0 ]] && return 0
    # "${scripts_path}"/mirror_client.py "$TRY_MIRRORS" "${target_yum_cfgs[@]}"
    for file in "${target_yum_cfgs[@]}"; do
        if [[ -f "$file" ]]; then
            new_repo_file="${file##*/}"
            new_repo_file="${new_repo_file%.yumrepos}"
            cp "$file" "/etc/yum.repos.d/${new_repo_file}.repo"
        fi
    done
}

resolve_multiple_files() {
    local path_to_script="${1?}"
    local suffix="${2?}"
    local distro="${3?}"
    local path_to_script_no_ext="${path_to_script%.*}"
    local matches

    matches=($(
        printf "%s\n" "${path_to_script_no_ext}"?(.*)".${suffix}.${distro}" | sort -r
        printf "%s\n" "${path_to_script_no_ext}"?(.*)".${suffix}" | sort -r
    ))
    echo "${matches[@]}"
}

prepare_code_mnt() {
    local src_mnt
    local dst_mnt
    local mount_opt
    local code_dir_orig
    echo "Mounting code"
    # Mount code mounts
    for mount_opt in "${CODE_MNTS[@]}"; do
        src_mnt="${mount_opt%%:*}"
        dst_mnt="${mount_opt##*:}"
        code_dir_orig="$MOCK_CONF_DIR/../$src_mnt"
        cp -rpL "$code_dir_orig" "$dst_mnt"
        PATH=$PATH:"$dst_mnt"
    done
}

run_script() {
    local distro="${1?}"
    local cleanup="${2?}"
    local script="${3?}"
    local packages \
        start \
        end \
        res \
        exec_script \
        src_mnt \
        dst_mnt
    scripts_path="$(dirname "$(which "$0")")/../../../stdci_libs"
    prepare_code_mnt
    [[ -n "$TRY_MIRRORS" ]] && [[ -n "$script" ]] && \
        inject_ci_mirrors "$script" "$distro"
    packages=(
        $(get_data_from_file "$script" req "$distro")
        $(get_data_from_file "$script" packages "$distro")
        "${PACKAGES[@]}"
    )
    if [[ "$distro" == el8 ]]; then
        packages+=(podman)
    fi
    inject_repos "$distro" "${script}" "${packages[@]}"
    systemctl start libvirtd

    exec_script="$(resolve_file "$script" "sh" "$distro")"
    [[ -r "$exec_script" ]] \
    || {
        echo "ERROR: Script $exec_script does not exist or is not readable."
        return 1
    }
    if [[ "$exec_script" == /* ]]; then
        script_path="$exec_script"
    else
        script_path="./$exec_script"
    fi
    start="$(date +%s)"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    echo "@@ $(date) Running script: $exec_script"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    source "${script_path}"
    res=$?
    end="$(date +%s)"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    echo "@@ $(date) $exec_script run finished"
    echo "@@      took $((end - start)) seconds"
    echo "@@      rc = $res"
    echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    return $res
}

#### MAIN

if ! [[ "$0" =~ ^.*/bash$ ]]; then
    script="$DEFAULT_SCRIPT"

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
    verify_ipv6
    setup_qemu
    source /etc/os-release
    os="${ID:?}${VERSION_ID:?}"
    # Removing any dots after the version id - e.g: centos7.8
    distro=${os/.*/}
    if [[ ${distro} =~ 'centos8' ]]; then
        distro=el8
    elif [[ ${distro} =~ 'centos7' ]]; then
        distro=el7
    fi
    start="$(date +%s)"
    echo "##########################################################"
    echo "##########################################################"
    echo "## $(date) Running env: $distro"
    echo "##########################################################"
    run_script "$distro" "$CLEANUP" "$script"
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
    exit $res
fi
