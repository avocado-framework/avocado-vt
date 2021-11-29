"""
Virt-v2v test utility functions.

:copyright: 2008-2012 Red Hat Inc.
"""

from __future__ import print_function

import glob
import logging
import os
import pwd
import random
import uuid
import re
import shutil
import tempfile
import time

import aexpect

from aexpect import remote
from avocado.utils import path
from avocado.utils import process
from avocado.utils.astring import to_text
from avocado.core import exceptions

from virttest import libvirt_vm as lvirt
from virttest import ovirt
from virttest import virsh
from virttest import ppm_utils
from virttest import data_dir
from virttest import remote as remote_old
from virttest import utils_misc
from virttest import ssh_key
from virttest.utils_test import libvirt
from virttest.libvirt_xml import vm_xml
from virttest.utils_version import VersionInterval
from virttest.utils_misc import asterisk_passwd
from virttest.utils_misc import compare_md5

try:
    V2V_EXEC = path.find_command('virt-v2v')
except path.CmdNotFoundError:
    V2V_EXEC = None

LOG = logging.getLogger('avocado.' + __name__)


class Uri(object):

    """
    This class is used for generating uri.
    """

    def __init__(self, hypervisor):
        if hypervisor is None:
            # kvm is a default hypervisor
            hypervisor = "kvm"
        self.hyper = hypervisor

    def get_uri(self, hostname, vpx_dc=None, esx_ip=None):
        """
        Uri dispatcher.

        :param hostname: String with host name.
        """
        uri_func = getattr(self, "_get_%s_uri" % self.hyper)
        self.host = hostname
        self.vpx_dc = vpx_dc
        self.esx_ip = esx_ip
        return uri_func()

    def _get_kvm_uri(self):
        """
        Return kvm uri.
        """
        uri = "qemu:///system"
        return uri

    def _get_xen_uri(self):
        """
        Return xen uri.
        """
        uri = "xen+ssh://root@" + self.host + "/"
        return uri

    def _get_esx_uri(self):
        """
        Return esx uri.
        """
        uri = ''
        if self.vpx_dc and self.esx_ip:
            uri = "vpx://root@%s/%s/%s/?no_verify=1" % (self.host,
                                                        self.vpx_dc,
                                                        self.esx_ip)
        if not self.vpx_dc and self.esx_ip:
            uri = "esx://root@%s/?no_verify=1" % self.esx_ip
        return uri

    # add new hypervisor in here.


