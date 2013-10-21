#!/usr/bin/python
from vdsm import libvirtconnection
c = libvirtconnection.get()
nets = c.listAllNetworks(0)
for net in nets:
    if net.name().startswith('vdsm-test-network'):
        net.destroy()
        net.undefine()
