#!/bin/bash -x
echo "shell-scripts/fix_rpmdb_problems.sh"

## Save some info on the system status
get_info(){
    mkdir -p "$WORKSPACE/logs/"
    for option in CA e m x; do
        sudo db_stat -$option -h /var/lib/rpm \
        | tee "$WORKSPACE/logs/rpmdb.${option}.log"
        ls -l "$WORKSPACE/logs/"
    done
}

verify() {
    sudo /usr/lib/rpm/rpmdb_verify /var/lib/rpm/Packages 2>&1
}


## Duplicated packages check and preemtive cleanup
## Also takes care of the stall locks
sudo rm -f /var/lib/rpm/__db*
sudo rpm --rebuilddb
sudo yum clean rpmdb
sudo package-cleanup --cleandupes --noscripts -y

duplicated="$(rpm -qa | sort | uniq -c | grep -v '^[ ]*1')"
if [[ -n "$duplicated" ]]; then
    echo -e "IT FAILED; STILL SOME DUPLICATED PACKAGES:\n$duplicated"
    exit 1
fi

## corrupt Packages database check
verification_out="$(verify)"
verification_res=$?
if [[ $verification_res -ne 0 ]]; then
    get_info
    echo "FIX: rebuilding rpm database, corrupt: $verification_out"
    sudo rm -f /var/lib/rpm/__db.* || echo "No rpmdb files found"
    sudo rpm --rebuilddb
    ## reverify to take some more drastic measures if needed
    verification_out="$(verify)"
    verification_res=$?
    if [[ $verification_res -ne 0 ]]; then
        sudo mv /var/lib/rpm/Packages /var/lib/rpm/Packages.backup
        /usr/lib/rpm/rpmdb_dump /var/lib/rpm/Packages.backup \
        | sudo /usr/lib/rpm/rpmdb_load /var/lib/rpm/Packages
        verification_out="$(verify)"
        verification_res=$?
        if [[ $verification_res -ne 0 ]]; then
            echo "FAILED TO FIX rpmdb problems, please check personally."
            echo "Last check error: $verification_out"
            exit 1
        fi
    fi
    echo "RPMDB FIXED! Continuing with the job."
fi
