#
# library for cpu related helper functions
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
# Copyright: IBM (c) 2019
# Author: Satheesh Rajendran <sathnaga@linux.vnet.ibm.com>


import re
import json
import logging
import platform
import time
import os
import xml.etree.ElementTree as ET


from avocado.utils import cpu as utils
from avocado.utils import software_manager
from avocado.utils import process
from avocado.core import exceptions
from virttest import virsh
from virttest import utils_misc
from virttest import libvirt_xml
from virttest.libvirt_xml.xcepts import LibvirtXMLNotFoundError
from virttest import libvirt_version


ARCH = platform.machine()

CPU_TYPES = {"AuthenticAMD": ["EPYC-Rome", "EPYC", "Opteron_G5",
                              "Opteron_G4", "Opteron_G3", "Opteron_G2",
                              "Opteron_G1"],
             "GenuineIntel": ["KnightsMill", "Cooperlake",
                              "Icelake-Server", "Icelake-Server-noTSX",
                              "Icelake-Client", "Icelake-Client-noTSX",
                              "Cascadelake-Server", "Cascadelake-Server-noTSX",
                              "Skylake-Server", "Skylake-Server-noTSX-IBRS",
                              "Skylake-Client", "Skylake-Client-noTSX-IBRS",
                              "Broadwell", "Broadwell-noTSX",
                              "Haswell", "Haswell-noTSX", "IvyBridge",
                              "SandyBridge", "Westmere", "Nehalem",
                              "Penryn", "Conroe"]}
CPU_TYPES_RE = {"EPYC-Rome": "rdpid,wbnoinvd,stibp,clwb,umip",
                "EPYC": "avx2,adx,bmi2,sha_ni",
                "Opteron_G5": "f16c,fma4,xop,tbm",
                "Opteron_G4": ("fma4,xop,avx,xsave,aes,sse4.2|sse4_2,"
                               "sse4.1|sse4_1,cx16,ssse3,sse4a"),
                "Opteron_G3": "cx16,sse4a",
                "Opteron_G2": "cx16",
                "Opteron_G1": "",
                "KnightsMill": "avx512_4vnniw,avx512pf,avx512er",
                "Cooperlake": "avx512_bf16,stibp,arch_capabilities,hle,rtm",
                "Icelake-Server": "avx512_vnni,la57,clflushopt,hle,rtm",
                "Icelake-Server-noTSX": "avx512_vnni,la57,clflushopt",
                "Icelake-Client": ("avx512_vpopcntdq|avx512-vpopcntdq,"
                                   "avx512vbmi,avx512_vbmi2|avx512vbmi2,hle,rtm"
                                   "gfni,vaes,vpclmulqdq,avx512_vnni,hle,rtm"),
                "Icelake-Client-noTSX": ("avx512_vpopcntdq|avx512-vpopcntdq,"
                                         "avx512vbmi,avx512_vbmi2|avx512vbmi2,"
                                         "gfni,vaes,vpclmulqdq,avx512_vnni"),
                "Cascadelake-Server": ("avx512f,avx512dq,avx512bw,avx512cd,"
                                       "avx512vl,clflushopt,avx512_vnni,hle,rtm"),
                "Cascadelake-Server-noTSX": ("avx512f,avx512dq,avx512bw,avx512cd,"
                                             "avx512vl,clflushopt,avx512_vnni"),
                "Skylake-Server": "avx512f,clwb,xgetbv1,pcid,hle,rtm",
                "Skylake-Server-noTSX-IBRS": "avx512f,clwb,xgetbv1,pcid",
                "Skylake-Client": "xgetbv1,pcid,hle,rtm",
                "Skylake-Client-noTSX-IBRS": "xgetbv1,pcid",
                "Broadwell": "adx,rdseed,3dnowprefetch,hle,rtm",
                "Broadwell-noTSX": "adx,rdseed,3dnowprefetch",
                "Haswell": "fma,avx2,movbe,hle,rtm",
                "Haswell-noTSX": "fma,avx2,movbe",
                "IvyBridge": "f16c,fsgsbase,erms",
                "SandyBridge": ("avx,xsave,aes,sse4_2|sse4.2,sse4.1|sse4_1,"
                                "cx16,ssse3"),
                "Westmere": "aes,sse4.2|sse4_2,sse4.1|sse4_1,cx16,ssse3",
                "Nehalem": "sse4.2|sse4_2,sse4.1|sse4_1,cx16,ssse3",
                "Penryn": "sse4.1|sse4_1,cx16,ssse3",
                "Conroe": "ssse3"}


