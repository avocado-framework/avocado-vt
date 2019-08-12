#
# library for hotplug(cpu) related helper functions
# can be extended to memory related helper functions aswell
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


import re
import json
import logging
import platform
import time

from virttest import virsh
from virttest import libvirt_xml
from virttest import utils_misc
from virttest import utils_test
from virttest.utils_test import libvirt
from virttest.libvirt_xml.devices import memory
from virttest.libvirt_xml.xcepts import LibvirtXMLNotFoundError
from virttest.compat_52lts import results_stdout_52lts, results_stderr_52lts
from avocado.utils import cpu as utils
from avocado.utils import software_manager
from avocado.utils import process


def get_cpu_xmldata(vm, options=""):
    """
    Return the vcpu count details from guest xml

    :param vm: vm object
    :param options: VM options

    :return: vcpu count details on xml
    """
    cpu_xmldata = {'current_vcpu': 0, 'vcpu': None,
                   'mtype': None, 'vcpus': None}
    # Grab a dump of the guest - if we're using the --config,
    # then get an --inactive dump.
    extra_opts = ""
    if "--config" in options or vm.is_dead():
        extra_opts = "--inactive"
    vm_xml = libvirt_xml.VMXML.new_from_dumpxml(vm.name, extra_opts)
    cpu_xmldata['mtype'] = vm_xml.os.machine
    try:
        cpu_xmldata['current_vcpu'] = int(vm_xml.current_vcpu)
    except LibvirtXMLNotFoundError:
        logging.debug("current vcpu value not present in xml, set as max value")
        cpu_xmldata['current_vcpu'] = int(vm_xml.vcpu)
    cpu_xmldata['vcpu'] = int(vm_xml.vcpu)
    return cpu_xmldata


def hotplug_supported(vm_name, mtype):
    """
    hotplug support check for ppc64le

    :param vm_name: VM name
    :param mtype: machine type

    :return: True if supported and False in all other cases
    """
    supported = False
    if "ppc64" in platform.machine():
        cmd = '{\"execute\":\"query-machines\"}'
        json_result = virsh.qemu_monitor_command(vm_name, cmd, "--pretty",
                                                 debug=False)
        try:
            result = json.loads(results_stdout_52lts(json_result))
        except Exception:
            # Failure to parse json output and default support to False
            # TODO: Handle for failure cases
            return supported
        for item in result['return']:
            try:
                if item['name'] == mtype:
                    try:
                        if item['hotpluggable-cpus'] == 'True':
                            supported = True
                    except KeyError:
                        pass
            except KeyError:
                pass
    else:
        # For now returning for other arch by default true
        supported = True
    return supported


def affinity_from_vcpuinfo(vm):
    """
    Returns list of the vcpu's affinity from
    virsh vcpuinfo output

    :param vm: VM object

    :return: affinity list of VM
    """
    output = results_stdout_52lts(virsh.vcpuinfo(vm.name)).rstrip()
    affinity = re.findall('CPU Affinity: +[-y]+', output)
    total_affinity = [list(vcpu_affinity.split()[-1].strip())
                      for vcpu_affinity in affinity]
    return total_affinity


def affinity_from_xml(vm):
    """
    Returns dict of the vcpu's affinity from
    guest xml

    :param vm: VM object

    :return: dict of affinity of VM
    """
    host_cpu_count = utils.total_cpus_count()
    xml_affinity_list = []
    xml_affinity = {}
    try:
        vmxml = libvirt_xml.VMXML.new_from_dumpxml(vm.name)
        xml_affinity_list = vmxml['cputune'].vcpupins
    except LibvirtXMLNotFoundError:
        logging.debug("No <cputune> element find in domain xml")
        return xml_affinity
    # Store xml_affinity_list to a dict
    for vcpu in xml_affinity_list:
        xml_affinity[vcpu['vcpu']] = libvirt.cpus_string_to_affinity_list(vcpu['cpuset'],
                                                                          host_cpu_count)
    return xml_affinity


def affinity_from_vcpupin(vm, vcpu=None, options=None):
    """
    Returns dict of vcpu's affinity from virsh vcpupin output

    :param vm: VM object
    :param vcpu: virtual cpu to qeury
    :param options: --live, --current or --config
    :return: dict of affinity of VM
    """
    vcpupin_output = {}
    vcpupin_affinity = {}
    host_cpu_count = utils.total_cpus_count()
    result = virsh.vcpupin(vm.name, vcpu=vcpu, options=options, debug=True)
    for vcpu in results_stdout_52lts(result).strip().split('\n')[2:]:
        # On newer version of libvirt, there is no ':' in
        # vcpupin output anymore
        vcpupin_output[int(vcpu.split()[0].rstrip(':'))] = vcpu.split()[1]
    for vcpu in vcpupin_output:
        vcpupin_affinity[vcpu] = libvirt.cpus_string_to_affinity_list(
            vcpupin_output[vcpu], host_cpu_count)
    return vcpupin_affinity


