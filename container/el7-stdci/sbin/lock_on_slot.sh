#!/bin/bash -ex
#
# Find and lock the first available slot. If slot doesn't exist - create one
#

readonly MAX_CONTAINER_SLOTS="${MAX_CONTAINER_SLOTS:-10}"
readonly CONTAINER_SLOTS="${CONTAINER_SLOTS:-/var/lib/stdci}"
readonly MY_SLOT=/slt
readonly PIDFILE=/var/run/lock-on-slot.pid

main() {
    lock_on_slot
}

lock_on_slot() {
    local slot lockfile
    for (( i = 0; i < MAX_CONTAINER_SLOTS; ++i )) {
        slot="${CONTAINER_SLOTS}/${i}"
        mkdir -p "$slot"
        lockfile="${slot}/lock"
        daemonize -l "$lockfile" -p "$PIDFILE" /bin/sleep infinity || continue
        ln -nsf "$slot" "$MY_SLOT"
        return 0
    }
    echo "Failed to lock on slot"
    return 1
}

main