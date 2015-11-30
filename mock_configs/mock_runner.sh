#!/usr/bin/env bash

MOCKS=(
    el6:epel-6-x86_64
    el7:epel-7-x86_64
    fc22:fedora-22-x86_64
    fc23:fedora-23-x86_64
)
SCRIPTS=()
RUN_SHELL="false"
CLEANUP="false"
MOCK_CONF_DIR="/etc/mock"
MOCK="mock"
MOUNT_POINT="$PWD"
LOGS_DIR="logs"
TRY_PROXY="false"
PACKAGES=()


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
    without extension, for example fedora-22-x86_64)

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

        -r|--cleanup
            Clean the chroot prior to initializing, just in case

        -P|--try-proxy
            If set, will try to use the proxied config and set the proxy inside
            the mock env

        -C|--mock-confs-dir
            Directory where the base mock configs are located (default is
            /etc/mock).

        -a|--add-package
            Add the given package to the mock env when installing, can be
            specified more than once

    Parameters:
        mock_env
            Name of the mock chroot to use, if none passed all of the defaults
            will be used: ${MOCKS[@]}

            If you pass only one of the elements separated by ':' it will use
            the first one from that contains the passed string

    Example:

    To run the build script on all the chroots:
    > $0 --build-only

    To run only the build artifacts script on fedoras 22 and 23
    > $0 --build-only fc22:fedora-22-x86_64 fc23:fedora-23-x86_64

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
        mock_conf_with_mounts

    mock_conf="$(
        gen_mock_config "$base_chroot" "$dist_label" "$script"
    )"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"
    mock_dir="${mock_conf%/*}"
    if [[ "$cleanup" == "true" ]]; then
        clean_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    [[ -e "$LOGS_DIR/${mock_chroot}.init" ]] \
    || mkdir -p "$LOGS_DIR/${mock_chroot}.init"
    init_chroot "${mock_chroot}" "${mock_dir}" \
        | tee -a "$LOGS_DIR/${mock_chroot}.init/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    [[ -e "$LOGS_DIR/${mock_chroot}.install_packages" ]] \
    || mkdir -p "$LOGS_DIR/${mock_chroot}.install_packages"
    install_packages \
        "$mock_chroot" \
        "$mock_dir" \
        $(get_data_from_file "$script" req "$dist_label")  \
        $(get_data_from_file "$script" packages "$dist_label")  \
        "${PACKAGES[@]}" \
        2>&1 \
        | tee -a "$LOGS_DIR/${mock_chroot}.install_packages/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    [[ -e "$LOGS_DIR/${mock_chroot}.clean_rpmdb" ]] \
    || mkdir -p "$LOGS_DIR/${mock_chroot}.clean_rpmdb"
    clean_rpmdb "$mock_chroot" "$mock_dir" \
        | tee -a "$LOGS_DIR/${mock_chroot}.clean_rpmdb/stdout_stderr.log"
    [[ "${PIPESTATUS[0]}" != 0 ]] && return 1
    mock_conf_with_mounts="$(
        gen_mock_config "$base_chroot" "$dist_label" "$script" "with_mounts"
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
        last_gen_repo_name

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
if int(distro_maj) >= 22:
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

        for mount_opt in $(get_data_from_file "$script" mounts "$dist_label"); do
            [[ "$mount_opt" == "" ]] && continue
            if [[ "$mount_opt" =~ ^([^:]*)(:(.*))?$ ]]; then
                src_mnt="${BASH_REMATCH[1]}"
                dst_mnt="${BASH_REMATCH[3]:-$src_mnt}"
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
    if [[ "$repos" != "" ]]; then
        repos_md5=($(echo "${repos[@]}" | sort | md5sum ))
        tmp_chroot="${chroot}-${repos_md5[0]}"
    else
        tmp_chroot="$chroot"
    fi
    echo "Using temp chroot = ${tmp_chroot}" >&2
    echo "config_opts['root'] = '${tmp_chroot}'" >> "$tmp_conf"
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
    touch --date "yesterday" "$tmp_conf"
    echo "$tmp_conf"
    return 0
}


