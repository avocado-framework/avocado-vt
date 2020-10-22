from __future__ import division
import logging
import time
import re
import os
import tempfile
import threading
import shutil
import stat
import xml.dom.minidom
try:
    import configparser as ConfigParser
except ImportError:
    import ConfigParser

from aexpect import remote

from avocado.core import exceptions
from avocado.utils import astring
from avocado.utils import iso9660
from avocado.utils import process
from avocado.utils import crypto
from avocado.utils import download

from virttest import virt_vm
from virttest import asset
from virttest import utils_disk
from virttest import qemu_monitor
from virttest import syslog_server
from virttest import http_server
from virttest import data_dir
from virttest import utils_net
from virttest import utils_test
from virttest import utils_misc
from virttest import funcatexit
from virttest import storage
from virttest import error_context
from virttest import qemu_storage


# Whether to print all shell commands called
DEBUG = False

_url_auto_content_server_thread = None
_url_auto_content_server_thread_event = None

_unattended_server_thread = None
_unattended_server_thread_event = None

_syslog_server_thread = None
_syslog_server_thread_event = None


def start_auto_content_server_thread(port, path):
    global _url_auto_content_server_thread
    global _url_auto_content_server_thread_event

    if _url_auto_content_server_thread is None:
        _url_auto_content_server_thread_event = threading.Event()
        _url_auto_content_server_thread = threading.Thread(
            target=http_server.http_server,
            args=(port, path, terminate_auto_content_server_thread))
        _url_auto_content_server_thread.start()


def start_unattended_server_thread(port, path):
    global _unattended_server_thread
    global _unattended_server_thread_event

    if _unattended_server_thread is None:
        _unattended_server_thread_event = threading.Event()
        _unattended_server_thread = threading.Thread(
            target=http_server.http_server,
            args=(port, path, terminate_unattended_server_thread))
        _unattended_server_thread.start()


def terminate_auto_content_server_thread():
    global _url_auto_content_server_thread
    global _url_auto_content_server_thread_event

    if _url_auto_content_server_thread is None:
        return False
    if _url_auto_content_server_thread_event is None:
        return False

    if _url_auto_content_server_thread_event.isSet():
        return True

    return False


def terminate_unattended_server_thread():
    global _unattended_server_thread, _unattended_server_thread_event

    if _unattended_server_thread is None:
        return False
    if _unattended_server_thread_event is None:
        return False

    if _unattended_server_thread_event.isSet():
        return True

    return False


class RemoteInstall(object):

    """
    Represents a install http server that we can master according to our needs.
    """

    def __init__(self, path, ip, port, filename):
        self.path = path
        utils_disk.cleanup(self.path)
        os.makedirs(self.path)
        self.ip = ip
        self.port = port
        self.filename = filename

        start_unattended_server_thread(self.port, self.path)

    def get_url(self):
        return 'http://%s:%s/%s' % (self.ip, self.port, self.filename)

    def get_answer_file_path(self, filename):
        return os.path.join(self.path, filename)

    def close(self):
        os.chmod(self.path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)
        logging.debug("unattended http server %s successfully created",
                      self.get_url())