class Target(object):

    """
    This class is used for generating command options.
    """

    def __init__(self, target, uri):
        if target is None:
            # libvirt is a default target
            target = "libvirt"
        self.target = target
        self.uri = uri
        # Save NFS mount records like {0:(src, dst, fstype)}
        self.mount_records = {}
        # Authorized_keys is a list which every element is a tuple.
        # The value of each tuple is like (session, key, server_type).
        self.authorized_keys = []

    def cleanup(self):
        """
        Cleanup NFS mount records
        """
        for src, dst, fstype in self.mount_records.values():
            utils_misc.umount(src, dst, fstype)

        self.cleanup_authorized_keys()

    def cleanup_authorized_keys(self):
        """
        Clean up authorized_keys in remote server
        """
        try:
            for session, key, server_type in self.authorized_keys:
                if not session or not key:
                    continue
                LOG.debug(
                    "session=%s key=%s server_type=%s",
                    session,
                    key,
                    server_type)
                session.cmd("sed -i '/%s/d' %s" %
                            (key, get_authorized_keys_file(server_type)))
        finally:
            # Close session here in case the following element use same
            # session, although it could not happen in general.
            for session, _, _ in self.authorized_keys:
                if session:
                    LOG.debug("closed session = %s", session)
                    session.close()

    def get_cmd_options(self, params):
        """
        Target dispatcher.
        """
        self.params = params
        self.pub_key = params_get(params, 'pub_key')
        self.unprivileged_user = params_get(params, 'unprivileged_user')
        self.os_directory = params_get(params, 'os_directory')
        self.output_method = self.params.get('output_method', 'rhv')
        self.input_mode = self.params.get('input_mode')
        self.esxi_host = self.params.get(
            'esxi_host', self.params.get('esx_ip'))
        self.datastore = self.params.get('datastore')
        self._nfspath = self.params.get('_nfspath')
        self.src_uri_type = params.get('src_uri_type')
        self.esxi_password = params.get('esxi_password')
        self.input_transport = self.params.get('input_transport')
        self.vddk_libdir = self.params.get('vddk_libdir')
        self.vddk_libdir_src = self.params.get('vddk_libdir_src')
        self.vddk_thumbprint = self.params.get('vddk_thumbprint')
        self.vcenter_host = self.params.get('vcenter_host')
        self.vcenter_password = self.params.get('vcenter_password')
        self.vm_name = self.params.get('main_vm')
        self.bridge = self.params.get('bridge')
        self.network = self.params.get('network')
        self.of_format = self.params.get('of_format', 'raw')
        self.input_file = self.params.get('input_file')
        self.new_name = self.params.get('new_name')
        self.username = self.params.get('username', 'root')
        self.vmx_nfs_src = self.params.get('vmx_nfs_src')
        self.has_genid = self.params.get('has_genid')
        # --mac arguments with format as v2v, multiple macs can be
        # separated by ';'.
        self.iface_macs = self.params.get('iface_macs')
        # '_iface_list' is set automatically, Users should not use it.
        self._iface_list = self.params.get('_iface_list')
        self.net_vm_opts = ""
        self._vmx_filename_fullpath = self._vmx_filename = ""

        def _compose_vmx_filename():
            """
            Return vmx filename for '-i vmx'.

            All vmname, nfs directory and vmx name may be different
            e.g.
            vmname:  esx6.7-ubuntu18.04-x86_64
            nfspath: esx6.5-ubuntu18.04-x86_64-bug1481930/esx6.5-ubuntu18.04-x86_64-bug1481930.vmx
            """
            if self.vmx_nfs_src and ':' in self.vmx_nfs_src:
                mount_point = v2v_mount(self.vmx_nfs_src, 'vmx_nfs_src')
                self.mount_records[len(self.mount_records)] = (
                    self.vmx_nfs_src, mount_point, None)

                vmx_path = os.path.join(mount_point, self._nfspath, '*.vmx')
                vmxfiles = glob.glob(vmx_path)

                if len(vmxfiles) == 0:
                    raise exceptions.TestError(
                        "Did not found any vmx files in %s" % vmx_path)

                self._vmx_filename_fullpath = vmxfiles[0]
                self._vmx_filename = os.path.basename(vmxfiles[0])
                LOG.debug(
                    'vmx file full path is %s' %
                    self._vmx_filename_fullpath)
            else:
                # This only works for -i vmx -it ssh, because it only needs an vmx filename,
                # and doesn't have to mount the nfs storage. If the guessed name is wrong,
                # v2v will report an error.
                LOG.info(
                    'vmx_nfs_src is not set in cfg file, try to guess vmx filename')
                # some guest's directory name ends with '_1',
                # e.g. esx5.5-win10-x86_64_1/esx5.5-win10-x86_64.vmx
                #
                # Note: the pattern order cannot be changed
                guess_ptn_list = [r'(^.*?(x86_64|i386))_[0-9]+$',
                                  r'(^.*?(x86_64|i386)$)',
                                  r'(^.*?)_[0-9]+$']

                for ptn in guess_ptn_list:
                    if re.search(ptn, self._nfspath):
                        self._vmx_filename = re.search(
                            ptn, self._nfspath).group(1)
                        break

                if not self._vmx_filename:
                    self._vmx_filename = self._nfspath

                self._vmx_filename = self._vmx_filename + '.vmx'
                LOG.debug(
                    'Guessed vmx file name is %s' %
                    self._vmx_filename)

        def _compose_input_transport_options():
            """
            Set input transport options for v2v
            """
            options = ''
            if self.input_transport is None:
                return options

            # -it vddk
            if self.input_transport == 'vddk':
                if self.vddk_libdir is None or not os.path.isdir(
                        self.vddk_libdir):
                    # Invalid nfs mount source if no ':'
                    if self.vddk_libdir_src is None or ':' not in self.vddk_libdir_src:
                        LOG.error(
                            'Neither vddk_libdir nor vddk_libdir_src was set')
                        raise exceptions.TestError(
                            "VDDK library directory or NFS mount point must be set")

                    vddk_lib_prefix = 'vddklib_'
                    # General vddk directory
                    if self.unprivileged_user:
                        home = pwd.getpwnam(self.unprivileged_user).pw_dir
                        vddk_lib_rootdir = os.path.join(home, 'vddk_libdir')
                    else:
                        vddk_lib_rootdir = os.path.expanduser('~/vddk_libdir')
                    vddk_libdir = '%s/latest' % vddk_lib_rootdir
                    check_list = ['FILES',
                                  'lib64/libgvmomi.so',
                                  'bin64/vmware-vdiskmanager']

                    mount_point = v2v_mount(
                        self.vddk_libdir_src, 'vddk_libdir')

                    LOG.info('Preparing vddklib on local server')
                    if os.path.exists(vddk_lib_rootdir):
                        if os.path.exists(vddk_libdir):
                            os.unlink(vddk_libdir)

                        vddklib_count = len(
                            glob.glob(
                                '%s/%s*' %
                                (vddk_lib_rootdir, vddk_lib_prefix)))
                        for i in range(1, vddklib_count + 1):
                            vddk_lib = '%s/%s' % (vddk_lib_rootdir,
                                                  vddk_lib_prefix + str(i))
                            if all(
                                compare_md5(
                                    os.path.join(
                                        mount_point, file_i), os.path.join(
                                        vddk_lib, file_i)) for file_i in check_list):
                                os.symlink(vddk_lib, vddk_libdir, True)
                                break

                        if not os.path.exists(vddk_libdir):
                            vddk_lib = '%s/%s' % (vddk_lib_rootdir,
                                                  vddk_lib_prefix + str(vddklib_count + 1))
                            shutil.copytree(mount_point, vddk_lib)
                            os.symlink(vddk_lib, vddk_libdir, True)
                    else:
                        vddk_lib = '%s/%s' % (vddk_lib_rootdir,
                                              vddk_lib_prefix + '1')
                        shutil.copytree(mount_point, vddk_lib)
                        os.symlink(vddk_lib, vddk_libdir, True)

                    LOG.info('vddklib on local server is %s', vddk_lib)
                    self.vddk_libdir = vddk_libdir
                    utils_misc.umount(self.vddk_libdir_src, mount_point, None)

                # Invalid vddk thumbprint if no ':'
                if self.vddk_thumbprint is None or ':' not in self.vddk_thumbprint:
                    self.vddk_thumbprint = get_vddk_thumbprint(
                        *
                        (
                            self.esxi_host,
                            self.esxi_password,
                            self.src_uri_type) if self.src_uri_type == 'esx' else (
                            self.vcenter_host,
                            self.vcenter_password,
                            self.src_uri_type))

            # -it ssh
            if self.input_transport == 'ssh':
                pub_key, session = v2v_setup_ssh_key(
                    self.esxi_host, self.username, self.esxi_password, server_type='esx', public_key=self.pub_key, auto_close=False)
                self.authorized_keys.append(
                    (session, pub_key.split()[1].split('/')[0], 'esx'))
                utils_misc.add_identities_into_ssh_agent()

            # New input_transport type can be added here

            # A dict to save input_transport types and their io options, new it_types
            # should be added here. Their io values were composed during running time
            # based on user's input
            input_transport_args = {
                'vddk': "-io vddk-libdir=%s -io vddk-thumbprint=%s" % (self.vddk_libdir,
                                                                       self.vddk_thumbprint),
                'ssh': "ssh://root@{}/vmfs/volumes/{}/{}/{}".format(
                    self.esxi_host,
                    self.datastore,
                    self._nfspath,
                    self._vmx_filename)}

            options = " -it %s " % (self.input_transport)
            options += input_transport_args[self.input_transport]
            return options

        supported_mac = v2v_supported_option(
            r'--mac <mac:network\|bridge(\|ip)?:out>')
        if supported_mac:
            if self.iface_macs:
                for mac_i in self.iface_macs.split(';'):
                    # [mac, net_type, net], e.x. ['xx:xx:xx:xx:xx:xx', 'bridge', 'virbr0']
                    mac_i_list = mac_i.rsplit(':', 2)
                    # Just warning invalid values in case for negative testing
                    if len(mac_i_list) != 3 or mac_i_list[1] not in [
                            'bridge', 'network']:
                        LOG.warning(
                            "Invalid value for --mac '%s'" %
                            mac_i_list)
                    mac, net_type, netname = mac_i_list
                    self.net_vm_opts += " --mac %s:%s:%s" % (
                        mac, net_type, netname)
            else:
                LOG.info("auto set --mac option")
                for mac, _ in self._iface_list:
                    # Randomly cover both 'bridge' and 'network' even thought there is no
                    # difference.
                    if random.choice(['bridge', 'network']) == 'network':
                        self.net_vm_opts += " --mac %s:%s:%s" % (
                            mac, 'network', self.network)
                    else:
                        self.net_vm_opts += " --mac %s:%s:%s" % (
                            mac, 'bridge', self.bridge)

        if self.input_mode == 'vmx':
            _compose_vmx_filename()

        if not self.net_vm_opts:
            if supported_mac:
                LOG.warning("auto set --mac failed, roll back to -b/-n")
            if self.bridge:
                self.net_vm_opts += " -b %s" % self.bridge
            if self.network:
                self.net_vm_opts += " -n %s" % self.network

        if self.input_mode != 'vmx':
            self.net_vm_opts += " %s" % self.vm_name
        elif self.input_transport is None:
            self.net_vm_opts += " %s" % self._vmx_filename_fullpath

        options = self.get_target_options() + _compose_input_transport_options()

        if self.new_name:
            options += ' -on %s' % self.new_name

        if self.input_mode is not None:
            options = " -i %s %s" % (self.input_mode, options)
            if self.input_mode in ['ova', 'disk',
                                   'libvirtxml'] and self.input_file:
                options = options.replace(self.vm_name, self.input_file)

        # In '-i vmx', '-ic' is not needed
        if self.input_mode == 'vmx':
            options = re.sub(r'-ic .*? ', '', options)
        return options

    def _get_os_directory(self):
        """
        Prepare a local os directory for v2v conversion.

        Correspond to '-os DIRECTORY'.
        """
        if not self.os_directory:
            base_image_dir = '/var/lib/libvirt/images'
            self.os_directory = tempfile.mkdtemp(prefix='v2v_os_directory', dir=base_image_dir)
        # Pass the json directory to testcase for checking
        self.params.get('params').update({'os_directory': self.os_directory})

        LOG.debug(
            'The os directory(-os DIRECTORY) is %s.',
            self.os_directory)
        return self.os_directory

    def _get_libvirt_options(self):
        """
        Construct output options for -o libvirt

        'os_pool' corresponds to '-os POOL'.
        """
        os_pool = self.params.get('os_pool')
        options = " -os %s" % os_pool

        return options

    def _get_ovirt_options(self):
        """
        Construct output options for -o ovirt

        'os_storage' corresponds to '-o rhv -os [esd:/path|/path'.
        'os_storage_name' corresponds to '-o rhv -os STORAGE'.
        'rhv_upload_opts' includes all '-oo xxx' options.
        """
        os_storage = self.params.get('os_storage')
        os_storage_name = self.params.get('os_storage_name')
        rhv_upload_opts = self.params.get('rhv_upload_opts')
        output_method = self.output_method
        options = " -os %s" % (os_storage if output_method !=
                               "rhv_upload" else os_storage_name)
        if rhv_upload_opts:
            options += ' %s' % rhv_upload_opts

        return options

    def _get_local_options(self):
        """
        Construct output options for -o local
        """
        os_directory = self._get_os_directory()
        options = " -os %s" % os_directory

        return options

    def _get_null_options(self):
        """
        Construct output options for -o null
        """
        return ''

    def _get_json_options(self):
        """
        Construct output options for -o json

        'oo_json_disk_pattern' corresponds to '-o json [-oo json-disks-pattern=PATTERN]'
        """
        oo_json_disk_pattern = self.params.get('oo_json_disk_pattern')
        os_directory = self._get_os_directory()

        options = " -os %s" % os_directory
        if oo_json_disk_pattern:
            options += " -oo json-disks-pattern=%s" % oo_json_disk_pattern

        return options

    def get_target_options(self):
        """
        Return command options.
        """
        uri = self.uri
        target = self.target
        o_fmt = self.of_format
        _get_target_specific_options = getattr(
            self, "_get_%s_options" % self.target)

        if target == 'ovirt':
            target = self.output_method.replace('_', '-')

        options = " -ic %s -o %s -of %s" % (uri, target, o_fmt)
        options += _get_target_specific_options() + self.net_vm_opts

        return options

    # add new target in here.


