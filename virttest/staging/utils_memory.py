from __future__ import division
import re
import math
import logging
import os

from avocado.core import exceptions
from avocado.utils import process

from virttest import kernel_interface


# Returns total memory in kb
def read_from_meminfo(key, session=None):
    """
    wrapper to return value from /proc/meminfo using key

    :param key: filter based on the key
    :param session: ShellSession Object of remote host / guest
    :return: value mapped to the key of type int
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    meminfo = func('grep %s /proc/meminfo' % key)
    return int(re.search(r'\d+', meminfo).group(0))


def memtotal(session=None):
    """
    Method to get the memtotal from /proc/meminfo

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('MemTotal', session=session)


def freememtotal(session=None):
    """
    Method to get the freememtotal from /proc/meminfo

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('MemFree', session=session)


def rounded_memtotal(session=None):
    """
    Method to get total of all physical mem, in kbytes

    :param session: ShellSession Object of remote host / guest
    """
    usable_kbytes = memtotal(session=session)
    # usable_kbytes is system's usable DRAM in kbytes,
    #   as reported by memtotal() from device /proc/meminfo memtotal
    #   after Linux deducts 1.5% to 5.1% for system table overhead
    # Undo the unknown actual deduction by rounding up
    #   to next small multiple of a big power-of-two
    #   eg  12GB - 5.1% gets rounded back up to 12GB
    mindeduct = 0.015  # 1.5 percent
    maxdeduct = 0.055  # 5.5 percent
    # deduction range 1.5% .. 5.5% supports physical mem sizes
    #    6GB .. 12GB in steps of .5GB
    #   12GB .. 24GB in steps of 1 GB
    #   24GB .. 48GB in steps of 2 GB ...
    # Finer granularity in physical mem sizes would require
    #   tighter spread between min and max possible deductions

    # increase mem size by at least min deduction, without rounding
    min_kbytes = int(usable_kbytes / (1.0 - mindeduct))
    # increase mem size further by 2**n rounding, by 0..roundKb or more
    round_kbytes = int(usable_kbytes / (1.0 - maxdeduct)) - min_kbytes
    # find least binary roundup 2**n that covers worst-cast roundKb
    mod2n = 1 << int(math.ceil(math.log(round_kbytes, 2)))
    # have round_kbytes <= mod2n < round_kbytes*2
    # round min_kbytes up to next multiple of mod2n
    phys_kbytes = min_kbytes + mod2n - 1
    phys_kbytes = phys_kbytes - (phys_kbytes % mod2n)  # clear low bits
    return phys_kbytes


def numa_nodes(session=None):
    """
    Method to get total no of numa nodes

    :param session: ShellSession Object of remote host / guest
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    base_path = "/sys/devices/system/node"
    node_avail = func("ls %s | grep 'node'" % base_path).split()
    node_paths = [os.path.join(base_path, each_node) for each_node in node_avail]
    nodes = [int(re.sub(r'.*node(\d+)', r'\1', x)) for x in node_paths]
    return (sorted(nodes))