class UnsupportedCPU(exceptions.TestError):
    pass


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
            result = json.loads(json_result.stdout_text)
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
    output = virsh.vcpuinfo(vm.name).stdout_text.rstrip()
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
    host_cpu_count = utils.total_count() if hasattr(utils, 'total_count') else utils.total_cpus_count()
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
        xml_affinity[vcpu['vcpu']] = cpus_string_to_affinity_list(vcpu['cpuset'],
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
    host_cpu_count = utils.total_count() if hasattr(utils, 'total_count') else utils.total_cpus_count()
    result = virsh.vcpupin(vm.name, vcpu=vcpu, options=options, debug=True)
    for vcpu in result.stdout_text.strip().split('\n')[2:]:
        # On newer version of libvirt, there is no ':' in
        # vcpupin output anymore
        vcpupin_output[int(vcpu.split()[0].rstrip(':'))] = vcpu.split()[1]
    for vcpu in vcpupin_output:
        vcpupin_affinity[vcpu] = cpus_string_to_affinity_list(vcpupin_output[vcpu], host_cpu_count)
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
    host_cpu_count = utils.total_count() if hasattr(utils, 'total_count') else utils.total_cpus_count()
    vcpu_pids = vm.get_vcpus_pid()
    for vcpu in range(len(vcpu_pids)):
        output = cpu_allowed_list_by_task(pid, vcpu_pids[vcpu])
        output_affinity = cpus_string_to_affinity_list(output, int(host_cpu_count))
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
    if result.exit_status:
        logging.debug("vcpu count command failed")
        return (result, vcpucount_details)

    if options:
        stdout = result.stdout_text.strip()
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
        output = result.stdout_text.strip().split('\n')
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
    host_cpu_count = utils.total_count() if hasattr(utils, 'total_count') else utils.total_cpus_count()
    affinity_xml = affinity_from_xml(vm)
    affinity_vcpupin = affinity_from_vcpupin(vm)
    affinity_vcpuinfo = affinity_from_vcpuinfo(vm)
    result = True

    for vcpu in list(expect_vcpupin.keys()):
        expect_affinity = cpus_string_to_affinity_list(str(expect_vcpupin[vcpu]), host_cpu_count)
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
    if vcresult.stderr_text:
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
        if cpu_xml['current_vcpu'] != exp_vcpu['cur_config']:
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
    host_cpu_online = utils.online_list() if hasattr(utils, 'online_list') else utils.cpu_online_list()
    cpustats = {}
    if cpu:
        cpustats[cpu] = []
        option = "--start %s --count 1" % cpu
        result = virsh.cpu_stats(vm.name, option)
        if result.exit_status != 0:
            logging.error("cpu stats command failed: %s",
                          result.stderr_text)
            return None
        output = result.stdout_text.strip().split()
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
                              result.stderr_text)
                return None
            output = result.stdout_text.strip().split()
            if re.match("CPU%s" % host_cpu_online[i], output[0]):
                cpustats[host_cpu_online[i]] = [float(output[5]),
                                                float(output[2]) - float(output[5]),
                                                float(output[2])]
    result = virsh.cpu_stats(vm.name, "--total")
    cpustats["total"] = []
    if result.exit_status != 0:
        logging.error("cpu stats command failed: %s",
                      result.stderr_text)
        return None
    output = result.stdout_text.strip().split()
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
    for item in domstats_output.stdout_text.strip().split():
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
        exp_cur_max = exp_vcpu['max_live']
    else:
        exp_cur_vcpu = exp_vcpu['cur_config']
        exp_cur_max = exp_vcpu['max_config']
    if exp_cur_vcpu != cur_vcpu:
        status = False
        logging.error("Mismatch in current vcpu in domstats output, "
                      "Expected: %s Actual: %s", exp_cur_vcpu, cur_vcpu)
    if exp_cur_max != max_vcpu:
        status = False
        logging.error("Mismatch in maximum vcpu in domstats output, Expected:"
                      " %s Actual: %s", exp_cur_max, max_vcpu)

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
        vcpu_hotplug_timeout = 120  # maximum time to wait for a hotplug event to complete
        # 1.5 Check inside the guest
        if not utils_misc.wait_for(lambda: check_if_vm_vcpu_match(exp_vcpu['guest_live'],
                                                                  vm),
                                   vcpu_hotplug_timeout, text="wait for vcpu online"):
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