class VMCheck(object):

    """
    This is VM check class dispatcher.
    """

    def __new__(cls, test, params, env):
        # 'linux' is default os type
        os_type = params.get('os_type', 'linux')

        if cls is VMCheck:
            class_name = eval(os_type.capitalize() + str(cls.__name__))
            return super(VMCheck, cls).__new__(class_name)
        else:
            return super(VMCheck, cls).__new__(cls, test, params, env)

    def __init__(self, test, params, env):
        self.vm = None
        self.test = test
        self.env = env
        self.params = params
        self.name = params.get('main_vm')
        self.os_version = params.get("os_version")
        self.os_type = params.get('os_type', 'linux')
        self.target = params.get('target')
        self.username = params.get('vm_user', 'root')
        self.password = params.get('vm_pwd')
        self.nic_index = params.get('nic_index', 0)
        self.export_name = params.get('export_name')
        self.delete_vm = 'yes' == params.get('vm_cleanup', 'yes')
        self.virsh_session = params.get('virsh_session')
        self.virsh_session_id = self.virsh_session.get_id(
            ) if self.virsh_session else params.get('virsh_session_id')
        self.windows_root = params.get("windows_root", r"C:\WINDOWS")
        self.output_method = params.get("output_method")
        # Need create session after create the instance
        self.session = None

        if self.name is None:
            LOG.error("vm name not exist")

        # libvirt is a default target
        if self.target == "libvirt" or self.target is None:
            self.vm = lvirt.VM(self.name, self.params, self.test.bindir,
                               self.env.get("address_cache"))
            self.pv = libvirt.PoolVolumeTest(test, params)
        elif self.target == "ovirt":
            self.vm = ovirt.VMManager(self.name, self.params, self.test.bindir,
                                      self.env.get("address_cache"))
        else:
            raise ValueError("Doesn't support %s target now" % self.target)

    def create_session(self, timeout=480):
        if self.session:
            LOG.debug('vm session %s exists', self.session)
            return
        self.session = self.vm.wait_for_login(nic_index=self.nic_index,
                                              timeout=timeout,
                                              username=self.username,
                                              password=self.password)
        LOG.debug('A new vm session %s was created', self.session)

    def cleanup(self):
        """
        Cleanup VM and remove all of storage files about guest
        """
        if self.session:
            LOG.debug('vm session %s is closing', self.session)
            self.session.close()
            self.session = None

        # If VMChecker is instantiated before import_vm_to_ovirt and
        # the VMChecker.run is skiped, self.vm.instance will be NULL.
        # The update_instance should be ran before cleaning up.
        if hasattr(self.vm, 'update_instance'):
            self.vm.update_instance()
        if self.vm.instance and self.vm.is_alive():
            self.vm.destroy(gracefully=False)
            time.sleep(5)

        if self.target == "libvirt":
            if self.vm.exists() and self.vm.is_persistent():
                self.vm.undefine()

        if self.target == "ovirt":
            LOG.debug("Deleting VM %s in Ovirt", self.name)
            self.vm.delete()
            # When vm is deleted, the disk will also be removed from
            # data domain, so it's not necessary to delete disk from
            # export domain for rhv_upload.
            if self.output_method != "rhv_upload":
                self.vm.delete_from_export_domain(self.export_name)
            ovirt.disconnect()

    def storage_cleanup(self):
        """
        Cleanup storage pool and volume
        """
        raise NotImplementedError

    def run_cmd(self, cmd, debug=True):
        """
        Run command in VM

        If cmd is a list or tuple, the run_cmd tries every element of
        cmd until success.
        """

        if isinstance(cmd, str):
            status, output = self.session.cmd_status_output(cmd)
        elif isinstance(cmd, list) or isinstance(cmd, tuple):
            for cmd_i in cmd:
                status, output = self.session.cmd_status_output(cmd_i)
                if status == 0:
                    break
        else:
            raise exceptions.TestError("Incorrect cmd: %s" % cmd)

        if debug:
            LOG.debug("Command return status: %s", status)
            LOG.debug("Command output:\n%s", output)
        return status, output


class LinuxVMCheck(VMCheck):

    """
    This class handles all basic linux VM check operations.
    """

    def get_vm_kernel(self):
        """
        Get vm kernel info.
        """
        cmd = "uname -r"
        return self.run_cmd(cmd)[1]

    def get_vm_os_info(self):
        """
        Get vm os info.
        """
        os_info = ""
        try:
            cmd = "cat /etc/os-release"
            status, output = self.run_cmd(cmd)
            if status != 0:
                cmd = "cat /etc/issue"
                output = self.run_cmd(cmd)[1]
                os_info = output.splitlines()[0]
            else:
                os_info = re.search(r'PRETTY_NAME="(.+)"', output).group(1)
        except Exception as e:
            LOG.error("Fail to get os distribution: %s", e)
        return os_info

    def get_vm_os_vendor(self):
        """
        Get vm os vendor.
        """
        os_info = self.get_vm_os_info()
        if re.search('Red Hat', os_info):
            vendor = 'Red Hat'
        elif re.search('Fedora', os_info):
            vendor = 'Fedora Core'
        elif re.search('SUSE', os_info):
            vendor = 'SUSE'
        elif re.search('Ubuntu', os_info):
            vendor = 'Ubuntu'
        elif re.search('Debian', os_info):
            vendor = 'Debian'
        else:
            vendor = 'Unknown'
        LOG.debug("The os vendor of VM '%s' is: %s" %
                  (self.vm.name, vendor))
        return vendor

    def get_vm_dmesg(self):
        """
        Get VM dmesg output.
        """
        cmd = "dmesg"
        return self.run_cmd(cmd)[1]

    def get_vm_parted(self):
        """
        Get vm parted info.
        """
        cmd = "parted -l"
        return self.run_cmd(cmd)[1]

    def get_vm_modules(self):
        """
        Get vm modules list.
        """
        cmd = "lsmod"
        return self.run_cmd(cmd)[1]

    def get_vm_pci_list(self):
        """
        Get vm pci list.
        """
        cmd_list = ['lspci', 'lshw', 'hwinfo']
        return self.run_cmd(cmd_list)[1]

    def get_vm_rc_local(self):
        """
        Get vm /etc/rc.local output.
        """
        cmd = "cat /etc/rc.local"
        return self.run_cmd(cmd)[1]

    def has_vmware_tools(self):
        """
        Check vmware tools.
        """
        cmd = "rpm -q VMwareTools"
        status, output = self.run_cmd(cmd)
        if status != 0:
            cmd = "ls /usr/bin/vmware-uninstall-tools.pl"
            status, output = self.run_cmd(cmd)
        return status == 0

    def get_vm_tty(self):
        """
        Get vm tty config.
        """
        confs = ('/etc/securetty', '/etc/inittab', '/boot/grub/grub.conf',
                 '/etc/default/grub')
        all_output = ''
        for conf in confs:
            cmd = "cat " + conf
            output = self.run_cmd(cmd)[1]
            all_output += output
        return all_output

    def wait_for_x_start(self, timeout=30):
        """
        Wait for S server start
        """
        cmd = 'xset -q'
        if self.run_cmd(cmd)[0] == 127:
            return
        utils_misc.wait_for(
            lambda: not bool(
                self.run_cmd(
                    cmd,
                    debug=False)[0]),
            timeout)

    def vm_xorg_search(self, substr):
        """
        Search expected string in Xorg config/log on VM.

        :param substr: The expected string.
        :return: True if search result meets expectation, otherwise False
        """
        self.wait_for_x_start()
        xorg_file_list = ["/etc/X11/xorg.conf",
                          "/var/log/Xorg.0.log"]
        # Ubuntu or rhel8 save xorg file in normal users home directory
        # A shell script gets the xorg file:
        #
        # uid_min=$(grep -E '^UID_MIN' /etc/login.defs | awk -F' ' '{ print $2}');
        # getent_cmd=('getent passwd' {${uid_min}..$(expr ${uid_min} + 100)});
        # for i in $(eval ${getent_cmd[@]} | awk -F: '{ print $1}');
        # do
        #    found=false;
        #    for j in $(seq 0 3);
        #    do
        #        if [ -f /home/${i}/.local/share/xorg/Xorg.${j}.log ]; then
        #            echo \"/home/${i}/.local/share/xorg/Xorg.${j}.log\";
        #            found=true;
        #            break;
        #        fi;
        #    done;
        #    if ${found}; then break; fi;
        # done
        get_uid_min = r"grep -E '^UID_MIN' /etc/login.defs | awk -F' ' '{ print $2}'"
        uid_min = self.run_cmd(get_uid_min, debug=False)[
            1].strip().splitlines()[-1]
        if uid_min.isdigit():
            # 100 times is enough
            uid_max = str(int(uid_min) + 100)
            extract_normal_users = r"getent passwd {%s..%s} | awk -F: '{ print $1}'" % (
                uid_min, uid_max)
            xorg_log_path = r"/home/${i}/.local/share/xorg/Xorg.${j}.log"
            xorg_log_chk = "if [ -f {0} ]; then echo {0}; found=true; break; fi;".format(
                xorg_log_path)
            break_if_found = r"if ${found}; then break; fi;"
            xorg_logs_loop = "for j in $(seq 0 3); do %s done; %s" % (
                xorg_log_chk, break_if_found)
            get_xorg_logs = "for i in $(%s);do found=false; %s done" % (
                extract_normal_users, xorg_logs_loop)
            LOG.debug("Get xorg logs shell script:\n%s", get_xorg_logs)

            # The first element is a malformed get_xorg_logs string, it
            # should be removed.
            xorg_files = self.run_cmd(get_xorg_logs, debug=False)[
                1].strip().splitlines()
            if len(xorg_files) > 0:
                xorg_file_list.extend(xorg_files[1:])
        else:
            LOG.debug("Get UID_MIN failed: %s", uid_min)

        LOG.debug("xorg files: %s", xorg_file_list)
        for file_i in xorg_file_list:
            cmd = 'grep -i "%s" "%s"' % (substr, file_i)
            if self.run_cmd(cmd)[0] == 0:
                return True
        return False

    def vm_journal_search(self, substr, options=None, flags=re.IGNORECASE):
        """
        Search journalctl log on vm

        :param substr: The expected string.
        :param options: the journalctl options
        :param flags: A RegexFlag, Please refer RE module of python
        :return: True if search result meets expectation, otherwise False
        """
        cmd = "journalctl --no-pager"
        if options:
            cmd += " %s" % options

        if self.vm_general_search(
                cmd,
                substr,
                flags,
                ignore_status=True,
                debug=False):
            return True
        return False

    def vm_general_search(
            self,
            cmd,
            substr,
            flags=re.IGNORECASE,
            ignore_status=False,
            debug=True):
        """
        Search a string by running a command on vm

        :param cmd: A command to be executed
        :param substr: The expected string in output of cmd.
        :param flags: A RegexFlag, Please refer RE module of python
        :param ignore_status: If True, will not check command return status.
        :param debug: If True, will print cmd output.
        :return: True if search result meets expectation, otherwise False
        """
        status, output = self.run_cmd(cmd, debug)

        if (ignore_status or status == 0) and re.search(substr, output, flags):
            return True
        return False

    def is_net_virtio(self):
        """
        Check whether vm's interface is virtio
        """
        cmd = "ls -l /sys/class/net/eth%s/device" % self.nic_index
        output = self.run_cmd(cmd)[1]
        try:
            if re.search("virtio", output.split('/')[-1]):
                return True
        except IndexError:
            LOG.error("Fail to find virtio driver")
        return False

    def is_disk_virtio(self):
        """
        Check whether disk is virtio after conversion.

        Note: If kernel supports virtio_blk, v2v will always convert disks
        to virtio_blk in copying mode. That means all disk have /dev/vdx
        path name.
        """
        cmd = "fdisk -l"
        virtio_disks = r'/dev/vd[a-z]+[0-9]*'
        non_virtio_disks = r'/dev/[hs]d[a-z]+[0-9]*'
        output = self.run_cmd(cmd)[1]
        if re.search(non_virtio_disks, output):
            return False
        if re.search(virtio_disks, output):
            return True
        return False

    def is_uefi_guest(self):
        """
        Check whether guest is uefi guest
        """
        cmd = "ls /sys/firmware/efi"
        status, output = self.run_cmd(cmd)
        if status != 0:
            return False
        return True

    def get_grub_device(self, dev_map="/boot/grub*/device.map"):
        """
        Check whether vd[a-z] device is in device map.
        """
        cmd = "cat %s" % dev_map
        output = self.run_cmd(cmd)[1]
        if re.search("vd[a-z]", output):
            return True
        return False


