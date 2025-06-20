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

def create_numa_nodes(nodes):
    devs = []
    for node in nodes:
        mem = node.get("mem")
        memdev = node.get("memdev")
        cpus = node.get("cpus")
        nodeid = node.get("nodeid")
        initiator = node.get("initiator")
        numa_cmd = " -numa node"
        if mem is not None:
            numa_cmd += ",mem=%s" % mem
        elif memdev is not None:
            numa_cmd += ",memdev=%s" % memdev
        if cpus is not None:
            cpus = map(lambda x: x.strip(), cpus.split(","))
            cpus = ",".join(map(lambda x: "cpus=%s" % x, cpus))
            numa_cmd += ",%s" % cpus
        if nodeid is not None:
            numa_cmd += ",nodeid=%s" % nodeid
        if initiator is not None:
            numa_cmd += ",initiator=%s" % initiator
        devs.append(qdevices.QStringDevice("numa", cmdline=numa_cmd))
    return devs


def create_numa_dists(dists):
    devs = []
    for dist in dists:
        cmd = " -numa dist,src=%s,dst=%s,val=%s"
        cmd = cmd % (dist["src"], dist["dst"], dist["val"])
        devs.append(qdevices.QStringDevice("numa_dist", cmdline=cmd))
    return devs


def create_numa_cpus(cpus):
    devs = []
    for cpu in cpus:
        numa_cpu_cmd = " -numa cpu,node-id=%s" % cpu.get("node_id")
        options = {
            "drawer-id": cpu.get("drawer_id"),
            "book-id": cpu.get("book_id"),
            "socket-id": cpu.get("socket_id"),
            "die-id": cpu.get("die_id"),
            "cluster-id": cpu.get("cluster_id"),
            "core-id": cpu.get("core_id"),
            "thread-id": cpu.get("thread_id"),
        }
        for key, value in options.items():
            if value is not None:
                numa_cpu_cmd += ",%s=%s" % (key, value)
            devs.append(qdevices.QStringDevice("numa_cpu", cmdline=numa_cpu_cmd))
        return devs

def create_numa_hmat_lbs(hmat_lbs):
    devs = []
    for hmat_lb in hmat_lbs:
        aobject = "%s_hmat_lb" % hmat_lb["target"]
        if "latency" in hmat_lb["data-type"]:
            aobject += "_latency"
        elif "bandwidth" in hmat_lb["data-type"]:
            aobject += "_bandwidth"
        devs.append(qdevices.QCustomDevice(
            "numa", params=hmat_lb, aobject=aobject,backend="hmat_type"))
    return devs

def create_numa_hmat_caches(hmat_caches):
    devs = []
    for hmat_cache in hmat_caches:
        nodeid = hmat_cache["node-id"]
        aobject = "%s_hmat_cache" % nodeid
        aobject += "_level_%s" % hmat_cache["level"]
        devs.append(
            qdevices.QCustomDevice("numa", hmat_cache,
                                   aobject=aobject,
                                   backend="hmat_type"
            )
        )
    return devs