def guest_numa_check(vm, exp_vcpu):
    """
    To check numa node values

    :param vm: VM object
    :param exp_vcpu: dict of expected vcpus
    :return: True if check succeed, False otherwise
    """
    logging.debug("Check guest numa")
    session = vm.wait_for_login()
    vm_cpu_info = get_cpu_info(session)
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
            node_cpu_xml = cpus_parser(node_cpu_xml)
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
            node_cpu_guest = cpus_parser(node_cpu_guest)
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


def get_thread_cpu(thread):
    """
    Get the light weight process(thread) used cpus.

    :param thread: thread checked
    :type thread: string
    :return: A list include all cpus the thread used
    :rtype: builtin.list
    """
    cmd = "ps -o cpuid,lwp -eL | grep -w %s$" % thread
    cpu_thread = process.run(cmd, shell=True).stdout_text
    if not cpu_thread:
        return []
    return list(set([_.strip().split()[0] for _ in cpu_thread.splitlines()]))


def get_pid_cpu(pid):
    """
    Get the process used cpus.

    :param pid: process id
    :type thread: string
    :return: A list include all cpus the process used
    :rtype: builtin.list
    """
    cmd = "ps -o cpuid -L -p %s" % pid
    cpu_pid = process.run(cmd).stdout_text
    if not cpu_pid:
        return []
    return list(set([_.strip() for _ in cpu_pid.splitlines()]))


def get_cpu_info(session=None):
    """
    Return information about the CPU architecture

    :param session: session Object
    :return: A dirt of cpu information
    """
    cpu_info = {}
    cmd = "lscpu"
    if session is None:
        output = process.run(cmd, ignore_status=True).stdout_text.splitlines()
    else:
        try:
            output = session.cmd_output(cmd).splitlines()
        finally:
            session.close()
    cpu_info = dict(map(lambda x: [i.strip() for i in x.split(":")], output))
    return cpu_info


class Flag(str):

    """
    Class for easy merge cpuflags.
    """
    aliases = {}

    def __new__(cls, flag):
        if flag in Flag.aliases:
            flag = Flag.aliases[flag]
        return str.__new__(cls, flag)

    def __eq__(self, other):
        s = set(self.split("|"))
        o = set(other.split("|"))
        if s & o:
            return True
        else:
            return False

    def __str__(self):
        return self.split("|")[0]

    def __repr__(self):
        return self.split("|")[0]

    def __hash__(self, *args, **kwargs):
        return 0


kvm_map_flags_to_test = {
    Flag('avx'): set(['avx']),
    Flag('sse3|pni'): set(['sse3']),
    Flag('ssse3'): set(['ssse3']),
    Flag('sse4.1|sse4_1|sse4.2|sse4_2'): set(['sse4']),
    Flag('aes'): set(['aes', 'pclmul']),
    Flag('pclmuldq'): set(['pclmul']),
    Flag('pclmulqdq'): set(['pclmul']),
    Flag('rdrand'): set(['rdrand']),
    Flag('sse4a'): set(['sse4a']),
    Flag('fma4'): set(['fma4']),
    Flag('xop'): set(['xop']),
}