class UnattendedInstallConfig(object):

    """
    Creates a floppy disk image that will contain a config file for unattended
    OS install. The parameters to the script are retrieved from environment
    variables.
    """

    def __init__(self, test, params, vm):
        """
        Sets class attributes from test parameters.

        :param test: QEMU test object.
        :param params: Dictionary with test parameters.
        """
        root_dir = data_dir.get_data_dir()
        self.deps_dir = os.path.join(test.virtdir, 'deps')
        self.unattended_dir = os.path.join(test.virtdir, 'unattended')
        self.results_dir = test.debugdir
        self.params = params

        self.attributes = ['kernel_args', 'finish_program', 'cdrom_cd1',
                           'unattended_file', 'medium', 'url', 'kernel',
                           'initrd', 'nfs_server', 'nfs_dir', 'install_virtio',
                           'floppy_name', 'cdrom_unattended', 'boot_path',
                           'kernel_params', 'extra_params', 'qemu_img_binary',
                           'cdkey', 'finish_program', 'vm_type',
                           'process_check', 'vfd_size', 'cdrom_mount_point',
                           'floppy_mount_point', 'cdrom_virtio',
                           'virtio_floppy', 're_driver_match',
                           're_hardware_id', 'driver_in_floppy', 'vga',
                           'unattended_file_kernel_param_name']

        for a in self.attributes:
            setattr(self, a, params.get(a, ''))

        # Make finish.bat work well with positional arguments
        if not self.process_check.strip():  # pylint: disable=E0203
            self.process_check = '""'       # pylint: disable=E0203

        # Will setup the virtio attributes
        v_attributes = ['virtio_floppy', 'virtio_scsi_path',
                        'virtio_storage_path', 'virtio_network_path',
                        'virtio_balloon_path', 'virtio_viorng_path',
                        'virtio_vioser_path', 'virtio_pvpanic_path',
                        'virtio_vioinput_path', 'virtio_viofs_path',
                        'virtio_oemsetup_id',
                        'virtio_network_installer_path',
                        'virtio_balloon_installer_path',
                        'virtio_qxl_installer_path']

        for va in v_attributes:
            setattr(self, va, params.get(va, ''))

        self.tmpdir = test.tmpdir
        self.qemu_img_binary = utils_misc.get_qemu_img_binary(params)

        def get_unattended_file(backend):
            providers = asset.get_test_provider_names(backend)
            if not providers:
                return
            for provider_name in providers:
                provider_info = asset.get_test_provider_info(provider_name)
                if backend not in provider_info["backends"]:
                    continue
                if "path" not in provider_info["backends"][backend]:
                    continue
                path = provider_info["backends"][backend]["path"]
                tp_unattended_file = os.path.join(path, self.unattended_file)
                if os.path.exists(tp_unattended_file):
                    # Using unattended_file from test-provider
                    unattended_file = tp_unattended_file
                    # Take the first matched
                    return unattended_file

        if getattr(self, 'unattended_file'):
            # Fail-back to general unattended_file
            unattended_file = os.path.join(test.virtdir, self.unattended_file)
            for backend in asset.get_known_backends():
                found_file = get_unattended_file(backend)
                if found_file:
                    unattended_file = found_file
                    break
            self.unattended_file = unattended_file

        if getattr(self, 'finish_program'):
            self.finish_program = os.path.join(test.virtdir,
                                               self.finish_program)

        if getattr(self, 'cdrom_cd1'):
            self.cdrom_cd1 = os.path.join(root_dir, self.cdrom_cd1)
        self.cdrom_cd1_mount = tempfile.mkdtemp(prefix='cdrom_cd1_',
                                                dir=self.tmpdir)
        if getattr(self, 'cdrom_unattended'):
            self.cdrom_unattended = os.path.join(root_dir,
                                                 self.cdrom_unattended)

        if getattr(self, 'virtio_floppy'):
            self.virtio_floppy = os.path.join(root_dir, self.virtio_floppy)

        if getattr(self, 'cdrom_virtio'):
            self.cdrom_virtio = os.path.join(root_dir, self.cdrom_virtio)

        if getattr(self, 'kernel'):
            self.kernel = os.path.join(root_dir, self.kernel)
        if getattr(self, 'initrd'):
            self.initrd = os.path.join(root_dir, self.initrd)

        if self.medium == 'nfs':
            self.nfs_mount = tempfile.mkdtemp(prefix='nfs_',
                                              dir=self.tmpdir)

        setattr(self, 'floppy', self.floppy_name)
        if getattr(self, 'floppy'):
            self.floppy = os.path.join(root_dir, self.floppy)
            if not os.path.isdir(os.path.dirname(self.floppy)):
                os.makedirs(os.path.dirname(self.floppy))

        self.image_path = os.path.dirname(self.kernel)

        # Content server params
        # lookup host ip address for first nic by interface name
        try:
            netdst = vm.virtnet[0].netdst
            # 'netdst' parameter is taken from cartesian config. Sometimes
            # netdst=<empty>. Call get_ip_address_by_interface() only for case
            # when netdst= is defined to something.
            if netdst:
                auto_ip = utils_net.get_ip_address_by_interface(netdst)
            else:
                auto_ip = utils_net.get_host_ip_address(params)
        except utils_net.NetError:
            auto_ip = None

        params_auto_ip = params.get('url_auto_ip', None)
        if params_auto_ip:
            self.url_auto_content_ip = params_auto_ip
        else:
            self.url_auto_content_ip = auto_ip

        self.url_auto_content_port = None

        # Kickstart server params
        # use the same IP as url_auto_content_ip, but a different port
        self.unattended_server_port = None

        # Embedded Syslog Server
        self.syslog_server_enabled = params.get('syslog_server_enabled', 'no')
        self.syslog_server_ip = params.get('syslog_server_ip', auto_ip)
        self.syslog_server_port = int(params.get('syslog_server_port', 5140))
        self.syslog_server_tcp = params.get('syslog_server_proto',
                                            'tcp') == 'tcp'

        self.vm = vm

    @error_context.context_aware
    def get_driver_hardware_id(self, driver, run_cmd=True):
        """
        Get windows driver's hardware id from inf files.

        :param dirver: Configurable driver name.
        :param run_cmd:  Use hardware id in windows cmd command or not.
        :return: Windows driver's hardware id
        """
        if not os.path.exists(self.cdrom_mount_point):
            os.mkdir(self.cdrom_mount_point)
        if not os.path.exists(self.floppy_mount_point):
            os.mkdir(self.floppy_mount_point)
        if not os.path.ismount(self.cdrom_mount_point):
            process.system("mount %s %s -o loop" % (self.cdrom_virtio,
                                                    self.cdrom_mount_point), timeout=60)
        if not os.path.ismount(self.floppy_mount_point):
            process.system("mount %s %s -o loop" % (self.virtio_floppy,
                                                    self.floppy_mount_point), timeout=60)
        drivers_d = []
        driver_link = None
        if self.driver_in_floppy is not None:
            driver_in_floppy = self.driver_in_floppy
            drivers_d = driver_in_floppy.split()
        else:
            drivers_d.append('qxl.inf')
        for driver_d in drivers_d:
            if driver_d in driver:
                driver_link = os.path.join(self.floppy_mount_point, driver)
        if driver_link is None:
            driver_link = os.path.join(self.cdrom_mount_point, driver)
        try:
            txt = open(driver_link, "r").read()
            hwid = re.findall(self.re_hardware_id, txt)[-1].rstrip()
            if run_cmd:
                hwid = '^&'.join(hwid.split('&'))
            return hwid
        except Exception as e:
            logging.error("Fail to get hardware id with exception: %s" % e)

    @error_context.context_aware
    def update_driver_hardware_id(self, driver):
        """
        Update driver string with the hardware id get from inf files

        @driver: driver string
        :return: new driver string
        """
        if 'hwid' in driver:
            if 'hwidcmd' in driver:
                run_cmd = True
            else:
                run_cmd = False
            if self.re_driver_match is not None:
                d_str = self.re_driver_match
            else:
                d_str = "(\S+)\s*hwid"

            drivers_in_floppy = []
            if self.driver_in_floppy is not None:
                drivers_in_floppy = self.driver_in_floppy.split()

            mount_point = self.cdrom_mount_point
            storage_path = self.cdrom_virtio
            for driver_in_floppy in drivers_in_floppy:
                if driver_in_floppy in driver:
                    mount_point = self.floppy_mount_point
                    storage_path = self.virtio_floppy
                    break

            d_link = re.findall(d_str, driver)[0].split(":")[1]
            d_link = "/".join(d_link.split("\\\\")[1:])
            hwid = utils_test.get_driver_hardware_id(d_link, mount_point,
                                                     storage_path,
                                                     run_cmd=run_cmd)
            if hwid:
                driver = driver.replace("hwidcmd", hwid.strip())
            else:
                raise exceptions.TestError("Can not find hwid from the driver"
                                           " inf file")
        return driver

    def answer_kickstart(self, answer_path):
        """
        Replace KVM_TEST_CDKEY (in the unattended file) with the cdkey
        provided for this test and replace the KVM_TEST_MEDIUM with
        the tree url or nfs address provided for this test.

        :return: Answer file contents
        """
        contents = open(self.unattended_file).read()

        dummy_cdkey_re = r'\bKVM_TEST_CDKEY\b'
        if re.search(dummy_cdkey_re, contents):
            if self.cdkey:
                contents = re.sub(dummy_cdkey_re, self.cdkey, contents)

        dummy_medium_re = r'\bKVM_TEST_MEDIUM\b'
        if self.medium in ["cdrom", "kernel_initrd"]:
            content = "cdrom"

        elif self.medium == "url":
            content = "url --url %s" % self.url

        elif self.medium == "nfs":
            content = "nfs --server=%s --dir=%s" % (self.nfs_server,
                                                    self.nfs_dir)
        else:
            raise ValueError("Unexpected installation medium %s" % self.url)
        contents = re.sub(dummy_medium_re, content, contents)

        dummy_rh_system_stream_id_re = r'\bRH_SYSTEM_STREAM_ID\b'
        if re.search(dummy_rh_system_stream_id_re, contents):
            rh_system_stream_id = self.params.get("rh_system_stream_id", "")
            contents = re.sub(dummy_rh_system_stream_id_re, rh_system_stream_id, contents)

        dummy_repos_re = r'\bKVM_TEST_REPOS\b'
        if re.search(dummy_repos_re, contents):
            repo_list = self.params.get("kickstart_extra_repos", "").split()
            lines = ["# Extra repositories"]
            for index, repo_url in enumerate(repo_list, 1):
                line = ("repo --name=extra_repo%d --baseurl=%s --install "
                        "--noverifyssl" % (index, repo_url))
                lines.append(line)
            content = "\n".join(lines)
            contents = re.sub(dummy_repos_re, content, contents)

        dummy_logging_re = r'\bKVM_TEST_LOGGING\b'
        if re.search(dummy_logging_re, contents):
            if self.syslog_server_enabled == 'yes':
                log = 'logging --host=%s --port=%s --level=debug'
                log = log % (self.syslog_server_ip, self.syslog_server_port)
            else:
                log = ''
            contents = re.sub(dummy_logging_re, log, contents)

        dummy_graphical_re = re.compile('GRAPHICAL_OR_TEXT')
        if dummy_graphical_re.search(contents):
            if not self.vga or self.vga.lower() == "none":
                contents = dummy_graphical_re.sub('text', contents)
            else:
                contents = dummy_graphical_re.sub('graphical', contents)

        """
        cmd_only_use_disk is used for specifying disk which will be used during installation.
        """
        if self.params.get("cmd_only_use_disk"):
            insert_info = self.params.get("cmd_only_use_disk") + '\n'
            contents += insert_info
        logging.debug("Unattended install contents:")
        for line in contents.splitlines():
            logging.debug(line)
        with open(answer_path, 'w') as answer_file:
            answer_file.write(contents)

    def answer_windows_ini(self, answer_path):
        parser = ConfigParser.ConfigParser()
        parser.read(self.unattended_file)
        # First, replacing the CDKEY
        if self.cdkey:
            parser.set('UserData', 'ProductKey', self.cdkey)
        else:
            logging.error("Param 'cdkey' required but not specified for "
                          "this unattended installation")

        # Now, replacing the virtio network driver path, under double quotes
        if self.install_virtio == 'yes':
            parser.set('Unattended', 'OemPnPDriversPath',
                       '"%s"' % self.virtio_network_path)
        else:
            parser.remove_option('Unattended', 'OemPnPDriversPath')

        dummy_re_dirver = {'KVM_TEST_VIRTIO_NETWORK_INSTALLER':
                           'virtio_network_installer_path',
                           'KVM_TEST_VIRTIO_BALLOON_INSTALLER':
                           'virtio_balloon_installer_path',
                           'KVM_TEST_VIRTIO_QXL_INSTALLER':
                           'virtio_qxl_installer_path'}
        dummy_re = ""
        for dummy in dummy_re_dirver:
            if dummy_re:
                dummy_re += "|%s" % dummy
            else:
                dummy_re = dummy

        # Replace the process check in finish command
        dummy_process_re = r'\bPROCESS_CHECK\b'
        for opt in parser.options('GuiRunOnce'):
            check = parser.get('GuiRunOnce', opt)
            if re.search(dummy_process_re, check):
                process_check = re.sub(dummy_process_re,
                                       "%s" % self.process_check,
                                       check)
                parser.set('GuiRunOnce', opt, process_check)
            elif re.findall(dummy_re, check):
                dummy = re.findall(dummy_re, check)[0]
                driver = getattr(self, dummy_re_dirver[dummy])
                if driver.endswith("msi"):
                    driver = 'msiexec /passive /package ' + driver
                elif 'INSTALLER' in dummy:
                    driver = self.update_driver_hardware_id(driver)
                elif driver is None:
                    driver = 'dir'
                check = re.sub(dummy, driver, check)
                parser.set('GuiRunOnce', opt, check)
        # Now, writing the in memory config state to the unattended file
        fp = open(answer_path, 'w')
        parser.write(fp)
        fp.close()

        # Let's read it so we can debug print the contents
        fp = open(answer_path, 'r')
        contents = fp.read()
        fp.close()
        logging.debug("Unattended install contents:")
        for line in contents.splitlines():
            logging.debug(line)

    def answer_windows_xml(self, answer_path):
        doc = xml.dom.minidom.parse(self.unattended_file)

        if self.cdkey:
            # First, replacing the CDKEY
            product_key = doc.getElementsByTagName('ProductKey')[0]
            if product_key.getElementsByTagName('Key'):
                key = product_key.getElementsByTagName('Key')[0]
                key_text = key.childNodes[0]
            else:
                key_text = product_key.childNodes[0]

            assert key_text.nodeType == doc.TEXT_NODE
            key_text.data = self.cdkey
        else:
            logging.error("Param 'cdkey' required but not specified for "
                          "this unattended installation")

        # Now, replacing the virtio driver paths or removing the entire
        # component PnpCustomizationsWinPE Element Node
        if self.install_virtio == 'yes':
            paths = doc.getElementsByTagName("Path")
            values = [self.virtio_scsi_path,
                      self.virtio_storage_path, self.virtio_network_path,
                      self.virtio_balloon_path, self.virtio_viorng_path,
                      self.virtio_vioser_path, self.virtio_pvpanic_path,
                      self.virtio_vioinput_path, self.virtio_viofs_path]

            # XXX: Force to replace the drive letter which loaded the
            # virtio driver by the specified letter.
            letter = self.params.get('virtio_drive_letter')
            if letter is not None:
                values = (re.sub(r'^\w+', letter, val) for val in values)

            for path, value in list(zip(paths, values)):
                if value:
                    path_text = path.childNodes[0]
                    assert path_text.nodeType == doc.TEXT_NODE
                    path_text.data = value
        else:
            settings = doc.getElementsByTagName("settings")
            for s in settings:
                for c in s.getElementsByTagName("component"):
                    if (c.getAttribute('name') ==
                            "Microsoft-Windows-PnpCustomizationsWinPE"):
                        s.removeChild(c)

        # Last but not least important, replacing the virtio installer command
        # And process check in finish command
        command_lines = doc.getElementsByTagName("CommandLine")
        dummy_re_dirver = {'KVM_TEST_VIRTIO_NETWORK_INSTALLER':
                           'virtio_network_installer_path',
                           'KVM_TEST_VIRTIO_BALLOON_INSTALLER':
                           'virtio_balloon_installer_path',
                           'KVM_TEST_VIRTIO_QXL_INSTALLER':
                           'virtio_qxl_installer_path'}
        process_check_re = 'PROCESS_CHECK'
        dummy_re = ""
        for dummy in dummy_re_dirver:
            if dummy_re:
                dummy_re += "|%s" % dummy
            else:
                dummy_re = dummy

        for command_line in command_lines:
            command_line_text = command_line.childNodes[0]
            assert command_line_text.nodeType == doc.TEXT_NODE

            if re.findall(dummy_re, command_line_text.data):
                dummy = re.findall(dummy_re, command_line_text.data)[0]
                driver = getattr(self, dummy_re_dirver[dummy])

                if driver.endswith("msi"):
                    driver = 'msiexec /passive /package ' + driver
                elif 'INSTALLER' in dummy:
                    driver = self.update_driver_hardware_id(driver)
                t = command_line_text.data
                t = re.sub(dummy_re, driver, t)
                command_line_text.data = t

            if process_check_re in command_line_text.data:
                t = command_line_text.data
                t = re.sub(process_check_re, self.process_check, t)
                command_line_text.data = t

        contents = doc.toxml()
        logging.debug("Unattended install contents:")
        for line in contents.splitlines():
            logging.debug(line)

        fp = open(answer_path, 'w')
        doc.writexml(fp)
        fp.close()

    def answer_suse_xml(self, answer_path):
        # There's nothing to replace on SUSE files to date. Yay!
        doc = xml.dom.minidom.parse(self.unattended_file)

        contents = doc.toxml()
        logging.debug("Unattended install contents:")
        for line in contents.splitlines():
            logging.debug(line)

        fp = open(answer_path, 'w')
        doc.writexml(fp)
        fp.close()

    def preseed_initrd(self):
        """
        Puts a preseed file inside a gz compressed initrd file.

        Debian and Ubuntu use preseed as the OEM install mechanism. The only
        way to get fully automated setup without resorting to kernel params
        is to add a preseed.cfg file at the root of the initrd image.
        """
        logging.debug("Remastering initrd.gz file with preseed file")
        dest_fname = 'preseed.cfg'
        remaster_path = os.path.join(self.image_path, "initrd_remaster")
        if not os.path.isdir(remaster_path):
            os.makedirs(remaster_path)

        base_initrd = os.path.basename(self.initrd)
        os.chdir(remaster_path)
        process.run("gzip -d < ../%s | fakeroot cpio --extract --make-directories "
                    "--no-absolute-filenames" % base_initrd, verbose=DEBUG,
                    shell=True)
        process.run("cp %s %s" % (self.unattended_file, dest_fname),
                    verbose=DEBUG)

        # For libvirt initrd.gz will be renamed to initrd.img in setup_cdrom()
        process.run("find . | fakeroot cpio -H newc --create | gzip -9 > ../%s" %
                    base_initrd, verbose=DEBUG, shell=True)

        os.chdir(self.image_path)
        process.run("rm -rf initrd_remaster", verbose=DEBUG)
        contents = open(self.unattended_file).read()

        logging.debug("Unattended install contents:")
        for line in contents.splitlines():
            logging.debug(line)

    def set_unattended_param_in_kernel(self, unattended_file_url):
        '''
        Check if kernel parameter that sets the unattended installation file
        is present.
        Add the parameter with the passed URL if it does not exist,
        otherwise replace the existing URL.

        :param unattended_file_url: URL to unattended installation file
        :return: modified kernel parameters
        '''
        unattended_param = '%s=%s' % (self.unattended_file_kernel_param_name,
                                      unattended_file_url)
        if '%s=' % self.unattended_file_kernel_param_name in self.kernel_params:
            kernel_params = re.sub('%s=[\w\d:\-\./]+' %
                                   (self.unattended_file_kernel_param_name),
                                   unattended_param,
                                   self.kernel_params)
        else:
            kernel_params = '%s %s' % (self.kernel_params, unattended_param)
        return kernel_params

    def setup_unattended_http_server(self):
        '''
        Setup a builtin http server for serving the kickstart/preseed file

        Does nothing if unattended file is not a kickstart/preseed file
        '''
        if self.unattended_file.endswith('.ks') or self.unattended_file.endswith('.preseed'):
            # Red Hat kickstart install or Ubuntu preseed install
            dest_fname = 'ks.cfg'

            answer_path = os.path.join(self.tmpdir, dest_fname)
            self.answer_kickstart(answer_path)

            if self.unattended_server_port is None:
                self.unattended_server_port = utils_misc.find_free_port(
                    8000,
                    8099,
                    self.url_auto_content_ip)

            start_unattended_server_thread(self.unattended_server_port,
                                           self.tmpdir)
        else:
            return

        # Point installation to this kickstart url
        unattended_file_url = 'http://%s:%s/%s' % (self.url_auto_content_ip,
                                                   self.unattended_server_port,
                                                   dest_fname)
        kernel_params = self.set_unattended_param_in_kernel(
            unattended_file_url)

        # reflect change on params
        self.kernel_params = kernel_params

    def setup_boot_disk(self):
        if self.unattended_file.endswith('.sif'):
            dest_fname = 'winnt.sif'
            setup_file = 'winnt.bat'
            boot_disk = utils_disk.FloppyDisk(self.floppy,
                                              self.qemu_img_binary,
                                              self.tmpdir, self.vfd_size)
            answer_path = boot_disk.get_answer_file_path(dest_fname)
            self.answer_windows_ini(answer_path)
            setup_file_path = os.path.join(self.unattended_dir, setup_file)
            boot_disk.copy_to(setup_file_path)
            if self.install_virtio == "yes":
                boot_disk.setup_virtio_win2003(self.virtio_floppy,
                                               self.virtio_oemsetup_id)
            boot_disk.copy_to(self.finish_program)

        elif self.unattended_file.endswith('.ks'):
            # Red Hat kickstart install
            dest_fname = 'ks.cfg'
            if self.params.get('unattended_delivery_method') == 'integrated':
                unattended_file_url = 'cdrom:/dev/sr0:/isolinux/%s' % (
                    dest_fname)
                kernel_params = self.set_unattended_param_in_kernel(
                    unattended_file_url)

                # Standard setting is kickstart disk in /dev/sr0 and
                # install cdrom in /dev/sr1. As we merge them together,
                # we need to change repo configuration to /dev/sr0
                if 'repo=cdrom' in kernel_params:
                    kernel_params = re.sub('repo=cdrom[:\w\d\-/]*',
                                           'repo=cdrom:/dev/sr0',
                                           kernel_params)

                self.kernel_params = None
                boot_disk = utils_disk.CdromInstallDisk(
                    self.cdrom_unattended,
                    self.tmpdir,
                    self.cdrom_cd1_mount,
                    kernel_params)
            elif self.params.get('unattended_delivery_method') == 'url':
                if self.unattended_server_port is None:
                    self.unattended_server_port = utils_misc.find_free_port(
                        8000,
                        8099,
                        self.url_auto_content_ip)
                path = os.path.join(os.path.dirname(self.cdrom_unattended),
                                    'ks')
                boot_disk = RemoteInstall(path, self.url_auto_content_ip,
                                          self.unattended_server_port,
                                          dest_fname)
                unattended_file_url = boot_disk.get_url()
                kernel_params = self.set_unattended_param_in_kernel(
                    unattended_file_url)

                # Standard setting is kickstart disk in /dev/sr0 and
                # install cdrom in /dev/sr1. When we get ks via http,
                # we need to change repo configuration to /dev/sr0
                kernel_params = re.sub('repo=cdrom[:\w\d\-/]*',
                                       'repo=cdrom:/dev/sr0',
                                       kernel_params)

                self.kernel_params = kernel_params
            elif self.params.get('unattended_delivery_method') == 'cdrom':
                boot_disk = utils_disk.CdromDisk(self.cdrom_unattended,
                                                 self.tmpdir)
            elif self.params.get('unattended_delivery_method') == 'floppy':
                boot_disk = utils_disk.FloppyDisk(self.floppy,
                                                  self.qemu_img_binary,
                                                  self.tmpdir, self.vfd_size)
                ks_param = '%s=floppy' % self.unattended_file_kernel_param_name
                kernel_params = self.kernel_params
                if '%s=' % self.unattended_file_kernel_param_name in kernel_params:
                    # Reading ks from floppy directly doesn't work in some OS,
                    # options 'ks=hd:/dev/fd0' can reading ks from mounted
                    # floppy, so skip repace it;
                    if not re.search("fd\d+", kernel_params):
                        kernel_params = re.sub('%s=[\w\d\-:\./]+' %
                                               (self.unattended_file_kernel_param_name),
                                               ks_param,
                                               kernel_params)
                else:
                    kernel_params = '%s %s' % (kernel_params, ks_param)

                kernel_params = re.sub('repo=cdrom[:\w\d\-/]*',
                                       'repo=cdrom:/dev/sr0',
                                       kernel_params)

                self.kernel_params = kernel_params
            else:
                raise ValueError("Neither cdrom_unattended nor floppy set "
                                 "on the config file, please verify")
            answer_path = boot_disk.get_answer_file_path(dest_fname)
            self.answer_kickstart(answer_path)

        elif self.unattended_file.endswith('.xml'):
            if "autoyast" in self.kernel_params:
                # SUSE autoyast install
                dest_fname = "autoinst.xml"
                if (self.cdrom_unattended and
                        self.params.get('unattended_delivery_method') == 'cdrom'):
                    boot_disk = utils_disk.CdromDisk(self.cdrom_unattended,
                                                     self.tmpdir)
                elif self.floppy:
                    autoyast_param = 'autoyast=device://fd0/autoinst.xml'
                    kernel_params = self.kernel_params
                    if 'autoyast=' in kernel_params:
                        kernel_params = re.sub('autoyast=[\w\d\-:\./]+',
                                               autoyast_param,
                                               kernel_params)
                    else:
                        kernel_params = '%s %s' % (
                            kernel_params, autoyast_param)

                    self.kernel_params = kernel_params
                    boot_disk = utils_disk.FloppyDisk(self.floppy,
                                                      self.qemu_img_binary,
                                                      self.tmpdir,
                                                      self.vfd_size)
                else:
                    raise ValueError("Neither cdrom_unattended nor floppy set "
                                     "on the config file, please verify")
                answer_path = boot_disk.get_answer_file_path(dest_fname)
                self.answer_suse_xml(answer_path)

            else:
                # Windows unattended install
                dest_fname = "autounattend.xml"
                if self.params.get('unattended_delivery_method') == 'cdrom':
                    boot_disk = utils_disk.CdromDisk(self.cdrom_unattended,
                                                     self.tmpdir)
                    if self.install_virtio == "yes":
                        boot_disk.setup_virtio_win2008(self.virtio_floppy,
                                                       self.cdrom_virtio)
                    else:
                        self.cdrom_virtio = None
                else:
                    boot_disk = utils_disk.FloppyDisk(self.floppy,
                                                      self.qemu_img_binary,
                                                      self.tmpdir,
                                                      self.vfd_size)
                    if self.install_virtio == "yes":
                        boot_disk.setup_virtio_win2008(self.virtio_floppy)
                answer_path = boot_disk.get_answer_file_path(dest_fname)
                self.answer_windows_xml(answer_path)

                boot_disk.copy_to(self.finish_program)

        else:
            raise ValueError('Unknown answer file type: %s' %
                             self.unattended_file)

        boot_disk.close()

    @error_context.context_aware
    def setup_cdrom(self):
        """
        Mount cdrom and copy vmlinuz and initrd.img.
        """
        error_context.context("Copying vmlinuz and initrd.img from install cdrom %s" %
                              self.cdrom_cd1)
        if not os.path.isdir(self.image_path):
            os.makedirs(self.image_path)

        if (self.params.get('unattended_delivery_method') in
                ['integrated', 'url']):
            i = iso9660.Iso9660Mount(self.cdrom_cd1)
            self.cdrom_cd1_mount = i.mnt_dir
        else:
            i = iso9660.iso9660(self.cdrom_cd1)

        if i is None:
            raise exceptions.TestFail("Could not instantiate an iso9660 class")

        i.copy(os.path.join(self.boot_path, os.path.basename(self.kernel)),
               self.kernel)
        assert(os.path.getsize(self.kernel) > 0)
        i.copy(os.path.join(self.boot_path, os.path.basename(self.initrd)),
               self.initrd)
        assert(os.path.getsize(self.initrd) > 0)

        if self.unattended_file.endswith('.preseed'):
            self.preseed_initrd()

        if self.params.get("vm_type") == "libvirt":
            if self.vm.driver_type == 'qemu':
                # Virtinstall command needs files "vmlinuz" and "initrd.img"
                os.chdir(self.image_path)
                base_kernel = os.path.basename(self.kernel)
                base_initrd = os.path.basename(self.initrd)
                if base_kernel != 'vmlinuz':
                    process.run("mv %s vmlinuz" % base_kernel, verbose=DEBUG)
                if base_initrd != 'initrd.img':
                    process.run("mv %s initrd.img" %
                                base_initrd, verbose=DEBUG)
                if (self.params.get('unattended_delivery_method') !=
                        'integrated'):
                    i.close()
                    utils_disk.cleanup(self.cdrom_cd1_mount)
            elif ((self.vm.driver_type == 'xen') and
                  (self.params.get('hvm_or_pv') == 'pv')):
                logging.debug("starting unattended content web server")

                self.url_auto_content_port = utils_misc.find_free_port(8100,
                                                                       8199,
                                                                       self.url_auto_content_ip)

                start_auto_content_server_thread(self.url_auto_content_port,
                                                 self.cdrom_cd1_mount)

                self.medium = 'url'
                self.url = ('http://%s:%s' % (self.url_auto_content_ip,
                                              self.url_auto_content_port))

                pxe_path = os.path.join(
                    os.path.dirname(self.image_path), 'xen')
                if not os.path.isdir(pxe_path):
                    os.makedirs(pxe_path)

                pxe_kernel = os.path.join(pxe_path,
                                          os.path.basename(self.kernel))
                pxe_initrd = os.path.join(pxe_path,
                                          os.path.basename(self.initrd))
                process.run("cp %s %s" % (self.kernel, pxe_kernel))
                process.run("cp %s %s" % (self.initrd, pxe_initrd))

                if 'repo=cdrom' in self.kernel_params:
                    # Red Hat
                    self.kernel_params = re.sub('repo=[:\w\d\-/]*',
                                                'repo=http://%s:%s' %
                                                (self.url_auto_content_ip,
                                                 self.url_auto_content_port),
                                                self.kernel_params)

    @error_context.context_aware
    def setup_url_auto(self):
        """
        Configures the builtin web server for serving content
        """
        auto_content_url = 'http://%s:%s' % (self.url_auto_content_ip,
                                             self.url_auto_content_port)
        self.params['auto_content_url'] = auto_content_url

    @error_context.context_aware
    def setup_url(self):
        """
        Download the vmlinuz and initrd.img from URL.
        """
        # it's only necessary to download kernel/initrd if running bare qemu
        if self.vm_type == 'qemu':
            error_context.context(
                "downloading vmlinuz/initrd.img from %s" % self.url)
            if not os.path.exists(self.image_path):
                os.mkdir(self.image_path)
            os.chdir(self.image_path)

            kernel_basename = os.path.basename(self.kernel)
            initrd_basename = os.path.basename(self.initrd)
            sha1sum_kernel_cmd = 'sha1sum %s' % kernel_basename
            sha1sum_kernel_output = process.run(sha1sum_kernel_cmd,
                                                ignore_status=True,
                                                verbose=DEBUG).stdout_text
            try:
                sha1sum_kernel = sha1sum_kernel_output.split()[0]
            except IndexError:
                sha1sum_kernel = ''

            sha1sum_initrd_cmd = 'sha1sum %s' % initrd_basename
            sha1sum_initrd_output = process.run(sha1sum_initrd_cmd,
                                                ignore_status=True,
                                                verbose=DEBUG).stdout_text
            try:
                sha1sum_initrd = sha1sum_initrd_output.split()[0]
            except IndexError:
                sha1sum_initrd = ''

            url_kernel = os.path.join(self.url, self.boot_path,
                                      os.path.basename(self.kernel))
            url_initrd = os.path.join(self.url, self.boot_path,
                                      os.path.basename(self.initrd))

            if not sha1sum_kernel == self.params.get('sha1sum_vmlinuz',
                                                     None):
                if os.path.isfile(self.kernel):
                    os.remove(self.kernel)
                logging.info('Downloading %s -> %s', url_kernel,
                             self.image_path)
                download.get_file(url_kernel, os.path.join(self.image_path,
                                                           os.path.basename(self.kernel)))

            if not sha1sum_initrd == self.params.get('sha1sum_initrd',
                                                     None):
                if os.path.isfile(self.initrd):
                    os.remove(self.initrd)
                logging.info('Downloading %s -> %s', url_initrd,
                             self.image_path)
                download.get_file(url_initrd, os.path.join(self.image_path,
                                                           os.path.basename(self.initrd)))

            if 'repo=cdrom' in self.kernel_params:
                # Red Hat
                self.kernel_params = re.sub('repo=[:\w\d\-/]*',
                                            'repo=%s' % self.url,
                                            self.kernel_params)
            elif 'autoyast=' in self.kernel_params:
                # SUSE
                self.kernel_params = (
                    self.kernel_params + " ip=dhcp install=" + self.url)

        elif self.vm_type == 'libvirt':
            logging.info("Not downloading vmlinuz/initrd.img from %s, "
                         "letting virt-install do it instead")

        else:
            logging.info("No action defined/needed for the current virt "
                         "type: '%s'" % self.vm_type)

    def setup_nfs(self):
        """
        Copy the vmlinuz and initrd.img from nfs.
        """
        error_context.context(
            "copying the vmlinuz and initrd.img from NFS share")

        m_cmd = ("mount %s:%s %s -o ro" %
                 (self.nfs_server, self.nfs_dir, self.nfs_mount))
        process.run(m_cmd, verbose=DEBUG)

        if not os.path.isdir(self.image_path):
            os.makedirs(self.image_path)

        try:
            kernel_fetch_cmd = ("cp %s/%s/%s %s" %
                                (self.nfs_mount, self.boot_path,
                                 os.path.basename(self.kernel), self.image_path))
            process.run(kernel_fetch_cmd, verbose=DEBUG)
            initrd_fetch_cmd = ("cp %s/%s/%s %s" %
                                (self.nfs_mount, self.boot_path,
                                 os.path.basename(self.initrd), self.image_path))
            process.run(initrd_fetch_cmd, verbose=DEBUG)
        finally:
            utils_disk.cleanup(self.nfs_mount)

        if 'autoyast=' in self.kernel_params:
            # SUSE
            self.kernel_params = (self.kernel_params + " ip=dhcp "
                                  "install=nfs://" + self.nfs_server + ":" + self.nfs_dir)

    def setup_import(self):
        self.unattended_file = None
        self.kernel_params = None

    def setup(self):
        """
        Configure the environment for unattended install.

        Uses an appropriate strategy according to each install model.
        """
        logging.info("Starting unattended install setup")
        if DEBUG:
            utils_misc.display_attributes(self)

        if self.syslog_server_enabled == 'yes':
            start_syslog_server_thread(self.syslog_server_ip,
                                       self.syslog_server_port,
                                       self.syslog_server_tcp)

        if self.medium in ["cdrom", "kernel_initrd"]:
            if self.kernel and self.initrd:
                self.setup_cdrom()
        elif self.medium == "url":
            self.setup_url()
        elif self.medium == "nfs":
            self.setup_nfs()
        elif self.medium == "import":
            self.setup_import()
        else:
            raise ValueError("Unexpected installation method %s" %
                             self.medium)

        if self.unattended_file:
            if self.floppy or self.cdrom_unattended:
                self.setup_boot_disk()
                if self.params.get("store_boot_disk") == "yes":
                    logging.info("Storing the boot disk to result directory "
                                 "for further debug")
                    src_dir = self.floppy or self.cdrom_unattended
                    dst_dir = self.results_dir
                    shutil.copy(src_dir, dst_dir)
            else:
                self.setup_unattended_http_server()

        # Update params dictionary as some of the values could be updated
        for a in self.attributes:
            self.params[a] = getattr(self, a)


