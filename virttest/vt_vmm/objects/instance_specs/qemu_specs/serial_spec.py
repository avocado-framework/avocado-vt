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

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecSerial(QemuSpec):
    def __init__(self, name, vt_params, node, serial):
        super(QemuSpecSerial, self).__init__(name, vt_params, node)
        self._serial = serial
        self._parse_params()

    def _define_spec(self):
        serial = {}
        serial_id = self._serial
        serial_params = self._params.object_params(serial_id)
        serial["id"] = serial_id
        serial["type"] = serial_params.get("serial_type")
        if serial_params["serial_type"].startswith("pci"):
            serial["bus"] = self._get_pci_bus(serial_params, "serial", False)

        serial_props = {}
        bus_extra_params = serial_params.get("virtio_serial_extra_params", "")
        bus_extra_params = dict(
            [_.split("=") for _ in bus_extra_params.split(",") if _])
        for k, v in bus_extra_params.items():
            serial_props[k] = v

        serial_backend = dict()
        backend = serial_params.get("chardev_backend", "unix_socket")
        serial_backend["type"] = backend

        serial_backend_props = dict()
        serial_backend_props["path"] = serial_params.get("chardev_path")
        if backend == "tcp_socket":
            host = serial_params.get("chardev_host", "127.0.0.1")
            serial_backend_props["host"] = host
            serial_backend_props["port"] = (5000, 5899)
            serial_backend_props["ipv4"] = serial_params.get(
                "chardev_ipv4")
            serial_backend_props["ipv6"] = serial_params.get(
                "chardev_ipv6")
            serial_backend_props["to"] = serial_params.get("chardev_to")
            serial_backend_props["server"] = serial_params.get(
                "chardev_server", "on")
            serial_backend_props["wait"] = serial_params.get("chardev_wait",
                                                             "off")

        elif backend == "udp":
            host = serial_params.get("chardev_host", "127.0.0.1")
            serial_backend_props["host"] = host
            serial_backend_props["port"] = (5000, 5899)
            serial_backend_props["ipv4"] = serial_params.get(
                "chardev_ipv4")
            serial_backend_props["ipv6"] = serial_params.get(
                "chardev_ipv6")

        elif backend == "unix_socket":
            serial_backend_props["abstract"] = serial_params.get(
                "chardev_abstract")
            serial_backend_props["tight"] = serial_params.get(
                "chardev_tight")
            serial_backend_props["server"] = serial_params.get(
                "chardev_server", "on")
            serial_backend_props["wait"] = serial_params.get("chardev_wait",
                                                             "off")

        elif backend in ["spicevmc", "spiceport"]:
            serial_backend_props.update(
                {
                    "debug": serial_params.get("chardev_debug"),
                    "name": serial_params.get("chardev_name"),
                }
            )
        elif "ringbuf" in backend:
            serial_backend_props.update(
                {"ringbuf_write_size": int(
                    serial_params.get("ringbuf_write_size"))}
            )
        serial_backend["props"] = serial_backend_props

        prefix = serial_params.get("virtio_port_name_prefix")
        serial_name = serial_params.get("serial_name")
        if not serial_name:
            serial_name = prefix if prefix else serial_id
            serial_props["name"] = serial_name
        serial["props"] = serial_props
        serial["backend"] = serial_backend
        return serial

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecSerials(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecSerials, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for serial_name in self._params.objects("serials"):
            self._specs.append(QemuSpecSerial(self._name, self._params,
                                              self._node.tag, serial_name))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"serials": [serial.spec for serial in self._specs]})