kvm_map_flags_aliases = {
    'sse4_1': 'sse4.1',
    'sse4_2': 'sse4.2',
    'pclmuldq': 'pclmulqdq',
    'sse3': 'pni',
    'ffxsr': 'fxsr_opt',
    'xd': 'nx',
    'i64': 'lm',
    'psn': 'pn',
    'clfsh': 'clflush',
    'dts': 'ds',
    'htt': 'ht',
    'CMPXCHG8B': 'cx8',
    'Page1GB': 'pdpe1gb',
    'LahfSahf': 'lahf_lm',
    'ExtApicSpace': 'extapic',
    'AltMovCr8': 'cr8_legacy',
    'cr8legacy': 'cr8_legacy'
}


def kvm_flags_to_stresstests(flags):
    """
    Covert [cpu flags] to [tests]

    :param cpuflags: list of cpuflags
    :return: Return tests like string.
    """
    tests = set([])
    for f in flags:
        tests |= kvm_map_flags_to_test[f]
    param = ""
    for f in tests:
        param += "," + f
    return param


def get_cpu_flags(cpu_info=""):
    """
    Returns a list of the CPU flags
    """
    cpu_flags_re = "flags\s+:\s+([\w\s]+)\n"
    if not cpu_info:
        fd = open("/proc/cpuinfo")
        cpu_info = fd.read()
        fd.close()
    cpu_flag_lists = re.findall(cpu_flags_re, cpu_info)
    if not cpu_flag_lists:
        return []
    cpu_flags = cpu_flag_lists[0]
    return re.split("\s+", cpu_flags.strip())


def get_cpu_vendor(cpu_info="", verbose=True):
    """
    Returns the name of the CPU vendor
    """
    vendor_re = "vendor_id\s+:\s+(\w+)"
    if not cpu_info:
        fd = open("/proc/cpuinfo")
        cpu_info = fd.read()
        fd.close()
    vendor = re.findall(vendor_re, cpu_info)
    if not vendor:
        vendor = 'unknown'
    else:
        vendor = vendor[0]
    if verbose:
        logging.debug("Detected CPU vendor as '%s'", vendor)
    return vendor


def get_recognized_cpuid_flags(qemu_binary="/usr/libexec/qemu-kvm"):
    """
    Get qemu recongnized CPUID flags

    :param qemu_binary: qemu-kvm binary file path
    :return: flags list
    """
    out = process.run("%s -cpu ?" % qemu_binary).stdout.decode(errors='replace')
    match = re.search("Recognized CPUID flags:(.*)", out, re.M | re.S)
    try:
        return list(filter(None, re.split('\s', match.group(1))))
    except AttributeError:
        pass
    return []


def get_host_cpu_models():
    """
    Get cpu model from host cpuinfo
    """
    def _cpu_flags_sort(cpu_flags):
        """
        Update the cpu flags get from host to a certain order and format
        """
        flag_list = sorted(re.split("\s+", cpu_flags.strip()))
        cpu_flags = " ".join(flag_list)
        return cpu_flags

    def _make_up_pattern(flags):
        """
        Update the check pattern to a certain order and format
        """
        pattern_list = sorted(re.split(",", flags.strip()))
        pattern = r"(\b%s\b)" % pattern_list[0]
        for i in pattern_list[1:]:
            pattern += r".+(\b%s\b)" % i
        return pattern

    if ARCH in ('ppc64', 'ppc64le'):
        return []     # remove -cpu and leave it on qemu to decide

    fd = open("/proc/cpuinfo")
    cpu_info = fd.read()
    fd.close()

    cpu_flags = " ".join(get_cpu_flags(cpu_info))
    vendor = get_cpu_vendor(cpu_info)

    cpu_model = None
    cpu_support_model = []
    if cpu_flags:
        cpu_flags = _cpu_flags_sort(cpu_flags)
        for cpu_type in CPU_TYPES.get(vendor):
            pattern = _make_up_pattern(CPU_TYPES_RE.get(cpu_type))
            if re.findall(pattern, cpu_flags):
                cpu_model = cpu_type
                cpu_support_model.append(cpu_model)
    else:
        logging.warn("Can not Get cpu flags from cpuinfo")

    return cpu_support_model


