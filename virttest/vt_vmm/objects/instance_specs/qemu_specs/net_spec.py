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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import logging

from virttest import utils_misc

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecNet(QemuSpec):
    def __init__(self, name, vt_params, node, nic):
        super(QemuSpecNet, self).__init__(name, vt_params, node)
        self._nic = nic
        self._parse_params()

    def _define_spec(self):
        def _define_device_spec():
            # Define the nic device spec
            dev = dict()
            dev_props = dict()
            nic_model = nic_params.get("nic_model")
            # Handle the '-net nic' part
            if self._params.get("machine_type") != "q35":
                pcie = False
            else:
                pcie = nic_model not in ["e1000", "rtl8139"]
            dev_bus = self._get_pci_bus(nic_params, "nic", pcie)

            if nic_model == "none":
                return {}

            # -device
            if self._has_option("device"):
                if not nic_model:
                    nic_model = "rtl8139"
                elif nic_model == "virtio":
                    machine_type = self._params.get("machine_type")
                    if "s390" in machine_type:
                        nic_model = "virtio-net-ccw"
                    elif "-mmio:" in machine_type:
                        nic_model = "virtio-net-device"
                    else:
                        nic_model = "virtio-net-pci"

                ctrl_mac_addr = nic_params.get("ctrl_mac_addr"),
                if ctrl_mac_addr and ctrl_mac_addr in ["on", "off"]:
                    dev_props["ctrl_mac_addr"] = ctrl_mac_addr

                dev_mac = nic_params.get("mac")
                # LOG.debug("Generating random mac address for nic")
                # dev_mac = self._node.proxy.network.generate_mac_address()

                # only pci domain=0,bus=0,function=0 is supported for now.
                #
                # libvirt gains the pci_slot, free_pci_addr here,
                # value by parsing the xml file, i.e. counting all the
                # pci devices and store the number.
                if nic_model != "spapr-vlan":
                    dev_addr = nic_params.get("nic_pci_addr")

                nic_extra_params = nic_params.get("bootindex")
                if nic_extra_params:
                    nic_extra_params = (
                        _.split("=", 1) for _ in nic_extra_params.split(",") if _
                    )
                    for key, val in nic_extra_params:
                        dev_props[key] = val

                dev_props["bootindex"] = nic_params.get("bootindex")
                arch = self._node.proxy.platform.get_arch()
                if "aarch64" in self._params.get("vm_arch_name", arch):
                    model_opts = self._node.proxy.virt.tools.qemu.get_help_info(
                        "-device %s," % nic_model)
                    if "rombar" in model_opts:
                        dev_props["rombar"] = 0

                romfile = nic_params.get("romfile")
                if romfile:
                    dev_props["romfile"] = romfile
            else:  # TODO: -net part
                pass
                # dev = qdevices.QCustomDevice("net", backend="type")
                # dev.set_param("type", "nic")
                # dev.set_param("model", model)
                # dev.set_param("macaddr", mac, "NEED_QUOTE", True)

            dev["id"] = utils_misc.generate_random_id()
            # if "virtio" in nic_model:
            #     if int(queues) > 1:
            #         mq = "on" if mq is None else mq
            #         dev.set_param("mq", mq)
            #     if vectors:
            #         dev.set_param("vectors", vectors)
            #     if failover:
            #         dev.set_param("failover", failover)
            # if devices.has_option("netdev"):
            #     dev.set_param("netdev", netdev_id)
            # else:
            #     dev.set_param("vlan", vlan)

            dev["type"] = nic_model
            dev["bus"] = dev_bus
            dev["addr"] = dev_addr
            dev["mac"] = dev_mac
            dev["props"] = dev_props

            return dev

        def _define_backend_spec(nettype):
            backend = dict()
            backend_props = dict()
            vhostdev = None

            if nettype in ["bridge", "network", "macvtap"]:
                mode = "tap"
            elif nettype == "user":
                mode = "user"
            elif nettype == "user:passt":
                mode = "stream"
                backend_props["rules"] = nic_params.get("net_port_forwards")
                backend_props["mtu"] = nic_params.get("net_mtu")
            elif nettype == "vdpa":
                mode = "vhost-vdpa"
                netdst = nic_params.get("netdst")
                vhostdev = self._node.proxy.vdpa.get_vdpa_dev_file_by_name(
                    netdst)
            else:
                LOG.warning("Unknown/unsupported nettype %s" % nettype)
                return {}

            backend["type"] = mode
            backend["id"] = utils_misc.generate_random_id()
            script = nic_params.get("nic_script")
            downscript = nic_params.get("nic_downscript")
            vhost = nic_params.get("vhost")
            vhostforce = nic_params.get("vhostforce")
            tftp = nic_params.get("tftp")
            bootfile = nic_params.get("bootfile")
            queues = nic_params.get("queues", 1)
            add_queues = nic_params.get("add_queues", "no") == "yes"
            add_tapfd = nic_params.get("add_tapfd", "no") == "yes"
            add_vhostfd = nic_params.get("add_vhostfd", "no") == "yes"
            helper = nic_params.get("helper")
            tapfds_len = int(nic_params.get("tapfds_len", -1))
            vhostfds_len = int(nic_params.get("vhostfds_len", -1))

            net_dst = nic_params.get("netdst")

            nic_params["nettype"] = "linux_bridge"
            nic_res_name = f"{self._name}_{self._nic}"
            nic_res_config = resmgr.define_resource_config(nic_res_name,
                                                           "port", nic_params)
            nic_res_id = resmgr.create_resource_object(nic_res_config)

            resmgr.update_resource(nic_res_id, {"bind": {"nodes": [self._node.name]}})
            resmgr.update_resource(nic_res_id, {"allocate": {"node_name": self._node.name}})
            # resmgr.update_resource(nic_res_id, {"sync": {"node_name": self._node.name}})

            # FIXME: save the port resource as the prot_source of the backend props
            backend_props["port_source"] = nic_res_id
            out = resmgr.get_resource_info(nic_res_id, request=None)
            ifname = None
            fds = None

            # ifname = out["spec"]["ifname"]
            # fds = out["spec"]["fds"]


            # ifname = nic_params.get("ifname", "tap0")  # FIXME:

            # if ifname in self._node.proxy.network.get_interfaces():
            #     self._node.proxy.network.delete_port_from_bridege(net_dst,
            #                                                       ifname)
            # tapfds = self._node.proxy.network.setup_tap_bridge(net_type,
            #                                                    ifname,
            #                                                    net_dst,
            #                                                    queues)
            # LOG.debug("Get tapfds: %s", tapfds)
            # LOG.debug("List all the interfaces: %s", self._node.proxy.network.get_interfaces())
            # if not tapfds:
            #     LOG.error("No tapfds")

            # vhostfds = []
            # if (nic_params.get("vhost") in ["on", "force", "vhost=on"]) and (
            #         nic_params.get("enable_vhostfd", "yes") == "yes"
            # ):
            #     for i in xrange(int(queues)):
            #         vhostfds.append(str(os.open("/dev/vhost-net", os.O_RDWR)))
            #     vhostfds = ":".join(vhostfds)
            # elif net_type == "user":
            #     LOG.info(
            #         "Assuming dependencies met for "
            #         "user mode nic %s, and ready to go" % nic_name
            #     )
            #
            # if vhostfds and vhostfds_len > -1:
            #     vhostfd_list = re.split(":", vhostfds)
            #     if vhostfds_len < len(vhostfd_list):
            #         vhostfds = ":".join(vhostfd_list[:vhostfds_len])
            # if tapfds and tapfds_len > -1:
            #     tapfd_list = re.split(":", tapfds)
            #     if tapfds_len < len(tapfd_list):
            #         tapfds = ":".join(tapfd_list[:tapfds_len])

            if self._has_option("netdev"):
                vhost = None
                if vhost:
                    if vhost in ["on", "off"]:
                        backend_props["vhost"] = vhost
                    elif vhost == "vhost=on":  # Keeps compatibility with old.
                        backend_props["vhost"] = "on"
                    # if vhostfds:
                    #     if int(queues) > 1 and "vhostfds=" in self._qemu_help:
                    #         backend_props["vhostfds"] = vhostfds
                    #     else:
                    #         txt = ""
                    #         if int(queues) > 1:
                    #             txt = "qemu do not support vhost multiqueue,"
                    #             txt += " Fall back to single queue."
                    #         if "vhostfd=" in self._qemu_help:
                    #             backend_props["vhostfd"] = vhostfds.split(":")[0]
                    #         else:
                    #             txt += " qemu do not support vhostfd."
                    #         if txt:
                    #             LOG.warning(txt)
                        # For negative test
                        # if add_vhostfd:
                        #     dev.set_param("vhostfd", vhostfds.split(":")[0])

                if vhostforce in ["on", "off"]:
                    backend_props["vhostforce"] = "on"

                netdev_extra_params = nic_params.get("netdev_extra_params")
                if netdev_extra_params:
                    for netdev_param in netdev_extra_params.strip(",").split(","):
                        arg_k, arg_v = netdev_param.split("=", 1)
                        backend_props["arg_k"] = arg_k
            # else:
            #     dev = qdevices.QCustomDevice(
            #         "net", {"id": netdev_id, "type": mode, "vlan": vlan}
            #     )
            if mode == "tap":
                if script:
                    backend_props["script"] = script
                    backend_props["downscript"] = downscript
                    if ifname:
                        backend_props["ifname"] = ifname
                else: #  FIXME: hardcode
                    if int(queues) > 1 and ",fds=" in self._qemu_help:
                        # backend_props["fds"] = "port_a"
                        if fds:
                            backend_props["fds"] = fds
                    else:
                        # backend_props["fd"] = "port_a"
                        if fds:
                            backend_props["fd"] = fds[0]
                # elif tapfds:
                #     if int(queues) > 1 and ",fds=" in self._qemu_help:
                #         backend_props["fds"] = tapfds
                #     else:
                #         backend_props["fd"] = tapfds.split(":")[0]
                #     # For negative test
                #     if add_tapfd:
                #         backend_props["fd"] = tapfds.split(":")[0]
            elif mode == "user":
                if tftp and "[,tftp=" in self._qemu_help:
                    backend_props["tftp"] = tftp
                if bootfile and "[,bootfile=" in self._qemu_help:
                    backend_props["bootfile"] = bootfile
                # if "[,hostfwd=" in self._qemu_help:
                #     fwd_array = [
                #         f"tcp::{host_port}-:{guest_port}"
                #         for host_port, guest_port in hostfwd
                #     ]
                #     if isinstance(dev, qdevices.QNetdev):
                #         dev.set_param("hostfwd", fwd_array, dynamic=True)
                #     else:
                #         dev.set_param("hostfwd", ",hostfwd=".join(fwd_array))
            # elif mode == "stream":
            #     dev.set_param("addr.type", "unix")
            #     dev.set_param("addr.path", sock_path)
            #     dev.set_param("server", "off")
            elif mode == "vhost-vdpa":
                backend_props["vhostdev"] = vhostdev

            if add_queues and queues:
                backend_props["queues"] = nic_params.get("queues")

            if helper:
                backend_props["helper"] = nic_params.get("helper")

            backend["props"] = backend_props
            return backend

        net = dict()
        nic_name = self._nic
        nic_params = self._params.object_params(nic_name)
        net_type = nic_params.get("nettype", "bridge")
        net_device = _define_device_spec()
        net_backend = _define_backend_spec(net_type)

        net["id"] = nic_name
        net["type"] = net_type
        net["device"] = net_device
        net["backend"] = net_backend
        return net

    def _parse_params(self):
        self._spec.update({"nets": [self._define_spec()]})


class QemuSpecNets(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecNets, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for nic_name in self._params.objects("nics"):
            self._specs.append(QemuSpecNet(self._name, self._params,
                                           self._node.tag, nic_name))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"nets": [net.spec["nets"][0] for net in self._specs]})