class WindowsVMCheck(VMCheck):

    """
    This class handles all basic Windows VM check operations.
    """

    def send_win32_key(self, keycode):
        """
        Send key to Windows VM
        """
        options = "--codeset win32 %s" % keycode
        virsh.sendkey(self.name, options, session_id=self.virsh_session_id)
        time.sleep(1)

    def move_mouse(self, coordinate):
        """
        Move VM mouse.
        """
        virsh.move_mouse(self.name, coordinate,
                         session_id=self.virsh_session_id)

    def click_left_button(self):
        """
        Click left button of VM mouse.
        """
        virsh.click_button(self.name, session_id=self.virsh_session_id)

    def click_tab_enter(self):
        """
        Send TAB and ENTER to VM.
        """
        self.send_win32_key('VK_TAB')
        self.send_win32_key('VK_RETURN')

    def click_install_driver(self):
        """
        Move mouse and click button to install driver for new
        device(Ethernet controller)
        """
        # Get window focus by click left button
        self.move_mouse((0, -80))
        self.click_left_button()
        self.move_mouse((0, 30))
        self.click_left_button()

    def get_screenshot(self):
        """
        Do virsh screenshot of the vm and fetch the image if the VM in
        remote host.
        """
        sshot_file = os.path.join(data_dir.get_tmp_dir(), "vm_screenshot.ppm")
        if self.target == "ovirt":
            # Note: This is a screenshot path on a remote host
            vm_sshot = os.path.join("/tmp", "vm_screenshot.ppm")
        else:
            vm_sshot = sshot_file
        virsh.screenshot(self.name, vm_sshot, session_id=self.virsh_session_id)
        if self.target == "ovirt":
            remote_ip = self.params.get("remote_ip")
            remote_user = self.params.get("remote_user")
            remote_pwd = self.params.get("remote_pwd")
            remote.scp_from_remote(remote_ip, '22', remote_user,
                                   remote_pwd, vm_sshot, sshot_file)
            r_runner = remote_old.RemoteRunner(
                host=remote_ip, username=remote_user, password=remote_pwd)
            r_runner.run("rm -f %s" % vm_sshot)
        return sshot_file

    def wait_for_match(self, images, similar_degree=0.98, timeout=300):
        """
        Compare VM screenshot with given images, if any image in the list
        matched, then return the image index, or return -1.
        """
        end_time = time.time() + timeout
        image_matched = False
        cropped_image = os.path.join(data_dir.get_tmp_dir(), "croped.ppm")
        while time.time() < end_time:
            vm_screenshot = self.get_screenshot()
            ppm_utils.image_crop_save(vm_screenshot, vm_screenshot)
            img_index = 0
            for image in images:
                LOG.debug("Compare vm screenshot with image %s", image)
                ppm_utils.image_crop_save(image, cropped_image)
                h_degree = ppm_utils.image_histogram_compare(cropped_image,
                                                             vm_screenshot)
                if h_degree >= similar_degree:
                    LOG.debug("Image %s matched", image)
                    image_matched = True
                    break
                img_index += 1
            if image_matched:
                break
            time.sleep(1)
        if os.path.exists(cropped_image):
            os.unlink(cropped_image)
        if os.path.exists(vm_screenshot):
            os.unlink(vm_screenshot)
        if image_matched:
            return img_index
        else:
            return -1

    def boot_windows(self, timeout=300):
        """
        Click buttons to activate windows and install ethernet controller driver
        to boot windows.
        """
        LOG.info("Booting Windows in %s seconds", timeout)
        compare_screenshot_vms = ["win2003"]
        timeout_msg = "No matching screenshots found after %s seconds" % timeout
        timeout_msg += ", trying to log into the VM directly"
        match_image_list = []
        if self.os_version in compare_screenshot_vms:
            image_name_list = self.params.get("screenshots_for_match",
                                              '').split(',')
            for image_name in image_name_list:
                match_image = os.path.join(data_dir.get_data_dir(), image_name)
                if not os.path.exists(match_image):
                    LOG.error(
                        "Screenshot '%s' does not exist", match_image)
                    return
                match_image_list.append(match_image)
            img_match_ret = self.wait_for_match(match_image_list,
                                                timeout=timeout)
            if img_match_ret < 0:
                LOG.error(timeout_msg)
            else:
                if self.os_version == "win2003":
                    if img_match_ret == 0:
                        self.click_left_button()
                        # VM may have no response for a while
                        time.sleep(20)
                        self.click_left_button()
                        self.click_tab_enter()
                    elif img_match_ret == 1:
                        self.click_left_button()
                        time.sleep(20)
                        self.click_left_button()
                        self.click_tab_enter()
                        self.click_left_button()
                        self.send_win32_key('VK_RETURN')
                    else:
                        pass
                elif self.os_version in ["win7", "win2008r2"]:
                    if img_match_ret in [0, 1]:
                        self.click_left_button()
                        self.click_left_button()
                        self.send_win32_key('VK_TAB')
                        self.click_tab_enter()
                elif self.os_version == "win2008":
                    if img_match_ret in [0, 1]:
                        self.click_tab_enter()
                        self.click_install_driver()
                        self.move_mouse((0, -50))
                        self.click_left_button()
                        self.click_tab_enter()
                    else:
                        self.click_install_driver()
        else:
            # No need sendkey/click button for any os except Win2003
            LOG.info("%s is booting up without program intervention",
                     self.os_version)

    def reboot_windows(self):
        """
        Reboot Windows immediately
        """
        cmd = "shutdown -t 0 -r -f"
        self.run_cmd(cmd)

    def get_viostor_info(self):
        """
        Get viostor info.
        """
        cmd = r"dir %s\Drivers\VirtIO\\viostor.sys" % self.windows_root
        return self.run_cmd(cmd)[1]

    def get_service_info(self, name=None):
        """
        Get service info.

        :param name: an optional service name
        """
        cmd = r"sc query"
        if name:
            cmd += ' ' + name
        return self.run_cmd(cmd)[1]

    def get_driver_info(self, signed=True):
        """
        Get windows signed driver info.
        """
        cmd = "DRIVERQUERY"
        if signed:
            cmd += " /SI"
        # Try 5 times to get driver info
        output, count = '', 5
        while count > 0:
            LOG.debug('%d times remaining for getting driver info' % count)
            try:
                # Clean up output
                self.session.cmd('cls')
                output = self.session.cmd_output(cmd)
            except Exception as detail:
                LOG.error(detail)
                count -= 1
            else:
                break
        if not output:
            LOG.error('Fail to get driver info')
        LOG.debug("Command output:\n%s", output)
        return output

    def get_windows_event_info(self):
        """
        Get windows event log info about WSH.
        """
        cmd = "wevtutil qe application | find \"WSH\""
        status, output = self.run_cmd(cmd)
        if status != 0:
            # For win2003 and winXP, use following cmd
            cmd = r"CSCRIPT %s\system32\eventquery.vbs " % self.windows_root
            cmd += "/l application /Fi \"Source eq WSH\""
            output = self.run_cmd(cmd)[1]
        return output

    def get_network_restart(self):
        """
        Get windows network restart.
        """
        cmd = "ipconfig /renew"
        return self.run_cmd(cmd)[1]

    def copy_windows_file(self):
        """
        Copy a widnows file
        """
        cmd = "COPY /y C:\\rss.reg C:\\rss.reg.bak"
        return self.run_cmd(cmd)[0]

    def delete_windows_file(self):
        """
        Delete a widnows file
        """
        cmd = "DEL C:\rss.reg.bak"
        return self.run_cmd(cmd)[0]

    def is_uefi_guest(self):
        """
        Check whether windows guest is uefi guest

        More info:
        https://www.tenforums.com/tutorials/85195-check-if-windows-10-using-uefi-legacy-bios.html
        """
        search_str = "Detected boot environment"
        target_file = r"c:\Windows\Panther\setupact.log"
        cmd = 'findstr /c:"%s" %s' % (search_str, target_file)
        status, output = self.run_cmd(cmd)
        if 'BIOS' in output:
            return False

        if 'EFI' in output:
            return True

        return False