def affinity_from_proc(vm):
    """
    Return dict of affinity from proc

    :param vm: VM object

    :return: dict of affinity of VM
    """
    pid = vm.get_pid()
    proc_affinity = {}
    vcpu_pids = []
    host_cpu_count = utils.total_cpus_count()
    vcpu_pids = vm.get_vcpus_pid()
    for vcpu in range(len(vcpu_pids)):
        output = utils_test.libvirt.cpu_allowed_list_by_task(
            pid, vcpu_pids[vcpu])
        output_affinity = utils_test.libvirt.cpus_string_to_affinity_list(
            output,
            int(host_cpu_count))
        proc_affinity[vcpu] = output_affinity
    return proc_affinity


def get_vcpucount_details(vm, options):
    """
    To get vcpucount output

    :param vm: VM object
    :param options: options to passed to vcpucount

    :return: tuple of result and dict of vcpucount output values
    """
    vcpucount_details = {'max_config': None, 'max_live': None,
                         'cur_config': None, 'cur_live': None,
                         'guest_live': None}

    result = virsh.vcpucount(vm.name, options, ignore_status=True,
                             debug=True)
    if results_stderr_52lts(result):
        logging.debug("vcpu count command failed")
        return (result, vcpucount_details)

    if options:
        stdout = results_stdout_52lts(result).strip()
        if 'guest' in options:
            vcpucount_details['guest_live'] = int(stdout)
        elif 'config' in options:
            if 'maximum' in options:
                vcpucount_details['max_config'] = int(stdout)
            else:
                vcpucount_details['cur_config'] = int(stdout)
        elif 'live' in options:
            if 'maximum' in options:
                vcpucount_details['max_live'] = int(stdout)
            else:
                vcpucount_details['cur_live'] = int(stdout)
    else:
        output = results_stdout_52lts(result).strip().split('\n')
        for item in output:
            if ('maximum' in item) and ('config' in item):
                vcpucount_details['max_config'] = int(item.split()[2].strip())
            elif ('maximum' in item) and ('live' in item):
                vcpucount_details['max_live'] = int(item.split()[2].strip())
            elif ('current' in item) and ('config' in item):
                vcpucount_details['cur_config'] = int(item.split()[2].strip())
            elif ('current' in item) and ('live' in item):
                vcpucount_details['cur_live'] = int(item.split()[2].strip())
            else:
                pass
    return (result, vcpucount_details)


def check_affinity(vm, expect_vcpupin):
    """
    Check the affinity of vcpus in various libvirt API output

    :param vm: VM object
    :param expect_vcpupin: Expected affinity details

    :return: True if affinity matches from different virsh API outputs,
             False if not
    """
    host_cpu_count = utils.total_cpus_count()
    affinity_xml = affinity_from_xml(vm)
    affinity_vcpupin = affinity_from_vcpupin(vm)
    affinity_vcpuinfo = affinity_from_vcpuinfo(vm)
    result = True

    for vcpu in list(expect_vcpupin.keys()):
        expect_affinity = libvirt.cpus_string_to_affinity_list(
            str(expect_vcpupin[vcpu]), host_cpu_count)
        # Check for vcpuinfo affinity
        if affinity_vcpuinfo[int(vcpu)] != expect_affinity:
            logging.error("CPU affinity in virsh vcpuinfo output"
                          " is unexpected")
            result = False
        # Check for vcpupin affinity
        if affinity_vcpupin[int(vcpu)] != expect_affinity:
            logging.error("Virsh vcpupin output is unexpected")
            result = False
        # Check for affinity in Domain xml
        if affinity_xml:
            if affinity_xml[vcpu] != expect_affinity:
                logging.error("Affinity in domain XML is unexpected")
                result = False
    if result:
        logging.debug("Vcpupin info check pass")
    return result


