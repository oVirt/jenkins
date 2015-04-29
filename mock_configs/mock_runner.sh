#!/usr/bin/env bash

MOCKS=(
    el6:epel-6-x86_64
    el7:epel-7-x86_64
    fc19:fedora-19-x86_64
    fc20:fedora-20-x86_64
    fc21:fedora-21-x86_64
    fc22:fedora-22-x86_64
)
SCRIPTS=(
    automation/check-patch.sh
    automation/check-merged.sh
    automation/build-artifacts.sh
)
RUN_SHELL="false"
REBUILD="false"
MOCK_CONF_DIR="/etc/mock"
MOUNT_POINT="/tmp/run"
BINDS=(
    /sys
    /lib/modules
)
EXTRA_REPOS=()


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

        -m|--merge-only
            Run/Prepare for the check-merged script only

        -b|--build-only
            Run/Prepare for the build-artifacts script only

        -e|--exec-script path/to/script.sh
            Run/Prepare for the given script (take into account that it needs a
            .req file for that script too)

        -r|--rebuild
            Clean the chroot prior to initializing, just in case

        --mount MOUNT
            Mount that local path too inside the chroot (be careful!)

        --repo REPO_STRING
            Add the given repo to the mock env too

    Parameters:
        mock_env
            Name of the mock chroot to use, if none passed all of the defaults
            will be used: ${MOCKS[@]}

            If you pass only one of the elements separated by ':' it will use
            the first one from that contains the passed string

    Example:

    To run all the scripts on all the chroots:
    > $0

    To run only the build artifacts script on fedoras 21 and 22
    > $0 --build-only fc21:fedora-21-x86_64 fc22:fedora-22-x86_64

    To open a shell to debug the check-merged script on el7
    > $0 --merge-only --shell el7:epel-7-x86_64

EOH
    return 0
}


prepare_chroot() {
    local chroot="${1?}"
    local packages_file="${2?}"
    local base_conf \
        tmp_conf

    base_conf="/etc/mock/$chroot.cfg"
    if ! [[ -e "$baseconf" ]]; then
        echo "Unable to find base mock conf $base_conf"
        return 1
    fi

    tmp_conf="mocker-$conf.cfg"
    cat >"$tmp_conf" <<EOC
import os

config_opts["plugin_conf"]["bind_mount_enable"]='True'
config_opts["plugin_conf"]["bind_mount_opts"]["dirs"]=[
    [os.path.realpath(os.curdir), u'/tmp/run'],
]
EOC
    cat "$base_conf" >> "$tmp_conf"

    init_chroot "$base_conf"
    install_packages "$MOCK_CONF_DIR/$base_conf" "$packages_file"
    clean_rpmdb "$MOCK_CONF_DIR/$base_conf"
    return 0
}


gen_mock_config() {
    local chroot="${1?}"
    local base_conf \
        tmp_conf
    base_conf="/etc/mock/$chroot.cfg"
    if ! [[ -e "$base_conf" ]]; then
        echo "Unable to find base mock conf $base_conf"
        return 1
    fi

    tmp_conf="mocker-${chroot}.cfg"
    cat >"$tmp_conf" <<EOC
import os

config_opts["plugin_conf"]["bind_mount_enable"]='True'
config_opts["plugin_conf"]["bind_mount_opts"]["dirs"]=[
    [os.path.realpath(os.curdir), u'$MOUNT_POINT'],
EOC
    for bind_option in "${BINDS[@]}"; do
        echo "    ['${bind_option%/}', '${bind_option%/}/']," >> "$tmp_conf"
    done
    echo "]" >> "$tmp_conf"
    cat "$base_conf" >> "$tmp_conf"
    touch -d yesterday "$tmp_conf"
    echo "${tmp_conf%.*}"
    return 0
}


install_packages() {
    local conf_file="${1?}"
    local packages=("${@:2}")
    local configdir="${conf_file%/*}"
    local chroot="${conf_file##*/}"
    mock \
        --configdir="$configdir" \
        --root="$chroot" \
        --install "${packages[@]}"
    return $?
}


clean_rpmdb() {
    local conf_file="${1?}"
    local packages=("${@:2}")
    local configdir="${conf_file%/*}"
    local chroot="${conf_file##*/}"
    mock \
        --configdir="$configdir" \
        --root="$chroot" \
        --shell <<EOC
            rm -Rf /var/lib/rpm/__*
            rpm --rebuilddb
EOC
    return $?
}


init_chroot() {
    local chroot="${1?}"
    mock \
        --configdir="$MOCK_CONF_DIR" \
        --root="$chroot" \
        --init
    return $?
}


clean_chroot() {
    local chroot="${1?}"
    mock \
        --configdir="$MOCK_CONF_DIR" \
        --root="$chroot" \
        --clean
    return $?
}


get_packages() {
    local script="${1?}"
    local distro_suffix="${2?}"
    local packages_file \
        pfile

    packages_file="${script%.sh}.req"
    found="false"
    for pfile in "$packages_file" "${packages_file}.$distro_suffix"; do
        if ! [[ -f "$pfile" ]]; then
            continue
        fi
        found="true"
        break
    done
    if [[ "$found" == "false" ]]; then
        echo "ERROR: Unable to find package requirements file" \
             "$packages_file or ${packages_file}.$distro_id" >&2
        return 1
    fi
    grep -v -e '^\#' "$pfile" \
    | grep -v -e '^\s*$'
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
    local script="${2?}"
    local rebuild="${3:-false}"
    local distro_id \
        mock_conf \
        packages_file \
        found \
        res

    mock_conf="${mock_env#*:}"
    distro_id="${mock_env%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$mock_conf" ]]; then
        echo "ERROR: invalid mock environment passed: ${MOCKS[0]}" >&2
        return 1
    fi

    packages=($(get_packages "$script" "$distro_id"))
    res=$?
    if [[ "$res" != "0" ]]; then
        return $res
    fi

    if [[ "$rebuild" == "true" ]]; then
        clean_chroot "$mock_conf"
    fi
    init_chroot "$mock_conf"
    install_packages "$MOCK_CONF_DIR/$mock_conf" "${packages[@]}"
    clean_rpmdb "$MOCK_CONF_DIR/$mock_conf"
    mock_conf="$(gen_mock_config "$mock_conf")"
    /usr/bin/mock \
        --configdir="$PWD" \
        --root="$mock_conf" \
        --shell
    return $?
}


