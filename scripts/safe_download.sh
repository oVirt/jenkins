#!/bin/bash

_safe_download_usage() {
    if [[ $# -gt 0 ]]; then
        echo "$@"
        echo
    fi
    echo "Usage: safe_download [OPTIONS] LOCKFILE FROM TO"
    echo
    echo "Download a file from the FROM URL to the TO filename while using"
    echo "LOCKFILE to ensure the download is done safely, and verify it with"
    echo "a cryptographic digest."
    echo "The download will be skipped if the file already exists locally and"
    echo "the digest matches."
    echo
    echo "positional arguments:"
    echo "  LOCKFILE               A path to a lockfile for synchronizing"
    echo "                         parallel downloads of the same file."
    echo "  FROM                   A URL of the file to download"
    echo "  TO                     Path to download the file into"
    echo
    echo "optional arguments:"
    echo "  -h                     Show helpful help."
    echo "  -t TIMEOUT_SEC         The amount of seconds to wait for the lock"
    echo "                         on LOCKFILE to be freed, defaults to 3600"
    echo "  -d DIGEST_ALGO         The digest algorithm to use for verifying"
    echo "                         the downloaded file, defaults to 'sha1'."
    echo "  -a AFTER_HOOK          The name of a shell command or function to"
    echo "                         run after the file had been downloaded."
    echo "  -s DIGEST_VALUE        The required result value for calculating"
    echo "                         the cryptographic digest of the downloaded"
    echo "                         file. If this is not specified, it would"
    echo "                         be assumed the value can be read from a"
    echo "                         remote file stored next to the downloaded"
    echo "                         file with an extension matching the digest"
    echo "                         algorithm"
    echo "                         If this is set to `CHECKSUM_FILE` if would"
    echo "                         be assumes the remote location contains a"
    echo "                         file called CHECKSUM that contains a"
    echo "                         space-separated table of checksum and file"
    echo "                         name"
}

safe_download() (
    # Download files into shared locations using a lock.
    # The lock will be released as soon as this subprocess will exit
    local timeout_sec=3600
    local digest=sha1
    local after_hook=''
    local remote_digest

    while getopts 'ht:d:a:s:' o; do
        case "$o" in
            h)
                _safe_download_usage
                return
                ;;
            t)
                if ! (( timeout_sec=OPTARG )) >> /dev/null; then
                    echo Timeout value should be an integer amount of seconds
                    return 2
                fi
                ;;
            d)
                digest="$OPTARG"
                ;;
            a)
                after_hook="$OPTARG"
                if ! type "$after_hook" >> /dev/null; then
                    echo After hook must be an executable or a shellfunction
                    return 5
                fi
                ;;
            s)
                remote_digest="$OPTARG"
                ;;
            *)
                echo 1>&2
                _safe_download_usage 1>&2
                return 3
                ;;
        esac
    done
    shift $((OPTIND-1))

    local digest_tool="/usr/bin/${digest}sum"
    if ! [[ -x "$digest_tool" ]]; then
        echo Invalid digest algorithm specified
        return 4
    fi

    local usage=_safe_download_usage
    local lockfile="${1:?"$($usage LOCKFILE was not specified)"}"
    local download_from="${2:?"$($usage FROM argument was not specified)"}"
    local download_to="${3:?"$($usage TO argument was not specified)"}"

    touch "$lockfile"
    exec {fd}< "$lockfile"
    flock -e  -w "$timeout_sec" "$fd" || {
        echo "ERROR: Timed out after $timeout_sec seconds waiting for lock" >&2
        return 1
    }

    if [[ -z "$remote_digest" ]]; then
        # Remote file includes only digest w/o filename suffix
        local remote_digest_url="${download_from}.${digest}"
        remote_digest="$(curl -sL "${remote_digest_url}")"
    elif [[ "$remote_digest" == CHECKSUM_FILE ]]; then
        local remote_checksum_file="${download_from%/*}/CHECKSUM"
        local checksum_file_contents
        checksum_file_contents="$(curl -sL "${remote_checksum_file}")"
        remote_digest="$(
            sed -nre "s/^(\S+)\s+.*${download_from##*/}$/\1/p" \
                <<<"$checksum_file_contents"
        )"
    fi
    local local_digest_file="${download_to}.${digest}"
    if [[ "$(cat "$local_digest_file")" != "$remote_digest" ]]; then
        echo "${download_to} is not up to date, corrupted or doesn't exist."
        echo "Downloading file from: ${remote_digest_url}"
        curl -L "$download_from" --output "$download_to"
        $digest_tool "$download_to" | cut -d " " -f1 > "$local_digest_file"
        if ! [[ "$(cat "$local_digest_file")" == "$remote_digest" ]]; then
            echo "${download_to} is corrupted"
            return 1
        fi
        if [[ -n "$after_hook" ]]; then
            $after_hook "$download_to"
        fi
    else
        echo "${download_to} is up to date"
    fi
)

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    safe_download "$@"
fi
