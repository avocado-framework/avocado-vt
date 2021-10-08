#
# library for hotplug(cpu) related helper functions
# can be extended to memory related helper functions as well
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: IBM (c) 2017
# Author: Satheesh Rajendran <sathnaga@linux.vnet.ibm.com>
#         Hariharan T S <harihare@in.ibm.com>


import logging
from virttest.libvirt_xml.devices import memory


LOG = logging.getLogger('avocado.' + __name__)


def create_mem_xml(tg_size, pg_size=None, mem_addr=None, tg_sizeunit="KiB",
                   pg_unit="KiB", tg_node=0, node_mask=0, mem_model="dimm",
                   mem_discard=None, alias=None, lb_size=None,
                   lb_sizeunit="Kib", mem_access=None, uuid=None):
    """
    Create memory device xml.
    Parameters:
    :param tg_size: Target hotplug memory size
    :param pg_size: Source page size in case of hugepages backed.
    :param mem_addr: Memory address to be mapped in guest.
    :param tg_sizeunit: Target size unit, Default=KiB.
    :param pg_unit: Source page size unit, Default=KiB.
    :param tg_node: Target node to hotplug.
    :param node_mask: Source node for hotplug.
    :param mem_model: Memory Model, Default="dimm".
    :param mem_discard: discard, Default="no".
    :param lb_size: Label size in Target
    :param lb_sizeunit: Label size unit, Default=KiB
    :param mem_access: Value of attrib 'access' of memory
    :param uuid: Value of attrib 'uuid' of memory
    :return: Returns a copy of Memory Hotplug xml instance.
    """
    mem_xml = memory.Memory()
    mem_xml.mem_model = mem_model

    if tg_size:
        tg_xml = memory.Memory.Target()
        tg_xml.size = int(tg_size)
        tg_xml.size_unit = tg_sizeunit
        if tg_node != "":
            tg_xml.node = int(tg_node)
        if lb_size:
            lb_xml = memory.Memory.Target.Label()
            lb_xml.size = int(lb_size)
            lb_xml.size_unit = lb_sizeunit
            tg_xml.label = lb_xml
        mem_xml.target = tg_xml
    if pg_size:
        src_xml = memory.Memory.Source()
        src_xml.pagesize = int(pg_size)
        src_xml.pagesize_unit = pg_unit
        src_xml.nodemask = node_mask
        mem_xml.source = src_xml
    if mem_discard:
        mem_xml.mem_discard = mem_discard
    if mem_addr:
        mem_xml.address = mem_xml.new_mem_address(
            **{"attrs": mem_addr})
    if mem_access:
        mem_xml.mem_access = mem_access
    if alias:
        mem_xml.alias = dict(name=alias)
    if uuid:
        mem_xml.uuid = uuid

    LOG.debug("Memory device xml: %s", mem_xml)
    return mem_xml.copy()