install_packages() {
    local chroot="${1?}"
    local conf_dir="${2?}"
    local packages=("${@:3}")
    local start \
        end
    start="$(date +%s)"
    echo "========== Installing extra packages"
    [[ "$packages" == "" ]] && return 0
    cat <<EOC
    $MOCK \\
        --configdir="$conf_dir" \\
        --root="$chroot" \\
        --install ${packages[@]} \\
        --resultdir="$LOGS_DIR/${chroot}.install_packages"
EOC
    $MOCK \
        --configdir="$conf_dir" \
        --root="$chroot" \
        --install "${packages[@]}" \
        --resultdir="$LOGS_DIR/${chroot}.install_packages"
    res=$?
    end="$(date +%s)"
    echo "Install packages took $((end - start)) seconds"
    echo "============================"
    return $res
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
        --configdir="$conf_dir" \\
        --root="$chroot" \\
        --resultdir="$LOGS_DIR/${chroot}.init" \\
        --init
EOC
    $MOCK \
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


clean_chroot() {
    local chroot="${1?}"
    local confdir="${2?}"
}


clean_rpmdb() {
    local chroot="${1?}"
    local conf_dir="${2?}"
    local packages=("${@:3}")
    local start \
        end
    start="$(date +%s)"
    echo "========== Cleaning rpmdb"
    cat <<EOC2
    $MOCK \\
        --configdir="$conf_dir" \\
        --root="$chroot" \\
        --resultdir="$LOGS_DIR/${chroot}.clean_rpmdb" \\
        --shell <<EOC
            set -e
            logdir="$MOUNT_POINT/$LOGS_DIR/${chroot}.clean_rpmdb"
            [[ -d \$logdir ]] \\
            || mkdir -p "\$logdir"
            # Fix that allows using yum inside the chroot on dnf enabled
            # distros
            [[ -d /etc/dnf ]] && cat /etc/yum/yum.conf > /etc/dnf/dnf.conf
            rm -Rf /var/lib/rpm/__* &>\$logdir/rpmbuild.log
            rpm --rebuilddb &>>\$logdir/rpmbuild.log
EOC
EOC2
    $MOCK \
        --configdir="$conf_dir" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/${chroot}.clean_rpmdb" \
        --shell <<EOC
            set -e
            logdir="$MOUNT_POINT/$LOGS_DIR/${chroot}.clean_rpmdb"
            [[ -d \$logdir ]] \\
            || mkdir -p "\$logdir"
            # Fix that allows using yum inside the chroot on dnf enabled
            # distros
            [[ -d /etc/dnf ]] && cat /etc/yum/yum.conf > /etc/dnf/dnf.conf
            rm -Rf /var/lib/rpm/__* &>\$logdir/rpmbuild.log
            rpm --rebuilddb &>>\$logdir/rpmbuild.log
EOC
    res=$?
    end="$(date +%s)"
    echo "Clean rpmdb took $((end - start)) seconds"
    echo "============================"
    return $res
}


clean_chroot() {
    local chroot="${1?}"
    local confdir="${2?}"
    local start \
        end
    start="$(date +%s)"
    echo "========== Cleaning chroot"
    cat <<EOC
    $MOCK \\
        --configdir="$confdir" \\
        --root="$chroot" \\
        --resultdir="$LOGS_DIR/${chroot}.clean" \\
        --clean
EOC
    $MOCK \
        --configdir="$MOCK_CONF_DIR" \
        --root="$chroot" \
        --resultdir="$LOGS_DIR/${chroot}.clean" \
        --clean
    res=$?
    end="$(date +%s)"
    echo "Clean chroot took $((end - start)) seconds"
    echo "============================"
    return $res
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
    local full_mock
    if [[ "${mock}" =~ ^.+:.+$ ]]; then
        echo "$mock"
        return 0
    fi
    for full_mock in "${MOCKS[@]}"; do
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
        base_chroot

    base_chroot="${mock_env#*:}"
    distro_id="${mock_env%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$base_chroot" ]]; then
        echo "ERROR: invalid mock environment passed: $mock_env" >&2
        return 1
    fi
    mock_conf="$(get_temp_conf "$base_chroot" "$distro_id")" \
    || return 1

    mock_dir="${mock_conf%/*}"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"

    echo "Using base mock conf $MOCK_CONF_DIR/${base_chroot}.cfg" >&2
    prepare_chroot "$base_chroot" "$distro_id" "$script" \
    || return 1
    echo "INFO The working directory is mounted at \$HOME, you can just run 'cd' to get there"
    cat <<EOC
    $MOCK \\
        --configdir="$mock_dir" \\
        --root="$mock_chroot" \\
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \\
        --shell
EOC
    $MOCK \
        --configdir="$mock_dir" \
        --root="$mock_chroot" \
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \
        --shell
    return $?
}