def v2v_cmd(params, auto_clean=True, cmd_only=False, interaction=False):
    """
    Create final v2v command, execute or only return the command

    Sometimes you need to retouch the v2v command, then execute it later.
    So you need to preserve the resources (nfs path, authorized keys, etc.)

    When auto_clean is False, the resources created during runtime will
    not be cleaned up, Users should do that.

    When cmd_only is True, the v2v command will not be executed but be returned.
    Users can reedit the command as cases required.

    :param params: A dictionary includes all of required parameters such as
                    'target', 'hypervisor' and 'hostname', etc.
                   This is a v2v specific params and not the global params in
                   run function.
    :param auto_clean: boolean flag, whether to cleanup runtime resources.
    :param cmd_only: boolean flag, whether to only return the command line without running
    :param interaction: boolean flag, If need to interact with v2v
    :return: A cmd string or CmdResult object
    """
    def _v2v_pre_cmd():
        """
        Preprocess before running v2v cmd, such as starting VM for warm conversion,
        create virsh instance, etc.
        """
        # Cannot get mac address in 'ova', 'libvirtxml', etc.
        if input_mode not in [
            'disk',
            'libvirtxml',
            'local',
                'ova'] and not skip_virsh_pre_conn:
            params['_v2v_virsh'] = v2v_virsh = create_virsh_instance(
                hypervisor, uri, hostname, username, password)
            iface_info = get_all_ifaces_info(vm_name, v2v_virsh)
            # For v2v option '--mac', this is automatically generated.
            params['_iface_list'] = iface_info

            # Get disk count
            disk_count = vm_xml.VMXML.get_disk_count_by_expr(
                vm_name, 'device!=cdrom', virsh_instance=v2v_virsh)
            params['_disk_count'] = disk_count

            if input_mode == 'vmx':
                disks_info = get_esx_disk_source_info(vm_name, v2v_virsh)
                if not disks_info:
                    raise exceptions.TestError(
                        "Found esx disk source error")
                # It's impossible that a VM is saved in two different
                # datastores
                params['datastore'] = list(disks_info)[0]
                params['_nfspath'] = list(disks_info[list(disks_info)[0]])[0]
        else:
            params['_iface_list'] = ''
            # Just set to 1 right now, but it could be improved if required
            # in future
            params['_disk_count'] = 1
            # params['_nfspath'] only be used when composing nfs vmx file path,
            # in the case, vm_name is same as nfs directory name
            if input_mode == 'vmx':
                params['_nfspath'] = vm_name
        # Pass it to testcase to do subsequent checking
        global_params.update({'vm_disk_count': params['_disk_count']})

    def _v2v_post_cmd():
        """
        Postprocess after running v2v cmd
        """
        v2v_virsh = params.get('_v2v_virsh')
        close_virsh_instance(v2v_virsh)

    if V2V_EXEC is None:
        raise ValueError('Missing command: virt-v2v')

    global_params = params.get('params', {})
    if not global_params:
        # For the back compatibility reason, only report a warning message
        LOG.warning(
            "The global params in run() need to be passed into v2v_cmd as an"
            "item of params, like {'params': params}. "
            "If not, some latest functions may not work as expected.")

    env_settings = params_get(params, 'env_settings')
    unprivileged_user = params_get(params, 'unprivileged_user')
    if unprivileged_user:
        try:
            pwd.getpwnam(unprivileged_user)
        except KeyError:
            process.system("useradd %s" % unprivileged_user)

    target = params.get('target')
    hypervisor = params.get('hypervisor')
    # vpx:// or esx://
    src_uri_type = params.get('src_uri_type')
    hostname = params.get('hostname')
    vpx_dc = params.get('vpx_dc')
    esxi_host = params.get('esxi_host', params.get('esx_ip'))
    opts_extra = params.get('v2v_opts')
    # Set v2v_cmd_timeout to 5 hours, the value can give v2v enough time to execute,
    # and avoid v2v process be killed by mistake.
    # the value is bigger than the timeout value in CI, so when some timeout
    # really happens, CI will still interrupt the v2v process.
    v2v_cmd_timeout = params.get('v2v_cmd_timeout', 18000)
    # username and password of remote hypervisor server
    username = params.get('username', 'root')
    password = params.get('password')
    vm_name = params.get('main_vm')
    input_mode = params.get('input_mode')
    cmd_has_ip = params.get('cmd_has_ip', True)
    # A switch controls a virsh pre-connection to source hypervisor,
    # but some testing environments(like, gating in OSP) don't have
    # source hypervisor, the pre-connection must be skipped.
    skip_virsh_pre_conn = 'yes' == params.get('skip_virsh_pre_conn')
    # virsh instance of remote hypervisor
    params.update({'_v2v_virsh': None})
    # if 'has_rhv_disk_uuid' is 'yes', will append rhv-disk-uuid automatically.
    has_rhv_disk_uuid = params_get(params, 'has_rhv_disk_uuid')

    uri_obj = Uri(hypervisor)

    # Return actual 'uri' according to 'hostname' and 'hypervisor'
    if src_uri_type == 'esx':
        vpx_dc = None
    uri = uri_obj.get_uri(hostname, vpx_dc, esxi_host)

    try:
        # Pre-process for v2v
        _v2v_pre_cmd()

        target_obj = Target(target, uri)
        # Return virt-v2v command line options based on 'target' and
        # 'hypervisor'
        options = target_obj.get_cmd_options(params)

        if opts_extra:
            options = options + ' ' + opts_extra
        # Add -oo rhv-disk-uuid
        if '-o rhv-upload' in options and has_rhv_disk_uuid == 'yes' and '-oo rhv-disk-uuid' not in options:
            for i in range(int(params.get('_disk_count', 0))):
                options += ' -oo rhv-disk-uuid=%s' % str(uuid.uuid4())

        # Protect the blanks in original guest name
        safe_vm_name = ''
        BLANK_REPLACEMENT = '%20'
        if ' ' in vm_name and vm_name in options:
            safe_vm_name = vm_name.replace(' ', BLANK_REPLACEMENT)
            options = options.replace(vm_name, safe_vm_name)
        # Construct a final virt-v2v command and remove redundant blanks
        cmd = ' '.join(('%s %s' % (V2V_EXEC, options)).split())
        # Restore the real original guest name
        if safe_vm_name:
            cmd = cmd.replace(safe_vm_name, vm_name)
        # Old v2v version doesn't support '-ip' option
        if not v2v_supported_option("-ip <filename>"):
            cmd = cmd.replace('-ip', '--password-file', 1)

        # update -ip option
        if not cmd_has_ip:
            ip_ptn = [r'-ip \S+\s*', r'--password-file \S+\s*']
            cmd = cmd_remove_option(cmd, ip_ptn)

        # For ENV settings
        if env_settings:
            cmd = env_settings + ' ' + cmd
        if unprivileged_user:
            cmd = "su - %s -c '%s'" % (unprivileged_user, cmd)
        # Save v2v command to params, then it can be passed to
        # import_vm_to_ovirt
        global_params.update({'v2v_command': cmd})

        if not cmd_only:
            if not interaction:
                cmd_result = process.run(
                    cmd,
                    timeout=v2v_cmd_timeout,
                    verbose=True,
                    ignore_status=True)
            else:
                cmd_result = interactive_run(
                    params,
                    timeout=v2v_cmd_timeout,
                    command=cmd,
                    output_func=lambda x: print(x, end=''))
    finally:
        # Save it into global params and release it by users
        v2v_dirty_resources = global_params.get('v2v_dirty_resources', [])
        global_params.update({'v2v_dirty_resources': v2v_dirty_resources})
        if 'target_obj' in locals():
            if auto_clean:
                target_obj.cleanup()
            else:
                v2v_dirty_resources.append(target_obj)
        # Post-process for v2v
        _v2v_post_cmd()

    if cmd_only:
        return cmd
    cmd_result.stdout = cmd_result.stdout_text
    cmd_result.stderr = cmd_result.stderr_text
    return cmd_result


