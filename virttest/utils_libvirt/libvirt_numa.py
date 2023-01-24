"""
Module simplifying manipulation of numa & hmat related part described at
http://libvirt.org/formatdomain.html
"""


import logging
import ast

from avocado.core import exceptions

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


def parse_numa_nodeset_to_str(numa_nodeset, node_list, ignore_error=False):
    """
    Parse numa nodeset to a string

    :param numa_nodeset: str, formats supported are 'x', 'x,y', 'x-y', 'x-y,^y'
    :param node_list: list, host numa nodes
    :param ignore_error: no exception raised if True
    :return: str, parsed numa nodeset
    :raises exceptions.TestError if unsupported format of numa nodeset
    """

    def _get_first_continuous_numa_node_index(node_list):
        """
        Get the first continues numa node index
        For example:
        If node list is [0, 1, 3, 4], return 0
        If node list is [0, 2, 3, 5], return 1
        If node list is [1, 4, 8], return -1

        :param node_list: list, the host numa node list
        :return: int, the first index of continuous numa node or -1 if not exists
        """
        for index in range(0, len(node_list) - 1):
            if node_list[index] + 1 == node_list[index + 1]:
                return index
        return -1

    LOG.debug("numa_nodeset='%s', node_list=%s" % (numa_nodeset, node_list))
    if numa_nodeset == "x":
        numa_nodeset = str(node_list[0])
    elif numa_nodeset == "x,y":
        numa_nodeset = ",".join(map(str, node_list))
    elif numa_nodeset == "x-y":
        candidate_index = _get_first_continuous_numa_node_index(node_list)
        if candidate_index == -1:
            LOG.debug(
                "No continuous numa node, use 'x,y' format instead of 'x-y' format"
            )
            numa_nodeset = ",".join(map(str, node_list))
        else:
            numa_nodeset = "%s-%s" % (
                str(node_list[candidate_index]),
                str(node_list[candidate_index + 1]),
            )
    elif numa_nodeset == "x-y,^y":
        candidate_index = _get_first_continuous_numa_node_index(node_list)
        if candidate_index == -1:
            LOG.debug(
                "No continuous numa node, use 'x,y' format instead of 'x-y' format"
            )
            numa_nodeset = ",".join(map(str, node_list))
        else:
            numa_nodeset = "%s-%s,^%s" % (
                str(node_list[candidate_index]),
                str(node_list[candidate_index + 1]),
                str(node_list[candidate_index + 1]),
            )
    elif ignore_error:
        LOG.error("Supported formats are not found. No parsing happens.")
    else:
        raise exceptions.TestError(
            "Unsupported format for numa_" "nodeset value '%s'" % numa_nodeset
        )

    LOG.debug("Parse output for numa nodeset: '%s'", numa_nodeset)
    return numa_nodeset