def extract_qemu_cpu_models(qemu_cpu_help_text):
    """
    Get all cpu models from qemu -cpu help text.

    :param qemu_cpu_help_text: text produced by <qemu> -cpu '?'
    :return: list of cpu models
    """
    def check_model_list(pattern):
        cpu_re = re.compile(pattern)
        qemu_cpu_model_list = cpu_re.findall(qemu_cpu_help_text)
        if qemu_cpu_model_list:
            return qemu_cpu_model_list
        else:
            return None

    x86_pattern_list = "x86\s+\[?([a-zA-Z0-9_-]+)\]?.*\n"
    ppc64_pattern_list = "PowerPC\s+\[?([a-zA-Z0-9_-]+\.?[0-9]?)\]?.*\n"
    s390_pattern_list = "s390\s+\[?([a-zA-Z0-9_-]+)\]?.*\n"

    for pattern_list in [x86_pattern_list, ppc64_pattern_list, s390_pattern_list]:
        model_list = check_model_list(pattern_list)
        if model_list is not None:
            return model_list

    e_msg = ("CPU models reported by qemu -cpu ? not supported by avocado-vt. "
             "Please work with us to add support for it")
    logging.error(e_msg)
    for line in qemu_cpu_help_text.splitlines():
        logging.error(line)
    raise UnsupportedCPU(e_msg)


def check_if_vm_vcpu_match(vcpu_desire, vm, connect_uri=None, session=None):
    """
    This checks whether the VM vCPU quantity matches
    the value desired.

    :param vcpu_desire: vcpu value to be checked
    :param vm: VM Object
    :param connect_uri: libvirt uri of target host
    :param session: ShellSession object of VM

    :return: Boolean, True if actual vcpu value matches with vcpu_desire
    """
    release = vm.get_distro(connect_uri=connect_uri)
    if release and release in ['fedora', ]:
        vcpu_actual = vm.get_cpu_count("cpu_chk_all_cmd",
                                       connect_uri=connect_uri)
    else:
        vcpu_actual = vm.get_cpu_count("cpu_chk_cmd",
                                       connect_uri=connect_uri)
    if isinstance(vcpu_desire, str) and vcpu_desire.isdigit():
        vcpu_desire = int(vcpu_desire)
    if vcpu_desire != vcpu_actual:
        logging.debug("CPU quantity mismatched !!! guest said it got %s "
                      "but we assigned %s" % (vcpu_actual, vcpu_desire))
        return False
    logging.info("CPU quantity matched: %s" % vcpu_actual)
    return True


def get_model_features(model_name):
    """
    libvirt-4.5.0 :/usr/share/libvirt/cpu_map.xml defines all CPU models.
    libvirt-5.0.0 :/usr/share/libvirt/cpu_map/ defines all CPU models.
    One CPU model is a set of features.
    This function is to get features of one specific model.

    :params model_name: CPU model name, valid name is given in cpu_map.xml
    :return: feature list, like ['apic', 'ss']

    """
    features = []
    conf = "/usr/share/libvirt/cpu_map.xml"
    conf_dir = "/usr/share/libvirt/cpu_map/"

    try:
        if not libvirt_version.version_compare(5, 0, 0):
            with open(conf, 'r') as output:
                root = ET.fromstring(output.read())
                while True:
                    # Find model in file /usr/share/libvirt/cpu_map.xml
                    for model_n in root.findall('arch/model'):
                        if model_n.get('name') == model_name:
                            model_node = model_n
                            for feature in model_n.findall('feature'):
                                features.append(feature.get('name'))
                            break
                    # Handle nested model
                    if model_node.find('model') is not None:
                        model_name = model_node.find('model').get('name')
                        continue
                    else:
                        break

        else:
            # Find model in dir /usr/share/libvirt/cpu_map
            filelist = os.listdir(conf_dir)
            for file_name in filelist:
                if model_name in file_name:
                    with open(os.path.join(conf_dir, file_name), "r") as output:
                        model = ET.fromstring(output.read())
                        for feature in model.findall("model/feature"):
                            features.append(feature.get('name'))
                        break
    except ET.ParseError as error:
        logging.warn("Configuration file %s has wrong xml format" % conf)
        raise
    except AttributeError as elem_attr:
        logging.warn("No attribute %s in file %s" % (str(elem_attr), conf))
        raise
    except Exception:
        # Other excptions like IOError when open/read configuration file,
        # capture here
        logging.warn("Some other exceptions, like configuration file is not "
                     "found or not file: %s" % conf)
        raise

    return features