run_script() {
    local conf_file="${1?}"
    local script="${2?}"
    local chroot \
        configdir
    configdir="${conf_file%/*}"
    chroot="${conf_file##*/}"
    /usr/bin/mock \
        --configdir="$configdir" \
        --root="$chroot" \
        --no-clean \
        --shell <<EOS
            export HOME=$MOUNT_POINT
            cd
            chmod +x $script
            ./$script
EOS
    return $?
}


run_scripts() {
    local mock_env="${1?}"
    local rebuild="${2?}"
    local scripts=("${@:3}")
    local distro_id \
        mock_conf \
        packages_file \
        packages \
        script \
        res

    mock_conf="${mock_env#*:}"
    distro_id="${mock_env%:*}"
    if [[ -z "$distro_id" ]] || [[ -z "$mock_conf" ]]; then
        echo "ERROR: invalid mock environment passed: ${MOCKS[0]}"
        return 1
    fi

    if [[ "$rebuild" == "true" ]]; then
        clean_chroot "$mock_conf"
    fi
    init_chroot "$mock_conf"
    res="$?"
    if [[ "$res" != "0" ]]; then
        return $res
    fi
    mock_conf="$(gen_mock_config "$mock_conf")"
    for script in "${scripts[@]}"; do
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@  Running script: $script"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        packages=($(get_packages "$script" "$distro_id"))
        res=$?
        if [[ "$res" != "0" ]]; then
            return $res
        fi

        install_packages "$PWD/$mock_conf" "${packages[@]}"
        clean_rpmdb "$PWD/$mock_conf"
        run_script "$PWD/$mock_conf" "$script"
        res=$?
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        echo "@@  $script finished"
        echo "@@      rc = $res"
        echo "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
        if [[ "$res" != "0" ]]; then
            return $res
        fi
    done
    return 0
}



if ! [[ "$0" =~ ^.*/bash$ ]]; then

    # Parse options
    args="$(getopt \
        -o s:pmvhrbe: \
        -l "shell:,patch-only,merged-only,verbose,help,rebuild,build-only,execute-script:,mount:" \
        -n "$0" -- "$@" \
    )"
    #Bad arguments
    if [[ $? -ne 0 ]]; then
        help
        exit 1
    fi
    eval set -- "$args";
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
            -e|--execute-scpipt)
                SCRIPTS=( "$2" )
                shift 2
            ;;
            -r|--rebuild)
                shift
                REBUILD="true"
            ;;
            --mount)
                BINDS+=( "$2" )
                shift 2
                ;;
            --)
                # end of options
                shift
                break
            ;;
        esac
    done

    if [[ "$RUN_SHELL" == "true" ]]; then
        run_shell "${mock_env:?}" "${SCRIPTS[0]}" "$REBUILD"
        exit $?
    else
        if [[ -n "$1" ]]; then
            mocks=("$@")
        else
            mocks=("${MOCKS[@]} ")
        fi
        for mock_env in "${mocks[@]}"; do
            full_mock_env="$(resolve_mock "$mock_env")" \
            || {
                echo "Unable to find mock env $mock_env" \
                     "use one of" "${MOCKS[@]}" \
                >&2
                exit 1
            }
            echo "##########################################################"
            echo "##########################################################"
            echo "##  Running env: $full_mock_env"
            echo "##########################################################"
            run_scripts "$full_mock_env" "$REBUILD" "${SCRIPTS[@]}"
            res="$?"
            echo "##########################################################"
            echo "##  Finished env: $full_mock_env"
            echo "##      rc = $res"
            echo "##########################################################"
            echo "##########################################################"
            if [[ "$res" != "0" ]]; then
                exit $res
            fi
        done
    fi
fi
