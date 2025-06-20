# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025 and Avocado contributors
# Authors: Yongxue Hong <yhong@redhat.com>


import logging
import os

from avocado_vt.agent.core import data_dir as core_data_dir
from avocado_vt.agent.managers import resbacking_mgr
from virttest.qemu_devices import qdevices
from virttest.qemu_devices.utils import set_cmdline_format_by_cfg

LOG = logging.getLogger("avocado.service." + __name__)


def create_net_devices(
    dev_container, net, parent_bus, format_cfg, sock_name, pass_fds=[]
):
    devs = []

    net_type = net.get("type")
    net_dev = net.get("device")
    net_backend = net.get("backend")

    model = net_dev.get("type")
    dev = qdevices.QDevice(model)
    devs.append(dev)
    mac = net_dev.get("mac")
    dev.set_param("mac", mac, dynamic=True)
    # only pci domain=0,bus=0,function=0 is supported for now.
    #
    # libvirt gains the pci_slot, free_pci_addr here,
    # value by parsing the xml file, i.e. counting all the
    # pci devices and store the number.
    if model == "virtio-net-device":
        dev.parent_bus = {"type": "virtio-bus"}
    elif model == "virtio-net-ccw":  # For s390x platform
        dev.parent_bus = {"type": "virtual-css"}
    elif model != "spapr-vlan":
        dev.parent_bus = parent_bus
        dev.set_param("addr", net_dev.get("addr"))

    for key, val in net_dev.get("props").items():
        dev.set_param(key, val)

    if dev_container.has_option("netdev"):
        dev.set_param("netdev", net_backend.get("id"))

    mode = net_backend.get("type")
    netdev_id = net_backend.get("id")
    backend_props = net_backend.get("props")

    # get the backing resource id by the port resource
    port_resource_id = backend_props.pop("port_source")
    for backing_id, res_backing in resbacking_mgr.backings.items():
        if res_backing.binding_resource_id == port_resource_id:
            backing = resbacking_mgr.get_resource_info_by_backing(backing_id)[1]
            backend_props["fd"] = backing["out"]["spec"]["fds"][0]
            # backend_props["ifname"] = backing["out"]["spec"]["ifname"]
            break
    else:
        raise ValueError(f"No found the binding resource for {port_resource_id}")

    if net_type == "user:passt":
        sock_path = os.path.join(core_data_dir.get_tmp_dir(), sock_name)
        # FIXME: hardcode the passt binary path
        passt_bin = "/usr/bin/passt"
        portfwds = backend_props.get("rules")
        mtu = backend_props.get("mtu")
        passt_dev = qdevices.QPasstDev(
            f"{netdev_id}-passt", passt_bin, sock_path, portfwds, mtu
        )
        devs.append(passt_dev)

    if dev_container.has_option("netdev"):
        dev = qdevices.QNetdev(mode, {"id": netdev_id})
        devs.append(dev)
        for key, value in backend_props.items():
            if key in (
                "fd",
                "vhostfd",
            ):
                # if key == "fd":
                #     ifname = "tap0"
                #     net_dst = "switch"
                #     queues = 1
                #     if ifname in network.get_interfaces():
                #         network.delete_port_from_bridege(net_dst, ifname)
                #     tapfds = network.setup_tap_bridge(net_type, ifname, net_dst, queues)
                #     value = tapfds
                pass_fds.append(int(value))
            dev.set_param(key, value)

    for dev in devs:
        set_cmdline_format_by_cfg(dev, format_cfg, "nics")
    return devs
