"""
Utility classes and functions to handle Virtual Machine creation using libvirt.

:copyright: 2011 Red Hat Inc.
"""

from __future__ import division
import time
import string
import os
import logging
import fcntl
import re
import shutil
import tempfile
import platform

import aexpect
from aexpect import remote

from avocado.utils import process
from avocado.utils import crypto
from avocado.core import exceptions

from virttest import error_context
from virttest import utils_misc
from virttest import cpu
from virttest import virt_vm
from virttest import storage
from virttest import virsh
from virttest import libvirt_xml
from virttest import data_dir
from virttest import xml_utils
from virttest import utils_selinux
from virttest import test_setup
from virttest import utils_package


# Using as lower capital is not the best way to do, but this is just a
# workaround to avoid changing the entire file.
LOG = logging.getLogger('avocado.' + __name__)


def normalize_connect_uri(connect_uri):
    """
    Processes connect_uri Cartesian into something virsh can use

    :param connect_uri: Cartesian Params setting
    :return: Normalized connect_uri
    """
    if connect_uri == "default":
        result = virsh.canonical_uri()
    else:
        result = virsh.canonical_uri(uri=connect_uri)

    if not result:
        raise ValueError("Normalizing connect_uri '%s' failed, is libvirt "
                         "running?" % connect_uri)
    return result


def complete_uri(ip_address, protocol=None, port=None):
    """
    Return a complete URI with the combination of ip_address and local uri.
    It is useful when you need to connect remote hypervisor.

    :param ip_address: an ip address or a hostname
    :param protocol: protocol for uri eg: tcp, spice etc.
    :param port: port for the protocol
    :return: a complete uri
    """
    if protocol and port:
        complete_uri = "%s://%s:%s" % (protocol, ip_address, port)
    else:
        # Allow to raise CmdError if canonical_uri is failed
        uri = virsh.canonical_uri(ignore_status=False)
        driver = uri.split(":")[0]
        # The libvirtd daemon's mode(system or session on qemu)
        daemon_mode = uri.split("/")[-1]
        complete_uri = "%s+ssh://%s/%s" % (driver, ip_address, daemon_mode)
    return complete_uri


def get_uri_with_transport(uri_type='qemu', transport="", dest_ip=""):
    """
    Return a URI to connect driver on dest with a specified transport.

    :param origin_uri: The URI on dest used to connect itself directly.
    :param transport: The transport type connect to dest.
    :param dest_ip: The ip of destination.
    """
    _type2uri_ = {'qemu': "qemu:///system",
                  'qemu_system': "qemu:///system",
                  'qemu_session': "qemu:///session",
                  'lxc': "lxc:///",
                  'xen': "xen:///",
                  'esx': "esx:///"}
    try:
        origin_uri = _type2uri_[uri_type]
    except KeyError:
        raise ValueError("Param uri_type = %s is not supported." % (uri_type))

    # For example:
    #   ("qemu:///system")-->("qemu", "system")
    #   ("lxc:///")-->("lxc", "")
    origin_uri_elems = origin_uri.split(":///")
    transport_uri_driver = origin_uri_elems[0]
    transport_uri_dest = origin_uri_elems[-1]
    if transport:
        transport_uri_driver = ("%s+%s" % (transport_uri_driver, transport))

    transport_uri_dest = ("://%s/%s" % (dest_ip, transport_uri_dest))
    return ("%s%s" % (transport_uri_driver, transport_uri_dest))


class Monitor(object):
    """
    This class handles qemu monitor commands from libvirt VM object
    TODO: other methods supported from qemu_monitor have to be included
          but still vm.monitor.command(cmd) can serve the purpose
    """

    def __init__(self, name, protocol="--hmp"):
        """
        Initialize the object and set a few attributes.

        :param name: The name of the VM
        :param protocol: qemu monitor protocol
        """
        self.name = name
        self.protocol = protocol

    def command(self, cmd, **dargs):
        """
        Interface to execute qemu command from libvirt VM

        :param cmd: qemu monitor command to execute
        :param dargs: standardized virsh function API keywords
        :return: standard output from monitor command executed
        """
        result = virsh.qemu_monitor_command(self.name, cmd,
                                            options=self.protocol, **dargs)
        if result.exit_status != 0:
            raise exceptions.TestError("Failed to execute monitor cmd %s: %s"
                                       % cmd, result.stderr_text)
        return result.stderr_text

    def system_powerdown(self):
        """
        Perform powerdown of guest using qemu monitor
        """
        cmd = "system_powerdown"
        return self.command(cmd, debug=True)

    def get_status(self):
        """
        Retrieve VM status information using qemu monitor
        """
        cmd = "info status"
        return self.command(cmd, debug=True)