def check_vcpucount(vm, exp_vcpu, option="", guest_agent=False):
    """
    To check the vcpu count details from vcpucount API

    :param vm: VM object
    :param exp_vcpu: dict of expected vcpus
    :param option: options to vcpucount API if any
    :param guest_agest: True if need to check inside guest,guest agent present

    :return: True if exp_vcpu matches the vcpucount output, False if not
    """
    result = True
    vcpucount_result = {}
    vcpucount_option = ""
    if option == "--guest" and vm.is_alive() and guest_agent:
        vcpucount_option = "--guest"
    (vcresult, vcpucount_result) = get_vcpucount_details(vm, vcpucount_option)
    if results_stderr_52lts(vcresult):
        result = False
    if vcpucount_option == "--guest" and guest_agent:
        if vcpucount_result['guest_live'] != exp_vcpu['guest_live']:
            logging.error("Virsh vcpucount output is unexpected\nExpected: "
                          "%s\nActual: %s", exp_vcpu, vcpucount_result)
            result = False
    else:
        # Check for config option results
        if vm.is_dead():
            if (exp_vcpu['max_config'] != vcpucount_result['max_config'] or
                    exp_vcpu['cur_config'] != vcpucount_result['cur_config']):
                logging.error("Virsh vcpucount output is unexpected\nExpected"
                              ":%s\nActual:%s", exp_vcpu, vcpucount_result)
                result = False
        else:
            if (exp_vcpu['max_config'] != vcpucount_result['max_config'] or
                    exp_vcpu['max_live'] != vcpucount_result['max_live'] or
                    exp_vcpu['cur_config'] != vcpucount_result['cur_config'] or
                    exp_vcpu['cur_live'] != vcpucount_result['cur_live']):
                logging.error("Virsh vcpucount output is unexpected\n "
                              "Expected:%s\nActual:%s", exp_vcpu,
                              vcpucount_result)
                result = False
    if result:
        logging.debug("Command vcpucount check pass")
    return result


def check_vcpuinfo(vm, exp_vcpu):
    """
    To check vcpu count details from virsh vcpuinfo API

    :param vm: VM object
    :param exp_vcpu: dict of expected vcpu details

    :return: True if exp_vcpu matches the vcpuinfo output, False if not
    """
    result = True
    # Decide based on vm alive status to check actual vcpu count
    if vm.is_alive():
        idx = 'cur_live'
    else:
        idx = 'cur_config'

    affinity_vcpuinfo = affinity_from_vcpuinfo(vm)
    vcpuinfo_num = len(affinity_vcpuinfo)
    if vcpuinfo_num != exp_vcpu[idx]:
        logging.error("Vcpu number in virsh vcpuinfo is unexpected\n"
                      "Expected: %s\nActual: %s", exp_vcpu[idx], vcpuinfo_num)
        result = False
    else:
        logging.debug("Command vcpuinfo check pass")
    return result


def check_xmlcount(vm, exp_vcpu, option):
    """
    To check vcpu count details from guest XML

    :param vm: VM object
    :param exp_vcpu: dict of expected vcpu details
    :param option: VM options

    :return: True if exp_vcpu matches the vcpuinfo output, False if not
    """
    result = True
    cpu_xml = {}
    cpu_xml = get_cpu_xmldata(vm, option)
    if "--config" in option or vm.is_dead():
        exp_key = "cur_config"
    else:
        exp_key = "cur_live"
    if cpu_xml['current_vcpu'] != exp_vcpu[exp_key]:
        logging.error("currrent vcpu number mismatch in xml\n"
                      "Expected: %s\nActual:%s", exp_vcpu[exp_key],
                      cpu_xml['current_vcpu'])
        result = False
    else:
        logging.debug("current vcpu count in xml check pass")
    if cpu_xml['vcpu'] != exp_vcpu['max_config']:
        logging.error("vcpu count mismatch in xml\nExpected: %s\nActual: %s",
                      exp_vcpu['max_config'], cpu_xml['vcpu'])
        result = False
    else:
        logging.debug("vcpu count in xml check pass")
    return result