def cpus_string_to_affinity_list(cpus_string, num_cpus):
    """
    Parse the cpus_string string to a affinity list.

    e.g
    host_cpu_count = 4
    0       -->     [y,-,-,-]
    0,1     -->     [y,y,-,-]
    0-2     -->     [y,y,y,-]
    0-2,^2  -->     [y,y,-,-]
    r       -->     [y,y,y,y]
    """
    # Check the input string.
    single_pattern = r"\d+"
    between_pattern = r"\d+-\d+"
    exclude_pattern = r"\^\d+"
    sub_pattern = r"(%s)|(%s)|(%s)" % (exclude_pattern,
                                       single_pattern, between_pattern)
    pattern = r"^((%s),)*(%s)$" % (sub_pattern, sub_pattern)
    if not re.match(pattern, cpus_string):
        logging.debug("Cpus_string=%s is not a supported format for cpu_list."
                      % cpus_string)
    # Init a list for result.
    affinity = []
    for i in range(int(num_cpus)):
        affinity.append('-')
    # Letter 'r' means all cpus.
    if cpus_string == "r":
        for i in range(len(affinity)):
            affinity[i] = "y"
        return affinity
    # Split the string with ','.
    sub_cpus = cpus_string.split(",")
    # Parse each sub_cpus.
    for cpus in sub_cpus:
        if "-" in cpus:
            minmum = cpus.split("-")[0]
            maxmum = cpus.split("-")[-1]
            for i in range(int(minmum), int(maxmum) + 1):
                affinity[i] = "y"
        elif "^" in cpus:
            affinity[int(cpus.strip("^"))] = "-"
        else:
            affinity[int(cpus)] = "y"
    return affinity


def cpu_allowed_list_by_task(pid, tid):
    """
    Get the Cpus_allowed_list in status of task.
    """
    cmd = "cat /proc/%s/task/%s/status|grep Cpus_allowed_list:| awk '{print $2}'" % (
        pid, tid)
    result = process.run(cmd, ignore_status=True, shell=True)
    if result.exit_status:
        return None
    return result.stdout_text.strip()


def hotplug_domain_vcpu(vm, count, by_virsh=True, hotplug=True):
    """
    Hot-plug/Hot-unplug vcpu for domian

    :param vm:   VM object
    :param count:    to setvcpus it's the current vcpus number,
                     but to qemu-monitor-command,
                     we need to designate a specific CPU ID.
                     The default will be got by (count - 1)
    :param by_virsh: True means hotplug/unplug by command setvcpus,
                     otherwise, using qemu_monitor
    :param hotplug:  True means hot-plug, False means hot-unplug
    """
    if by_virsh:
        result = virsh.setvcpus(vm.name, count, "--live", debug=True)
    else:
        cmds = []
        cmd_type = "--hmp"
        result = None
        if "ppc" in platform.machine():
            vmxml = libvirt_xml.VMXML.new_from_inactive_dumpxml(vm.name)
            topology = vmxml.get_cpu_topology()
            vcpu_count = vm.get_cpu_count()

            if topology:
                threads = int(topology["threads"])
            else:
                threads = 1
            # test if count multiple of threads
            err_str = "Expected vcpu counts to be multiples of %d" % threads
            if hotplug:
                err_str += ",Invalid vcpu counts for hotplug"
            else:
                err_str += ",Invalid vcpu counts for hotunplug"
            if (count % threads) != 0:
                raise exceptions.TestError(err_str)
            if hotplug:
                for item in range(0, int(count), threads):
                    if item < vcpu_count:
                        continue
                    cmds.append("device_add host-spapr-cpu-core,id=core%d,core-id=%d" % (item, item))
            else:
                for item in range(int(count), vcpu_count, threads):
                    cmds.append("device_del core%d" % item)
        else:
            cmd_type = "--pretty"
            if hotplug:
                cpu_opt = "cpu-add"
            else:
                cpu_opt = "cpu-del"
                # Note: cpu-del is supported currently, it will return error.
                # as follow,
                # {
                #    "id": "libvirt-23",
                #    "error": {
                #        "class": "CommandNotFound",
                #        "desc": "The command cpu-del has not been found"
                #    }
                # }
                # so, the caller should check the result.
            # hot-plug/hot-plug the CPU has maximal ID
            params = (cpu_opt, (count - 1))
            cmds.append('{\"execute\":\"%s\",\"arguments\":{\"id\":%d}}' % params)
        # Execute cmds to hot(un)plug
        for cmd in cmds:
            result = virsh.qemu_monitor_command(vm.name, cmd, cmd_type,
                                                debug=True)
            if result.exit_status != 0:
                raise exceptions.TestFail(result.stderr_text)
            else:
                logging.debug("Command output:\n%s",
                              result.stdout_text.strip())
    return result