def start_syslog_server_thread(address, port, tcp):
    global _syslog_server_thread
    global _syslog_server_thread_event

    syslog_server.set_default_format('[UnattendedSyslog '
                                     '(%s.%s)] %s')

    if _syslog_server_thread is None:
        _syslog_server_thread_event = threading.Event()
        _syslog_server_thread = threading.Thread(
            target=syslog_server.syslog_server,
            args=(address, port, tcp, terminate_syslog_server_thread))
        _syslog_server_thread.start()


def terminate_syslog_server_thread():
    global _syslog_server_thread, _syslog_server_thread_event

    if _syslog_server_thread is None:
        return False
    if _syslog_server_thread_event is None:
        return False

    if _syslog_server_thread_event.isSet():
        return True

    return False


def copy_file_from_nfs(src, dst, mount_point, image_name):
    logging.info("Test failed before the install process start."
                 " So just copy a good image from nfs for following tests.")
    utils_misc.mount(src, mount_point, "nfs", perm="ro")
    image_src = utils_misc.get_path(mount_point, image_name)
    shutil.copy(image_src, dst)
    utils_misc.umount(src, mount_point, "nfs")


def string_in_serial_log(serial_log_file_path, string):
    """
    Check if string appears in serial console log file.

    :param serial_log_file_path: Path to the installation serial log file.
    :param string: String to look for in serial log file.
    :return: Whether the string is found in serial log file.
    :raise: IOError: Serial console log file could not be read.
    """
    if not string:
        return

    with open(serial_log_file_path, 'r') as serial_log_file:
        serial_log_msg = serial_log_file.read()

    if string in serial_log_msg:
        logging.debug("Message read from serial console log: %s", string)
        return True
    else:
        return False


