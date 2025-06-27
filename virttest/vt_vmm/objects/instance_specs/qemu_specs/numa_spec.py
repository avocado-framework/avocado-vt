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
import ast

from virttest import utils_misc

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError


LOG = logging.getLogger("avocado." + __name__)


class QemuSpecNuma(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecNuma, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        numa_total_cpus = 0
        numa_total_mem = 0

        numa = dict()
        nodes = []
        if self._has_option("numa"):
            for numa_node in self._params.objects("guest_numa_nodes"):
                node = dict()
                numa_params = self._params.object_params(numa_node)
                numa_mem = numa_params.get("numa_mem")
                numa_cpus = numa_params.get("numa_cpus")
                numa_nodeid = numa_params.get("numa_nodeid")
                numa_memdev = numa_params.get("numa_memdev")
                numa_initiator = numa_params.get("numa_initiator")
                if numa_mem is not None:
                    numa_total_mem += int(numa_mem)
                if numa_cpus is not None:
                    numa_total_cpus += len(utils_misc.cpu_str_to_list(numa_cpus))
                node["mem"] = numa_mem
                node["cpus"] = numa_mem
                node["nodeid"] = numa_nodeid
                node["memdev"] = numa_memdev
                node["initiator"] = numa_initiator
                nodes.append(node)

        dists = []
        dist = dict()
        if self._has_option("numa dist,.*"):
            for numa_node in self._params.objects("guest_numa_nodes"):
                numa_params = self._params.object_params(numa_node)
                numa_nodeid = numa_params.get("numa_nodeid")
                numa_dist = ast.literal_eval(numa_params.get("numa_dist", "[]"))
                if numa_nodeid is None or not numa_dist:
                    continue
                for dst_distance in numa_dist:
                    dist["src"] = numa_nodeid
                    dist["dst"] = dst_distance[0]
                    dist["val"] = dst_distance[1]
                    dists.append(dist)

        cpus = []
        cpu = dict()
        if self._has_option("numa cpu,.*"):
            for numa_cpu in self._params.objects("guest_numa_cpus"):
                numa_cpu_params = self._params.object_params(numa_cpu)
                numa_cpu_nodeid = numa_cpu_params.get("numa_cpu_nodeid")
                numa_cpu_drawerid = numa_cpu_params.get("numa_cpu_drawerid")
                numa_cpu_bookid = numa_cpu_params.get("numa_cpu_bookid")
                numa_cpu_socketid = numa_cpu_params.get("numa_cpu_socketid")
                numa_cpu_dieid = numa_cpu_params.get("numa_cpu_dieid")
                numa_cpu_clusterid = numa_cpu_params.get("numa_cpu_clusterid")
                numa_cpu_coreid = numa_cpu_params.get("numa_cpu_coreid")
                numa_cpu_threadid = numa_cpu_params.get("numa_cpu_threadid")

                cpu["node_id"] = numa_cpu_nodeid
                cpu["drawer_id"] = numa_cpu_drawerid
                cpu["book_id"] = numa_cpu_bookid
                cpu["socket_id"] = numa_cpu_socketid
                cpu["die_id"] = numa_cpu_dieid
                cpu["cluster_id"] = numa_cpu_clusterid
                cpu["core_id"] = numa_cpu_coreid
                cpu["thread_id"] = numa_cpu_threadid
                cpus.append(cpu)

        hmat_lbs = []
        if self._has_option("numa hmat-lb,.*"):
            for numa_node in self._params.objects("guest_numa_nodes"):
                numa_params = self._params.object_params(numa_node)
                if not numa_params.get("numa_hmat_lb"):
                    continue
                nodeid = numa_params["numa_nodeid"]
                initiator = numa_params.get("numa_hmat_lb_initiator", nodeid)
                for _hmat_lb in numa_params.objects("numa_hmat_lb"):
                    hmat_lb = dict()
                    _parmas = self._params.object_params(_hmat_lb)
                    hmat_lb["target"] = nodeid
                    hmat_lb["initiator"] = initiator
                    hmat_lb["hierarchy"] = _parmas["numa_hmat_lb_hierarchy"]
                    hmat_lb["hmat_type"] = "hmat-lb"
                    hmat_lb["data-type"] = _parmas["numa_hmat_lb_data_type"]
                    if "latency" in hmat_lb["data-type"]:
                        hmat_lb.update({"latency": _parmas["numa_hmat_lb_latency"]})
                    elif "bandwidth" in hmat_lb["data-type"]:
                        hmat_lb.update({"bandwidth": _parmas["numa_hmat_lb_bandwidth"]})
                    hmat_lbs.append(hmat_lb)

        hmat_caches = []
        for numa_node in self._params.objects("guest_numa_nodes"):
            numa_params = self._params.object_params(numa_node)
            if not numa_params.get("numa_hmat_lb"):
                continue

            nodeid = numa_params["numa_nodeid"]

            numa_hmat_caches = numa_params.objects("numa_hmat_caches")
            if numa_hmat_caches:
                for hmat_lb in hmat_lbs:
                    if nodeid == hmat_lb.get("target"):
                        if hmat_lb.get("latency") and hmat_lb.get("bandwidth"):
                            break
                else:
                    raise InstanceSpecError(
                        "Please make sure both hmat-lb bandwidth and "
                        "hmat-lb latency are defined when define hmat-cache."
                    )

            # aobject = "%s_hmat_cache" % nodeid
            for _hmat_cache in numa_hmat_caches:
                hmat_cache = dict()
                hmat_cache_params = numa_params.object_params(_hmat_cache)
                level = hmat_cache_params.get_numeric("numa_hmat_caches_level")
                size = utils_misc.normalize_data_size(
                    hmat_cache_params["numa_hmat_caches_size"], "K"
                )
                hc_params = {
                    "node-id": nodeid,
                    "level": level,
                    "hmat_type": "hmat-cache",
                    "size": str(int(float(size))) + "K",
                    "associativity": hmat_cache_params.get(
                        "numa_hmat_caches_associativity"
                    ),
                    "policy": hmat_cache_params.get("numa_hmat_caches_policy"),
                    "line": hmat_cache_params.get("numa_hmat_caches_line"),
                }
                hmat_cache.update(hc_params)
                hmat_caches.append(hmat_cache)

        if nodes:
            numa["nodes"] = nodes
        if dists:
            numa["dists"] = dists
        if cpus:
            numa["cpus"] = cpus
        if hmat_lbs:
            numa["hmat_lbs"] = hmat_lbs
        if hmat_caches:
            numa["hmat_caches"] = hmat_caches

        return numa

    def _parse_params(self):
        self._spec.update({"numa": self._define_spec()})
