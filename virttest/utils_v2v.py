"""
Virt-v2v test utility functions.

:copyright: 2008-2012 Red Hat Inc.
"""

import os
import re
import time
import logging

from avocado.utils import path
from avocado.utils import process
from avocado.core import exceptions
from virttest.compat_52lts import results_stdout_52lts, results_stderr_52lts, decode_to_text

from virttest import ovirt
from virttest.utils_test import libvirt
from virttest import libvirt_vm as lvirt
from virttest import virsh
from virttest import ppm_utils
from virttest import data_dir
from virttest import remote
from virttest import utils_misc
from virttest import ssh_key

try:
    V2V_EXEC = path.find_command('virt-v2v')
except path.CmdNotFoundError:
    V2V_EXEC = None


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
        uri = "xen+ssh://" + self.host + "/"
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
        # authorized_keys in remote vmx host
        self.authorized_keys = []

    def cleanup(self):
        """
        Cleanup NFS mount records
        """
        for src, dst, fstype in self.mount_records.values():
            utils_misc.umount(src, dst, fstype)

        self.cleanup_authorized_keys_in_vmx()

    def cleanup_authorized_keys_in_vmx(self):
        """
        Clean up authorized_keys in vmx server
        """
        session = None
        if len(self.authorized_keys) == 0:
            return

        try:
            session = remote.remote_login(
                client='ssh',
                host=self.esxi_host,
                port=22,
                username=self.username,
                password=self.esxi_password,
                prompt=r"[\#\$\[\]]",
                preferred_authenticaton='password,keyboard-interactive')
            for key in self.authorized_keys:
                session.cmd(
                    "sed -i '/%s/d' /etc/ssh/keys-root/authorized_keys" %
                    key)
        finally:
            if session:
                session.close()

    def get_cmd_options(self, params):
        """
        Target dispatcher.
        """
        opts_func = getattr(self, "_get_%s_options" % self.target)
        self.params = params
        self.output_method = self.params.get('output_method', 'rhev')
        self.input_mode = self.params.get('input_mode')
        self.esxi_host = self.params.get(
            'esxi_host', self.params.get('esx_ip'))
        self.datastore = self.params.get('datastore')
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
        self.storage = self.params.get('storage')
        self.storage_name = self.params.get('storage_name')
        self.format = self.params.get('output_format', 'raw')
        self.input_file = self.params.get('input_file')
        self.new_name = self.params.get('new_name')
        self.username = self.params.get('username', 'root')
        self.vmx_nfs_src = self.params.get('vmx_nfs_src')
        self.has_genid = self.params.get('has_genid')
        self.net_vm_opts = ""

        def _compose_vmx_filename():
            """
            Return vmx filename for '-i vmx'.
            """
            mount_point = v2v_mount(self.vmx_nfs_src, 'vmx_nfs_src')
            self.mount_records[len(self.mount_records)] = (
                self.vmx_nfs_src, mount_point, None)

            vmx_filename = "{}/{name}/{name}.vmx".format(
                mount_point, name=self.vm_name)

            return vmx_filename

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
                        logging.error(
                            'Neither vddk_libdir nor vddk_libdir_src was set')
                        raise exceptions.TestError(
                            "VDDK library directory or NFS mount point must be set")

                    mount_point = v2v_mount(
                        self.vddk_libdir_src, 'vddk_libdir')
                    self.vddk_libdir = mount_point
                    self.mount_records[len(self.mount_records)] = (
                        self.vddk_libdir_src, self.vddk_libdir, None)

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
                pub_key = setup_esx_ssh_key(
                    self.esxi_host, self.username, self.esxi_password)
                self.authorized_keys.append(pub_key.split()[1].split('/')[0])
                utils_misc.add_identities_into_ssh_agent()

            # New input_transport type can be added here

            # A dict to save input_transport types and their io options, new it_types
            # should be added here. Their io values were composed during running time
            # based on user's input
            input_transport_args = {
                'vddk': "-io vddk-libdir=%s -io vddk-thumbprint=%s" % (self.vddk_libdir,
                                                                       self.vddk_thumbprint),
                'ssh': "ssh://root@{}/vmfs/volumes/{}/{name}/{name}.vmx".format(
                    self.esxi_host,
                    self.datastore,
                    name=self.vm_name)}

            options = " -it %s " % (self.input_transport)
            options += input_transport_args[self.input_transport]
            return options

        if self.bridge:
            self.net_vm_opts += " -b %s" % self.bridge

        if self.network:
            self.net_vm_opts += " -n %s" % self.network

        if self.input_mode != 'vmx':
            self.net_vm_opts += " %s" % self.vm_name
        elif self.input_transport is None:
            self.net_vm_opts += " %s" % _compose_vmx_filename()

        options = opts_func() + _compose_input_transport_options()

        if self.new_name:
            options += ' -on %s' % self.new_name

        if self.input_mode is not None:
            options = " -i %s %s" % (self.input_mode, options)
            if self.input_mode in ['ova', 'disk',
                                   'libvirtxml'] and self.input_file:
                options = options.replace(self.vm_name, self.input_file)
        return options

    def _get_libvirt_options(self):
        """
        Return command options.
        """
        options = " -ic %s -os %s -of %s" % (self.uri,
                                             self.storage,
                                             self.format)
        options = options + self.net_vm_opts

        return options

    def _get_libvirtxml_options(self):
        """
        Return command options.
        """
        options = " -os %s" % self.storage
        options = options + self.net_vm_opts

        return options

    def _get_ovirt_options(self):
        """
        Return command options.
        """
        options = " -ic %s -o %s -os %s -of %s" % (
            self.uri,
            self.output_method.replace('_', '-'),
            self.storage if self.output_method != "rhv_upload" else self.storage_name,
            self.format)
        options = options + self.net_vm_opts

        return options

    def _get_local_options(self):
        """
        Return command options.
        """
        options = " -ic %s -o local -os %s -of %s" % (self.uri,
                                                      self.storage,
                                                      self.format)
        options = options + self.net_vm_opts

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
        self.virsh_session_id = params.get("virsh_session_id")
        self.windows_root = params.get("windows_root", r"C:\WINDOWS")
        self.output_method = params.get("output_method")
        # Need create session after create the instance
        self.session = None

        if self.name is None:
            logging.error("vm name not exist")

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
        self.session = self.vm.wait_for_login(nic_index=self.nic_index,
                                              timeout=timeout,
                                              username=self.username,
                                              password=self.password)

    def cleanup(self):
        """
        Cleanup VM and remove all of storage files about guest
        """
        if self.vm.instance and self.vm.is_alive():
            self.vm.destroy(gracefully=False)
            time.sleep(5)

        if self.target == "libvirt":
            if self.vm.exists() and self.vm.is_persistent():
                self.vm.undefine()

        if self.target == "ovirt":
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
        """
        status, output = self.session.cmd_status_output(cmd)
        if debug:
            logging.debug("Command return status: %s", status)
            logging.debug("Command output:\n%s", output)
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
            logging.error("Fail to get os distribution: %s", e)
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
        logging.debug("The os vendor of VM '%s' is: %s" %
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
        cmd = "lspci"
        return self.run_cmd(cmd)[1]

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

    def get_vm_xorg(self):
        """
        Get vm Xorg config/log.
        """
        self.wait_for_x_start()
        cmd_file_exist = "ls /etc/X11/xorg.conf || ls /var/log/Xorg.0.log"
        if self.run_cmd(cmd_file_exist)[0]:
            return False
        cmd = "cat /etc/X11/xorg.conf /var/log/Xorg.0.log"
        return self.run_cmd(cmd)[1]

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
            logging.error("Fail to find virtio driver")
        return False

    def is_disk_virtio(self, disk="/dev/vda"):
        """
        Check whether disk is virtio.
        """
        cmd = "fdisk -l %s" % disk
        output = self.run_cmd(cmd)[1]
        if re.search(disk, output):
            return True
        return False

    def is_uefi_guest(self):
        """
        Check whether guest is uefi guest
        """
        cmd = "ls /boot/efi/EFI/BOOT/"
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
        Move mouse and click button to install dirver for new
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
            r_runner = remote.RemoteRunner(
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
                logging.debug("Compare vm screenshot with image %s", image)
                ppm_utils.image_crop_save(image, cropped_image)
                h_degree = ppm_utils.image_histogram_compare(cropped_image,
                                                             vm_screenshot)
                if h_degree >= similar_degree:
                    logging.debug("Image %s matched", image)
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
        logging.info("Booting Windows in %s seconds", timeout)
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
                    logging.error(
                        "Screenshot '%s' does not exist", match_image)
                    return
                match_image_list.append(match_image)
            img_match_ret = self.wait_for_match(match_image_list,
                                                timeout=timeout)
            if img_match_ret < 0:
                logging.error(timeout_msg)
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
            logging.info("%s is booting up without program intervention",
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
            logging.debug('%d times remaining for getting driver info' % count)
            try:
                # Clean up output
                self.session.cmd('cls')
                output = self.session.cmd_output(cmd)
            except Exception as detail:
                logging.error(detail)
                count -= 1
            else:
                break
        if not output:
            logging.error('Fail to get driver info')
        logging.debug("Command output:\n%s", output)
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


def v2v_cmd(params):
    """
    Append 'virt-v2v' and execute it.

    :param params: A dictionary includes all of required parameters such as
                    'target', 'hypervisor' and 'hostname', etc.
    :return: A CmdResult object
    """
    if V2V_EXEC is None:
        raise ValueError('Missing command: virt-v2v')

    target = params.get('target')
    hypervisor = params.get('hypervisor')
    # vpx:// or esx://
    src_uri_type = params.get('src_uri_type')
    hostname = params.get('hostname')
    vpx_dc = params.get('vpx_dc')
    esxi_host = params.get('esxi_host', params.get('esx_ip'))
    opts_extra = params.get('v2v_opts')
    # Set v2v_timeout to 3 hours, the value can give v2v enough time to execute,
    # and avoid v2v process be killed by mistake.
    # the value is bigger than the timeout value in CI, so when some timeout
    # really happens, CI will still interrupt the v2v process.
    v2v_timeout = params.get('v2v_timeout', 10800)
    rhv_upload_opts = params.get('rhv_upload_opts')

    uri_obj = Uri(hypervisor)
    # Return actual 'uri' according to 'hostname' and 'hypervisor'
    if src_uri_type == 'esx':
        vpx_dc = None
    uri = uri_obj.get_uri(hostname, vpx_dc, esxi_host)

    target_obj = Target(target, uri)
    try:
        # Return virt-v2v command line options based on 'target' and
        # 'hypervisor'
        options = target_obj.get_cmd_options(params)

        if rhv_upload_opts:
            options = options + ' ' + rhv_upload_opts
        if opts_extra:
            options = options + ' ' + opts_extra

        # Construct a final virt-v2v command
        cmd = '%s %s' % (V2V_EXEC, options)
        cmd_result = process.run(cmd, timeout=v2v_timeout,
                                 verbose=True, ignore_status=True)
    finally:
        target_obj.cleanup()

    cmd_result.stdout = results_stdout_52lts(cmd_result)
    cmd_result.stderr = results_stderr_52lts(cmd_result)

    return cmd_result


def import_vm_to_ovirt(params, address_cache, timeout=600):
    """
    Import VM from export domain to oVirt Data Center
    """
    vm_name = params.get('main_vm')
    os_type = params.get('os_type')
    export_name = params.get('export_name')
    storage_name = params.get('storage_name')
    cluster_name = params.get('cluster_name')
    output_method = params.get('output_method')
    # Check oVirt status
    dc = ovirt.DataCenterManager(params)
    logging.info("Current data centers list: %s", dc.list())
    cm = ovirt.ClusterManager(params)
    logging.info("Current cluster list: %s", cm.list())
    hm = ovirt.HostManager(params)
    logging.info("Current host list: %s", hm.list())
    sdm = ovirt.StorageDomainManager(params)
    logging.info("Current storage domain list: %s", sdm.list())
    vm = ovirt.VMManager(vm_name, params, address_cache=address_cache)
    logging.info("Current VM list: %s", vm.list())
    if vm_name in vm.list() and output_method != 'rhv_upload':
        logging.error("%s already exist", vm_name)
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
            logging.info("The latest VM list: %s", vm.list())
        except Exception as e:
            # Try to delete the vm from export domain
            vm.delete_from_export_domain(export_name)
            logging.error("Import %s failed: %s", vm.name, e)
            return False
    try:
        # Start VM
        vm.start(wait_for_up=wait_for_up)
    except Exception as e:
        logging.error("Start %s failed: %s", vm.name, e)
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
            logging.info('Searching for %s log: %s' % (expected, pattern))
            compiled_pattern = re.compile(line)
            search = re.search(compiled_pattern, log)
            if search:
                logging.info('Found log: %s', search.group(0))
                if not expect:
                    return False
            else:
                logging.info('Not find log: %s', pattern)
                if expect:
                    return False
        return True

    expect_msg = params.get('expect_msg')
    ret = ''
    if not expect_msg:
        logging.info('No need to check v2v log')
    else:
        expect = expect_msg == 'yes'
        if params.get('msg_content'):
            msg_list = params['msg_content'].split('%')
            if _check_log(msg_list, expect=expect):
                logging.info('Finish checking v2v log')
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
                decode_to_text(
                    result.stderr,
                    errors=error_flag))
        else:
            logging.debug(
                "Command output:\n%s",
                decode_to_text(
                    result.stdout,
                    errors=error_flag).strip())
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

    map(os.remove, [x for x in tmpfiles if x and os.path.isfile(x)])


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

    r_runner = remote.RemoteRunner(
        host=host,
        password=password,
        prompt=prompt,
        preferred_authenticaton='password,keyboard-interactive')
    cmdresult = r_runner.run(cmd)
    logging.debug("vddk thumbprint:\n%s", cmdresult.stdout)
    vddk_thumbprint = cmdresult.stdout.strip().split('=')[1]

    return vddk_thumbprint


def setup_esx_ssh_key(hostname, username, password, port=22):
    """
    Setup up remote login in esx server by using public key

    :param hostname: hostname or IP address
    :param username: username
    :param password: Password
    :param port: ssh port number
    """
    session = None
    logging.debug('Performing SSH key setup on %s:%d as %s.' %
                  (hostname, port, username))
    try:
        session = remote.remote_login(
            client='ssh',
            host=hostname,
            username=username,
            port=port,
            password=password,
            prompt=r"[\#\$\[\]]",
            preferred_authenticaton='password,keyboard-interactive')
        public_key = ssh_key.get_public_key()
        session.cmd("echo '%s' >> /etc/ssh/keys-root/authorized_keys; " %
                    public_key)
        logging.debug('SSH key setup complete.')

        return public_key
    except Exception as err:
        raise exceptions.TestFail("SSH key setup failed: '%s'" % err)
    finally:
        if session:
            session.close()


def v2v_mount(src, dst='v2v_mount_point'):
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
        'nfs',
            verbose=True):
        raise exceptions.TestError(
            'Mount %s for %s failed' %
            (src, mount_point))

    return mount_point