def cmd_run(cmd, obj_be_cleaned=None, auto_clean=True, timeout=18000):
    """
    Run v2v command and cleanup resources automatically

    When you preserved the resources in v2v_cmd, the users need to release
    them. This function can help you do it automatically.

    :param obj_be_cleaned: the resources to be cleaned up
    :param auto_clean: If true, cleanup obj_be_cleaned automatically
    :param timeout: the timeout value for the command to run
    """
    try:
        cmd_result = process.run(
            cmd,
            timeout=timeout,
            verbose=True,
            ignore_status=True)
    finally:
        if auto_clean and obj_be_cleaned:
            LOG.debug('Running cleanup for %s', obj_be_cleaned)
            if isinstance(obj_be_cleaned, list):
                for obj in obj_be_cleaned:
                    obj.cleanup()
            else:
                obj_be_cleaned.cleanup()

    return cmd_result


def import_vm_to_ovirt(params, address_cache, timeout=600):
    """
    Import VM from export domain to oVirt Data Center
    """
    v2v_cmd = params.get('v2v_command')
    vm_name = params.get('main_vm')
    os_type = params.get('os_type')
    export_name = params.get('export_name')
    storage_name = params.get('storage_name')
    cluster_name = params.get('cluster_name')
    output_method = params.get('output_method')
    # Check oVirt status
    dc = ovirt.DataCenterManager(params)
    LOG.info("Current data centers list: %s", dc.list())
    cm = ovirt.ClusterManager(params)
    LOG.info("Current cluster list: %s", cm.list())
    hm = ovirt.HostManager(params)
    LOG.info("Current host list: %s", hm.list())
    sdm = ovirt.StorageDomainManager(params)
    LOG.info("Current storage domain list: %s", sdm.list())
    vm = ovirt.VMManager(vm_name, params, address_cache=address_cache)
    LOG.info("Current VM list: %s", vm.list())
    if vm_name in vm.list() and output_method != 'rhv_upload':
        LOG.error("%s already exist", vm_name)
        return False
    wait_for_up = True
    if os_type == 'windows':
        wait_for_up = False

    # If output_method is None or "" or is not 'rhv_upload', treat it as
    # old way.
    if output_method != 'rhv_upload':
        try:
            # Import VM
            vm.import_from_export_domain(export_name,
                                         storage_name,
                                         cluster_name,
                                         timeout=timeout)
            LOG.info("The latest VM list: %s", vm.list())
        except Exception as e:
            # Try to delete the vm from export domain
            vm.delete_from_export_domain(export_name)
            LOG.error("Import %s failed: %s", vm.name, e)
            return False
    try:
        if not is_option_in_v2v_cmd(v2v_cmd, '--no-copy'):
            # Start VM
            vm.start(wait_for_up=wait_for_up)
        else:
            LOG.debug(
                'Skip starting VM: --no-copy is in cmdline:\n%s',
                v2v_cmd)
    except Exception as e:
        LOG.error("Start %s failed: %s", vm.name, e)
        vm.delete()
        if output_method != 'rhv_upload':
            vm.delete_from_export_domain(export_name)
        return False
    return True


def check_log(params, log):
    """
    Check if error/warning meets expectation in v2v log

    :param params: A dictionary includes all of required parameters such as
                    'expect_msg', 'msg_content', etc.
    :param log: The log string to be checked
    :return: True if search result meets expectation, otherwise False
    """

    def _check_log(pattern_list, expect=True):
        for pattern in pattern_list:
            line = r'\s*'.join(pattern.split())
            expected = 'expected' if expect else 'not expected'
            LOG.info('Searching for %s log: %s' % (expected, pattern))
            compiled_pattern = re.compile(line, flags=re.S)
            search = re.search(compiled_pattern, log)
            if search:
                LOG.info('Found log: %s', search.group(0))
                if not expect:
                    return False
            else:
                LOG.info('Not find log: %s', pattern)
                if expect:
                    return False
        return True

    expect_msg = params.get('expect_msg')
    ret = ''
    if not expect_msg:
        LOG.info('No need to check v2v log')
    else:
        expect = expect_msg == 'yes'
        if params.get('msg_content'):
            msg_list = params['msg_content'].split('%')
            if _check_log(msg_list, expect=expect):
                LOG.info('Finish checking v2v log')
            else:
                ret = 'Check v2v log failed'
        else:
            ret = 'Missing error message to compare'
    return ret


def check_exit_status(result, expect_error=False, error_flag='strict'):
    """
    Check the exit status of virt-v2v/libguestfs commands

    :param result: Virsh command result object
    :param expect_error: Boolean value, expect command success or fail
    :param error_flag: same as errors argument in str.decode
    """
    if not expect_error:
        if result.exit_status != 0:
            raise exceptions.TestFail(
                to_text(result.stderr, errors=error_flag))
    elif expect_error and result.exit_status == 0:
        raise exceptions.TestFail("Run '%s' expect fail, but run "
                                  "successfully." % result.command)


def cleanup_constant_files(params):
    """
    Cleanup some constant files which generated for v2v commands.
    For example, rhv_upload_passwd_file, local_ca_file_path,
    vpx_passwd_file, etc.

    :param params: A dict containing all cfg params
    """
    # Please Add new constant files into below list.
    tmpfiles = [params.get("rhv_upload_passwd_file"),
                params.get("local_ca_file_path"),
                params.get("vpx_passwd_file")]

    # Python3 only returns a map object which is different from python2.
    list(map(os.remove, [x for x in tmpfiles if x and os.path.isfile(x)]))


def get_vddk_thumbprint(host, password, uri_type, prompt=r"[\#\$\[\]]"):
    """
    Get vddk thumbprint from VMware vCenter

    :param host: hostname or IP address
    :param password: Password
    :param uri_type: conversion source uri type
    :param prompt: Shell prompt (regular expression)
    """

    if uri_type == 'esx':
        cmd = 'openssl x509 -in /etc/vmware/ssl/rui.crt -fingerprint -sha1 -noout'
    else:
        cmd = 'openssl x509 -in /etc/vmware-vpx/ssl/rui.crt -fingerprint -sha1 -noout'

    r_runner = remote_old.RemoteRunner(
        host=host,
        password=password,
        prompt=prompt,
        preferred_authenticaton='password,keyboard-interactive')
    cmdresult = r_runner.run(cmd)
    LOG.debug("vddk thumbprint:\n%s", cmdresult.stdout)
    vddk_thumbprint = cmdresult.stdout.strip().split('=')[1]

    return vddk_thumbprint