def get_cpustats(vm, cpu=None):
    """
    Get the cpustats output of a given domain
    :param vm: VM domain
    :param cpu: Host cpu index, default all cpus
    :return: dict of cpu stats values
    result format:
    {0:[vcputime,emulatortime,cputime]
    ..
    'total':[cputime]}
     """
    host_cpu_online = utils.cpu_online_list()
    cpustats = {}
    if cpu:
        cpustats[cpu] = []
        option = "--start %s --count 1" % cpu
        result = virsh.cpu_stats(vm.name, option)
        if result.exit_status != 0:
            logging.error("cpu stats command failed: %s",
                          results_stderr_52lts(result))
            return None
        output = results_stdout_52lts(result).strip().split()
        if re.match("CPU%s" % cpu, output[0]):
            cpustats[cpu] = [float(output[5]),  # vcputime
                             float(output[2]) - float(output[5]),  # emulator
                             float(output[2])]  # cputime

    else:
        for i in range(len(host_cpu_online)):
            cpustats[host_cpu_online[i]] = []
            option = "--start %s --count 1" % host_cpu_online[i]
            result = virsh.cpu_stats(vm.name, option)
            if result.exit_status != 0:
                logging.error("cpu stats command failed: %s",
                              results_stderr_52lts(result))
                return None
            output = results_stdout_52lts(result).strip().split()
            if re.match("CPU%s" % host_cpu_online[i], output[0]):
                cpustats[host_cpu_online[i]] = [float(output[5]),
                                                float(output[2]) - float(output[5]),
                                                float(output[2])]
    result = virsh.cpu_stats(vm.name, "--total")
    cpustats["total"] = []
    if result.exit_status != 0:
        logging.error("cpu stats command failed: %s",
                      results_stderr_52lts(result))
        return None
    output = results_stdout_52lts(result).strip().split()
    cpustats["total"] = [float(output[2])]  # cputime
    return cpustats


def get_domstats(vm, key):
    """
    Get VM's domstats output value for given keyword
    :param vm: VM object
    :param key: keyword for which value is needed
    :return: value string
    """
    domstats_output = virsh.domstats(vm.name)
    for item in results_stdout_52lts(domstats_output).strip().split():
        if key in item:
            return item.split("=")[1]


def check_vcpu_domstats(vm, exp_vcpu):
    """
    Check the cpu values from domstats output
    :param vm: VM object
    :param exp_vcpu: dict of expected vcpus
    :return: True if exp_vcpu matches the domstats output, False if not
    """
    status = True
    cur_vcpu = int(get_domstats(vm, "vcpu.current"))
    max_vcpu = int(get_domstats(vm, "vcpu.maximum"))
    if vm.is_alive():
        exp_cur_vcpu = exp_vcpu['cur_live']
    else:
        exp_cur_vcpu = exp_vcpu['cur_config']
    if exp_cur_vcpu != cur_vcpu:
        status = False
        logging.error("Mismatch in current vcpu in domstats output, "
                      "Expected: %s Actual: %s", exp_cur_vcpu, cur_vcpu)
    if exp_vcpu['max_config'] != max_vcpu:
        status = False
        logging.error("Mismatch in maximum vcpu in domstats output, Expected:"
                      " %s Actual: %s", exp_vcpu['max_config'], max_vcpu)

    return status


def check_vcpu_value(vm, exp_vcpu, vcpupin=None, option="", guest_agent=False):
    """
    Check domain vcpu, including vcpucount, vcpuinfo, vcpupin, vcpu number and
    cputune in domain xml, vcpu number inside the domain.

    :param vm: VM object
    :param exp_vcpu: dict of expect vcpu number:
        exp_vcpu['max_config'] = maximum config vcpu number
        exp_vcpu['max_live'] = maximum live vcpu number
        exp_vcpu['cur_config'] = current config vcpu number
        exp_vcpu['cur_live'] = current live vcpu number
        exp_vcpu['guest_live'] = vcpu number inside the domain
    :param vcpupin: A Dict of expect vcpu affinity
    :param option: Option for virsh commands(setvcpu, setvcpus etc)
    :param guest_agent: True if agent present

    :return: True if the exp_vcpu values matches with virsh API values
            False if not
    """
    final_result = True
    logging.debug("Expect vcpu number: %s", exp_vcpu)

    # 1.1 Check virsh vcpucount output
    if not check_vcpucount(vm, exp_vcpu, option, guest_agent):
        final_result = False

    # 1.2 Check virsh vcpuinfo output
    if not check_vcpuinfo(vm, exp_vcpu):
        final_result = False

    # 1.3 Check affinity from virsh vcpupin,virsh vcpuinfo, xml(cputune)
    if vcpupin:
        if not check_affinity(vm, vcpupin):
            final_result = False

    # 1.4 Check the vcpu count in the xml
    if not check_xmlcount(vm, exp_vcpu, option):
        final_result = False

    if vm.is_alive() and (not vm.is_paused()) and "live" in option:
        # 1.5 Check inside the guest
        if not utils_misc.check_if_vm_vcpu_match(exp_vcpu['guest_live'], vm):
            final_result = False
        # 1.6 Check guest numa
        if not guest_numa_check(vm, exp_vcpu):
            final_result = False
    # 1.7 Check virsh domstats output
    if not check_vcpu_domstats(vm, exp_vcpu):
        final_result = False

    return final_result


def is_qemu_kvm_ma():
    """
    Check if qemu-kvm-ma is installed in host
    """
    sm = software_manager.SoftwareManager()
    return sm.check_installed("qemu-kvm-ma")


