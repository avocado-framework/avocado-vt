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

from virttest.utils_params import Params
from avocado.utils import process

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec

LOG = logging.getLogger("avocado." + __name__)


class QemuSpecMonitor(QemuSpec):
    def __init__(self, name, vt_params, node, monitor_name):
        super(QemuSpecMonitor, self).__init__(name, vt_params, node)
        self._monitor_name = monitor_name
        self._parse_params()

    def _define_spec(self):
        monitor = dict()
        monitor_name = self._monitor_name
        monitor_params = self._params.object_params(monitor_name)
        monitor["id"] = "qmp_id_%s" % monitor_name
        monitor["type"] = monitor_params.get("monitor_type")

        monitor_props = dict()
        monitor_backend = dict()
        monitor_backend_props = dict()
        # FIXME: hardcoded here
        monitor_filename = "/tmp/monitor-%s-%s" % (monitor_name, self._name)
        # monitor_backend_props["filename"] = monitor_filename

        if monitor["type"] == "qmp":
            if not self._has_option("qmp"):
                LOG.warning(
                    "Fallback to human monitor since qmp is" " unsupported")
                monitor["type"] = "hmp"
            elif not self._has_option("chardev"):
                monitor_props["filename"] = monitor_filename
            else:
                # Define qmp specification
                monitor_backend["type"] = monitor_params.get("chardev_backend",
                                                             "unix_socket")
                monitor_backend["id"] = "qmp_id_%s" % monitor_name
                if monitor_backend["type"] == "tcp_socket":
                    host = monitor_params.get("chardev_host", "127.0.0.1")
                    port = str(
                        self._node.proxy.network.find_free_ports(5000, 6000, 1,
                                                                 host)[0])
                    # monitor_backend_props["host"] = host
                    # monitor_backend_props["port"] = port
                    self._params["chardev_host_%s" % monitor_name] = host
                    self._params["chardev_port_%s" % monitor_name] = port
                elif monitor_backend["type"] == "unix_socket":
                    self._params[
                        "monitor_filename_%s" % monitor_name] = monitor_filename
                    # monitor_backend_props["filename"] = monitor_filename
                else:
                    raise ValueError(
                        "Unsupported chardev backend: %s" % monitor_backend[
                            "type"])
                monitor_props["mode"] = "control"

        else:
            if not self._has_option("chardev"):
                monitor_props["filename"] = monitor_filename
            else:
                # Define hmp specification
                monitor_backend["type"] = monitor_params.get("chardev_backend",
                                                             "unix_socket")
                monitor_backend["id"] = "hmp_id_%s" % monitor_name
                if monitor_backend["type"] != "unix_socket":
                    raise NotImplementedError(
                        "human monitor don't support backend" " %s" %
                        monitor_backend["type"]
                    )
                self._params[
                    "monitor_filename_%s" % monitor_name] = monitor_filename
                # monitor_backend_props["filename"] = monitor_filename
                monitor_props["mode"] = "readline"

        # Define the chardev specification
        params = self._params.object_params(monitor_name)
        chardev_id = monitor_backend["id"]
        file_name = self._params["monitor_filename_%s" % monitor_name]
        backend = params.get("chardev_backend", "unix_socket")
        # for tcp_socket and unix_socket, both form to 'socket'
        _backend = "socket" if "socket" in backend else backend
        # Generate -chardev device
        chardev_param = Params({"backend": _backend})
        if backend in [
            "unix_socket",
            "file",
            "pipe",
            "serial",
            "tty",
            "parallel",
            "parport",
        ]:
            chardev_param.update({"path": file_name})
            if backend == "pipe" and params.get("auto_create_pipe",
                                                "yes") == "yes":
                # FIXME: skip to support multiple hosts at this moment
                process.system("mkfifo %s" % file_name)
            if backend == "unix_socket":
                chardev_param.update(
                    {
                        "abstract": params.get("chardev_abstract"),
                        "tight": params.get("chardev_tight"),
                    }
                )
        elif backend in ["udp", "tcp_socket"]:
            chardev_param.update(
                {
                    "host": params["chardev_host"],
                    "port": params["chardev_port"],
                    "ipv4": params.get("chardev_ipv4"),
                    "ipv6": params.get("chardev_ipv6"),
                }
            )
        if backend == "tcp_socket":
            chardev_param.update({"to": params.get("chardev_to")})
        if "socket" in backend:  # tcp_socket & unix_socket
            chardev_param.update(
                {
                    "server": params.get("chardev_server", "on"),
                    "wait": params.get("chardev_wait", "off"),
                }
            )
        elif backend in ["spicevmc", "spiceport"]:
            chardev_param.update(
                {
                    "debug": params.get("chardev_debug"),
                    "name": params.get("chardev_name"),
                }
            )
        elif "ringbuf" in backend:
            chardev_param.update(
                {"ringbuf_write_size": int(
                    params.get("ringbuf_write_size"))}
            )
        monitor_backend_props.update({k: v for k, v in chardev_param.items()})
        monitor_backend["props"] = monitor_backend_props
        monitor["props"] = monitor_props
        monitor["backend"] = monitor_backend
        return monitor

    def _parse_params(self):
        self._spec.update(self._define_spec())


class QemuSpecMonitors(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecMonitors, self).__init__(name, vt_params, node)
        self._monitors = []
        self._parse_params()

    def _define_spec(self):
        catch_monitor = self._params.get("catch_monitor")
        if catch_monitor:
            if catch_monitor not in self._params.get("monitors"):
                self._params["monitors"] += " %s" % catch_monitor

        for monitor_name in self._params.objects("monitors"):
            self._monitors.append(QemuSpecMonitor(self._name, self._params,
                                                  self._node.tag, monitor_name))

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"monitors": [monitor.spec for monitor in self._monitors]})