def v2v_setup_ssh_key(
        hostname,
        username,
        password,
        port=22,
        server_type=None,
        auto_close=True,
        preferred_authenticaton=None,
        user_known_hosts_file=None,
        unprivileged_user=None,
        public_key=None):
    """
    Setup up remote login in another server by using public key

    :param hostname: hostname or IP address
    :param username: username
    :param password: password
    :param port: ssh port number
    :param server_type: the type of remote server, the values could be 'esx' or 'None'.
    :param auto_close: If it's True, the session will closed automatically,
                       else Uses should call v2v_setup_ssh_key_cleanup to close the session
    :param preferred_authenticaton: The preferred authentication of SSH connection
    :param user_known_hosts_file: one or more files to use for the user host key database

    :return: A tuple (public_key, session) will always be returned
    """
    session = None
    LOG.debug('Performing SSH key setup on %s:%d as %s.' %
              (hostname, port, username))
    try:
        # Both Xen and ESX can work with following settings.
        if not preferred_authenticaton:
            preferred_authenticaton = 'password,keyboard-interactive'
        if not user_known_hosts_file:
            user_known_hosts_file = os.path.expanduser('~/.ssh/known_hosts')

        # If remote host identification has changed, v2v will fail.
        # We always delete the identification first.
        if os.path.isfile(user_known_hosts_file):
            cmd = r"sed -i '/%s/d' %s" % (hostname, user_known_hosts_file)
            process.run(cmd, verbose=True, ignore_status=True)

        session = remote_old.ssh_login_to_migrate(
            client='ssh',
            host=hostname,
            username=username,
            port=port,
            password=password,
            prompt=r"[\#\$\[\]%]",
            verbose=True,
            preferred_authenticaton=preferred_authenticaton,
            user_known_hosts_file=user_known_hosts_file)

        # Add rstrip to avoid blank lines in authorized_keys on remote server
        default_public_key = ssh_key.get_public_key().rstrip()
        if not public_key:
            public_key = default_public_key

        if server_type == 'esx':
            session.cmd(
                "echo '%s' >> /etc/ssh/keys-root/authorized_keys; " %
                public_key)
        else:
            session.cmd('mkdir -p ~/.ssh')
            session.cmd('chmod 700 ~/.ssh')
            session.cmd("echo '%s' >> ~/.ssh/authorized_keys; " % public_key)
            session.cmd('chmod 600 ~/.ssh/authorized_keys')

        LOG.debug('SSH key setup complete, session is %s', session)

        return public_key, session
    except Exception as err:
        # auto close session when exception occurs
        auto_close = True
        raise exceptions.TestFail("SSH key setup failed: '%s'" % err)
    finally:
        if auto_close and session:
            LOG.debug('cleaning session: %s', session)
            session.close()


def v2v_setup_ssh_key_cleanup(session=None, key=None, server_type=None):
    """
    Close the session and delete the key from authorized_keys.

    If auto_close is 'False' in v2v_setup_ssh_key, Users must call this
    function to cleanup session and keys on remote server explicitly.
    But if the caller of v2v_setup_ssh_key is an instance of class Target,
    you can save the resources in self.authorized_keys to cleanup
    automatically.

    :param session: An aexpect session to remote server
    :param key: The public_key which get by ssh_key.get_public_key().
    :param server_type: the type of remote server, the values could be 'esx' or 'None'.
    """
    try:
        if not session or not key:
            return

        # Only use a part of pub_keys as a pattern in sed
        key = key.rstrip().split()[1].split('/')[0]
        authorized_keys = get_authorized_keys_file(server_type)
        cmd = r"sed -i '/%s/d' %s" % (key, authorized_keys)
        session.cmd(cmd)
    finally:
        if session:
            LOG.debug('cleaning session: %s', session)
            session.close()


def get_authorized_keys_file(server_type=None):
    """
    Get authorized_keys file path for a remote server

    :param server_type: the type of remote server, the values could be 'esx' or 'None'.

    :return: The path of authorized_keys file on remote server
    """
    if server_type == 'esx':
        authorized_keys = '/etc/ssh/keys-root/authorized_keys'
    else:
        authorized_keys = os.path.expanduser('~/.ssh/authorized_keys')
    return authorized_keys


def v2v_mount(src, dst='v2v_mount_point', fstype='nfs'):
    """
    Mount nfs src to dst

    :param src: NFS source
    :param dst: NFS mount point
    """
    mount_point = os.path.join(
        data_dir.get_tmp_dir(), dst)
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)

    if not utils_misc.mount(
        src,
        mount_point,
        fstype,
            verbose=True):
        raise exceptions.TestError(
            'Mount %s for %s failed' %
            (src, mount_point))

    return mount_point


def create_virsh_instance(
        hypervisor,
        uri,
        remote_ip,
        remote_user,
        remote_pwd,
        debug=True):
    """
    Create a virsh instance for all hypervisors(VMWARE, XEN, KVM)

    :param hypervisor: a hypervisor type
    :param uri: uri of libvirt instance to connect to
    :param remote_ip: Hostname/IP of remote system to ssh into (if any)
    :param remote_user: Username to ssh in as (if any)
    :param remote_pwd: Password to use, or None for host/pubkey
    :param debug: Whether to enable debug
    """
    LOG.debug(
        "virsh connection info: hypervisor=%s uri=%s ip=%s",
        hypervisor,
        uri,
        remote_ip)
    if hypervisor == 'kvm':
        v2v_virsh = virsh
    else:
        virsh_dargs = {'uri': uri,
                       'remote_ip': remote_ip,
                       'remote_user': remote_user,
                       'remote_pwd': remote_pwd,
                       'auto_close': True,
                       'debug': debug}
        v2v_virsh = wait_for(virsh.VirshPersistent, **virsh_dargs)
    LOG.debug('A new virsh persistent session %s was created', v2v_virsh)
    return v2v_virsh


def close_virsh_instance(virsh_instance=None):
    """
    Close a virsh instance

    :param v2v_virsh_instance: a virsh instance
    """

    LOG.debug('Closing session (%s) in VT', virsh_instance)
    if virsh_instance and hasattr(virsh_instance, 'close_session'):
        virsh_instance.close_session()


def get_all_ifaces_info(vm_name, virsh_instance):
    """
    Get all interfaces' information

    :param vm_name: vm's name
    :param v2v_virsh_instance: a virsh instance
    """
    # virsh can't find guest every time on old XEN server.
    vmxml = wait_for(
        vm_xml.VMXML.new_from_dumpxml,
        vm_name=vm_name,
        virsh_instance=virsh_instance)
    interfaces = vmxml.get_iface_all()
    if len(interfaces.keys()) == 0:
        raise exceptions.TestError("Not found mac address for vm %s" % vm_name)

    # vm_ifaces = [(mac, type), ...]
    vm_ifaces = []
    for mac, iface in interfaces.items():
        vm_ifaces.append((mac, iface.get('type')))

    LOG.debug("Iface information for vm %s: %s", vm_name, vm_ifaces)
    return vm_ifaces


def get_esx_disk_source_info(vm_name, virsh_instance):
    """
    Get VM's datastore, real path of disks in NFS, etc

    The return values looks like:
    {'esx6.7': {'esx6.7-rhel7.5-multi-disks':
      ['esx6.7-rhel7.5-multi-disks.vmdk', 'esx6.7-rhel7.5-multi-disks_2.vmdk']}}

    It can be used to construct real path value in
    '-i vmx -it ssh' mode of v2v command.

    disk info example:
    <disk type='file' device='disk'>
      <source file='[esx6.7] esx6.7-rhel7.5-multi-disks/esx6.7-rhel7.5-multi-disks.vmdk'/>
      <target dev='sda' bus='scsi'/>
      <address type='drive' controller='0' bus='0' target='0' unit='0'/>
    </disk>

    The meanings of source file info.
    '[esx6.7]' is datastore of the VM.
    'esx6.7-rhel7.5-multi-disks' is the real path in NFS storage.
    'esx6.7-rhel7.5-multi-disks.vmdk' is disk name.

    Only works for VMs in ESX server

    :param vm_name: vm's name
    :param v2v_virsh_instance: a virsh instance
    """
    def _parse_file_info(path):
        res = re.search(r'\[(.*)\] (.*)/(.*\.vmdk)', path)
        if not res:
            return []
        return [res.group(i) for i in range(1, 4)]

    disks_info = {}
    disks = vm_xml.VMXML.get_disk_source_by_expr(
        vm_name,
        exprs=['type==file', 'device!=cdrom'],
        virsh_instance=virsh_instance)
    for disk in disks:
        attr_value = disk.find('source').get('file')
        file_info = _parse_file_info(attr_value)
        if not file_info:
            continue
        if file_info[0] not in disks_info:
            disks_info[file_info[0]] = {file_info[1]: []}
        if file_info[1] not in disks_info[file_info[0]]:
            disks_info[file_info[0]][file_info[1]] = []
        disks_info[file_info[0]][file_info[1]].append(file_info[2])

    LOG.debug("source disk info vm %s: %s", vm_name, disks_info)
    return disks_info


