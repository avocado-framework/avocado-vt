"""
Module simplifying manipulation of numa & hmat related part described at
http://libvirt.org/formatdomain.html
"""

import ast
import logging

from virttest.libvirt_xml import vm_xml

LOG = logging.getLogger("avocado." + __name__)


def create_cell_distances_xml(vmxml, params):
    """
    Create cell distances xml for test

    :param vmxml: VMXML instance of the domain
    :param params: dict of the numa cell related parameter pairs
    :return the updated vmxml
    """
    cpu_xml = vmxml.cpu
    i = 0
    cells = []

    for numacell_xml in cpu_xml.numa_cell:
        LOG.debug("numacell_xml:%s" % numacell_xml)
        cell_distances_xml = numacell_xml.CellDistancesXML()
        cell_distances_xml.update({"sibling": eval(params.get("sibling%s" % i))})
        numacell_xml.distances = cell_distances_xml
        i = i + 1
        cells.append(numacell_xml)
    cpu_xml.numa_cell = cells
    LOG.debug("cpu_xml with cell distances added: %s" % cpu_xml)
    vmxml.cpu = cpu_xml
    vmxml.sync()

    return vmxml


def create_hmat_xml(vmxml, params):
    """
    Create hmat xml for test

    :param vmxml: VMXML instance of the domain
    :param params: dict of the hmat related parameter pairs
    :return the updated vmxml
    """
    cpu_xml = vmxml.cpu
    i = 0
    cells = []

    for numacell_xml in cpu_xml.numa_cell:
        LOG.debug("numacell_xml:%s" % numacell_xml)
        caches = []
        cell_caches = params.get("cell_caches%s" % i, "").split()
        cell_cache_list = [ast.literal_eval(x) for x in cell_caches]
        for cell_cache in cell_cache_list:
            cellcache_xml = vm_xml.CellCacheXML()
            cellcache_xml.update(cell_cache)
            LOG.debug("cellcach_xml:%s" % cellcache_xml)
            caches.append(cellcache_xml)
        numacell_xml.caches = caches
        LOG.debug("numacell_xml:%s" % numacell_xml)
        i = i + 1
        cells.append(numacell_xml)
    cpu_xml.numa_cell = cells

    latency_list = eval(params.get("latency", ""))
    bandwidth_list = eval(params.get("bandwidth", ""))
    interconnects_xml = vm_xml.VMCPUXML().InterconnectsXML()
    interconnects_xml.latency = latency_list
    interconnects_xml.bandwidth = bandwidth_list

    cpu_xml.interconnects = interconnects_xml
    LOG.debug("cpu_xml with HMAT configuration added: %s" % cpu_xml)
    vmxml.cpu = cpu_xml
    vmxml.sync()

    return vmxml


def convert_all_nodes_to_string(node_list):
    """
    Convert the node list to a string representation.
    For example:
    If node list is [0, 1, 2, 3, 4], return "0-4"
    If node list is [0, 1, 3, 4, 6], return "0-1,3-4,6"

    :param node_list: list, the host numa node list
    :return: str, the string representation of the node list
    """

    LOG.debug("node_list=%s" % node_list)
    node_ranges = []
    start_node = node_list[0]
    end_node = node_list[0]

    for node in node_list[1:]:
        if node == end_node + 1:
            end_node = node
        else:
            if start_node == end_node:
                node_ranges.append(f"{start_node}")
            else:
                node_ranges.append(f"{start_node}-{end_node}")
            start_node = node
            end_node = node

    if start_node == end_node:
        node_ranges.append(f"{start_node}")
    else:
        node_ranges.append(f"{start_node}-{end_node}")

    converted_numa_nodes = ",".join(node_ranges)
    LOG.debug("Convert output for all online numa nodes: '%s'", converted_numa_nodes)
    return converted_numa_nodes