class VM(virt_vm.BaseVM):

    """
    This class handles all basic VM operations for libvirt.
    """

    def __init__(self, name, params, root_dir, address_cache, state=None):
        """
        Initialize the object and set a few attributes.

        :param name: The name of the object
        :param params: A dict containing VM params
                (see method make_create_command for a full description)
        :param root_dir: Base directory for relative filenames
        :param address_cache: A dict that maps MAC addresses to IP addresses
        :param state: If provided, use this as self.__dict__
        """

        if state:
            self.__dict__ = state
        else:
            self.process = None
            self.serial_ports = []
            self.serial_console_log = None
            self.redirs = {}
            self.vnc_port = None
            self.vnc_autoport = True
            self.pci_assignable = None
            self.netdev_id = []
            self.device_id = []
            self.pci_devices = []
            self.uuid = None
            self.remote_sessions = []

        self.spice_port = 8000
        self.name = name
        self.params = params
        self.root_dir = root_dir
        self.address_cache = address_cache
        self.vnclisten = "0.0.0.0"
        self.connect_uri = normalize_connect_uri(params.get("connect_uri",
                                                            "default"))
        self.driver_type = virsh.driver(uri=self.connect_uri)
        self.params['driver_type_' + self.name] = self.driver_type
        self.monitor = Monitor(self.name)
        # virtnet init depends on vm_type/driver_type being set w/in params
        super(VM, self).__init__(name, params)
        LOG.info("Libvirt VM '%s', driver '%s', uri '%s'",
                 self.name, self.driver_type, self.connect_uri)

    def is_lxc(self):
        """
        Return True if VM is linux container.
        """
        return (self.connect_uri and self.connect_uri.count("lxc"))

    def is_qemu(self):
        """
        Return True if VM is a qemu guest.
        """
        return (self.connect_uri and self.connect_uri.count("qemu"))

    def is_xen(self):
        """
        Return True if VM is a xen guest.
        """
        return (self.connect_uri and self.connect_uri.count("xen"))

    def is_esx(self):
        """
        Return True if VM is a esx guest.
        """
        return (self.connect_uri and self.connect_uri.count("esx"))

    def verify_alive(self):
        """
        Make sure the VM is alive.

        :raise VMDeadError: If the VM is dead
        """
        if not self.is_alive():
            raise virt_vm.VMDeadError("Domain %s is inactive" % self.name,
                                      self.state())

    def is_alive(self):
        """
        Return True if VM is alive.
        """
        return virsh.is_alive(self.name, uri=self.connect_uri)

    def is_dead(self):
        """
        Return True if VM is dead.
        """
        return virsh.is_dead(self.name, uri=self.connect_uri)

    def is_paused(self):
        """
        Return True if VM is paused.
        """
        return (self.state() == "paused")

    def is_persistent(self):
        """
        Return True if VM is persistent.
        """
        try:
            result = virsh.dominfo(self.name, uri=self.connect_uri)
            dominfo = result.stdout_text.strip()
            return bool(re.search(r"^Persistent:\s+[Yy]es", dominfo,
                                  re.MULTILINE))
        except process.CmdError:
            return False

    def is_autostart(self):
        """
        Return True if VM is autostart.
        """
        try:
            result = virsh.dominfo(self.name, uri=self.connect_uri)
            dominfo = result.stdout_text.strip()
            return bool(re.search(r"^Autostart:\s+enable", dominfo,
                                  re.MULTILINE))
        except process.CmdError:
            return False

    def exists(self):
        """
        Return True if VM exists.
        """
        return virsh.domain_exists(self.name, uri=self.connect_uri)

    def undefine(self, options=None):
        """
        Undefine the VM.
        """
        # If the current machine contains nvram, we have to set --nvram
        if self.params.get("vir_domain_undefine_nvram") == "yes":
            if options is None:
                options = "--nvram"
            else:
                options += " --nvram"
        try:
            virsh.undefine(self.name, options=options, uri=self.connect_uri,
                           ignore_status=False)
        except process.CmdError as detail:
            LOG.error("Undefined VM %s failed:\n%s", self.name, detail)
            return False
        return True

    def define(self, xml_file):
        """
        Define the VM.
        """
        if not os.path.exists(xml_file):
            LOG.error("File %s not found." % xml_file)
            return False
        try:
            virsh.define(xml_file, uri=self.connect_uri,
                         ignore_status=False)
        except process.CmdError as detail:
            LOG.error("Defined VM from %s failed:\n%s", xml_file, detail)
            return False
        return True

    def state(self):
        """
        Return domain state.
        """
        result = virsh.domstate(self.name, uri=self.connect_uri)
        return result.stdout_text.strip()

    def get_id(self):
        """
        Return VM's ID.
        """
        result = virsh.domid(self.name, uri=self.connect_uri)
        return result.stdout_text.strip()

    def get_xml(self):
        """
        Return VM's xml file.
        """
        result = virsh.dumpxml(self.name, uri=self.connect_uri)
        return result.stdout_text.strip()

    def backup_xml(self, active=False):
        """
        Backup the guest's xmlfile.
        """
        # Since backup_xml() is not a function for testing,
        # we have to handle the exception here.
        try:
            xml_file = tempfile.mktemp(dir=data_dir.get_tmp_dir())

            if active:
                extra = ""
            else:
                extra = "--inactive"

            virsh.dumpxml(self.name, extra=extra,
                          to_file=xml_file, uri=self.connect_uri)
            return xml_file
        except Exception as detail:
            if os.path.exists(xml_file):
                os.remove(xml_file)
            LOG.error("Failed to backup xml file:\n%s", detail)
            return ""

    def clone(self, name=None, params=None, root_dir=None, address_cache=None,
              copy_state=False):
        """
        Return a clone of the VM object with optionally modified parameters.
        The clone is initially not alive and needs to be started using create().
        Any parameters not passed to this function are copied from the source
        VM.

        :param name: Optional new VM name
        :param params: Optional new VM creation parameters
        :param root_dir: Optional new base directory for relative filenames
        :param address_cache: A dict that maps MAC addresses to IP addresses
        :param copy_state: If True, copy the original VM's state to the clone.
                Mainly useful for make_create_command().
        """
        if name is None:
            name = self.name
        if params is None:
            params = self.params.copy()
        if root_dir is None:
            root_dir = self.root_dir
        if address_cache is None:
            address_cache = self.address_cache
        if copy_state:
            state = self.__dict__.copy()
        else:
            state = None
        return VM(name, params, root_dir, address_cache, state)

    def make_create_command(self, name=None, params=None, root_dir=None):
        """
        Generate a libvirt command line. All parameters are optional. If a
        parameter is not supplied, the corresponding value stored in the
        class attributes is used.

        :param name: The name of the object
        :param params: A dict containing VM params
        :param root_dir: Base directory for relative filenames

        :note: The params dict should contain:
               mem -- memory size in MBs
               cdrom -- ISO filename to use with the qemu -cdrom parameter
               extra_params -- a string to append to the qemu command
               shell_port -- port of the remote shell daemon on the guest
               (SSH, Telnet or the home-made Remote Shell Server)
               shell_client -- client program to use for connecting to the
               remote shell daemon on the guest (ssh, telnet or nc)
               x11_display -- if specified, the DISPLAY environment variable
               will be be set to this value for the qemu process (useful for
               SDL rendering)
               images -- a list of image object names, separated by spaces
               nics -- a list of NIC object names, separated by spaces

               For each image in images:
               drive_format -- string to pass as 'if' parameter for this
               image (e.g. ide, scsi)
               image_snapshot -- if yes, pass 'snapshot=on' to qemu for
               this image
               image_boot -- if yes, pass 'boot=on' to qemu for this image
               In addition, all parameters required by get_image_filename.

               For each NIC in nics:
               nic_model -- string to pass as 'model' parameter for this
               NIC (e.g. e1000)
        """
        from virttest.utils_test import libvirt

        # helper function for command line option wrappers
        def has_option(help_text, option):
            return bool(re.search(r"--%s" % option, help_text, re.MULTILINE))

        def has_os_variant(os_text, os_variant):
            return bool(re.search(r"%s" % os_variant, os_text, re.MULTILINE))

        def has_sub_option(option, sub_option):
            option_help_text = process.run("%s --%s help" %
                                           (virt_install_binary, option),
                                           verbose=False).stdout_text
            return bool(re.search(r"%s" % sub_option, option_help_text, re.MULTILINE))

        # Wrappers for all supported libvirt command line parameters.
        # This is meant to allow support for multiple libvirt versions.
        # Each of these functions receives the output of 'libvirt --help' as a
        # parameter, and should add the requested command line option
        # accordingly.

        def add_name(help_text, name):
            return " --name '%s'" % name

        def add_machine_type(help_text, machine_type):
            if has_option(help_text, "machine"):
                return " --machine %s" % machine_type
            else:
                return ""

        def add_hvm_or_pv(help_text, hvm_or_pv):
            if hvm_or_pv == "hvm":
                return " --hvm --accelerate"
            elif hvm_or_pv == "pv":
                return " --paravirt"
            else:
                LOG.warning("Unknown virt type hvm_or_pv, using default.")
                return ""

        def add_mem(help_text, mem, maxmem=None, hugepage=False,
                    hotplugmaxmem=None, hotplugmemslots=1):
            if has_option(help_text, "memory"):
                cmd = " --memory=%s" % mem
                if maxmem:
                    if not has_sub_option('memory', 'maxmemory'):
                        LOG.warning("maxmemory option not supported by "
                                    "virt-install")
                    else:
                        cmd += ",maxmemory=%s" % maxmem
                if hugepage:
                    if not has_sub_option('memory', 'hugepages'):
                        LOG.warning("hugepages option not supported by "
                                    "virt-install")
                    else:
                        cmd += ",hugepages=yes"
                if hotplugmaxmem:
                    if not has_sub_option('memory', 'hotplugmemorymax'):
                        LOG.warning("hotplugmemorymax option not supported"
                                    "by virt-install")
                    else:
                        cmd += ",hotplugmemorymax=%s" % hotplugmaxmem
                    if not has_sub_option('memory', 'hotplugmemoryslots'):
                        LOG.warning("hotplugmemoryslots option not "
                                    "supported by virt-install")
                    else:
                        cmd += ",hotplugmemoryslots=%d" % hotplugmemslots
                return cmd
            else:
                return " --ram=%s" % mem

        def add_check_cpu(help_text):
            if has_option(help_text, "check-cpu"):
                return " --check-cpu"
            else:
                return ""

        def add_smp(help_text, smp, maxvcpus=None, sockets=None,
                    cores=None, threads=None):
            cmd = " --vcpu=%s" % smp
            if maxvcpus:
                cmd += ",maxvcpus=%s" % maxvcpus
            if sockets:
                cmd += ",sockets=%s" % sockets
            if cores:
                cmd += ",cores=%s" % cores
            if threads:
                cmd += ",threads=%s" % threads
            return cmd

        def add_numa():
            """
            Method to add Numa node to guest
            :return: appended numa parameter to virt-install cmd
            """
            if not has_sub_option('cpu', 'cell'):
                LOG.warning("virt-install version does not support numa cmd line")
                return ""
            cmd = " --cpu"
            cell = "cell%s.cpus=%s,cell%s.id=%s,cell%s.memory=%s"
            cells = ""
            numa_val = {}
            for numa_node in params.objects("guest_numa_nodes"):
                numa_params = params.object_params(numa_node)
                numa_mem = numa_params.get("numa_mem")
                numa_cpus = numa_params.get("numa_cpus")
                numa_nodeid = numa_params.get("numa_nodeid")
                numa_memdev = numa_params.get("numa_memdev")
                numa_distance = numa_params.get("numa_distance", "").split()
                numa_val[numa_nodeid] = [numa_cpus, numa_mem, numa_memdev,
                                         numa_distance]
            if numa_val:
                for cellid, value in numa_val.items():
                    cells += "%s," % cell % (cellid, value[0], cellid, cellid,
                                             cellid, value[1])
                    if value[3]:  # numa_distance
                        for siblingid in range(len(value[3])):
                            cells += "cell%s.distances.sibling%s.id=%s," % (cellid,
                                                                            siblingid,
                                                                            siblingid)
                            cells += "cell%s.distances.sibling%s.value=%s," % (cellid,
                                                                               siblingid,
                                                                               value[3][siblingid])
            else:
                # Lets calculate and assign the node cpu and memory
                vcpus = int(params.get("smp"))
                vcpu_max_cpus = params.get("vcpu_maxcpus")
                max_mem = int(params.get("mem")) * 1024
                maxmemory = params.get("maxmemory", None)
                numa_nodes = int(params.get("numa_nodes", 2))
                if vcpu_max_cpus:
                    vcpus = int(vcpu_max_cpus)
                if maxmemory:
                    max_mem = int(maxmemory) * 1024
                # we need at least 1 vcpu for 1 numa node
                if numa_nodes > vcpus:
                    numa_nodes = vcpus
                    params['numa_nodes'] = vcpus
                if vcpus > 1:
                    cpus = vcpus // numa_nodes
                    cpus_balance = vcpus % numa_nodes
                    memory = max_mem // numa_nodes
                    memory_balance = max_mem % numa_nodes
                else:
                    cpus = vcpus
                    memory = max_mem
                cpu_start = 0
                for numa in range(numa_nodes):
                    if numa == numa_nodes - 1 and vcpus > 1:
                        cpus = cpus + cpus_balance
                        memory = memory + memory_balance
                    if cpus == 1:
                        cpu_str = "%s" % (cpu_start + (cpus - 1))
                    else:
                        cpu_str = "%s-%s" % (cpu_start, cpu_start + (cpus - 1))
                    cpu_start += cpus
                    cells += "%s," % cell % (numa, cpu_str, numa, numa, numa, memory)
            cmd += " %s" % cells
            return cmd.strip(",")

        def pin_numa(help_text, host_numa_node_list):
            """
            Method to pin guest numa with host numa
            :param help_text: virt-install help message to check the option
            :param host_numa_node_list: list of online host numa nodes

            :return: parameter to pin host and guest numa with virt-install
            """
            if not has_option(help_text, "numatune"):
                return ""
            cmd = " --numatune"
            numa_pin_mode = params.get("numa_pin_mode", "strict")
            # If user gives specific host numa nodes to pin by comma separated
            # string pin_to_host_numa_node = "0,1,2", check if the numa
            # node is in online numa list and use.
            host_numa = str(params.get("pin_to_host_numa_node", ""))
            if host_numa:
                host_numa_list = host_numa.split(',')
                for each_numa in host_numa_list:
                    if each_numa not in host_numa_node_list:
                        LOG.error("host numa node - %s is not online or "
                                  "doesn't have memory", each_numa)
                        host_numa_list.remove(each_numa)
                if host_numa_list:
                    host_numa = ','.join(map(str, host_numa_list))
                else:
                    return ""
            # If user haven't mention any specific host numa nodes, use
            # available online numa nodes
            else:
                host_numa = ','.join((map(str, host_numa_node_list)))
            cmd += " %s,mode=%s" % (host_numa, numa_pin_mode)
            return cmd

        def pin_hugepage(help_text, hp_size, guest_numa):
            """
            Method to pin hugepages to guest numa with virt-install

            :param help_text: virt-install help message text
            :param hp_size: hugepage size supported
            :param guest_numa: guest numa nodes to be pinned with hugepage

            :return: cmd parameter to pin hugepage with Numa with virt-install
            """
            if not has_option(help_text, "memorybacking"):
                return ""
            cmd = " --memorybacking"
            hp_unit = params.get("hugepage_unit", "KiB")
            cmd += " size=%s,nodeset=%s,unit=%s" % (hp_size, guest_numa, hp_unit)
            # Instructs hypervisor to disable shared pages (memory merge, KSM) for
            # this domain
            if params.get("hp_nosharepages", "no") == "yes":
                cmd += ",nosharepages=yes"

            # memory pages belonging to the domain will be locked in host's memory
            # and the host will not be allowed to swap them out
            if params.get("hp_locked", "no") == "yes":
                cmd += ",locked=yes"
            return cmd

        def add_cpu_mode(virt_install_cmd, mode='', model='',
                         match='', vendor=False):
            """
            To add cpu mode, model etc... params
            :param virt_install_cmd: previous virt install cmd line
            :param mode: cpu mode host-passthrough, host-model, custom
            :param model: cpu model (coreduo, power8 etc.)
            :param match: minimum, exact, strict
            :param vendor: cpu vendor
            :return: updated virt_install_cmd
            """
            cmd = ''
            cpu_match = re.match(r".*\s--cpu\s(\S+)\s", virt_install_cmd)
            if cpu_match:
                cmd = " --cpu %s," % cpu_match.group(1)
            else:
                cmd = " --cpu "
            if mode and has_sub_option('cpu', 'mode'):
                cmd += 'mode="%s",' % mode
            if model and has_sub_option('cpu', 'model'):
                cmd += 'model="%s",' % model
            if match and has_sub_option('cpu', 'match'):
                cmd += 'match="%s",' % match
            if vendor and has_sub_option('cpu', 'vendor'):
                cmd += 'vendor="%s",' % libvirt_xml.CapabilityXML().vendor
            virt_install_cmd += cmd.strip(',')

            return virt_install_cmd

        def add_location(help_text, location):
            if has_option(help_text, "location"):
                return " --location %s" % location
            else:
                return ""

        def add_cdrom(help_text, filename, index=None):
            if has_option(help_text, "cdrom"):
                return " --cdrom %s" % filename
            else:
                return ""

        def add_pxe(help_text):
            if has_option(help_text, "pxe"):
                return " --pxe"
            else:
                return ""

        def add_import(help_text):
            if has_option(help_text, "import"):
                return " --import"
            else:
                return ""

        def add_controller(model=None):
            """
            Add controller option for virt-install command line.

            :param model: string, controller model.
            :return: string, empty or controller option.
            """
            if model == 'virtio-scsi':
                return " --controller type=scsi,model=virtio-scsi"
            else:
                return ""

        def check_controller(virt_install_cmd_line, controller):
            """
            Check for the controller already available in virt-install
            command line.

            :param virt_install_cmd_line: string, virt-install command line.
            :param controller: string, controller model.
            :return: True if succeed of False if failed.
            """
            found = False
            output = re.findall(
                r"controller\stype=(\S+),model=(\S+)", virt_install_cmd_line)
            for item in output:
                if controller in item[1]:
                    found = True
                    break
            return found

        def add_drive(help_text, filename, pool=None, vol=None, device=None,
                      bus=None, perms=None, size=None, sparse=False,
                      cache=None, fmt=None):
            cmd = " --disk"
            if filename:
                cmd += " path=%s" % filename
            elif pool:
                if vol:
                    cmd += " vol=%s/%s" % (pool, vol)
                else:
                    cmd += " pool=%s" % pool
            if device:
                cmd += ",device=%s" % device
            if bus:
                cmd += ",bus=%s" % bus
            if perms:
                cmd += ",%s" % perms
            if size:
                cmd += ",size=%s" % size.rstrip("Gg")
            if sparse:
                cmd += ",sparse=false"
            if fmt:
                cmd += ",format=%s" % fmt
            if cache:
                cmd += ",cache=%s" % cache
            return cmd

        def add_floppy(help_text, filename):
            return " --disk path=%s,device=floppy,ro" % filename

        def add_vnc(help_text, vnc_port=None):
            if vnc_port:
                return " --vnc --vncport=%d" % (vnc_port)
            else:
                return " --vnc"

        def add_vnclisten(help_text, vnclisten):
            if has_option(help_text, "vnclisten"):
                return " --vnclisten=%s" % (vnclisten)
            else:
                return ""

        def add_sdl(help_text):
            if has_option(help_text, "sdl"):
                return " --sdl"
            else:
                return ""

        def add_nographic(help_text):
            return " --nographics"

        def add_video(help_text, video_device):
            if has_option(help_text, "video"):
                return " --video=%s" % (video_device)
            else:
                return ""

        def add_uuid(help_text, uuid):
            if has_option(help_text, "uuid"):
                return " --uuid %s" % uuid
            else:
                return ""

        def add_os_type(help_text, os_type):
            if has_option(help_text, "os-type"):
                return " --os-type %s" % os_type
            else:
                return ""

        def add_os_variant(help_text, os_variant):
            if has_option(help_text, "os-variant"):
                return " --os-variant %s" % os_variant
            else:
                return ""

        def add_pcidevice(help_text, pci_device):
            if has_option(help_text, "host-device"):
                return " --host-device %s" % pci_device
            else:
                return ""

        def add_soundhw(help_text, sound_device):
            if has_option(help_text, "soundhw"):
                return " --soundhw %s" % sound_device
            else:
                return ""

        def add_serial(help_text):
            if has_option(help_text, "serial"):
                return " --serial pty"
            else:
                return ""

        def add_kernel_cmdline(help_text, cmdline):
            return " -append %s" % cmdline

        def add_connect_uri(help_text, uri):
            if uri and has_option(help_text, "connect"):
                return " --connect=%s" % uri
            else:
                return ""

        def add_security(help_text, sec_type, sec_label=None, sec_relabel=None):
            """
            Return security options for install command.
            """
            if has_option(help_text, "security"):
                result = " --security"
                if sec_type == 'static':
                    if sec_label is None:
                        raise ValueError("Seclabel is not setted for static.")
                    result += " type=static,label=%s" % (sec_label)
                elif sec_type == 'dynamic':
                    result += " type=dynamic"
                else:
                    raise ValueError("Security type %s is not supported."
                                     % sec_type)
                if sec_relabel is not None:
                    result += ",relabel=%s" % sec_relabel
            else:
                result = ""

            return result

        def add_nic(help_text, nic_params):
            """
            Return additional command line params based on dict-like nic_params
            """
            mac = nic_params.get('mac')
            nettype = nic_params.get('nettype')
            netdst = nic_params.get('netdst')
            nic_model = nic_params.get('nic_model')
            nic_queues = nic_params.get('queues')
            nic_driver = nic_params.get('net_driver')
            if nettype:
                result = " --network=%s" % nettype
            else:
                result = ""
            if has_option(help_text, "bridge"):
                # older libvirt (--network=NATdev --bridge=bridgename
                # --mac=mac)
                if nettype != 'user':
                    result += ':%s' % netdst
                if mac:  # possible to specify --mac w/o --network
                    result += " --mac=%s" % mac
            else:
                # newer libvirt (--network=mynet,model=virtio,mac=00:11)
                if nettype != 'user':
                    result += '=%s' % netdst
                if nettype and nic_model:  # only supported along with nettype
                    result += ",model=%s" % nic_model
                if nettype and mac:
                    result += ',mac=%s' % mac
                if nettype and nic_queues and has_sub_option('network', 'driver_queues'):
                    result += ',driver_queues=%s' % nic_queues
                    if nic_driver and has_sub_option('network', 'driver_name'):
                        result += ',driver_name=%s' % nic_driver
                elif mac:  # possible to specify --mac w/o --network
                    result += " --mac=%s" % mac
            LOG.debug("vm.make_create_command.add_nic returning: %s",
                      result)
            return result

        def add_memballoon(help_text, memballoon_model):
            """
            Adding memballoon device to the vm.

            :param help_text: string, virt-install help text.
            :param memballon_model: string, memballoon model.
            :return: string, empty or memballoon model option.
            """
            if has_option(help_text, "memballoon"):
                result = " --memballoon model=%s" % memballoon_model
            else:
                LOG.warning("memballoon is not supported")
                result = ""
            LOG.debug("vm.add_memballoon returning: %s", result)
            return result

        def add_kernel(help_text, cmdline, kernel_path=None, initrd_path=None,
                       kernel_args=None):
            """
            Adding Custom kernel option to boot.

            : param help_text: string, virt-install help text
            : param cmdline: string, current virt-install cmdline
            : param kernel_path: string, custom kernel path.
            : param initrd_path: string, custom initrd path.
            : param kernel_args: string, custom boot args.
            """
            if has_option(help_text, "boot"):
                if "--boot" in cmdline:
                    result = ","
                else:
                    result = " --boot "
                if has_sub_option("boot", "kernel") and kernel_path:
                    result += "kernel=%s," % kernel_path
                if has_sub_option("boot", "initrd") and initrd_path:
                    result += "initrd=%s," % initrd_path
                if has_sub_option("boot", "kernel_args") and kernel_args:
                    result += "kernel_args=\"%s\"," % kernel_args
            else:
                result = ""
                LOG.warning("boot option is not supported")
            return result.rstrip(',')

        def add_cputune(vcpu_cputune=""):
            """
            Add cputune for guest
            """
            if not vcpu_cputune:
                return ""
            cputune_list = vcpu_cputune.split(" ")
            item = 0
            cputune_str = " --cputune "
            for vcpu, cpulist in enumerate(cputune_list):
                if "N" in cpulist:
                    continue
                cputune_str += "vcpupin%s.cpuset=\"%s\",vcpupin%s.vcpu=\"%s\"," % (item, cpulist, item, vcpu)
                item += 1
            return cputune_str.rstrip(",")

        def add_tpmdevice(help_text, device_path, model=None, type=None):
            """
            Add TPM device to guest xml
            :param help_text: string, virt-install help text
            :param device_path: path to TPM device
            :param model: tpm device model to be added
                          tpm-tis, tpm-crb, tpm-spapr etc
            :param type: type of device attach
                         passthrough, emulator
            :return: string of tpm cmdline for virt-install
            """
            result = ""
            if not has_option(help_text, "tpm"):
                LOG.warning("tpm option is not supported in virt-install")
                return result
            if not (device_path and os.path.exists(device_path)):
                LOG.warning("Given TPM device is not valid or not present")
                return result
            result = " --tpm path=%s" % device_path
            if has_sub_option("tpm", "model") and model:
                result += ",model=%s" % model
            if has_sub_option("tpm", "type") and type:
                result += ",type=%s" % type
            return result

        # End of command line option wrappers

        if name is None:
            name = self.name
        if params is None:
            params = self.params
        if root_dir is None:
            root_dir = self.root_dir

        # Clone this VM using the new params
        vm = self.clone(name, params, root_dir, copy_state=True)

        virt_install_binary = utils_misc.get_path(
            root_dir,
            params.get("virt_install_binary",
                       "virt-install"))

        help_text = process.run("%s --help" % virt_install_binary,
                                verbose=False).stdout_text

        try:
            os_text = process.run("osinfo-query os --fields short-id",
                                  verbose=False).stdout_text
        except process.CmdError:
            os_text = process.run("%s --os-variant list" % virt_install_binary,
                                  verbose=False).stdout_text

        # Find all supported machine types, so we can rule out an unsupported
        # machine type option passed in the configuration.
        hvm_or_pv = params.get("hvm_or_pv", "hvm")
        # default to 'uname -m' output
        arch_name = params.get("vm_arch_name", platform.machine())
        support_machine_type = libvirt.get_machine_types(arch_name, hvm_or_pv,
                                                         ignore_status=False)
        LOG.debug("Machine types supported for %s/%s: %s",
                  hvm_or_pv, arch_name, support_machine_type)

        # Start constructing the qemu command
        virt_install_cmd = ""
        # Set the X11 display parameter if requested
        if params.get("x11_display"):
            virt_install_cmd += "DISPLAY=%s " % params.get("x11_display")
        # Add the qemu binary
        virt_install_cmd += virt_install_binary

        # set connect uri
        virt_install_cmd += add_connect_uri(help_text, self.connect_uri)

        # hvm or pv specified by libvirt switch (pv used  by Xen only)
        if hvm_or_pv:
            virt_install_cmd += add_hvm_or_pv(help_text, hvm_or_pv)

        # Add the VM's name
        virt_install_cmd += add_name(help_text, name)

        # The machine_type format is [avocado-type:]machine_type
        # where avocado-type is optional part and is used in
        # tp-qemu to use different devices. Use only the second part
        machine_type = params.get("machine_type").split(':', 1)[-1]
        if machine_type:
            if machine_type in support_machine_type:
                virt_install_cmd += add_machine_type(help_text, machine_type)
            else:
                raise exceptions.TestSkipError("Unsupported machine type %s." %
                                               (machine_type))

        mem = params.get("mem")
        maxmemory = params.get("maxmemory", None)

        # hugepage setup in host will be taken care in env_process
        hugepage = params.get("hugepage", "no") == "yes"
        hotplugmaxmem = params.get("hotplugmaxmem", None)
        hotplugmemslots = int(params.get("hotplugmemslots", 1))
        if mem:
            virt_install_cmd += add_mem(help_text, mem, maxmemory, hugepage,
                                        hotplugmaxmem, hotplugmemslots)

        # TODO: should we do the check before we call ? negative case ?
        check_cpu = params.get("use_check_cpu")
        if check_cpu:
            virt_install_cmd += add_check_cpu(help_text)

        smp = params.get("smp")
        vcpu_max_cpus = params.get("vcpu_maxcpus")
        vcpu_sockets = params.get("vcpu_sockets")
        vcpu_cores = params.get("vcpu_cores")
        vcpu_threads = params.get("vcpu_threads")
        if smp:
            virt_install_cmd += add_smp(help_text, smp, vcpu_max_cpus,
                                        vcpu_sockets, vcpu_cores, vcpu_threads)
        numa = params.get("numa", "no") == "yes"
        if numa:
            virt_install_cmd += add_numa()
            if params.get("numa_pin", "no") == "yes":
                # Get online host numa nodes
                host_numa_node = utils_misc.NumaInfo()
                host_numa_node_list = host_numa_node.online_nodes_withcpumem
                # check if memory is available in host numa node
                for each_numa in host_numa_node_list:
                    if hugepage:
                        hp = test_setup.HugePageConfig(params)
                        free_hp = host_numa_node.read_from_node_meminfo(each_numa,
                                                                        "HugePages_Free")
                        free_mem = int(free_hp) * int(hp.get_hugepage_size())
                    else:
                        free_mem = int(host_numa_node.read_from_node_meminfo(each_numa,
                                                                             'MemFree'))
                    # Numa might be online but if it doesn't have free memory,
                    # skip it
                    if free_mem == 0:
                        LOG.debug("Host numa node: %s doesn't have memory",
                                  each_numa)
                        host_numa_node_list.remove(each_numa)
                if not host_numa_node_list:
                    LOG.error("Host Numa nodes are not online or doesn't "
                              "have memory to pin")
                else:
                    virt_install_cmd += pin_numa(help_text, host_numa_node_list)

        if params.get("hugepage_pin", "no") == "yes":
            if numa and hugepage:
                # get host hugepage size
                hp_obj = test_setup.HugePageConfig(params)
                hp_size = hp_obj.get_hugepage_size()
                # specify numa nodes to be backed by HP by comma separated
                # string, hugepage_pinnned_numa = "0-2,4" to back guest numa
                # nodes 0 to 2 and 4.
                guest_numa = str(params.get("hugepage_pinned_numa"))
                if guest_numa == 'None':
                    # if user didn't mention hugepage_pinnned_numa use
                    # numa_nodes to back all the numa nodes.
                    guest_numa = int(params.get("numa_nodes", 2))
                    guest_numa = ','.join(map(str, list(range(guest_numa))))
                virt_install_cmd += pin_hugepage(help_text, hp_size, guest_numa)
            else:
                LOG.error("Can't pin hugepage without hugepage enabled"
                          "and Numa enabled")

        cpu_mode = params.get("virt_cpu_mode", '')
        if cpu_mode:
            virt_install_cmd = add_cpu_mode(virt_install_cmd,
                                            mode=cpu_mode,
                                            model=params.get('virt_cpu_model', ''),
                                            match=params.get('virt_cpu_match', ''),
                                            vendor=params.get('virt_cpu_vendor', False))
        cputune_list = params.get("vcpu_cputune", "")
        if cputune_list:
            virt_install_cmd += add_cputune(cputune_list)
        # TODO: directory location for vmlinuz/kernel for cdrom install ?
        location = None
        if params.get("medium") == 'url':
            location = params.get('url')

        elif params.get("medium") == 'kernel_initrd':
            # directory location of kernel/initrd pair (directory layout must
            # be in format libvirt will recognize)
            location = params.get("image_dir")

        elif params.get("medium") == 'nfs':
            location = "nfs:%s:%s" % (params.get("nfs_server"),
                                      params.get("nfs_dir"))

        elif params.get("medium") == 'cdrom':
            if params.get("use_libvirt_cdrom_switch") == 'yes':
                virt_install_cmd += add_cdrom(
                    help_text, params.get("cdrom_cd1"))
            elif params.get("unattended_delivery_method") == "integrated":
                cdrom_path = os.path.join(data_dir.get_data_dir(),
                                          params.get("cdrom_unattended"))
                virt_install_cmd += add_cdrom(help_text, cdrom_path)
            else:
                location = os.path.join(data_dir.get_data_dir(),
                                        params.get("cdrom_cd1"))
                kernel_dir = os.path.dirname(params.get("kernel"))
                kernel_parent_dir = os.path.dirname(kernel_dir)
                pxeboot_link = os.path.join(kernel_parent_dir, "pxeboot")
                if os.path.islink(pxeboot_link):
                    os.unlink(pxeboot_link)
                if os.path.isdir(pxeboot_link):
                    LOG.info("Removed old %s leftover directory", pxeboot_link)
                    shutil.rmtree(pxeboot_link)
                os.symlink(kernel_dir, pxeboot_link)

        elif params.get("medium") == "import":
            virt_install_cmd += add_import(help_text)

        if location:
            virt_install_cmd += add_location(help_text, location)

        # Disable display when vga is disabled (used mainly by machines.cfg)
        if params.get("vga") == "none":
            virt_install_cmd += add_nographic(help_text)
        elif params.get("display") == "vnc":
            if params.get("vnc_autoport") == "yes":
                vm.vnc_autoport = True
            else:
                vm.vnc_autoport = False
            if not vm.vnc_autoport and params.get("vnc_port"):
                vm.vnc_port = int(params.get("vnc_port"))
            virt_install_cmd += add_vnc(help_text, vm.vnc_port)
            if params.get("vnclisten"):
                vm.vnclisten = params.get("vnclisten")
            virt_install_cmd += add_vnclisten(help_text, vm.vnclisten)
        elif params.get("display") == "sdl":
            virt_install_cmd += add_sdl(help_text)
        elif params.get("display") == "nographic":
            virt_install_cmd += add_nographic(help_text)

        video_device = params.get("video_device")
        if video_device:
            virt_install_cmd += add_video(help_text, video_device)

        sound_device = params.get("sound_device")
        if sound_device:
            virt_install_cmd += add_soundhw(help_text, sound_device)

        # if none is given a random UUID will be generated by libvirt
        if params.get("uuid"):
            virt_install_cmd += add_uuid(help_text, params.get("uuid"))

        # selectable OS type
        if params.get("use_os_type") == "yes":
            virt_install_cmd += add_os_type(help_text, params.get("os_type"))

        # selectable OS variant
        if params.get("use_os_variant") == "yes":
            if not has_os_variant(os_text, params.get("os_variant")):
                raise exceptions.TestSkipError("Unsupported OS variant: %s.\n"
                                               "Supported variants: %s" %
                                               (params.get('os_variant'),
                                                os_text))
            virt_install_cmd += add_os_variant(
                help_text, params.get("os_variant"))

        # Add serial console
        virt_install_cmd += add_serial(help_text)

        # Add memballoon device
        memballoon_model = params.get("memballoon_model")
        if memballoon_model:
            virt_install_cmd += add_memballoon(help_text, memballoon_model)

        # If the PCI assignment step went OK, add each one of the PCI assigned
        # devices to the command line.
        if self.pci_devices:
            for pci_id in self.pci_devices:
                virt_install_cmd += add_pcidevice(help_text, pci_id)

        for image_name in params.objects("images"):
            basename = False
            image_params = params.object_params(image_name)

            base_dir = image_params.get("images_base_dir",
                                        data_dir.get_data_dir())
            if params.get("storage_type") == "nfs":
                basename = True
                base_dir = params["nfs_mount_dir"]
            filename = storage.get_image_filename(image_params,
                                                  base_dir, basename=basename)
            if image_params.get("use_storage_pool") == "yes":
                filename = None
                virt_install_cmd += add_drive(help_text,
                                              filename,
                                              image_params.get("image_pool"),
                                              image_params.get("image_vol"),
                                              image_params.get("image_device"),
                                              image_params.get("image_bus"),
                                              image_params.get("image_perms"),
                                              image_params.get("image_size"),
                                              image_params.get("drive_sparse"),
                                              image_params.get("drive_cache"),
                                              image_params.get("image_format"))

            if image_params.get("boot_drive") == "no":
                continue
            if filename:
                libvirt_controller = image_params.get(
                    "libvirt_controller", None)
                _drive_format = image_params.get("drive_format")
                if libvirt_controller:
                    if not check_controller(virt_install_cmd, libvirt_controller):
                        virt_install_cmd += add_controller(libvirt_controller)
                    # this will reset the scsi-hd to scsi as we are adding controller
                    # to mention the drive format
                    if 'scsi' in _drive_format:
                        _drive_format = "scsi"
                virt_install_cmd += add_drive(help_text,
                                              filename,
                                              None,
                                              None,
                                              None,
                                              _drive_format,
                                              None,
                                              image_params.get("image_size"),
                                              image_params.get("drive_sparse"),
                                              image_params.get("drive_cache"),
                                              image_params.get("image_format"))

        unattended_integrated = (params.get('unattended_delivery_method') !=
                                 'integrated')
        xen_pv = self.driver_type == 'xen' and params.get('hvm_or_pv') == 'pv'
        if unattended_integrated and not xen_pv:
            for cdrom in params.objects("cdroms"):
                cdrom_params = params.object_params(cdrom)
                iso = cdrom_params.get("cdrom")
                if params.get("use_libvirt_cdrom_switch") == 'yes':
                    # we don't want to skip the winutils iso
                    if not cdrom == 'winutils':
                        LOG.debug(
                            "Using --cdrom instead of --disk for install")
                        LOG.debug("Skipping CDROM:%s:%s", cdrom, iso)
                        continue
                if params.get("medium") == 'cdrom':
                    if iso == params.get("cdrom_cd1"):
                        LOG.debug("Using cdrom or url for install")
                        LOG.debug("Skipping CDROM: %s", iso)
                        continue

                if iso:
                    iso_path = utils_misc.get_path(root_dir, iso)
                    iso_image_pool = image_params.get("iso_image_pool")
                    iso_image_vol = image_params.get("iso_image_vol")
                    virt_install_cmd += add_drive(help_text,
                                                  iso_path,
                                                  iso_image_pool,
                                                  virt_install_cmd,
                                                  'cdrom',
                                                  None,
                                                  None,
                                                  None,
                                                  None,
                                                  None,
                                                  None)

        # We may want to add {floppy_otps} parameter for -fda
        # {fat:floppy:}/path/. However vvfat is not usually recommended.
        # Only support to add the main floppy if you want to add the second
        # one please modify this part.
        floppy = params.get("floppy_name")
        if floppy:
            floppy = utils_misc.get_path(data_dir.get_data_dir(), floppy)
            virt_install_cmd += add_drive(help_text, floppy,
                                          None,
                                          None,
                                          'floppy',
                                          None,
                                          None,
                                          None,
                                          None,
                                          None,
                                          None)

        # setup networking parameters
        for nic in vm.virtnet:
            # make_create_command can be called w/o vm.create()
            nic = vm.add_nic(**dict(nic))
            LOG.debug("make_create_command() setting up command for"
                      " nic: %s" % str(nic))
            virt_install_cmd += add_nic(help_text, nic)

        if params.get("use_no_reboot") == "yes":
            virt_install_cmd += " --noreboot"

        if params.get("use_autostart") == "yes":
            virt_install_cmd += " --autostart"

        if params.get("virt_install_debug") == "yes":
            virt_install_cmd += " --debug"

        emulator_path = params.get("emulator_path", None)
        if emulator_path:
            if not has_sub_option('boot', 'emulator'):
                LOG.warning("emulator option not supported by virt-install")
            else:
                virt_install_cmd += " --boot emulator=%s" % emulator_path

        bios_path = params.get("bios_path", None)
        if bios_path:
            if not has_sub_option('boot', 'loader'):
                LOG.warning("bios option not supported by virt-install")
            else:
                if "--boot" in virt_install_cmd:
                    virt_install_cmd += ","
                else:
                    virt_install_cmd += " --boot "
                virt_install_cmd += "loader=%s" % bios_path

        kernel = params.get("kernel", None)
        initrd = params.get("initrd", None)
        kernel_args = params.get("kernel_args", None)
        if (kernel or initrd) and kernel_args:
            virt_install_cmd += add_kernel(help_text, virt_install_cmd, kernel,
                                           initrd, kernel_args)

        # bz still open, not fully functional yet
        if params.get("use_virt_install_wait") == "yes":
            virt_install_cmd += (" --wait %s" %
                                 params.get("virt_install_wait_time"))

        kernel_params = params.get("kernel_params")
        if kernel_params:
            virt_install_cmd += " --extra-args '%s'" % kernel_params

        virt_install_cmd += " --noautoconsole"
        # Add TPM device
        tpm_device = params.get("tpm_device_path", None)
        if tpm_device:
            tpm_model = params.get("tpm_model", None)
            tpm_type = params.get("tpm_type", None)
            virt_install_cmd += add_tpmdevice(help_text, tpm_device, tpm_model,
                                              tpm_type)
        sec_type = params.get("sec_type", None)
        if sec_type:
            sec_label = params.get("sec_label", None)
            sec_relabel = params.get("sec_relabel", None)
            virt_install_cmd += add_security(help_text, sec_type=sec_type,
                                             sec_label=sec_label,
                                             sec_relabel=sec_relabel)

        # Additional qemu commandline options to virt-install directly
        # helps to test new feature from qemu
        if has_option(help_text, "qemu-commandline"):
            virtinstall_qemu_cmdline = params.get("virtinstall_qemu_cmdline", "")
            if virtinstall_qemu_cmdline:
                virt_install_cmd += ' --qemu-commandline="%s"' % virtinstall_qemu_cmdline

            compat = params.get("qemu_compat")
            if compat:
                # TODO: Add a check whether "-compat" is supported
                virt_install_cmd += ' --qemu-commandline="-compat %s"' % compat

        virtinstall_extra_args = params.get("virtinstall_extra_args", "")
        if virtinstall_extra_args:
            virt_install_cmd += " %s" % virtinstall_extra_args

        return virt_install_cmd

    def get_serial_console_filename(self, name):
        """
        Return the serial console filename.

        :param name: The serial port name.
        """
        return "serial-%s-%s-%s.log" % (name, self.name,
                                        utils_misc.generate_random_string(4))

    def get_serial_console_filenames(self):
        """
        Return a list of all serial console filenames
        (as specified in the VM's params).
        """
        return [self.get_serial_console_filename(_) for _ in
                self.params.objects("serials")]

    def _create_serial_console(self):
        """
        Establish a session with the serial console.

        The libvirt version uses virsh console to manage it.
        """
        if not self.serial_ports:
            for serial in self.params.objects("serials"):
                self.serial_ports.append(serial)
        if self.serial_console is None or self.serial_console.closed:
            try:
                cmd = 'virsh'
                if self.connect_uri:
                    cmd += ' -c %s' % self.connect_uri
                cmd += (" console %s %s" % (self.name, self.serial_ports[0]))
            except IndexError:
                raise virt_vm.VMConfigMissingError(self.name, "serial")
            output_func = utils_misc.log_line  # Because qemu-kvm uses this
            # Because qemu-kvm hard-codes this
            output_filename = self.get_serial_console_filename(self.serial_ports[0])
            output_params = (output_filename,)
            prompt = self.params.get("shell_prompt", "[\#\$]")
            LOG.debug("Command used to create serial console: %s", cmd)
            self.serial_console = aexpect.ShellSession(command=cmd, auto_close=False,
                                                       output_func=output_func,
                                                       output_params=output_params,
                                                       prompt=prompt)
            if not self.serial_console.is_alive():
                LOG.error("Failed to create serial_console")
            # Cause serial_console.close() to close open log file
            self.serial_console.set_log_file(output_filename)
            self.serial_console_log = os.path.join(utils_misc.get_log_file_dir(),
                                                   output_filename)

    def set_root_serial_console(self, device, remove=False):
        """
        Allow or ban root to login through serial console.

        :param device: device to set root login
        :param allow_root: do remove operation
        """
        try:
            session = self.login()
        except (remote.LoginError, virt_vm.VMError) as e:
            LOG.debug(e)
        else:
            try:
                securetty_output = session.cmd_output("cat /etc/securetty")
                devices = str(securetty_output).strip().splitlines()
                if device not in devices:
                    if not remove:
                        session.sendline("echo %s >> /etc/securetty" % device)
                else:
                    if remove:
                        session.sendline("sed -i -e /%s/d /etc/securetty"
                                         % device)
                LOG.debug("Set root login for %s successfully.", device)
                return True
            finally:
                session.close()
        LOG.debug("Set root login for %s failed.", device)
        return False

    def set_kernel_console(self, device, speed=None, remove=False,
                           guest_arch_name='x86_64'):
        """
        Set kernel parameter for given console device.

        :param device: a console device
        :param speed: speed of serial console
        :param remove: do remove operation
        :param guest_arch_name: architecture of the guest to update kernel param
        """
        from . import utils_test
        kernel_params = "console=%s" % device
        if speed is not None:
            kernel_params += ",%s" % speed
        if remove:
            utils_test.update_boot_option(self, args_removed=kernel_params,
                                          guest_arch_name=guest_arch_name)
        else:
            utils_test.update_boot_option(self, args_added=kernel_params,
                                          guest_arch_name=guest_arch_name)
        LOG.debug("Set kernel params for %s is successful", device)
        return True

    def set_kernel_param(self, parameter, value=None, remove=False):
        """
        Set a specific kernel parameter.

        :param option: A kernel parameter to set.
        :param value: The value of the parameter to be set.
        :param remove: Remove the parameter if True.
        :return: True if succeed of False if failed.
        """
        if self.is_dead():
            LOG.error("Can't set kernel param on a dead VM.")
            return False

        session = self.wait_for_login()
        try:
            grub_path = utils_misc.get_bootloader_cfg(session)
            if not grub_path:
                return False
            grub_text = session.cmd_output("cat %s" % grub_path)
            kernel_lines = [l.strip() for l in grub_text.splitlines()
                            if re.match(r"\s*(linux|kernel).*", l)]
            if not kernel_lines:
                LOG.error("Can't find any kernel lines in grub "
                          "file %s:\n%s" % (grub_path, grub_text))
                return False

            for line in kernel_lines:
                line = line.replace('\t', r'\t')
                if remove:
                    new_string = ""
                else:
                    if value is None:
                        new_string = parameter
                    else:
                        new_string = "%s=%s" % (parameter, value)

                patts = [
                    "\s+(%s=\S*)(\s|$)" % parameter,
                    "\s+(%s)(\s|$)" % parameter,
                ]
                old_string = ""
                for patt in patts:
                    res = re.search(patt, line)
                    if res:
                        old_string = res.group(1)
                        break

                if old_string:
                    new_line = line.replace(old_string, new_string)
                else:
                    new_line = " ".join((line, new_string))

                line_patt = "\s*".join(line.split())
                LOG.debug("Substituting grub line '%s' to '%s'." %
                          (line, new_line))
                stat_sed, output = session.cmd_status_output(
                    "sed -i --follow-symlinks -e \"s@%s@%s@g\" %s" %
                    (line_patt, new_line, grub_path))
                if stat_sed:
                    LOG.error("Failed to substitute grub file:\n%s" %
                              output)
                    return False
            if remove:
                LOG.debug("Remove kernel params %s successfully.",
                          parameter)
            else:
                LOG.debug("Set kernel params %s to %s successfully.",
                          parameter, value)
            return True
        finally:
            session.close()

    def set_boot_kernel(self, index, debug_kernel=False):
        """
        Set default kernel to the second one or to debug kernel

        :param index: index of kernel to set to default
        :param debug_kernel: True if set debug kernel to default
        :return: default kernel
        """
        if self.is_dead():
            LOG.error("Can't set kernel param on a dead VM.")
            return False

        session = self.wait_for_login()
        try:
            grub_path = utils_misc.get_bootloader_cfg(session)
            if not grub_path:
                return
            if "grub2" in grub_path:
                grub = 2
                output = session.cmd("cat %s |grep menuentry" % grub_path)
                kernel_list = re.findall("menuentry '.*?'", output)
            else:
                grub = 1
                output = session.cmd("cat %s |grep initramfs" % grub_path)
                kernel_list = re.findall("-.*", output)
            if index >= len(kernel_list):
                LOG.error("Index out of kernel list")
                return
            LOG.debug("kernel list of vm:")
            LOG.debug(kernel_list)
            if debug_kernel:
                index = -1
                LOG.info("Setting debug kernel as default")
                for i in range(len(kernel_list)):
                    if "debug" in kernel_list[i] and 'rescue' not in kernel_list[i].lower():
                        index = i
                        break
                if index == -1:
                    LOG.error("No debug kernel in grub file!")
                    return
            if grub == 1:
                cmd_set_grub = "sed -i 's/default=./default=%d/' " % index
                cmd_set_grub += grub_path
                boot_kernel = kernel_list[index].strip("-")
            else:
                boot_kernel = kernel_list[index].split("'")[1].strip("'")
                cmd_set_grub = 'grub2-set-default %d' % index
            session.cmd(cmd_set_grub)
            return boot_kernel
        finally:
            session.close()

    def has_swap(self):
        """
        Check if there is any active swap partition/file.

        :return : True if swap is on or False otherwise.
        """
        if self.is_dead():
            LOG.error("Can't check swap on a dead VM.")
            return False

        session = self.wait_for_login()
        try:
            cmd = "swapon -s"
            output = session.cmd_output(cmd)
            if output.strip():
                return True
            return False
        finally:
            session.close()

    def create_swap_partition(self, swap_path=None):
        """
        Make a swap partition and active it.

        A cleanup_swap() should be call after use to clean up
        the environment changed.

        :param swap_path: Swap image path.
        """
        if self.is_dead():
            LOG.error("Can't create swap on a dead VM.")
            return False

        if not swap_path:
            swap_path = os.path.join(data_dir.get_tmp_dir(), "swap_image")
        swap_size = self.get_used_mem()
        process.run("qemu-img create %s %s" % (swap_path, swap_size * 1024))
        self.created_swap_path = swap_path

        device = self.attach_disk(swap_path, extra="--persistent")

        session = self.wait_for_login()
        try:
            dev_path = "/dev/" + device
            session.cmd_status("mkswap %s" % dev_path)
            session.cmd_status("swapon %s" % dev_path)
            self.set_kernel_param("resume", dev_path)
            return True
        finally:
            session.close()
        LOG.error("Failed to create a swap partition.")
        return False

    def create_swap_file(self, swapfile='/swapfile'):
        """
        Make a swap file and active it through a session.

        A cleanup_swap() should be call after use to clean up
        the environment changed.

        :param swapfile: Swap file path in VM to be created.
        """
        if self.is_dead():
            LOG.error("Can't create swap on a dead VM.")
            return False

        session = self.wait_for_login()
        try:
            # Get memory size.
            swap_size = self.get_used_mem() // 1024

            # Create, change permission, and make a swap file.
            cmd = ("dd if=/dev/zero of={1} bs=1M count={0} && "
                   "chmod 600 {1} && "
                   "mkswap {1}".format(swap_size, swapfile))
            stat_create, output = session.cmd_status_output(cmd)
            if stat_create:
                LOG.error("Fail to create swap file in guest."
                          "\n%s" % output)
                return False
            self.created_swap_file = swapfile

            # Get physical swap file offset for kernel param resume_offset.
            cmd = "filefrag -v %s" % swapfile
            output = session.cmd_output(cmd)
            # For compatibility of different version of filefrag
            # Sample output of 'filefrag -v /swapfile'
            # On newer version:
            # Filesystem type is: 58465342
            # File size of /swapfile is 1048576000 (256000 blocks of 4096 bytes)
            # ext:     logical_offset:        physical_offset: length:   expected: flags:
            #        0:        0..   65519:     395320..    460839:  65520:
            # ...
            # On older version:
            # Filesystem type is: ef53
            # File size of /swapfile is 1048576000 (256000 blocks, blocksize 4096)
            # ext logical physical expected length flags
            #    0       0  2465792           32768
            # ...
            offset_line = output.splitlines()[3]
            if '..' in offset_line:
                offset = offset_line.split()[3].rstrip('..')
            else:
                offset = offset_line.split()[2]

            # Get physical swap file device for kernel param resume.
            cmd = "df %s" % swapfile
            output = session.cmd_output(cmd)
            # Sample output of 'df /swapfile':
            # Filesystem 1K-blocks     Used Available Use% Mounted on
            # /dev/vdb    52403200 15513848  36889352  30% /
            device = output.splitlines()[1].split()[0]

            # Set kernel parameters.
            self.set_kernel_param("resume", device)
            self.set_kernel_param("resume_offset", offset)
        finally:
            session.close()

        self.reboot()

        session = self.wait_for_login()
        try:
            # Activate a swap file.
            cmd = "swapon %s" % swapfile
            stat_swapon, output = session.cmd_status_output(cmd)
            if stat_create:
                LOG.error("Fail to activate swap file in guest."
                          "\n%s" % output)
                return False
        finally:
            session.close()

        if self.has_swap():
            LOG.debug("Successfully created swapfile %s." % swapfile)
            return True
        else:
            LOG.error("Failed to create swap file.")
            return False

    def cleanup_swap(self):
        """
        Cleanup environment changed by create_swap_partition() or
        create_swap_file().
        """
        if self.is_dead():
            LOG.error("Can't cleanup swap on a dead VM.")
            return False

        # Remove kernel parameters.
        self.set_kernel_param("resume", remove=True)
        self.set_kernel_param("resume_offset", remove=True)

        # Deactivate swap partition/file.
        session = self.wait_for_login()
        try:
            session.cmd_status("swapoff -a")
            if "created_swap_file" in dir(self):
                session.cmd_status("rm -f %s" % self.created_swap_file)
                del self.created_swap_file
        finally:
            session.close()

        # Cold unplug attached swap disk
        if self.shutdown():
            if "created_swap_device" in dir(self):
                self.detach_disk(
                    self.created_swap_device, extra="--persistent")
                del self.created_swap_device
            if "created_swap_path" in dir(self):
                os.remove(self.created_swap_path)
                del self.created_swap_path

    def set_console_getty(self, device, getty="mgetty", remove=False):
        """
        Set getty for given console device.

        :param device: a console device
        :param getty: getty type: agetty, mgetty and so on.
        :param remove: do remove operation
        """
        try:
            session = self.login()
        except (remote.LoginError, virt_vm.VMError) as e:
            LOG.debug(e)
        else:
            try:
                # Only configurate RHEL5 and below
                regex = "gettys are handled by"
                # As of RHEL7 systemd message is displayed
                regex += "|inittab is no longer used when using systemd"
                output = session.cmd_output("cat /etc/inittab")
                if re.search(regex, output):
                    LOG.debug("Skip setting inittab for %s", device)
                    return True
                getty_str = "co:2345:respawn:/sbin/%s %s" % (getty, device)
                matched_str = "respawn:/sbin/*getty %s" % device
                if not re.search(matched_str, output):
                    if not remove:
                        session.sendline("echo %s >> /etc/inittab" % getty_str)
                else:
                    if remove:
                        session.sendline("sed -i -e /%s/d "
                                         "/etc/inittab" % matched_str)
                LOG.debug("Set inittab for %s successfully.", device)
                return True
            finally:
                session.close()
        LOG.debug("Set inittab for %s failed.", device)
        return False

    def cleanup_serial_console(self):
        """
        Close serial console and associated log file
        """
        if self.serial_console is not None:
            if self.is_lxc():
                self.serial_console.sendline("^]")
            self.serial_console.close()
            self.serial_console = None
            self.serial_console_log = None
            self.console_manager.set_console(None)
        if hasattr(self, "migration_file"):
            try:
                os.unlink(self.migration_file)
            except OSError:
                pass

    def wait_for_login(self, nic_index=0, timeout=None,
                       internal_timeout=None,
                       serial=False, restart_network=False,
                       username=None, password=None):
        """
        Override the wait_for_login method of virt_vm to support other
        guest in libvirt.

        If connect_uri is lxc related, we call wait_for_serial_login()
        directly, without attempting login it via network.

        Other connect_uri, call virt_vm.wait_for_login().
        """
        # Set the default value of parameters if user did not use it.
        if not timeout:
            timeout = super(VM, self).LOGIN_WAIT_TIMEOUT

        if not internal_timeout:
            internal_timeout = super(VM, self).LOGIN_TIMEOUT

        if self.is_lxc():
            self.cleanup_serial_console()
            self.create_serial_console()
            return self.wait_for_serial_login(timeout, internal_timeout,
                                              restart_network,
                                              username, password)

        return super(VM, self).wait_for_login(nic_index, timeout,
                                              internal_timeout,
                                              serial, restart_network,
                                              username, password)

    @error_context.context_aware
    def create(self, name=None, params=None, root_dir=None, timeout=5.0,
               migration_mode=None, mac_source=None, autoconsole=True):
        """
        Start the VM by running a qemu command.
        All parameters are optional. If name, params or root_dir are not
        supplied, the respective values stored as class attributes are used.

        :param name: The name of the object
        :param params: A dict containing VM params
        :param root_dir: Base directory for relative filenames
        :param migration_mode: If supplied, start VM for incoming migration
                using this protocol (either 'tcp', 'unix' or 'exec')
        :param migration_exec_cmd: Command to embed in '-incoming "exec: ..."'
                (e.g. 'gzip -c -d filename') if migration_mode is 'exec'
        :param mac_source: A VM object from which to copy MAC addresses. If not
                specified, new addresses will be generated.

        :raise VMCreateError: If qemu terminates unexpectedly
        :raise VMKVMInitError: If KVM initialization fails
        :raise VMHugePageError: If hugepage initialization fails
        :raise VMImageMissingError: If a CD image is missing
        :raise VMHashMismatchError: If a CD image hash has doesn't match the
                expected hash
        :raise VMBadPATypeError: If an unsupported PCI assignment type is
                requested
        :raise VMPAError: If no PCI assignable devices could be assigned
        """
        error_context.context("creating '%s'" % self.name)
        self.destroy(free_mac_addresses=False)
        if name is not None:
            self.name = name
        if params is not None:
            self.params = params
        if root_dir is not None:
            self.root_dir = root_dir
        name = self.name
        params = self.params
        root_dir = self.root_dir

        if self.params.get("storage_type") == "nfs":
            storage.copy_nfs_image(self.params, data_dir.get_data_dir(),
                                   basename=True)
        # Verify the md5sum of the ISO images
        for cdrom in params.objects("cdroms"):
            if params.get("medium") == "import":
                break
            cdrom_params = params.object_params(cdrom)
            iso = cdrom_params.get("cdrom")
            xen_pv = (self.driver_type == 'xen' and
                      params.get('hvm_or_pv') == 'pv')
            iso_is_ks = os.path.basename(iso) == 'ks.iso'
            if xen_pv and iso_is_ks:
                continue
            if iso:
                iso = utils_misc.get_path(data_dir.get_data_dir(), iso)
                if not os.path.exists(iso):
                    raise virt_vm.VMImageMissingError(iso)
                compare = False
                if cdrom_params.get("skip_hash", "no") == "yes":
                    LOG.debug("Skipping hash comparison")
                elif cdrom_params.get("md5sum_1m"):
                    LOG.debug("Comparing expected MD5 sum with MD5 sum of "
                              "first MB of ISO file...")
                    actual_hash = crypto.hash_file(
                        iso, 1048576, algorithm="md5")
                    expected_hash = cdrom_params.get("md5sum_1m")
                    compare = True
                elif cdrom_params.get("md5sum"):
                    LOG.debug("Comparing expected MD5 sum with MD5 sum of "
                              "ISO file...")
                    actual_hash = crypto.hash_file(iso, algorithm="md5")
                    expected_hash = cdrom_params.get("md5sum")
                    compare = True
                elif cdrom_params.get("sha1sum"):
                    LOG.debug("Comparing expected SHA1 sum with SHA1 sum "
                              "of ISO file...")
                    actual_hash = crypto.hash_file(iso, algorithm="sha1")
                    expected_hash = cdrom_params.get("sha1sum")
                    compare = True
                if compare:
                    if actual_hash == expected_hash:
                        LOG.debug("Hashes match")
                    else:
                        raise virt_vm.VMHashMismatchError(actual_hash,
                                                          expected_hash)

        # Make sure the following code is not executed by more than one thread
        # at the same time
        lockfilename = os.path.join(data_dir.get_tmp_dir(),
                                    "libvirt-autotest-vm-create.lock")
        lockfile = open(lockfilename, "w+")
        fcntl.lockf(lockfile, fcntl.LOCK_EX)

        try:
            # Handle port redirections
            redir_names = params.objects("redirs")
            host_ports = utils_misc.find_free_ports(
                5000, 5899, len(redir_names))
            self.redirs = {}
            for i in range(len(redir_names)):
                redir_params = params.object_params(redir_names[i])
                guest_port = int(redir_params.get("guest_port"))
                self.redirs[guest_port] = host_ports[i]

            # Find available PCI devices
            self.pci_devices = []
            for device in params.objects("pci_devices"):
                self.pci_devices.append(device)

            # Find available VNC port, if needed
            if params.get("display") == "vnc":
                if params.get("vnc_autoport") == "yes":
                    self.vnc_port = None
                    self.vnc_autoport = True
                else:
                    self.vnc_port = utils_misc.find_free_port(5900, 6100)
                    self.vnc_autoport = False

            # Find available spice port, if needed
            if params.get("spice"):
                self.spice_port = utils_misc.find_free_port(8000, 8100)

            # Find random UUID if specified 'uuid = random' in config file
            if params.get("uuid") == "random":
                f = open("/proc/sys/kernel/random/uuid")
                self.uuid = f.read().strip()
                f.close()

            # Generate or copy MAC addresses for all NICs
            for nic in self.virtnet:
                nic_params = dict(nic)
                if mac_source is not None:
                    # Will raise exception if source doesn't
                    # have corresponding nic
                    LOG.debug("Copying mac for nic %s from VM %s",
                              nic.nic_name, mac_source.name)
                    nic_params['mac'] = mac_source.get_mac_address(
                        nic.nic_name)
                # make_create_command() calls vm.add_nic (i.e. on a copy)
                nic = self.add_nic(**nic_params)
                LOG.debug('VM.create activating nic %s' % nic)
                self.activate_nic(nic.nic_name)

            # Make qemu command
            install_command = self.make_create_command()

            LOG.info("Running libvirt command (reformatted):")
            for item in install_command.replace(" -", " \n    -").splitlines():
                LOG.info("%s", item)
            try:
                process.run(install_command, verbose=True, shell=True)
            except process.CmdError as details:
                stderr = details.result.stderr_text.strip()
                # This is a common newcomer mistake, be more helpful...
                if stderr.count('IDE CDROM must use'):
                    testname = params.get('name', "")
                    if testname.count('unattended_install.cdrom'):
                        if not testname.count('http_ks'):
                            e_msg = ("Install command "
                                     "failed:\n%s \n\nNote: "
                                     "Older versions of "
                                     "libvirt won't work "
                                     "properly with kickstart "
                                     "on cdrom  install. "
                                     "Try using the "
                                     "unattended_install.cdrom.http_ks method "
                                     "instead." % details.result)
                            raise exceptions.TestSkipError(e_msg)
                if stderr.count('failed to launch bridge helper'):
                    if utils_selinux.is_enforcing():
                        raise exceptions.TestSkipError("SELinux is enabled "
                                                       "and preventing the "
                                                       "bridge helper from "
                                                       "accessing the bridge. "
                                                       "Consider running as "
                                                       "root or placing "
                                                       "SELinux into "
                                                       "permissive mode.")
                # some other problem happened, raise normally
                raise
            # Wait for the domain to be created
            utils_misc.wait_for(func=self.is_alive, timeout=60,
                                text=("waiting for domain %s to start" %
                                      self.name))
            result = virsh.domuuid(self.name, uri=self.connect_uri)
            self.uuid = result.stdout_text.strip()
            # Create isa serial ports.
            self.create_serial_console()
        finally:
            fcntl.lockf(lockfile, fcntl.LOCK_UN)
            lockfile.close()

    def migrate(self, dest_uri="", option="--live --timeout 60", extra="",
                **dargs):
        """
        Migrate a VM to a remote host.

        :param dest_uri: Destination libvirt URI
        :param option: Migration options before <domain> <desturi>
        :param extra: Migration options after <domain> <desturi>
        :param dargs: Standardized virsh function API keywords
        :return: True if command succeeded
        """
        LOG.info("Migrating VM %s from %s to %s" %
                 (self.name, self.connect_uri, dest_uri))
        result = virsh.migrate(self.name, dest_uri, option,
                               extra, uri=self.connect_uri,
                               **dargs)
        # Close down serial_console logging process
        self.cleanup_serial_console()
        # On successful migration, point to guests new hypervisor.
        # Since dest_uri could be None, checking it is necessary.
        if result.exit_status == 0 and dest_uri:
            self.connect_uri = dest_uri

        # Set vm name in case --dname is specified.
        migrate_options = ""
        if option:
            migrate_options = str(option)
        if extra:
            migrate_options += " %s" % extra
        if migrate_options.count("--dname"):
            migrate_options_list = migrate_options.split()
            self.name = migrate_options_list[migrate_options_list.index("--dname") + 1]
        self.create_serial_console()
        return result

    def attach_disk(self, source, target=None, prefix="vd", extra="",
                    ignore_status=False, debug=False):
        """
        Attach a disk to VM and return the target device name.

        :param source: source of disk device
        :param target: target of disk device, None for automatic assignment.
        :param prefix: disk device prefix.
        :param extra: additional arguments to command
        :return: target device name if succeed, Otherwise None
        """
        # Find the next available target device name.
        if target is None:
            disks = self.get_disk_devices()
            for ch in string.ascii_lowercase:
                target = prefix + ch
                if target not in disks:
                    break

        result = virsh.attach_disk(self.name, source, target, extra,
                                   uri=self.connect_uri,
                                   ignore_status=ignore_status,
                                   debug=debug)
        if result.exit_status:
            LOG.error("Failed to attach disk %s to VM."
                      "Detail: %s."
                      % (source, result.stderr_text))
            return None
        return target

    def detach_disk(self, target, extra="",
                    ignore_status=False, debug=False):
        """
        Detach a disk from VM.

        :param target: target of disk device need to be detached.
        :param extra: additional arguments to command
        """
        return virsh.detach_disk(self.name, target, extra,
                                 uri=self.connect_uri,
                                 ignore_status=ignore_status,
                                 debug=debug)

    def attach_interface(self, option="", ignore_status=False,
                         debug=False):
        """
        Attach a NIC to VM.
        """
        return virsh.attach_interface(self.name, option,
                                      uri=self.connect_uri,
                                      ignore_status=ignore_status,
                                      debug=debug)

    def detach_interface(self, option="", ignore_status=False,
                         debug=False):
        """
        Detach a NIC from VM.
        """
        return virsh.detach_interface(self.name, option,
                                      uri=self.connect_uri,
                                      ignore_status=ignore_status,
                                      debug=debug)

    def destroy(self, gracefully=True, free_mac_addresses=True):
        """
        Destroy the VM.

        If gracefully is True, first attempt to shutdown the VM with a shell
        command. If that fails, send SIGKILL to the qemu process.

        :param gracefully: If True, an attempt will be made to end the VM
                using a shell command before trying to end the qemu process
                with a 'quit' or a kill signal.
        :param free_mac_addresses: If vm is undefined with libvirt, also
                                   release/reset associated mac address
        """
        try:
            # Is it already dead?
            if self.is_alive():
                LOG.debug("Destroying VM")
                if self.is_paused():
                    self.resume()
                if (not self.is_lxc() and gracefully and
                        self.params.get("shutdown_command")):
                    # Try to destroy with shell command
                    LOG.debug("Trying to shutdown VM with shell command")
                    try:
                        session = self.login()
                    except (remote.LoginError, virt_vm.VMError) as e:
                        LOG.debug(e)
                    else:
                        try:
                            # Send the shutdown command
                            session.sendline(
                                self.params.get("shutdown_command"))
                            LOG.debug("Shutdown command sent; waiting for VM "
                                      "to go down...")
                            if utils_misc.wait_for(self.is_dead, 60, 1, 1):
                                LOG.debug("VM is down")
                                return
                        finally:
                            session.close()
            # Destroy VM directly, as 'ignore_status=True' by default, so destroy
            # a shutoff domain is also acceptable here.
            destroy_opt = ''
            if gracefully:
                destroy_opt = '--graceful'
            virsh.destroy(self.name, destroy_opt, uri=self.connect_uri)

        finally:
            self.cleanup_serial_console()
        if free_mac_addresses:
            if self.is_persistent():
                LOG.warning("Requested MAC address release from "
                            "persistent vm %s. Ignoring." % self.name)
            else:
                LOG.debug("Releasing MAC addresses for vm %s." % self.name)
                for nic_name in self.virtnet.nic_name_list():
                    self.virtnet.free_mac_address(nic_name)

    def remove(self, undef_opts=None):
        """
        Remove vm, which means destroy and undefine vm, also release vm mac
        address.
        Note:
        1. Destroy failure is ignored, while undefine failure is raised.

        :param undef_opts: Virsh options used to undefine vm. Recommend to use
            "--snapshots-metadata"/"--managed-save"/"checkpoints-metadata" if
            vm has snapshot/managed-save file/checkpoint

        :raise VMRemoveError when vm undefine fails
        """
        self.destroy(gracefully=True, free_mac_addresses=False)
        if not self.undefine(options=undef_opts):
            raise virt_vm.VMRemoveError("VM '%s' undefine error" % self.name)
        self.destroy(gracefully=False, free_mac_addresses=True)
        LOG.debug("VM '%s' was removed", self.name)

    def remove_with_storage(self):
        """
        Virsh undefine provides an option named --remove-all-storage, but it
        only removes the storage which is managed by libvirt.

        This method undefines vm and removes the all storages related with this
        vm, no matter storages are managed by libvirt or not.
        """
        blklist = list(self.get_disk_devices().values())
        self.remove()
        for blk in blklist:
            path = blk['source']
            if os.path.exists(path):
                os.remove(path)

    def get_uuid(self):
        """
        Return VM's UUID.
        """
        result = virsh.domuuid(self.name, uri=self.connect_uri)
        uuid = result.stdout_text.strip()
        # only overwrite it if it's not set
        if self.uuid is None:
            self.uuid = uuid
        return self.uuid

    def get_ifname(self, nic_index=0):
        raise NotImplementedError

    def get_virsh_mac_address(self, nic_index=0):
        """
        Get the MAC of this VM domain.

        :param nic_index: Index of the NIC
        :raise VMMACAddressMissingError: If no MAC address is defined for the
                requested NIC
        """
        cmd_result = virsh.dumpxml(self.name, uri=self.connect_uri)
        if cmd_result.exit_status:
            raise exceptions.TestFail("dumpxml %s failed.\n"
                                      "Detail: %s.\n" % (self.name, cmd_result))
        thexml = cmd_result.stdout_text.strip()
        xtf = xml_utils.XMLTreeFile(thexml)
        interfaces = xtf.find('devices').findall('interface')
        # Range check
        try:
            mac = interfaces[nic_index].find('mac').get('address')
            if mac is not None:
                return mac
        except IndexError:
            pass  # Allow other exceptions through
        # IndexError (range check) or mac is None
        raise virt_vm.VMMACAddressMissingError(nic_index)

    def get_mac_address(self, nic_index=0):
        """
        Return the MAC address of a NIC.

        :param nic_index: Index of the NIC
        :return: MAC address of the NIC
        :raise VMMACAddressMissingError: If no MAC address is defined for the
                requested NIC
        """
        try:
            return super(VM, self).get_mac_address(nic_index)
        except virt_vm.VMMACAddressMissingError:
            mac = self.get_virsh_mac_address(nic_index)
            self.virtnet.set_mac_address(nic_index, mac)
            return mac

    def get_pid(self):
        """
        Return the VM's PID.

        :return: int with PID. If VM is not alive, returns None.
        """
        if self.is_lxc():
            pid_file = "/var/run/libvirt/lxc/%s.pid" % self.name
        elif self.is_qemu():
            pid_file = "/var/run/libvirt/qemu/%s.pid" % self.name
        elif self.is_esx():
            pid_file = "/var/run/libvirt/esx/%s.pid" % self.name
        # TODO: Add more vm driver type
        else:
            raise ValueError("Unsupport connect uri: %s." % self.connect_uri)
        pid = None
        if os.path.exists(pid_file):
            try:
                pid_file_contents = open(pid_file).read()
                pid = int(pid_file_contents)
            except IOError:
                LOG.error("Could not read %s to get PID", pid_file)
            except TypeError:
                LOG.error("PID file %s has invalid contents: '%s'",
                          pid_file, pid_file_contents)
        else:
            LOG.debug("PID file %s not present", pid_file)

        return pid

    def get_vcpus_pid(self):
        """
        Return the vcpu's pid for a given VM.

        :return: list of PID of vcpus of a VM.
        """
        output = virsh.qemu_monitor_command(self.name, "info cpus", "--hmp",
                                            uri=self.connect_uri)
        vcpu_pids = re.findall(r'thread_id=(\d+)',
                               output.stdout_text)
        return vcpu_pids

    def get_shell_pid(self):
        """
        Return the PID of the parent shell process.

        :note: This works under the assumption that ``self.process.get_pid()``
            returns the PID of the parent shell process.
        """
        return self.process.get_pid()

    def get_shared_meminfo(self):
        """
        Returns the VM's shared memory information.

        :return: Shared memory used by VM (MB)
        """
        if self.is_dead():
            LOG.error("Could not get shared memory info from dead VM.")
            return None

        filename = "/proc/%d/statm" % self.get_pid()
        shm = int(open(filename).read().split()[2])
        # statm stores information in pages, translate it to MB
        return shm * 4.0 / 1024

    def get_cpu_topology_in_cmdline(self):
        """
        Return the VM's cpu topology in VM cmdline.

        :return: A dirt of cpu topology
        """
        cpu_topology = {}
        vm_pid = self.get_pid()
        if vm_pid is None:
            LOG.error("Fail to get VM pid")
        else:
            cmdline = open("/proc/%d/cmdline" % vm_pid).read()
            values = re.findall("sockets=(\d+),cores=(\d+),threads=(\d+)",
                                cmdline)[0]
            cpu_topology = dict(zip(["sockets", "cores", "threads"], values))
        return cpu_topology

    def get_cpu_topology_in_vm(self):
        cpu_topology = {}
        cpu_info = cpu.get_cpu_info(self.wait_for_login())
        if cpu_info:
            cpu_topology['sockets'] = cpu_info['Socket(s)']
            cpu_topology['cores'] = cpu_info['Core(s) per socket']
            cpu_topology['threads'] = cpu_info['Thread(s) per core']
        return cpu_topology

    def activate_nic(self, nic_index_or_name):
        # TODO: Implement nic hotplugging
        pass  # Just a stub for now

    def deactivate_nic(self, nic_index_or_name):
        # TODO: Implement nic hot un-plugging
        pass  # Just a stub for now

    @error_context.context_aware
    def reboot(self, session=None, method="shell", nic_index=0, timeout=240,
               serial=False):
        """
        Reboot the VM and wait for it to come back up by trying to log in until
        timeout expires.

        :param session: A shell session object or None.
        :param method: Reboot method.  Can be "shell" (send a shell reboot
                command).
        :param nic_index: Index of NIC to access in the VM, when logging in
                after rebooting.
        :param timeout: Time to wait for login to succeed (after rebooting).
        :param serial: Just use to unify api in virt_vm module.
        :return: A new shell session object.
        """
        error_context.base_context("rebooting '%s'" % self.name, LOG.info)
        error_context.context("before reboot")
        session = session or self.login(timeout=timeout)
        error_context.context()

        if method == "shell":
            session.sendline(self.params.get("reboot_command"))
        else:
            raise virt_vm.VMRebootError("Unknown reboot method: %s" % method)

        error_context.context("waiting for guest to go down", LOG.info)
        if not utils_misc.wait_for(lambda: not
                                   session.is_responsive(timeout=30),
                                   120, 0, 1):
            raise virt_vm.VMRebootError("Guest refuses to go down")
        session.close()

        error_context.context("logging in after reboot", LOG.info)
        if serial:
            return self.wait_for_serial_login(timeout=timeout)
        return self.wait_for_login(nic_index, timeout=timeout)

    def screendump(self, filename, debug=False):
        if debug:
            LOG.debug("Requesting screenshot %s" % filename)
        return virsh.screenshot(self.name, filename, uri=self.connect_uri)

    def start(self, autoconsole=True):
        """
        Starts this VM.
        """
        uid_result = virsh.domuuid(self.name, uri=self.connect_uri)
        self.uuid = uid_result.stdout_text.strip()

        LOG.debug("Starting vm '%s'", self.name)
        result = virsh.start(self.name, uri=self.connect_uri)
        if not result.exit_status:
            # Wait for the domain to be created
            has_started = utils_misc.wait_for(func=self.is_alive, timeout=60,
                                              text=("waiting for domain %s "
                                                    "to start" % self.name))
            if has_started is None:
                raise virt_vm.VMStartError(self.name, "libvirt domain not "
                                                      "active after start")
            uid_result = virsh.domuuid(self.name, uri=self.connect_uri)
            self.uuid = uid_result.stdout_text.strip()
            # Establish a session with the serial console
            if autoconsole:
                self.create_serial_console()
        else:
            LOG.error("VM fails to start with:%s", result)
            raise virt_vm.VMStartError(self.name,
                                       result.stderr_text.strip())

        # Pull in mac addresses from libvirt guest definition
        for index, nic in enumerate(self.virtnet):
            try:
                mac = self.get_virsh_mac_address(index)
                if 'mac' not in nic:
                    LOG.debug("Updating nic %d with mac %s on vm %s"
                              % (index, mac, self.name))
                    nic.mac = mac
                elif nic.mac != mac:
                    LOG.warning("Requested mac %s doesn't match mac %s "
                                "as defined for vm %s", nic.mac, mac, self.name)
                # TODO: Checkout/Set nic_model, nettype, netdst also
            except virt_vm.VMMACAddressMissingError:
                LOG.warning("Nic %d requested by test but not defined for"
                            " vm %s" % (index, self.name))

    def wait_for_shutdown(self, count=60):
        """
        Return True on successful domain shutdown.

        Wait for a domain to shutdown, libvirt does not block on domain
        shutdown so we need to watch for successful completion.

        :param name: VM name
        :param name: Optional timeout value
        """
        timeout = count
        while count > 0:
            # check every 5 seconds
            if count % 5 == 0:
                if virsh.is_dead(self.name, uri=self.connect_uri):
                    LOG.debug("Shutdown took %d seconds", timeout - count)
                    return True
            count -= 1
            time.sleep(1)
            LOG.debug("Waiting for guest to shutdown %d", count)
        return False

    def shutdown(self):
        """
        Shuts down this VM.
        """
        try:
            if self.state() != 'shut off':
                virsh.shutdown(self.name, uri=self.connect_uri)
            if self.wait_for_shutdown():
                LOG.debug("VM %s shut down", self.name)
                self.cleanup_serial_console()
                return True
            else:
                LOG.error("VM %s failed to shut down", self.name)
                return False
        except process.CmdError:
            LOG.error("VM %s failed to shut down", self.name)
            return False

    def pause(self):
        try:
            state = self.state()
            if state != 'paused':
                virsh.suspend(
                    self.name, uri=self.connect_uri, ignore_status=False)
            return True
        except Exception:
            LOG.error("VM %s failed to suspend", self.name)
            return False

    def resume(self):
        try:
            virsh.resume(self.name, ignore_status=False, uri=self.connect_uri)
            if self.is_alive():
                LOG.debug("Resumed VM %s", self.name)
                return True
            else:
                return False
        except process.CmdError as detail:
            LOG.error("Resume VM %s failed:\n%s", self.name, detail)
            return False

    def save_to_file(self, path):
        """
        Override BaseVM save_to_file method
        """
        if self.is_dead():
            raise virt_vm.VMStatusError(
                "Cannot save a VM that is %s" % self.state())
        LOG.debug("Saving VM %s to %s" % (self.name, path))
        result = virsh.save(self.name, path, uri=self.connect_uri)
        if result.exit_status:
            raise virt_vm.VMError("Save VM to %s failed.\n"
                                  "Detail: %s."
                                  % (path, result.stderr_text))
        if self.is_alive():
            raise virt_vm.VMStatusError("VM not shut off after save")
        self.cleanup_serial_console()

    def restore_from_file(self, path):
        """
        Override BaseVM restore_from_file method
        """
        if self.is_alive():
            raise virt_vm.VMStatusError(
                "Can not restore VM that is %s" % self.state())
        LOG.debug("Restoring VM from %s" % path)
        result = virsh.restore(path, uri=self.connect_uri)
        if result.exit_status:
            raise virt_vm.VMError("Restore VM from %s failed.\n"
                                  "Detail: %s."
                                  % (path, result.stderr_text))
        if self.is_dead():
            raise virt_vm.VMStatusError(
                "VM should not be %s after restore." % self.state())
        self.create_serial_console()

    def managedsave(self):
        """
        Managed save of VM's state
        """
        if self.is_dead():
            raise virt_vm.VMStatusError(
                "Cannot save a VM that is %s" % self.state())
        LOG.debug("Managed saving VM %s" % self.name)
        result = virsh.managedsave(self.name, uri=self.connect_uri)
        if result.exit_status:
            raise virt_vm.VMError("Managed save VM failed.\n"
                                  "Detail: %s."
                                  % result.stderr_text)
        if self.is_alive():
            raise virt_vm.VMStatusError("VM not shut off after managed save")
        self.cleanup_serial_console()

    def pmsuspend(self, target='mem', duration=0):
        """
        Suspend a domain gracefully using power management functions
        """
        if self.is_dead():
            raise virt_vm.VMStatusError(
                "Cannot pmsuspend a VM that is %s" % self.state())
        LOG.debug("PM suspending VM %s" % self.name)
        result = virsh.dompmsuspend(self.name, target=target,
                                    duration=duration, uri=self.connect_uri)
        if result.exit_status:
            raise virt_vm.VMError("PM suspending VM failed.\n"
                                  "Detail: %s."
                                  % result.stderr_text)
        self.cleanup_serial_console()

    def pmwakeup(self):
        """
        Wakeup a domain from pmsuspended state
        """
        if self.is_dead():
            raise virt_vm.VMStatusError(
                "Cannot pmwakeup a VM that is %s" % self.state())
        LOG.debug("PM waking up VM %s" % self.name)
        result = virsh.dompmwakeup(self.name, uri=self.connect_uri)
        if result.exit_status:
            raise virt_vm.VMError("PM waking up VM failed.\n"
                                  "Detail: %s."
                                  % result.stderr_text)
        self.create_serial_console()

    def vcpupin(self, vcpu, cpu_list, options=""):
        """
        To pin vcpu to cpu_list
        """
        result = virsh.vcpupin(self.name, vcpu, cpu_list,
                               options, uri=self.connect_uri)
        if result.exit_status:
            raise exceptions.TestFail("Virsh vcpupin command failed.\n"
                                      "Detail: %s.\n" % result)

    def dominfo(self):
        """
        Return a dict include vm's information.
        """
        result = virsh.dominfo(self.name, uri=self.connect_uri)
        output = result.stdout_text.strip()
        # Key: word before ':' | value: content after ':' (stripped)
        dominfo_dict = {}
        for line in output.splitlines():
            key = line.split(':')[0].strip()
            value = line.split(':')[-1].strip()
            dominfo_dict[key] = value
        return dominfo_dict

    def vcpuinfo(self):
        """
        Return a dict's list include vm's vcpu information.
        """
        result = virsh.vcpuinfo(self.name, uri=self.connect_uri)
        output = result.stdout_text.strip()
        # Key: word before ':' | value: content after ':' (stripped)
        vcpuinfo_list = []
        vcpuinfo_dict = {}
        for line in output.splitlines():
            key = line.split(':')[0].strip()
            value = line.split(':')[-1].strip()
            vcpuinfo_dict[key] = value
            if key == "CPU Affinity":
                vcpuinfo_list.append(vcpuinfo_dict)
        return vcpuinfo_list

    def domfsinfo(self):
        """
        Return a dict's list include domain mounted filesystem information
        via virsh command
        """
        result = virsh.domfsinfo(self.name, ignore_status=False,
                                 uri=self.connect_uri)
        lines = result.stdout_text.strip().splitlines()
        domfsinfo_list = []
        if len(lines) > 2:
            head = lines[0]
            lines = lines[2:]
            names = head.split()
            for line in lines:
                values = line.split()
                domfsinfo_list.append(dict(zip(names, values)))

        return domfsinfo_list

    def get_used_mem(self):
        """
        Get vm's current memory(kilobytes).
        """
        dominfo_dict = self.dominfo()
        memory = dominfo_dict['Used memory'].split(' ')[0]  # strip off ' kb'
        return int(memory)

    def get_blk_devices(self):
        """
        Get vm's block devices.

        Return a dict include all devices detail info.
        example:
        {target: {'type': value, 'device': value, 'source': value}}
        """
        domblkdict = {}
        options = "--details"
        result = virsh.domblklist(self.name, options, ignore_status=True,
                                  uri=self.connect_uri)
        blklist = result.stdout_text.strip().splitlines()
        if result.exit_status != 0:
            LOG.info("Get vm devices failed.")
        else:
            blklist = blklist[2:]
            for line in blklist:
                linesplit = line.split(None, 4)
                target = linesplit[2]
                blk_detail = {'type': linesplit[0],
                              'device': linesplit[1],
                              'source': linesplit[3]}
                domblkdict[target] = blk_detail
        return domblkdict

    def get_disk_devices(self):
        """
        Get vm's disk type block devices.
        """
        blk_devices = self.get_blk_devices()
        disk_devices = {}
        for target in blk_devices:
            details = blk_devices[target]
            if details['device'] == "disk":
                disk_devices[target] = details
        return disk_devices

    def get_first_disk_devices(self):
        """
        Get vm's first disk type block devices.
        """
        disk = {}
        options = "--details"
        result = virsh.domblklist(self.name, options, ignore_status=True,
                                  uri=self.connect_uri)
        blklist = result.stdout_text.strip().splitlines()
        if result.exit_status != 0:
            LOG.info("Get vm devices failed.")
        else:
            blklist = blklist[2:]
            linesplit = blklist[0].split(None, 4)
            disk = {'type': linesplit[0],
                    'device': linesplit[1],
                    'target': linesplit[2],
                    'source': linesplit[3]}
        return disk

    def get_device_details(self, device_target):
        device_details = {}
        result = virsh.domblkinfo(self.name, device_target,
                                  uri=self.connect_uri)
        details = result.stdout_text.strip().splitlines()
        if result.exit_status != 0:
            LOG.info("Get vm device details failed.")
        else:
            for line in details:
                attrs = line.split(":")
                device_details[attrs[0].strip()] = attrs[-1].strip()
        return device_details

    def get_device_size(self, device_target):
        domblkdict = self.get_blk_devices()
        if device_target not in list(domblkdict.keys()):
            return None
        path = domblkdict[device_target]["source"]
        size = self.get_device_details(device_target)["Capacity"]
        return path, size

    def get_max_mem(self):
        """
        Get vm's maximum memory(kilobytes).
        """
        dominfo_dict = self.dominfo()
        max_mem = dominfo_dict['Max memory'].split(' ')[0]  # strip off 'kb'
        return int(max_mem)

    def domjobabort(self):
        """
        Abort job for vm.
        """
        result = virsh.domjobabort(self.name, ignore_status=True)
        if result.exit_status:
            LOG.debug(result)
            return False
        return True

    def dump(self, path, option=""):
        """
        Dump self to path.

        :raise: exceptions.TestFail if dump fail.
        """
        cmd_result = virsh.dump(self.name, path=path, option=option,
                                uri=self.connect_uri)
        if cmd_result.exit_status:
            raise exceptions.TestFail("Failed to dump %s to %s.\n"
                                      "Detail: %s." % (self.name, path, cmd_result))

    def get_job_type(self):
        jobresult = virsh.domjobinfo(self.name, uri=self.connect_uri)
        if not jobresult.exit_status:
            for line in jobresult.stdout_text.splitlines():
                key = line.split(':')[0]
                value = line.split(':')[-1]
                if key.count("type"):
                    return value.strip()
        else:
            LOG.error(jobresult)
        return False

    def get_pci_devices(self, device_str=None):
        """
        Get PCI devices in vm according to given device character.

        :param device_str: a string to identify device.
        """
        session = self.wait_for_login()
        if device_str is None:
            cmd = "lspci -D"
        else:
            cmd = "lspci -D | grep %s" % device_str
        lines = session.cmd_output(cmd)
        session.close()
        pci_devices = []
        for line in lines.splitlines():
            pci_devices.append(line.split()[0])
        return pci_devices

    def get_disks(self, diskname=None):
        """
        Get disks in vm.

        :param diskname: Specify disk to be listed,
                         used for checking given disk.
        """
        cmd = "lsblk --nodeps -n"
        if diskname:
            cmd += " | grep %s" % diskname
        session = self.wait_for_login()
        lines = session.cmd_output(cmd)
        session.close()
        disks = []
        for line in lines.splitlines():
            if line.count(" disk "):
                disks.append("/dev/%s" % line.split()[0])
        return disks

    def get_interfaces(self):
        """
        Get available interfaces in vm.
        """
        cmd = "cat /proc/net/dev"
        session = self.wait_for_login()
        lines = session.cmd_output(cmd)
        session.close()
        interfaces = []
        for line in lines.splitlines():
            if len(line.split(':')) != 2:
                continue
            interfaces.append(line.split(':')[0].strip())
        return interfaces

    def get_interface_mac(self, interface):
        """
        Get mac address of interface by given name.
        """
        if interface not in self.get_interfaces():
            return None
        cmd = "cat /sys/class/net/%s/address" % interface
        session = self.wait_for_login()
        try:
            mac = session.cmd_output(cmd)
        except Exception as detail:
            session.close()
            LOG.error(str(detail))
            return None
        session.close()
        return mac.strip()

    def install_package(self, name, ignore_status=False, timeout=300):
        """
        Install a package on VM.
        ToDo: Support multiple package manager.

        :param name: Name of package to be installed
        """
        session = self.wait_for_login()
        try:
            if not utils_package.package_install(name, session, timeout=timeout):
                raise virt_vm.VMError("Installation of package %s failed" %
                                      name)
        except Exception as exception_detail:
            if ignore_status:
                LOG.error("When install: %s\nError happened: %s\n",
                          name, exception_detail)
            else:
                raise exception_detail
        finally:
            session.close()

    def remove_package(self, name, ignore_status=False):
        """
        Remove a package from VM.
        ToDo: Support multiple package manager.

        :param name: Name of package to be removed
        """
        session = self.wait_for_login()
        if not utils_package.package_remove(name, session):
            if not ignore_status:
                session.close()
                raise virt_vm.VMError("Removal of package %s failed" % name)
            LOG.error("Removal of package %s failed", name)
        session.close()

    def prepare_guest_agent(self, prepare_xml=True, channel=True, start=True,
                            source_path=None, target_name='org.qemu.guest_agent.0'):
        """
        Prepare qemu guest agent on the VM.

        :param prepare_xml: Whether change VM's XML
        :param channel: Whether add agent channel in VM. Only valid if
                        prepare_xml is True
        :param start: Whether install and start the qemu-ga service
        :param source_path: Source path of the guest agent channel
        :param target_name: Target name of the guest agent channel
        """
        if prepare_xml:
            if self.is_alive():
                self.destroy()
            vmxml = libvirt_xml.VMXML.new_from_inactive_dumpxml(self.name)
            # Check if we need to change XML of VM by checking
            # whether the agent is existing.
            is_existing = False
            ga_channels = vmxml.get_agent_channels()
            for chnl in ga_channels:
                name = chnl.find('./target').get('name')
                try:
                    path = chnl.find('./source').get('path')
                except AttributeError:
                    path = None
                if (name == target_name and path == source_path):
                    is_existing = True
                break

            if channel != is_existing:
                if channel:
                    vmxml.set_agent_channel(src_path=source_path,
                                            tgt_name=target_name)
                else:
                    vmxml.remove_agent_channels()
                vmxml.sync()

        if not self.is_alive():
            self.start()

        self.install_package('pm-utils', ignore_status=True, timeout=15)
        self.install_package('qemu-guest-agent')

        self.set_state_guest_agent(start)

    def set_state_guest_agent(self, start):
        """
        Starts or stops the guest agent in guest.

        :param start: Start (True) or stop (False) the agent
        """

        session = self.wait_for_login()

        def _is_ga_running():
            return (not session.cmd_status("pgrep qemu-ga"))

        def _is_ga_finished():
            return (session.cmd_status("pgrep qemu-ga") == 1)

        def _start_ga():
            if not _is_ga_running():
                cmd = "service qemu-guest-agent start"
                status, output = session.cmd_status_output(cmd)
                # Sometimes the binary of the guest agent was corrupted on the
                # filesystem due to the guest being destroyed and cause service
                # masked, so need to reinstall agent to fix it
                if status and "is masked" in output:
                    self.remove_package('qemu-guest-agent')
                    self.install_package('qemu-guest-agent')
                    status, output = session.cmd_status_output(cmd)
                if status and "unrecognized service" in output:
                    cmd = "service qemu-ga start"
                    status, output = session.cmd_status_output(cmd)
                if status:
                    raise virt_vm.VMError("Start qemu-guest-agent failed:"
                                          "\n%s" % output)

        def _stop_ga():
            if _is_ga_running():
                cmd = "service qemu-guest-agent stop"
                status, output = session.cmd_status_output(cmd)
                if status and "unrecognized service" in output:
                    cmd = "service qemu-ga stop"
                    status, output = session.cmd_status_output(cmd)
                if status:
                    raise virt_vm.VMError("Stop qemu-guest-agent failed:"
                                          "\n%s" % output)

        try:
            # Start/stop qemu-guest-agent
            if start:
                _start_ga()
            else:
                _stop_ga()
            # Check qemu-guest-agent status
            if start:
                if not utils_misc.wait_for(_is_ga_running, timeout=60):
                    raise virt_vm.VMError("qemu-guest-agent is not running.")
            else:
                if not utils_misc.wait_for(_is_ga_finished, timeout=60):
                    raise virt_vm.VMError("qemu-guest-agent is running")
        finally:
            session.close()

    def getenforce(self):
        """
        Set SELinux mode in the VM.

        :return: SELinux mode [Enforcing|Permissive|Disabled]
        """
        self.install_package('libselinux-utils')
        session = self.wait_for_login()
        try:
            status, output = session.cmd_status_output("getenforce")
            if status != 0:
                raise virt_vm.VMError("Get SELinux mode failed:\n%s" % output)
            return output.strip()
        finally:
            session.close()

    def setenforce(self, mode):
        """
        Set SELinux mode in the VM.

        :param mode: SELinux mode [Enforcing|Permissive|1|0]
        """
        # SELinux is not supported by Ubuntu by default
        selinux_force = self.params.get("selinux_force", "no") == "yes"
        vm_distro = self.get_distro()
        if vm_distro.lower() == 'ubuntu' and not selinux_force:
            LOG.warning("Ubuntu doesn't support selinux by default")
            return
        self.install_package('selinux-policy')
        self.install_package('selinux-policy-targeted')
        self.install_package('libselinux-utils')
        try:
            if int(mode) == 1:
                target_mode = 'Enforcing'
            elif int(mode) == 0:
                target_mode = 'Permissive'
        except ValueError:
            pass

        session = self.wait_for_login()
        try:
            current_mode = self.getenforce()
            if current_mode == 'Disabled':
                LOG.warning("VM SELinux disabled. Can't set mode.")
                return
            elif current_mode != target_mode:
                cmd = "setenforce %s" % mode
                status, output = session.cmd_status_output(cmd)
                if status != 0:
                    raise virt_vm.VMError(
                        "Set SELinux mode failed:\n%s" % output)
            else:
                LOG.debug("VM SELinux mode don't need change.")
        finally:
            session.close()
