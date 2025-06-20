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


from virttest.qemu_devices import qdevices


def create_rng_devices(dev_container, rng, parent_bus):
    devs = []

    rng_type = rng.get("type")
    if rng_type == "pci":
        dev_type = "virtio-rng-pci"
        parent_bus = parent_bus
    elif rng_type == "ccw":
        dev_type = "virtio-rng-ccw"
        parent_bus = None
    else:
        raise NotImplementedError(rng_type)

    rng_dev = qdevices.QDevice(dev_type, rng["props"], parent_bus=parent_bus)
    rng_dev.set_param("id", rng["id"])

    rng_backend = rng.get("backend")
    if dev_container.has_device(dev_type):
        if rng_backend:
            if rng_backend.get("type") == "builtin":
                backend_type = "rng-builtin"
            elif rng_backend.get("type") == "random":
                backend_type = "rng-random"
            elif rng_backend.get("type") == "egd":
                backend_type = "rng-egd"
            else:
                raise NotImplementedError

            rng_backend_props = rng_backend.get("props")
            rng_backend_chardev = None
            if rng_backend_props.get("chardev"):
                rng_backend_chardev = rng_backend_props.pop("chardev")
            rng_backend_dev = qdevices.QObject(backend_type, rng_backend_props)
            rng_backend_dev.set_param("id", rng_backend["id"])

            if rng_backend_chardev:
                char_id = rng_backend_chardev.get("id")
                rng_chardev = qdevices.QCustomDevice(
                    dev_type="chardev",
                    params=rng_backend_chardev.get("props"),
                    backend=rng_backend_chardev.get("type"),
                )
                rng_chardev.set_param("id", char_id)
                devs.append(rng_chardev)
                rng_backend_dev.set_param("chardev", rng_chardev.get_qid())

            devs.append(rng_backend_dev)

            rng_dev.set_param("rng", rng_backend_dev.get_qid())
        devs.append(rng_dev)

    return devs