def vcpuhotunplug_unsupport_str():
    """
    Check if qemu-kvm-ma is installed and return unsupport err string
    """
    if is_qemu_kvm_ma():
        return "not currently supported"
    else:
        return ""


def create_mem_xml(tg_size, pg_size=None, mem_addr=None, tg_sizeunit="KiB",
                   pg_unit="KiB", tg_node=0, node_mask=0, mem_model="dimm",
                   lb_size=None, lb_sizeunit="Kib", mem_access=None):
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
    :param lb_size: Label size in Target
    :param lb_sizeunit: Label size unit, Default=KiB
    :param mem_access: Value of attrib 'access' of memory
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
    if mem_addr:
        mem_xml.address = mem_xml.new_mem_address(
            **{"attrs": mem_addr})
    if mem_access:
        mem_xml.mem_access = mem_access

    logging.debug("Memory device xml: %s", mem_xml)
    return mem_xml.copy()


def guest_numa_check(vm, exp_vcpu):
    """
    To check numa node values

    :param vm: VM object
    :param exp_vcpu: dict of expected vcpus
    :return: True if check succeed, False otherwise
    """
    logging.debug("Check guest numa")
    session = vm.wait_for_login()
    vm_cpu_info = utils_misc.get_cpu_info(session)
    session.close()
    vmxml = libvirt_xml.VMXML.new_from_dumpxml(vm.name)
    try:
        node_num_xml = len(vmxml.cpu.numa_cell)
    except (TypeError, LibvirtXMLNotFoundError):
        # handle if no numa cell in guest xml, bydefault node 0
        node_num_xml = 1
    node_num_guest = int(vm_cpu_info["NUMA node(s)"])
    exp_num_nodes = node_num_xml
    status = True
    for node in range(node_num_xml):
        try:
            node_cpu_xml = vmxml.cpu.numa_cell[node]['cpus']
            node_cpu_xml = libvirt.cpus_parser(node_cpu_xml)
        except (TypeError, LibvirtXMLNotFoundError):
            try:
                node_cpu_xml = vmxml.current_vcpu
            except LibvirtXMLNotFoundError:
                node_cpu_xml = vmxml.vcpu
            node_cpu_xml = list(range(int(node_cpu_xml)))
        try:
            node_mem_xml = vmxml.cpu.numa_cell[node]['memory']
        except (TypeError, LibvirtXMLNotFoundError):
            node_mem_xml = vmxml.memory
        node_mem_guest = int(vm.get_totalmem_sys(node=node))
        node_cpu_xml_copy = node_cpu_xml[:]
        for cpu in node_cpu_xml_copy:
            if int(cpu) >= int(exp_vcpu["guest_live"]):
                node_cpu_xml.remove(cpu)
        if (not node_cpu_xml) and node_mem_guest == 0:
            exp_num_nodes -= 1
        try:
            node_cpu_guest = vm_cpu_info["NUMA node%s CPU(s)" % node]
            node_cpu_guest = libvirt.cpus_parser(node_cpu_guest)
        except KeyError:
            node_cpu_guest = []
        # Check cpu
        if node_cpu_xml != node_cpu_guest:
            status = False
            logging.error("Mismatch in cpus in node %s: xml %s guest %s", node,
                          node_cpu_xml, node_cpu_guest)
        # Check memory
        if int(node_mem_xml) != node_mem_guest:
            status = False
            logging.error("Mismatch in memory in node %s: xml %s guest %s", node,
                          node_mem_xml, node_mem_guest)
    # Check no. of nodes
    if exp_num_nodes != node_num_guest:
        status = False
        logging.error("Mismatch in numa nodes expected nodes: %s guest: %s", exp_num_nodes,
                      node_num_guest)
    return status


def get_load_per(session=None, iterations=2, interval=10.0):
    """
    Get the percentage of load in Guest/Host
    :param session: Guest Sesssion
    :param iterations: iterations
    :param interval: interval between load calculation
    :return: load of system in percentage
    """
    idle_secs = []
    idle_per = []
    cmd = "cat /proc/uptime"
    for itr in range(iterations):
        if session:
            idle_secs.append(float(session.cmd_output(cmd).strip().split()[1]))
        else:
            idle_secs.append(float(process.system_output(cmd).split()[1]))
        time.sleep(interval)
    for itr in range(iterations - 1):
        idle_per.append((idle_secs[itr + 1] - idle_secs[itr]) / interval)
    return int((1 - (sum(idle_per) / len(idle_per))) * 100)