run_script() {
    local mock_conf="${1?}"
    local mock_env="${2?}"
    local script="${3?}"
    local base_chroot \
        configdir \
        custom_conf \
        distro_id
    base_chroot="${mock_env#*:}"
    distro_id="${mock_env%%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$base_chroot" ]]; then
        echo "ERROR: invalid mock environment passed: $mock_env" >&2
        return 1
    fi
    mock_conf="$(get_temp_conf "$base_chroot" "$distro_id")" \
    || return 1

    mock_dir="${mock_conf%/*}"
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"

    echo "Using base mock conf $MOCK_CONF_DIR/${base_chroot}.cfg" >&2
    prepare_chroot "$base_chroot" "${mock_env%%:*}" "$script" \
    || return 1
    cat <<EOC
    $MOCK \\
        --root="${mock_chroot}" \\
        --configdir="$mock_dir" \\
        --no-clean \\
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \\
        --shell <<EOS
            set -e
            logdir="$MOUNT_POINT/$LOGS_DIR/${mock_chroot}.${script##*/}"
            [[ -d "\\\$logdir" ]] \\
            || mkdir -p "\\\$logdir"
            export HOME=$MOUNT_POINT
            cd
            chmod +x $script
            runner_GID="$(id -g)"
            runner_GROUP="$(id -n -g)"
            # mock group is called mockbuild inside the chroot
            if [[ \\\$runner_GID == "mock" ]]; then
                runner_GROUP=mockbuild
            fi
            if ! getent group "\\\$runner_GROUP" &>/dev/null; then
                groupadd \\
                    --gid "\\\$runner_GID" \\
                    "\\\$runner_GROUP"
            fi
            start="\\\$(date +%s)"
            echo "========== Running the shellscript $script" \\
                | tee -a \\\$logdir/${script##*/}.log
            ./$script 2>&1 | tee -a \\\$logdir/${script##*/}.log
            res=\\\${PIPESTATUS[0]}
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
        --root="${mock_chroot}" \
        --configdir="$mock_dir" \
        --no-clean \
        --resultdir="$LOGS_DIR/${mock_chroot}.${script##*/}" \
        --shell <<EOS
            set -e
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
            echo "========== Running the shellscript $script" \
                | tee -a \$logdir/${script##*/}.log
            ./$script 2>&1 | tee -a \$logdir/${script##*/}.log
            res=\${PIPESTATUS[0]}
            end="\$(date +%s)"
            echo "Took \$((end - start)) seconds" \
            | tee -a \$logdir/${script##*/}.log
            echo "===================================" \
            | tee -a \$logdir/${script##*/}.log
            if [[ "\$(find . -uid 0 -print -quit)" != '' ]]; then
                chown -R "$UID:\$runner_GID" .
            fi
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
        res

    mock_conf="$(get_base_conf "$MOCK_CONF_DIR" "${mock_env#*:}")" \
    || return 1
    mock_chroot="${mock_conf##*/}"
    mock_chroot="${mock_chroot%.*}"
    mock_dir="${mock_conf%/*}"
    if [[ "$cleanup" == "true" ]]; then
        clean_chroot "$mock_chroot" "$mock_dir" \
        || return 1
    fi
    for script in "${scripts[@]}"; do
        [[ -r "$script" ]] \
        || {
            echo "ERROR: Script $script does not exist or is not readable."
            return 1
        }
        start="$(date +%s)"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@ $(date) Running chroot for script: $script"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        run_script "$mock_conf" "$mock_env" "$script"
        res=$?
        end="$(date +%s)"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@ $(date) $script chroot finished"
        echo "@@      took $((end - start)) seconds"
        echo "@@      rc = $res"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        if [[ "$res" != "0" ]]; then
            return $res
        fi
    done
    return 0
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

    long_opts+=",cleanup"
    short_opts+=",c"

    long_opts+=",mock-confs-dir:"
    short_opts+=",C:"

    long_opts+=",try-proxy"
    short_opts+=",P"

    long_opts+=",add-package:"
    short_opts+=",a:"

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
                mock_env="$(resolve_mock "$2")" \
                || {
                    echo "Unable to find mock env $mock_env" \
                        "use one of" "${MOCKS[@]}" \
                    >&2
                    exit 1
                }
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
            -c|--cleanup)
                shift
                CLEANUP="true"
            ;;
            -C|--mock-confs-dir)
                MOCK_CONF_DIR="$2"
                shift 2
            ;;
            -P|--try-proxy)
                TRY_PROXY="true"
                shift
            ;;
            -a|--add-package)
                PACKAGES+=("$2")
                shift 2
            ;;
            --)
                # end of options
                shift
                break
            ;;
        esac
    done

    rotate_logs_dir "$PWD/$LOGS_DIR"
    mkdir -p "$LOGS_DIR"

    if [[ "$RUN_SHELL" == "true" ]]; then
        run_shell \
            "${mock_env:?}" \
            "${SCRIPTS[0]}" \
            "$CLEANUP"
        exit $?
    else
        if [[ -n "$1" ]]; then
            mocks=("$@")
        else
            mocks=("${MOCKS[@]}")
        fi
        for mock_env in "${mocks[@]}"; do
            full_mock_env="$(resolve_mock "$mock_env")" \
            || {
                echo "Unable to find mock env $mock_env" \
                     "use one of" "${MOCKS[@]}" \
                >&2
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
                    find logs -iname \*.log \
                    | xargs ls -lt \
                    | head -n1\
                    | awk '{print $9}' \
                )"
                if [[ -r "$lastlog" ]]; then
                    echo "##! ERROR vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"
                    echo "##! Last 20 log enties: $lastlog"
                    echo "##!"
                    tail -n 20 "$lastlog"
                    echo "##!"
                    echo "##! ERROR ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^"
                else
                    echo "No log files found, check command output"
                fi
                echo "##!########################################################"
                exit $res
            else
                echo "## FINISHED SUCCESSFULY"
                echo "##########################################################"
            fi
            echo "##########################################################"
        done
    fi
fi