def node_size(session=None):
    """
    Method to get node size

    :param session: ShellSession Object of remote host / guest
    """
    nodes = max(len(numa_nodes(session=session)), 1)
    return ((memtotal() * 1024) // nodes)


def get_huge_page_size(session=None):
    """
    Method to get huge page size

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('Hugepagesize', session=session)


def get_num_huge_pages(session=None):
    """
    Method to get total no of hugepages

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('HugePages_Total', session=session)


def get_num_huge_pages_free(session=None):
    """
    Method to get free hugepages available

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('HugePages_Free', session=session)


def get_num_huge_pages_rsvd(session=None):
    """
    Method to get reserved hugepage pages

    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('HugePages_Rsvd', session=session)


def get_num_huge_pages_surp(session=None):
    """
    Method to get surplus hugepage pages
    :param session: ShellSession Object of remote host / guest
    """
    return read_from_meminfo('HugePages_Surp', session=session)


def get_num_anon_huge_pages(pid=0, session=None):
    """
    Method to get total no of anon hugepages

    :param pid: pid of the specific process
    :param session: ShellSession Object of remote host / guest
    """
    if int(pid) > 1:
        # get AnonHugePages usage of specified process
        return read_from_smaps(pid, 'AnonHugePages', session=session)
    else:
        # invalid pid, so return AnonHugePages of the host
        return read_from_meminfo('AnonHugePages', session=session)


def get_transparent_hugepage(session=None, regex="[]"):
    """
    Method to get total no of transparent hugepage

    :param regex: regex used to hightlight the selected value
    :param session: ShellSession Object of remote host / guest
    """
    UPSTREAM_THP_PATH = "/sys/kernel/mm/transparent_hugepage"
    RH_THP_PATH = "/sys/kernel/mm/redhat_transparent_hugepage"
    if os.path.isdir(UPSTREAM_THP_PATH):
        thp_path = UPSTREAM_THP_PATH
    elif os.path.isdir(RH_THP_PATH):
        thp_path = RH_THP_PATH
    else:
        raise exceptions.TestFail("transparent hugepage Not supported")
    thp = kernel_interface.SysFS(os.path.join(thp_path, 'enabled'),
                                 session=session)
    return thp.sys_fs_value.strip(regex)


def set_num_huge_pages(num, session=None):
    """
    Method to set no of transparent hugepages

    :param num: value to be set for THP
    :param session: ShellSession Object of remote host / guest
    """
    func = process.system
    if session:
        func = session.cmd_status
    return func('/sbin/sysctl vm.nr_hugepages=%d' % num) == 0


def set_transparent_hugepage(sflag, session=None):
    """
    Method to set THP parameter

    :param sflag:  only can be set always, madvise or never.
    :param session: ShellSession Object of remote host / guest
    """
    flags = ['always', 'madvise', 'never']
    if sflag not in flags:
        raise exceptions.TestFail("specify wrong parameter")
    UPSTREAM_THP_PATH = "/sys/kernel/mm/transparent_hugepage"
    RH_THP_PATH = "/sys/kernel/mm/redhat_transparent_hugepage"
    if os.path.isdir(UPSTREAM_THP_PATH):
        thp_path = UPSTREAM_THP_PATH
    elif os.path.isdir(RH_THP_PATH):
        thp_path = RH_THP_PATH
    else:
        raise exceptions.TestFail("transparent hugepage Not supported")
    thp = kernel_interface.SysFS(os.path.join(thp_path, 'enabled'),
                                 session=session)
    thp.sys_fs_value = sflag
    if sflag not in thp.sys_fs_value:
        raise exceptions.TestFail("setting transparent_hugepage failed")


def drop_caches(session=None):
    """
    Method to write back all dirty pages to disk and clears all the caches

    :param session: ShellSession Object of remote host / guest
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    func("sync")
    # We ignore failures here as this will fail on 2.6.11 kernels.
    drop_caches = kernel_interface.ProcFS("/proc/sys/vm/drop_caches",
                                          session=session)
    drop_caches.proc_fs_value = 3


def read_from_vmstat(key, session=None):
    """
    Get specific item value from vmstat

    :param key: The item you want to check from vmstat
    :type key: String
    :param session: ShellSession Object of remote host / guest
    :return: The value of the item
    :rtype: int
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    vmstat_info = func("cat /proc/vmstat")
    return int(re.findall("%s\s+(\d+)" % key, vmstat_info)[0])


def read_from_smaps(pid, key, session=None):
    """
    Get specific item value from the smaps of a process include all sections.

    :param pid: Process id
    :type pid: String
    :param key: The item you want to check from smaps
    :type key: String
    :param session: ShellSession Object of remote host / guest
    :return: The value of the item in kb
    :rtype: int
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    smaps_info = func('grep %s /proc/%s/smaps' % (key, pid))

    memory_size = 0
    for each_number in re.findall("%s:\s+(\d+)" % key, smaps_info):
        memory_size += int(each_number)

    return memory_size


def read_from_numastat(pid, key, session=None):
    """
    Get the process numastat from numastat output.

    :param pid: pid of the specific process
    :param key: filter based on the key
    :param session: ShellSession Object of remote host / guest
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    cmd = "numastat %s" % pid
    numa_mem = func(cmd).strip()
    mem_line = re.findall(r"^%s.*" % key, numa_mem, re.M)[0]
    return re.findall(r"(\d+.\d+)", mem_line)


def read_from_numa_maps(pid, key, session=None):
    """
    Get the process numa related info from numa_maps. This function
    only use to get the numbers like anon=1.

    :param pid: Process id
    :type pid: String
    :param key: The item you want to check from numa_maps
    :type key: String
    :param session: ShellSession Object of remote host / guest
    :return: A dict using the address as the keys
    :rtype: dict
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    numa_map_info = func("cat /proc/%s/numa_maps" % pid)

    numa_maps_dict = {}
    numa_pattern = r"(^[\dabcdfe]+)\s+.*%s[=:](\d+)" % key
    for address, number in re.findall(numa_pattern, numa_map_info, re.M):
        numa_maps_dict[address] = number

    return numa_maps_dict


def get_buddy_info(chunk_sizes, nodes="all", zones="all", session=None):
    """
    Get the fragement status of the host. It use the same method
    to get the page size in buddyinfo.
    2^chunk_size * page_size
    The chunk_sizes can be string make up by all orders that you want to check
    splited with blank or a mathematical expression with '>', '<' or '='.
    For example:
    The input of chunk_size could be: "0 2 4"
    And the return  will be: {'0': 3, '2': 286, '4': 687}
    if you are using expression: ">=9"
    the return will be: {'9': 63, '10': 225}

    :param chunk_size: The order number shows in buddyinfo. This is not
                       the real page size.
    :type chunk_size: string
    :param nodes: The numa node that you want to check. Default value is all
    :type nodes: string
    :param zones: The memory zone that you want to check. Default value is all
    :type zones: string
    :param session: ShellSession Object of remote host / guest
    :return: A dict using the chunk_size as the keys
    :rtype: dict
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    buddy_info_content = func("cat /proc/buddyinfo")

    re_buddyinfo = "Node\s+"
    if nodes == "all":
        re_buddyinfo += "(\d+)"
    else:
        re_buddyinfo += "(%s)" % "|".join(nodes.split())

    if not re.findall(re_buddyinfo, buddy_info_content):
        logging.warn("Can not find Nodes %s" % nodes)
        return None
    re_buddyinfo += ".*?zone\s+"
    if zones == "all":
        re_buddyinfo += "(\w+)"
    else:
        re_buddyinfo += "(%s)" % "|".join(zones.split())
    if not re.findall(re_buddyinfo, buddy_info_content):
        logging.warn("Can not find zones %s" % zones)
        return None
    re_buddyinfo += "\s+([\s\d]+)"

    buddy_list = re.findall(re_buddyinfo, buddy_info_content)

    if re.findall("[<>=]", chunk_sizes) and buddy_list:
        size_list = list(range(len(buddy_list[-1][-1].strip().split())))
        chunk_sizes = [str(_) for _ in size_list if eval("%s %s" % (_,
                                                                    chunk_sizes))]

        chunk_sizes = ' '.join(chunk_sizes)

    buddyinfo_dict = {}
    for chunk_size in chunk_sizes.split():
        buddyinfo_dict[chunk_size] = 0
        for _, _, chunk_info in buddy_list:
            chunk_info = chunk_info.strip().split()[int(chunk_size)]
            buddyinfo_dict[chunk_size] += int(chunk_info)

    return buddyinfo_dict


def getpagesize(session=None):
    """
    Get system page size

    :param session: ShellSession Object of VM/remote host
    :return: pagesize in kB
    """
    func = process.getoutput
    if session:
        func = session.cmd_output
    return int(func('getconf PAGE_SIZE')) // 1024
