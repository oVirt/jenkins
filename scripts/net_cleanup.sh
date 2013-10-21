#!/bin/bash
del_dummies() {
    for nic in `ip l | awk '{print $2;}' | egrep "^dummy"`; do
        ip link del dev ${nic:0:${#nic}-1}
    done
    rm -f /etc/sysconfig/network-scripts/ifcfg-dummy*
}

del_bonds() {
    for nic in `ip l | awk '{print $2;}' | egrep "^bond"`; do
        echo "-${nic:0:${#nic}-1}" > /sys/class/net/bonding_masters
    done
    rm -f /etc/sysconfig/network-scripts/ifcfg-bond*
}

del_bridges() {
    for bridge in `brctl show | awk '{print $1;}' | grep test-network`; do
        ip link set dev $bridge down
        brctl delbr $bridge
        rm -f "/etc/sysconfig/network-scripts/ifcfg-$bridge"
    done
}

del_test_nets() {
    python "$(dirname "$0")/vdsm_test_net_remover.py"
    rm -f /etc/sysconfig/network-scripts/ifcfg-test-network*
}

emergency_net_cleanup() {
    del_dummies
    del_bonds
    del_bridges
    del_test_nets
}

emergency_net_cleanup
