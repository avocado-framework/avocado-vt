#
# Library for memory related helper functions
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
# Copyright: Red Hat (c) 2024 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import math
import re

from avocado.utils import memory, process

from virttest import utils_numeric


def get_usable_memory_size(align=None):
    """
    Sync, then drop host caches, then return host free memory size.

    :param align: MB use to align free memory size.
    :type align: Integer
    :return: host free memory size in MB.
    :rtype: Float
    """
    memory.drop_caches()
    usable_mem = memory.read_from_meminfo("MemFree")
    usable_mem = float(utils_numeric.normalize_data_size("%s KB" % usable_mem))
    if align:
        usable_mem = math.floor(usable_mem / align) * align
    return usable_mem


def get_mem_info(attr="MemTotal"):
    """
    Get memory information attributes in Linux host.

    :param attr: Memory information attribute.
    :type attr: String

    :return: Memory information of attribute in kB.
    :rtype: Integer
    """
    cmd = "grep '%s:' /proc/meminfo" % attr
    output = process.run(cmd, shell=True).stdout_text
    output = re.findall(r"\d+\s\w", output)[0]
    output = float(utils_numeric.normalize_data_size(output, order_magnitude="K"))
    return int(output)


def get_used_mem():
    """
    Get Used memory for Linux.

    :return: Used space memory in M-bytes.
    :rtype: Integer
    """
    cmd = "free -m | grep 'Mem'"
    pattern = r"Mem:\s+(\d+)\s+(\d+)\s+"
    output = process.run(cmd, shell=True).stdout_text
    match = re.search(pattern, output, re.M | re.I)
    used = "%sM" % "".join(match.group(2).split(","))
    used = float(utils_numeric.normalize_data_size(used, order_magnitude="M"))
    return int(used)


def get_cache_mem():
    """
    Get cache memory for Linux.

    :return: Memory cache in M-bytes.
    :rtype: Integer
    """
    cache = "%s kB" % (get_mem_info("Cached") + get_mem_info("Buffers"))
    cache = float(utils_numeric.normalize_data_size(cache, order_magnitude="M"))
    return int(cache)


def get_free_mem():
    """
    Get Free memory for Linux.

    :return: Free space memory in M-bytes.
    :rtype: Integer
    """
    free = "%s kB" % get_mem_info("MemFree")
    free = float(utils_numeric.normalize_data_size(free, order_magnitude="M"))
    return int(free)