def v2v_supported_option(opt_str):
    """
    Check if an cmd option is supported by v2v

    :param opt_str: option string for checking
    """
    cmd = 'virt-v2v --help'
    result = process.run(cmd, verbose=False, ignore_status=True)
    if re.search(r'%s' % opt_str, result.stdout_text):
        return True
    return False


def is_option_in_v2v_cmd(v2v_cmd, option):
    """
    Check if specific v2v option(s) is(are) in v2v command line

    :param v2v_cmd: A v2v command line string
    :param option: option or option list
    """
    if not option or not v2v_cmd:
        return False

    if isinstance(option, list):
        return all([opt_i in v2v_cmd for opt_i in option])
    elif isinstance(option, str):
        return option in v2v_cmd
    else:
        return False


def wait_for(func, timeout=300, interval=10, *args, **kwargs):
    """
    Run a function 'func' until success or timeout

    :param func: the function to be called
    :param timeout: timeout value(seconds)
    :param interval: interval values (seconds) for every call
    :param *args: arguments to be passed to func
    :param **dwargs: diction arguments to be passed to func
    """
    count = 0
    end_time = time.time() + float(timeout)
    while time.time() < end_time:
        try:
            return func(*args, **kwargs)
        except Exception:
            count += 1
            time.sleep(interval)

    LOG.debug("Tried %s times", count)
    # Run once more, raise exception or success
    return func(*args, **kwargs)


def check_version(version, interval):
    """
    Check version against given interval string.

    :param version: The version to be compared
    :param interval: An interval is a string representation of a
     mathematical like interval. See the definition in utils_version.py.
    :return: True if version satisfied interval, otherwise False.
    """
    verison_interval = VersionInterval(interval)
    return version in verison_interval


def compare_version(interval, version=None, cmd=None):
    """
    Compare version against given interval string.

    :param interval: An interval is a string representation of a
     mathematical like interval. See the definition in utils_version.py.
    :param version: The version to be compared
    :param cmd: the command to get the version
    :return: True if version satisfied interval, otherwise False.
    """
    if not version:
        if not cmd:
            cmd = 'rpm -q virt-v2v'
        res = process.run(cmd, shell=True, ignore_status=True)
        if res.exit_status != 0:
            return False
        version = res.stdout_text.strip()

    return check_version(version, interval)


def multiple_versions_compare(interval):
    """
    Multiple pkgs can be specified by ';', e.g.
    "[libguestfs-1.40,);[nbkdit-1.17.4,)"

    If interval is '', it means no version limitation and return True.
    If interval is not '', return True for comparing success and False
    for Failure.

    :param interval: An interval is a string representation of a
    """
    re_pkg_name = r'(.*?)-(?=\d+\.?)+'
    versions = interval.split(';')
    # ';' is used to split multiple pkgs.
    for ver_i in versions:
        ver = ver_i.strip('[]()')
        if not ver:
            continue
        if not re.search(re_pkg_name, ver):
            return False

        pkg_name = re.search(re_pkg_name, ver).group(1)
        cmd = 'rpm -q %s' % pkg_name
        if not compare_version(ver_i, cmd=cmd):
            return False

    return True


def to_list(value):
    """
    Convert a string to list

    :param value: A string or list object
    """
    if not value:
        return []
    elif isinstance(value, list):
        return value
    elif isinstance(value, str):
        return [value]


def cmd_remove_option(cmd, opt_pattern):
    """
    Remove an option from cmd

    :param cmd: the cmd
    :param opt_pattern: a pattern stands for the option
    """
    for pattern in to_list(opt_pattern):
        for item in re.findall(pattern, cmd):
            cmd = cmd.replace(item, '').strip()
    return cmd


def params_get(params, name, default=None):
    """
    A convenient function for v2v to get value of a variant from params.

    The main advantage is all variants don't need to be passed to
    utils_v2v any more, this function will get it from the standard
    'params' if 'params' was passed to utils_v2v.

    This requires all variants have same name in the whole test life.

    :param params: A dictionary includes all of required parameters.
    :param name: A variant name
    :param default: The default value of a variant
    """
    return params.get(name) or (params.get('params').get(
        name, default) if 'params' in params else params.get(name, default))


def interactive_run(params, timeout=300, *args, **kwargs):
    """
    Run v2v command interactively.

    :param params: A dictionary includes all of required parameters.
    :param timeout: The max command running time.
    """
    username = params_get(params, 'username', 'root')
    password = params_get(params, 'password')
    luks_password = params_get(params, 'luks_password')
    choices = params_get(params, 'custom_inputs')
    cmd_result = process.CmdResult()

    # For last line matching
    LAST_LINE_PROMPTS = [r"[Ee]nter.*username",
                         r"[Ee]nter.*authentication name",
                         r"[Ee]nter root.*? password",
                         r"[Ee]nter host password",
                         r"[Ee]nter.*password",
                         r"password:",
                         r"Enter a number between 1 and 2",
                         r"Enter key or passphrase",
                         r"Finishing off",
                         r"Converting .*? to run on"]

    # Interaction Done
    FREE_RUNNING_PROMPTS = [r"Converting .*? to run on"]

    def handle_prompts(session, timeout=300, interval=1.0):
        """
        Interact with v2v when specific patterns are matched.

        :param session: An Expect or ShellSession instance to operate on
        :param timeout: The max command running time.
        :param interval: Seconds to wait until start reading output again
        """

        free_running = False
        last_line = ''
        # v2v running timeout, it is set when interaction finished.
        # This value gives v2v enough time to execute.
        # If '-v -x' not enabled, it should be greater than 7200s.
        running_timeout = timeout
        # interactive timeout
        # when debug enabled in v2v, lots of logs keep outputting to stdout,
        # the timeout value can be smaller. If debug is off, the timeout
        # should be big enough to avoid unexpected timeout.
        timeout = 120 if '-v -x' in session.command else 300
        while True:
            time.sleep(interval)
            if not session.is_alive() or session.is_defunct():
                break

            try:
                match, _ = session.read_until_last_line_matches(
                    LAST_LINE_PROMPTS, timeout=timeout, internal_timeout=0.5)
                if match in [0, 1]:  # "username:"
                    LOG.debug(
                        "Got username prompt; sending '%s'", username)
                    session.sendline(username)
                elif match in [2, 3, 4, 5]:
                    LOG.debug(
                        "Got password prompt, sending '%s'",
                        asterisk_passwd(password))
                    session.sendline(password)
                elif match == 6:  # Wait for custom input
                    LOG.debug(
                        "Got console '%s', send input list %s", match, choices)
                    session.sendline(choices)
                elif match == 7:  # LUKS password
                    LOG.debug(
                        "Got password prompt, sending '%s'",
                        asterisk_passwd(luks_password))
                    session.sendline(luks_password)
                elif match == 8:  # Done
                    break
                elif match == 9:  # Interaction Finish
                    timeout = running_timeout
            except aexpect.ExpectTimeoutError:
                # when free_running is true and timeout happens, it means
                # the command doesn't have any response, may be dead or
                # performance is quite poor.
                LOG.debug("timeout happens")
                if free_running:
                    raise

                # If timeout happens two times and the last line are same,
                # it means v2v may be dead or performance is quite poor.
                cont = session.get_output()
                new_last_line = ''
                nonempty_lines = [
                    l for l in cont.splitlines()[-10:] if l.strip()]
                if nonempty_lines:
                    new_last_line = nonempty_lines[-1]
                if last_line and last_line == new_last_line:
                    LOG.debug(
                        'v2v command may be dead or have bad performance')
                    raise
                last_line = new_last_line

                # Set a big timeout value when interaction finishes
                for pattern in FREE_RUNNING_PROMPTS:
                    if re.search(pattern, cont):
                        LOG.debug(
                            "interaction finished and begin running freely")
                        free_running = True
                        timeout = running_timeout
                        break

    try:
        subproc = aexpect.Expect(*args, **kwargs)
        LOG.debug('Running command: %s', subproc.command)
        handle_prompts(subproc, timeout)
    except aexpect.ExpectProcessTerminatedError:
        # v2v cmd is dead or finished
        pass
    except Exception:
        # aexpect.ExpectTimeoutError or other exceptions
        # send 'ctrl+c' to v2v process to interrupt running quickly
        subproc.sendcontrol('c')
        raise
    finally:
        LOG.debug(
            "Command '%s' finished with status %s",
            subproc.command,
            subproc.get_status())
        # Set command result
        cmd_result.command = subproc.command
        cmd_result.exit_status = subproc.get_status()
        cmd_result.stdout = subproc.get_output()
        # Close the expect session
        subproc.close()

    return cmd_result
