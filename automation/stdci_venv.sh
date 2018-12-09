#!/bin/bash -ex
# stdci_venv.sh - Shell functions for handling Python virtual environments for
#                 STDCI scripts. This file should generally be sourced by other
#                 scripts.
#

STDCI_VENV_CACHE_PATH=/var/host_cache/stdci_venv
# How long to keep cached virtual environments (in seconds)
STDCI_VENV_CACHE_RETENSION=$(( 2 * 24 * 60 * 60 ))

stdci_venv::activate() {
    local stdci_script="${1:?}"
    local lock_file
    local python_file
    local venv_python
    local venv_sha
    local venv_path

    lock_file="$(stdci_venv::_get_file "$stdci_script" requirements.lock)"
    python_file="$(stdci_venv::_get_file "$stdci_script" python)"

    if [[ "$lock_file" == /dev/null && "$python_file" == /dev/null ]]; then
        echo "No STDCI Python virtual environment configuration found"
        return
    fi
    echo "Entering STDCI Python virtual environment"

    venv_python="$(cat "$python_file")"
    if [[ -z "$venv_python" ]]; then
        venv_python="$(type -p python)"
    elif ! type -p "$venv_python" > /dev/null; then
        echo "WARNING: Define python interpreter '$venv_python' is not"
        echo "         executable. Will fallback to system default"
        venv_python="$(type -p python)"
    fi

    stdci_venv::_rm_old

    venv_sha="$(
        (echo "$venv_python"; cat "$lock_file") | sha256sum | cut -d\  -f1
    )"
    venv_path="$STDCI_VENV_CACHE_PATH/$venv_sha"
    stdci_venv::_ensure_exists "$lock_file" "$venv_python" "$venv_path" \
    && source "$venv_path/bin/activate"
}

stdci_venv::_get_file() {
    local stdci_script="${1:?}"
    local extnsion="${2:?}"
    local default="${3:-/dev/null}"
    local stdci_script_base
    local stdci_file

    stdci_script_base="$stdci_script"
    stdci_script_base="${stdci_script_base%.$STD_CI_DISTRO}"
    stdci_script_base="${stdci_script_base%.sh}"
    stdci_file="${stdci_script_base}.${extnsion}.$STD_CI_DISTRO"
    [[ -r "$stdci_file" ]] || \
        stdci_file="${stdci_script_base}.${extnsion}"
    [[ -r "$stdci_file" ]] || \
        stdci_file="$default"
    echo "$stdci_file"
}

stdci_venv::_rm_old() {
    local venv_lru_file
    local venv_dir
    local now="$(date +%s)"
    local venv_lru
    local padding

    (
        shopt -s nullglob
        for venv_lru_file in "$STDCI_VENV_CACHE_PATH"/*.lru; do
            read venv_lru padding < "$venv_lru_file"
            (( venv_lru > now - STDCI_VENV_CACHE_RETENSION )) && continue
            venv_dir="${venv_lru_file%.lru}"
            rm -rf "$venv_dir"
            rm -f "$venv_lru_file"
        done
    )
}

stdci_venv::_ensure_exists() {
    local lock_file="${1:?}"
    local venv_python="${2:?}"
    local venv_path="${3:?}"

    if [[ -e "${venv_path}.lru" ]]; then
        echo "Found cached Python virtualenv"
        date +%s > "${venv_path}.lru"
        return
    fi
    echo "Creating Python virtualenv"
    rm -rf "${venv_path}"
    virtualenv --python="$venv_python" "$venv_path" || return 1
    if source "$venv_path/bin/activate"; then
        if
            pip install --upgrade pip \
            && pip install -r "$lock_file"
        then
            deactivate || :
            date +%s > "${venv_path}.lru" && return
        fi
        deactivate || :
    fi
    rm -rf "${venv_path}"
    return 1
}