def cpus_parser(cpulist):
    """
    Parse a list of cpu list, its syntax is a comma separated list,
    with '-' for ranges and '^' denotes exclusive.
    :param cpulist: a list of physical CPU numbers
    """
    hyphens = []
    carets = []
    commas = []
    others = []

    if cpulist is None:
        return None

    else:
        if "," in cpulist:
            cpulist_list = re.split(",", cpulist)
            for cpulist in cpulist_list:
                if "-" in cpulist:
                    tmp = re.split("-", cpulist)
                    hyphens = hyphens + list(range(int(tmp[0]), int(tmp[-1]) + 1))
                elif "^" in cpulist:
                    tmp = re.split("\^", cpulist)[-1]
                    carets.append(int(tmp))
                else:
                    try:
                        commas.append(int(cpulist))
                    except ValueError:
                        logging.error("The cpulist has to be an "
                                      "integer. (%s)", cpulist)
        elif "-" in cpulist:
            tmp = re.split("-", cpulist)
            hyphens = list(range(int(tmp[0]), int(tmp[-1]) + 1))
        elif "^" in cpulist:
            tmp = re.split("^", cpulist)[-1]
            carets.append(int(tmp))
        else:
            try:
                others.append(int(cpulist))
                return others
            except ValueError:
                logging.error("The cpulist has to be an "
                              "integer. (%s)", cpulist)

        cpus_set = set(hyphens).union(set(commas)).difference(set(carets))

        return sorted(list(cpus_set))


def get_qemu_cpu_models(qemu_binary):
    """Get listing of CPU models supported by QEMU
    Get list of CPU models by parsing the output of <qemu> -cpu '?'
    """
    cmd = qemu_binary + " -cpu '?'"
    result = process.run(cmd, verbose=False)
    return extract_qemu_cpu_models(result.stdout_text)


def get_qemu_best_cpu_model(params):
    """
    Try to find out the best CPU model available for qemu.

    This function can't be in qemu_vm, because it is used in env_process,
    where there's no vm object available yet, and env content is synchronized
    in multi host testing.

    1) Get host CPU model
    2) Verify if host CPU model is in the list of supported qemu cpu models
    3) If so, return host CPU model
    4) If not, return the default cpu model set in params, if none defined,
        return 'qemu64'.
    """
    host_cpu_models = get_host_cpu_models()
    qemu_binary = utils_misc.get_qemu_binary(params)
    qemu_cpu_models = get_qemu_cpu_models(qemu_binary)
    # Let's try to find a suitable model on the qemu list
    for host_cpu_model in host_cpu_models:
        if host_cpu_model in qemu_cpu_models:
            return host_cpu_model
    # If no host cpu model can be found on qemu_cpu_models, choose the default
    return params.get("default_cpu_model", None)