def attempt_to_log_useful_files(test, vm):
    """
    Tries to use ssh or serial_console to get logs from usual locations.
    """
    if not vm.is_alive():
        return
    base_dst_dir = os.path.join(test.outputdir, vm.name)
    sessions = []
    close = []
    try:
        try:
            session = vm.wait_for_login()
            close.append(session)
            sessions.append(session)
        except Exception as details:
            pass
        if vm.serial_console:
            sessions.append(vm.serial_console)
        for i, console in enumerate(sessions):
            failures = False
            try:
                console.cmd("true")
            except Exception as details:
                logging.info("Skipping log_useful_files #%s: %s", i, details)
                continue
            failures = False
            for path_glob in ["/*.log", "/tmp/*.log", "/var/tmp/*.log", "/var/log/messages"]:
                try:
                    status, paths = console.cmd_status_output("ls -1 %s"
                                                              % path_glob)
                    if status:
                        continue
                except Exception as details:
                    failures = True
                    continue
                for path in paths.splitlines():
                    if not path:
                        continue
                    if path.startswith(os.path.sep):
                        rel_path = path[1:]
                    else:
                        rel_path = path
                    dst = os.path.join(test.outputdir, vm.name, str(i),
                                       rel_path)
                    dst_dir = os.path.dirname(dst)
                    if not os.path.exists(dst_dir):
                        os.makedirs(dst_dir)
                    with open(dst, 'w') as fd_dst:
                        try:
                            fd_dst.write(console.cmd("cat %s" % path))
                            logging.info('Attached "%s" log file from guest '
                                         'at "%s"', path, base_dst_dir)
                        except Exception as details:
                            logging.warning("Unknown exception while "
                                            "attempt_to_log_useful_files(): "
                                            "%s", details)
                            fd_dst.write("Unknown exception while getting "
                                         "content: %s" % details)
                            failures = True
            for cmd in ["journalctl --no-pager"]:
                dst = os.path.join(test.outputdir, vm.name, str(i),
                                   astring.string_to_safe_path(cmd))
                with open(dst, 'w') as fd_dst:
                    try:
                        fd_dst.write(console.cmd(cmd))
                        logging.info('Attached "%s" cmd output at "%s"',
                                     cmd, dst)
                    except Exception as details:
                        logging.warning("Unknown exception while "
                                        "attempt_to_log_useful_files(): "
                                        "%s", details)
                        fd_dst.write("Unknown exception while getting "
                                     "cmd output: %s" % details)
                        failures = True
            if not failures:
                # All commands succeeded, no need to use next session
                break
    finally:
        for session in close:
            session.close()


@error_context.context_aware
def run(test, params, env):
    """
    Unattended install test:
    1) Starts a VM with an appropriated setup to start an unattended OS install.
    2) Wait until the install reports to the install watcher its end.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    """
    @error_context.context_aware
    def copy_images():
        error_context.base_context(
            "Copy image from NFS after installation failure")
        image_copy_on_error = params.get("image_copy_on_error", "no")
        if image_copy_on_error == "yes":
            logging.info("Running image_copy to copy pristine image from NFS.")
            try:
                error_context.context(
                    "Quit qemu-kvm before copying guest image")
                vm.monitor.quit()
            except Exception as e:
                logging.warn(e)
            from virttest import utils_test
            error_context.context("Copy image from NFS Server")
            image = params.get("images").split()[0]
            t_params = params.object_params(image)
            qemu_image = qemu_storage.QemuImg(t_params, data_dir.get_data_dir(), image)
            ver_to = utils_test.get_image_version(qemu_image)
            utils_test.run_image_copy(test, params, env)
            qemu_image = qemu_storage.QemuImg(t_params, data_dir.get_data_dir(), image)
            ver_from = utils_test.get_image_version(qemu_image)
            utils_test.update_qcow2_image_version(qemu_image, ver_from, ver_to)

    vm = env.get_vm(params["main_vm"])
    # at this stage we need vm specific parameters
    params = params.object_params(vm.name)
    src = params.get('images_good')
    vt_data_dir = data_dir.get_data_dir()
    base_dir = params.get("images_base_dir", vt_data_dir)
    dst = storage.get_image_filename(params, base_dir)
    if params.get("storage_type") == "iscsi":
        dd_cmd = "dd if=/dev/zero of=%s bs=1M count=1" % dst
        txt = "iscsi used, need destroy data in %s" % dst
        txt += " by command: %s" % dd_cmd
        logging.info(txt)
        process.system(dd_cmd)
    image_name = os.path.basename(dst)
    mount_point = params.get("dst_dir")
    if mount_point and src:
        funcatexit.register(env, params.get("type"), copy_file_from_nfs, src,
                            dst, mount_point, image_name)

    local_dir = params.get("local_dir", os.path.abspath(vt_data_dir))
    local_dir = utils_misc.get_path(vt_data_dir, local_dir)
    for media in params.get("copy_to_local", "").split():
        media_path = params.get(media)
        if not media_path:
            logging.warn("Media '%s' is not available, will not "
                         "be copied into local directory", media)
            continue
        media_name = os.path.basename(media_path)
        nfs_link = utils_misc.get_path(vt_data_dir, media_path)
        local_link = os.path.join(local_dir, media_name)
        if os.path.isfile(local_link):
            file_hash = crypto.hash_file(local_link, algorithm="md5")
            expected_hash = crypto.hash_file(nfs_link, algorithm="md5")
            if file_hash == expected_hash:
                continue
        msg = "Copy %s to %s in local host." % (media_name, local_link)
        error_context.context(msg, logging.info)
        download.get_file(nfs_link, local_link)
        params[media] = local_link

    unattended_install_config = UnattendedInstallConfig(test, params, vm)
    unattended_install_config.setup()

    # params passed explicitly, because they may have been updated by
    # unattended install config code, such as when params['url'] == auto
    vm.create(params=params)

    install_error_str = params.get("install_error_str")
    install_error_exception_str = ("Installation error reported in serial "
                                   "console log: %s" % install_error_str)
    rh_upgrade_error_str = params.get("rh_upgrade_error_str",
                                      "RH system upgrade failed")
    post_finish_str = params.get("post_finish_str",
                                 "Post set up finished")
    install_timeout = int(params.get("install_timeout", 4800))
    wait_ack = params.get("wait_no_ack", "no") == "no"

    migrate_background = params.get("migrate_background") == "yes"
    if migrate_background:
        mig_timeout = float(params.get("mig_timeout", "3600"))
        mig_protocol = params.get("migration_protocol", "tcp")

    logging.info("Waiting for installation to finish. Timeout set to %d s "
                 "(%d min)", install_timeout, install_timeout // 60)
    error_context.context("waiting for installation to finish")

    start_time = time.time()

    log_file = vm.serial_console_log
    if log_file is None:
        raise virt_vm.VMConfigMissingError(vm.name, "serial")

    logging.debug("Monitoring serial console log for completion message: %s",
                  log_file)
    serial_read_fails = 0

    # As the install process start, we may need collect information from
    # the image. So use the test case instead this simple function in the
    # following code.
    if mount_point and src:
        funcatexit.unregister(env, params.get("type"), copy_file_from_nfs,
                              src, dst, mount_point, image_name)

    send_key_timeout = int(params.get("send_key_timeout", 60))
    kickstart_reboot_bug = params.get("kickstart_reboot_bug", "no") == "yes"
    while (time.time() - start_time) < install_timeout:
        try:
            vm.verify_alive()
            if (params.get("send_key_at_install") and
                    (time.time() - start_time) < send_key_timeout):
                vm.send_key(params.get("send_key_at_install"))
        # Due to a race condition, sometimes we might get a MonitorError
        # before the VM gracefully shuts down, so let's capture MonitorErrors.
        except (virt_vm.VMDeadError, qemu_monitor.MonitorError) as e:
            if wait_ack:
                try:
                    install_error_str_found = string_in_serial_log(
                        log_file, install_error_str)
                    rh_upgrade_error_str_found = string_in_serial_log(
                        log_file, rh_upgrade_error_str)
                    post_finish_str_found = string_in_serial_log(
                        log_file, post_finish_str)
                except IOError:
                    logging.warn("Could not read final serial log file")
                else:
                    if install_error_str_found:
                        raise exceptions.TestFail(install_error_exception_str)
                    if rh_upgrade_error_str_found:
                        raise exceptions.TestFail("rh system upgrade failed, please "
                                                  "check serial log")
                    if post_finish_str_found:
                        break
                # Bug `reboot` param from the kickstart is not actually restarts
                # the VM instead it shutsoff this is temporary workaround
                # for the test to proceed
                if unattended_install_config.unattended_file:
                    with open(unattended_install_config.unattended_file) as unattended_fd:
                        reboot_in_unattended = "reboot" in unattended_fd.read()
                    if (reboot_in_unattended and kickstart_reboot_bug and not
                            vm.is_alive()):
                        try:
                            vm.start()
                            break
                        except:
                            logging.warn("Failed to start unattended install "
                                         "image workaround reboot kickstart "
                                         "parameter bug")

                # Print out the original exception before copying images.
                logging.error(e)
                copy_images()
                raise e
            else:
                break

        try:
            test.verify_background_errors()
        except Exception as e:
            attempt_to_log_useful_files(test, vm)
            copy_images()
            raise e

        if wait_ack:
            try:
                install_error_str_found = string_in_serial_log(
                    log_file, install_error_str)
                rh_upgrade_error_str_found = string_in_serial_log(
                    log_file, rh_upgrade_error_str)
                post_finish_str_found = string_in_serial_log(
                    log_file, post_finish_str)
            except IOError:
                # Only make noise after several failed reads
                serial_read_fails += 1
                if serial_read_fails > 10:
                    logging.warn(
                        "Cannot read from serial log file after %d tries",
                        serial_read_fails)
            else:
                if install_error_str_found:
                    attempt_to_log_useful_files(test, vm)
                    raise exceptions.TestFail(install_error_exception_str)
                if rh_upgrade_error_str_found:
                    raise exceptions.TestFail("rh system upgrade failed, please "
                                              "check serial log")
                if post_finish_str_found:
                    break

        # Due to libvirt automatically start guest after import
        # we only need to wait for successful login.
        if params.get("medium") == "import":
            try:
                vm.login()
                break
            except (remote.LoginError, Exception) as e:
                pass

        if migrate_background:
            vm.migrate(timeout=mig_timeout, protocol=mig_protocol)
        else:
            time.sleep(1)
    else:
        logging.warn("Timeout elapsed while waiting for install to finish ")
        attempt_to_log_useful_files(test, vm)
        copy_images()
        raise exceptions.TestFail("Timeout elapsed while waiting for install to "
                                  "finish")

    logging.debug('cleaning up threads and mounts that may be active')
    global _url_auto_content_server_thread
    global _url_auto_content_server_thread_event
    if _url_auto_content_server_thread is not None:
        _url_auto_content_server_thread_event.set()
        _url_auto_content_server_thread.join(3)
        _url_auto_content_server_thread = None
        utils_disk.cleanup(unattended_install_config.cdrom_cd1_mount)

    global _unattended_server_thread
    global _unattended_server_thread_event
    if _unattended_server_thread is not None:
        _unattended_server_thread_event.set()
        _unattended_server_thread.join(3)
        _unattended_server_thread = None

    global _syslog_server_thread
    global _syslog_server_thread_event
    if _syslog_server_thread is not None:
        _syslog_server_thread_event.set()
        _syslog_server_thread.join(3)
        _syslog_server_thread = None

    time_elapsed = time.time() - start_time
    logging.info("Guest reported successful installation after %d s (%d min)",
                 time_elapsed, time_elapsed // 60)

    if params.get("shutdown_cleanly", "yes") == "yes":
        shutdown_cleanly_timeout = int(params.get("shutdown_cleanly_timeout",
                                                  120))
        logging.info("Wait for guest to shutdown cleanly")
        if params.get("medium", "cdrom") == "import":
            vm.shutdown()
        try:
            if utils_misc.wait_for(vm.is_dead, shutdown_cleanly_timeout, 1, 1):
                logging.info("Guest managed to shutdown cleanly")
        except qemu_monitor.MonitorError as e:
            logging.warning("Guest apparently shut down, but got a "
                            "monitor error: %s", e)
