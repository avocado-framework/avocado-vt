from __future__ import division
import os
import time
import re
import logging
import glob
import threading
import shutil
import sys
import copy
import multiprocessing
try:
    from urllib.request import ProxyHandler, build_opener, install_opener
except ImportError:
    from urllib2 import ProxyHandler, build_opener, install_opener

import aexpect
from aexpect import remote

from avocado.utils import process as a_process
from avocado.utils import crypto
from avocado.utils import path
from avocado.utils import distro
from avocado.utils import cpu as cpu_utils
from avocado.core import exceptions
from avocado.utils import archive

import six
from six.moves import xrange

from virttest import error_context
from virttest import qemu_monitor
from virttest import ppm_utils
from virttest import test_setup
from virttest import virt_vm
from virttest import utils_misc
from virttest import cpu
from virttest import storage
from virttest import utils_libguestfs
from virttest import qemu_storage
from virttest import utils_libvirtd
from virttest import data_dir
from virttest import utils_net
from virttest import nfs
from virttest import libvirt_vm
from virttest import virsh
from virttest import utils_test
from virttest import utils_iptables
from virttest import utils_package
from virttest import utils_qemu
from virttest import migration
from virttest import utils_kernel_module
from virttest import arch
from virttest.utils_conn import SSHConnection
from virttest.utils_version import VersionInterval
from virttest.staging import service

try:
    import PIL.Image
except ImportError:
    logging.getLogger('avocado.app').warning(
        'No python imaging library installed. PPM image conversion to JPEG '
        'disabled. In order to enable it, please install python-imaging or the '
        'equivalent for your distro.')

_screendump_thread = None
_screendump_thread_termination_event = None

_vm_info_thread = None
_vm_info_thread_termination_event = None

_setup_manager = test_setup.SetupManager()

# default num of surplus hugepage, order to compare the values before and after
# the test when 'setup_hugepages = yes'
_pre_hugepages_surp = 0
_post_hugepages_surp = 0

#: Hooks to use for own customization stages of the virtual machines with
#: test, params. and env as supplied arguments
preprocess_vm_off_hook = None
preprocess_vm_on_hook = None
postprocess_vm_on_hook = None
postprocess_vm_off_hook = None

#: A list to handle kvm and kvm_probe modules reload with certain parameters
KVM_MODULE_HANDLERS = []

#: QEMU version regex.  Attempts to extract the simple and extended version
#: information from the output produced by `qemu -version`
QEMU_VERSION_RE = r"QEMU (?:PC )?emulator version\s([0-9]+\.[0-9]+\.[0-9]+)\s?\((.*?)\)"

THREAD_ERROR = False

LOG = logging.getLogger('avocado.' + __name__)


def _get_qemu_version(qemu_cmd):
    """
    Return normalized qemu version

    :param qemu_cmd: Path to qemu binary
    """
    version_output = a_process.run("%s -version" % qemu_cmd,
                                   verbose=False).stdout_text
    version_line = version_output.split('\n')[0]
    matches = re.match(QEMU_VERSION_RE, version_line)
    if matches:
        return "%s (%s)" % matches.groups()
    else:
        return "Unknown"


def preprocess_image(test, params, image_name, vm_process_status=None):
    """
    Preprocess a single QEMU image according to the instructions in params.

    :param test: Autotest test object.
    :param params: A dict containing image preprocessing parameters.
    :param vm_process_status: This is needed in postprocess_image. Add it here
                              only for keep it work with process_images()
    :note: Currently this function just creates an image if requested.
    """
    base_dir = params.get("images_base_dir", data_dir.get_data_dir())

    if not storage.preprocess_image_backend(base_dir, params, image_name):
        LOG.error("Backend can't be prepared correctly.")

    image_filename = storage.get_image_filename(params,
                                                base_dir)

    create_image = False
    if params.get("force_create_image") == "yes":
        create_image = True
    elif (params.get("create_image") == "yes" and not
          storage.file_exists(params, image_filename)):
        create_image = True

    if params.get("backup_image_before_testing", "no") == "yes":
        image = qemu_storage.QemuImg(params, base_dir, image_name)
        image.backup_image(params, base_dir, "backup", True, True)
    if create_image:
        if storage.file_exists(params, image_filename):
            # As rbd image can not be covered, so need remove it if we need
            # force create a new image.
            storage.file_remove(params, image_filename)
        image = qemu_storage.QemuImg(params, base_dir, image_name)
        LOG.info("Create image on %s." % image.storage_type)
        image.create(params)


def preprocess_fs_source(test, params, fs_name, vm_process_status=None):
    """
    Preprocess a single QEMU filesystem source according to the
    instructions in params.

    :param test: Autotest test object.
    :param params: A dict containing filesystem preprocessing parameters.
    :param fs_name: The filesystem name.
    :param vm_process_status: This is needed in postprocess_fs_source.
                              Add it here only for keep it work with
                              process_fs_sources()
    """
    fs_type = params.get('fs_source_type', 'mount')
    fs_source_user_config = params.get('fs_source_user_config', 'no')
    # mount: A host directory to mount in the vm.
    if fs_type == 'mount':
        if fs_source_user_config == "no":
            fs_source = params.get('fs_source_dir')
            base_dir = params.get("fs_source_base_dir", data_dir.get_data_dir())
            if not os.path.isabs(fs_source):
                fs_source = os.path.join(base_dir, fs_source)

            create_fs_source = False
            if params.get("force_create_fs_source") == "yes":
                create_fs_source = True
            elif params.get("create_fs_source") == "yes" and not os.path.exists(fs_source):
                create_fs_source = True

            if create_fs_source:
                if os.path.exists(fs_source):
                    shutil.rmtree(fs_source, ignore_errors=True)
                LOG.info("Create filesystem source %s." % fs_source)
                os.makedirs(fs_source)
    else:
        test.cancel('Unsupport the type of filesystem "%s"' % fs_type)


def preprocess_vm(test, params, env, name):
    """
    Preprocess a single VM object according to the instructions in params.
    Start the VM if requested and get a screendump.

    :param test: An Autotest test object.
    :param params: A dict containing VM preprocessing parameters.
    :param env: The environment (a dict-like object).
    :param name: The name of the VM object.
    """
    vm = env.get_vm(name)
    vm_type = params.get('vm_type')
    connect_uri = params.get('connect_uri')
    target = params.get('target')

    create_vm = False
    if not vm or not isinstance(vm, virt_vm.BaseVM.lookup_vm_class(vm_type, target)):
        create_vm = True
    elif vm_type == 'libvirt':
        connect_uri = libvirt_vm.normalize_connect_uri(connect_uri)
        if (not vm.connect_uri == connect_uri):
            create_vm = True
    else:
        pass
    if create_vm:
        # configure nested guest
        if params.get("run_nested_guest_test", "no") == "yes":
            current_level = params.get("nested_guest_level", "L1")
            max_level = params.get("nested_guest_max_level", "L1")
            if current_level != max_level:
                if params.get("vm_type") == "libvirt":
                    params["create_vm_libvirt"] = "yes"
                    nested_cmdline = params.get("virtinstall_qemu_cmdline", "")
                    # virt-install doesn't have option, so use qemu-cmdline
                    if "cap-nested-hv=on" not in nested_cmdline:
                        params["virtinstall_qemu_cmdline"] = ("%s -M %s,cap-nested-hv=on" %
                                                              (nested_cmdline,
                                                               params["machine_type"]))
                elif params.get("vm_type") == "qemu":
                    nested_cmdline = params.get("machine_type_extra_params", "")
                    if "cap-nested-hv=on" not in nested_cmdline:
                        params["machine_type_extra_params"] = ("%s,cap-nested-hv=on" %
                                                               nested_cmdline)
        vm = env.create_vm(vm_type, target, name, params, test.bindir)
        if params.get("create_vm_libvirt") == "yes" and vm_type == 'libvirt':
            params["medium"] = "import"
            vm.create(params=params)

    old_vm = copy.copy(vm)

    if vm_type == 'libvirt':
        install_test = ('unattended_install.import.import.default_install.'
                        'aio_native')
        remove_test = 'remove_guest.without_disk'
        if not vm.exists() and (params.get("type") != "unattended_install" and
                                params.get("type") != "svirt_virt_install"):
            error_msg = "Test VM %s does not exist." % name
            if name == params.get("main_vm"):
                error_msg += (" Consider adding '%s' test as the first one "
                              "and '%s' test as last one to remove the "
                              "guest after testing" %
                              (install_test, remove_test))
                raise exceptions.TestError(error_msg)
            else:
                raise exceptions.TestSkipError(error_msg)

    remove_vm = False
    if params.get("force_remove_vm") == "yes":
        remove_vm = True

    if remove_vm:
        vm.remove()

    start_vm = False
    update_virtnet = False
    gracefully_kill = params.get("kill_vm_gracefully") == "yes"

    if params.get("migration_mode"):
        start_vm = True
    elif params.get("start_vm") == "yes":
        # need to deal with libvirt VM differently than qemu
        if vm_type == 'libvirt' or vm_type == 'v2v':
            if not vm.is_alive():
                start_vm = True
        else:
            if not vm.is_alive():
                start_vm = True
            if params.get("check_vm_needs_restart", "yes") == "yes":
                if vm.needs_restart(name=name,
                                    params=params,
                                    basedir=test.bindir):
                    vm.devices = None
                    start_vm = True
                    old_vm.destroy(gracefully=gracefully_kill)
                    update_virtnet = True

    if start_vm:
        if vm_type == "libvirt" and params.get("type") != "unattended_install":
            vm.params = params
            vm.start()
        elif vm_type == "v2v":
            vm.params = params
            vm.start()
        else:
            if update_virtnet:
                vm.update_vm_id()
                vm.virtnet = utils_net.VirtNet(params, name, vm.instance)
            # Start the VM (or restart it if it's already up)
            if params.get("reuse_previous_config", "no") == "no":
                vm.create(name, params, test.bindir,
                          timeout=int(params.get("vm_create_timeout", 90)),
                          migration_mode=params.get("migration_mode"),
                          migration_fd=params.get("migration_fd"),
                          migration_exec_cmd=params.get("migration_exec_cmd_dst"))
            else:
                vm.create(timeout=int(params.get("vm_create_timeout", 90)),
                          migration_mode=params.get("migration_mode"),
                          migration_fd=params.get("migration_fd"),
                          migration_exec_cmd=params.get("migration_exec_cmd_dst"))

        # Update kernel param
        serial_login = params.get_boolean("kernel_extra_params_serial_login")
        kernel_extra_params_add = params.get("kernel_extra_params_add", "")
        kernel_extra_params_remove = params.get("kernel_extra_params_remove", "")
        if params.get("disable_pci_msi"):
            disable_pci_msi = params.get("disable_pci_msi")
            if disable_pci_msi == "yes":
                if "pci=" in kernel_extra_params_add:
                    kernel_extra_params_add = re.sub("pci=.*?\s+", "pci=nomsi ",
                                                     kernel_extra_params_add)
                else:
                    kernel_extra_params_add += " pci=nomsi"
                params["ker_remove_similar_pci"] = "yes"
            else:
                kernel_extra_params_remove += " pci=nomsi"
        vendor = cpu_utils.get_vendor() if hasattr(cpu_utils, 'get_vendor') else cpu_utils.get_cpu_vendor_name()
        if (params.get("enable_guest_iommu") and vendor == 'intel'):
            enable_guest_iommu = params.get("enable_guest_iommu")
            if enable_guest_iommu == "yes":
                kernel_extra_params_add += " intel_iommu=on"
            else:
                kernel_extra_params_remove += " intel_iommu=on"
            guest_iommu_option = params.get("guest_iommu_option")
            if guest_iommu_option:
                kernel_extra_params_add += " iommu=%s" % guest_iommu_option
        if kernel_extra_params_add or kernel_extra_params_remove:
            utils_test.update_boot_option(vm,
                                          args_added=kernel_extra_params_add,
                                          args_removed=kernel_extra_params_remove,
                                          serial_login=serial_login)

    elif not vm.is_alive():    # VM is dead and won't be started, update params
        vm.devices = None
        vm.params = params
    else:
        # Only work when parameter 'start_vm' is no and VM is alive
        if params.get("kill_vm_before_test") == "yes" and\
           params.get("start_vm") == "no":
            old_vm.destroy(gracefully=gracefully_kill)
        else:
            # VM is alive and we just need to open the serial console
            vm.create_serial_console()

    if params.get("enable_strace") == "yes":
        strace = test_setup.StraceQemu(test, params, env)
        strace.start(params.objects("strace_vms"))

    pause_vm = False

    if params.get("paused_after_start_vm") == "yes":
        pause_vm = True
        # Check the status of vm
        if (not vm.is_alive()) or (vm.is_paused()):
            pause_vm = False

    if pause_vm:
        vm.pause()

    if params.get("check_kernel_cmd_line_from_serial") == "yes":
        debug_msg = ""
        if vm.is_paused():
            debug_msg += "VM is paused."
        elif not vm.is_alive():
            debug_msg += "VM is not alive."
        elif vm.serial_console is None:
            debug_msg += "There is no serial console in VM."
        if debug_msg:
            debug_msg += " Skip the kernel command line check."
            LOG.warn(debug_msg)
            return
        cmd_line = params.get("kernel_cmd_line_str", "Command line:")
        try:
            output = vm.serial_console.read_until_output_matches(cmd_line,
                                                                 timeout=60)

            kernel_cmd_line = re.findall("%s.*" % cmd_line, output[1])[0]
            kernel_options_exist = params.get("kernel_options_exist", "")
            kernel_options_not_exist = params.get("kernel_options_not_exist",
                                                  "")

            err_msg = ""
            for kernel_option in kernel_options_exist.split():
                if kernel_option not in kernel_cmd_line:
                    err_msg += "%s not in kernel command line" % kernel_option
                    err_msg += " as expect."
            for kernel_option in kernel_options_not_exist.split():
                if kernel_option in kernel_cmd_line:
                    err_msg += "%s exist in kernel command" % kernel_option
                    err_msg += " line."
            if err_msg:
                err_msg += " Kernel command line get from"
                err_msg += " serial output is %s" % kernel_cmd_line
                raise exceptions.TestError(err_msg)

            LOG.info("Kernel command line get from serial port is as expect")
        except Exception as err:
            LOG.warn("Did not get the kernel command line from serial "
                     "port output. Skip the kernel command line check."
                     "Error is %s" % err)


def check_image(test, params, image_name, vm_process_status=None):
    """
    Check a single QEMU image according to the instructions in params.

    :param test: An Autotest test object.
    :param params: A dict containing image postprocessing parameters.
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    clone_master = params.get("clone_master", None)
    base_dir = data_dir.get_data_dir()
    image = qemu_storage.QemuImg(params, base_dir, image_name)
    check_image_flag = params.get("check_image") == "yes"

    if vm_process_status == "running" and check_image_flag:
        if params.get("skip_image_check_during_running") == "yes":
            LOG.debug("Guest is still running, skip the image check.")
            check_image_flag = False
        else:
            image_info_output = image.info(force_share=True)
            image_info = {}
            if image_info_output is not None:
                for image_info_item in image_info_output.splitlines():
                    option = image_info_item.split(":")
                    if len(option) == 2:
                        image_info[option[0].strip()] = option[1].strip()
            else:
                LOG.debug("Can not find matched image for selected guest "
                          "os, skip the image check.")
                check_image_flag = False
            if ("lazy refcounts" in image_info and
                    image_info["lazy refcounts"] == "true"):
                LOG.debug("Should not check image while guest is alive"
                          " when the image is create with lazy refcounts."
                          " Skip the image check.")
                check_image_flag = False

    # Save the potential bad image when the test is not passed.
    # It should before image check.
    if params.get("save_image", "no") == "yes":
        if vm_process_status == "dead":
            hsh = utils_misc.generate_random_string(4)
            name = ("JOB-%s-TEST-%s-%s-%s.%s" % (
                test.job.unique_id[:7], str(test.name.uid),
                image_name, hsh, image.image_format))
            image.save_image(params, name)
        else:
            LOG.error("Not saving images, VM is not stopped.")

    if check_image_flag:
        try:
            if clone_master is None:
                image.check_image(params, base_dir, force_share=True)
            elif clone_master == "yes":
                if image_name in params.get("master_images_clone").split():
                    image.check_image(params, base_dir, force_share=True)
        except Exception as e:
            # FIXME: remove it from params, maybe as an img object attr
            params["img_check_failed"] = "yes"
            if (params.get("skip_cluster_leak_warn") == "yes" and
                    "Leaked clusters" in six.text_type(e)):
                LOG.warn(six.text_type(e))
            else:
                raise e


def postprocess_image(test, params, image_name, vm_process_status=None):
    """
    Postprocess a single QEMU image according to the instructions in params.

    The main operation is to remove images if instructions are given.

    :param test: An Autotest test object.
    :param params: A dict containing image postprocessing parameters.
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    if vm_process_status == "running":
        LOG.warn("Skipped processing image '%s' since "
                 "the VM is running!" % image_name)
        return

    restored, removed = (False, False)
    clone_master = params.get("clone_master", None)
    base_dir = params.get("images_base_dir", data_dir.get_data_dir())
    image = qemu_storage.QemuImg(params, base_dir, image_name)

    if params.get("img_check_failed") == "yes":
        if params.get("restore_image_on_check_error", "no") == "yes":
            image.backup_image(params, base_dir, "restore", True)
            restored = True
    else:
        # Allow test to overwrite any pre-testing  automatic backup
        # with a new backup. i.e. assume pre-existing image/backup
        # would not be usable after this test succeeds. The best
        # example for this is when 'unattended_install' is run.
        if (params.get("backup_image_after_testing_passed", "no") == "yes" and
                params.get("test_passed") == "True"):
            image.backup_image(params, base_dir, "backup", True)

    if (not restored and params.get("restore_image", "no") == "yes"):
        image.backup_image(params, base_dir, "restore", True)
        restored = True

    if (not restored and
            params.get("restore_image_after_testing", "no") == "yes"):
        image.backup_image(params, base_dir, "restore", True)

    if params.get("img_check_failed") == "yes":
        if params.get("remove_image_on_check_error", "no") == "yes":
            cl_images = params.get("master_images_clone", "")
            if image_name in cl_images.split():
                image.remove()
                removed = True

    if (not removed and params.get("remove_image", "yes") == "yes"):
        LOG.info("Remove image on %s." % image.storage_type)
        if clone_master is None:
            image.remove()
        elif clone_master == "yes":
            if image_name in params.get("master_images_clone").split():
                image.remove()


def postprocess_fs_source(test, params, fs_name, vm_process_status=None):
    """
    Postprocess a single QEMU filesystem source according to the
    instructions in params.

    The main operation is to remove images if instructions are given.

    :param test: An Autotest test object.
    :param params: A dict containing filesystem postprocessing parameters.
    :param fs_name: The filesystem name
    :param vm_process_status: (optional) vm process status like
                              running, dead or None for no vm exist.
    """
    if vm_process_status == "running":
        LOG.warn("Skipped processing filesystem '%s' since "
                 "the VM is running!" % fs_name)
        return

    fs_type = params.get('fs_source_type', 'mount')
    if fs_type == 'mount':
        fs_source = params.get('fs_source_dir')
        base_dir = params.get("fs_source_base_dir", data_dir.get_data_dir())
        if not os.path.isabs(fs_source):
            fs_source = os.path.join(base_dir, fs_source)

        if params.get("remove_fs_source") == 'yes':
            LOG.info("Remove filesystem source %s." % fs_source)
            shutil.rmtree(fs_source, ignore_errors=True)
    else:
        LOG.info("Skipped processing filesystem '%s' since "
                 "unsupported type '%s'." % (fs_name, fs_type))


def postprocess_vm(test, params, env, name):
    """
    Postprocess a single VM object according to the instructions in params.
    Kill the VM if requested and get a screendump.

    :param test: An Autotest test object.
    :param params: A dict containing VM postprocessing parameters.
    :param env: The environment (a dict-like object).
    :param name: The name of the VM object.
    """
    vm = env.get_vm(name)
    if not vm:
        return

    if params.get("start_vm") == "yes":
        # recover the changes done to kernel params in postprocess
        serial_login = params.get_boolean("kernel_extra_params_serial_login")
        kernel_extra_params_add = params.get("kernel_extra_params_add", "")
        kernel_extra_params_remove = params.get("kernel_extra_params_remove", "")

        if params.get("enable_guest_iommu") == "yes":
            kernel_extra_params_add += " intel_iommu=on"
            guest_iommu_option = params.get("guest_iommu_option")
            if guest_iommu_option:
                kernel_extra_params_add += " iommu=%s" % guest_iommu_option

        if kernel_extra_params_add or kernel_extra_params_remove:
            # VM might be brought down after test
            if vm and not vm.is_alive():
                if params.get("vm_type") == "libvirt":
                    vm.start()
                elif params.get("vm_type") == "qemu":
                    vm.create(params=params)
                utils_test.update_boot_option(vm,
                                              args_added=kernel_extra_params_remove,
                                              args_removed=kernel_extra_params_add,
                                              serial_login=serial_login)

    # Close all SSH sessions that might be active to this VM
    for s in vm.remote_sessions[:]:
        try:
            s.close()
            vm.remote_sessions.remove(s)
        except Exception:
            pass

    if params.get("vm_extra_dump_paths") is not None:
        vm_extra_dumps = os.path.join(test.outputdir, "vm_extra_dumps")
        if not os.path.exists(vm_extra_dumps):
            os.makedirs(vm_extra_dumps)
        for dump_path in params.get("vm_extra_dump_paths").split(";"):
            try:
                vm.copy_files_from(dump_path, vm_extra_dumps)
            except:
                LOG.error("Could not copy the extra dump '%s' from the vm '%s'",
                          dump_path, vm.name)

    if params.get("kill_vm") == "yes":
        kill_vm_timeout = float(params.get("kill_vm_timeout", 0))
        if kill_vm_timeout:
            utils_misc.wait_for(vm.is_dead, kill_vm_timeout, 0, 1)
        vm.destroy(gracefully=params.get("kill_vm_gracefully") == "yes")
        if params.get("kill_vm_libvirt") == "yes" and params.get("vm_type") == "libvirt":
            vm.undefine(options=params.get('kill_vm_libvirt_options'))

    if vm.is_dead():
        if params.get('vm_type') == 'qemu':
            if vm.devices is not None:
                vm.devices.cleanup_daemons()

    if params.get("enable_strace") == "yes":
        strace = test_setup.StraceQemu(test, params, env)
        strace.stop()


def process_command(test, params, env, command, command_timeout,
                    command_noncritical):
    """
    Pre- or post- custom commands to be executed before/after a test is run

    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param env: The environment (a dict-like object).
    :param command: Command to be run.
    :param command_timeout: Timeout for command execution.
    :param command_noncritical: If True test will not fail if command fails.
    """
    # Export environment vars
    for k in params:
        os.putenv("KVM_TEST_%s" % k, str(params[k]))
    # Execute commands
    try:
        a_process.system(
            "cd %s; %s" %
            (test.bindir, command), shell=True)
    except a_process.CmdError as e:
        if command_noncritical:
            LOG.warn(e)
        else:
            raise


class _CreateImages(threading.Thread):

    """
    Thread which creates images. In case of failure it stores the exception
    in self.exc_info
    """

    def __init__(self, image_func, test, images, params, exit_event,
                 vm_process_status):
        threading.Thread.__init__(self)
        self.image_func = image_func
        self.test = test
        self.images = images
        self.params = params
        self.exit_event = exit_event
        self.exc_info = None
        self.vm_process_status = vm_process_status

    def run(self):
        try:
            _process_images_serial(self.image_func, self.test, self.images,
                                   self.params, self.exit_event,
                                   self.vm_process_status)
        except Exception:
            self.exc_info = sys.exc_info()
            self.exit_event.set()


def process_images(image_func, test, params, vm_process_status=None):
    """
    Wrapper which chooses the best way to process images.

    :param image_func: Process function
    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    images = params.objects("images")
    if len(images) > 20:    # Lets do it in parallel
        _process_images_parallel(image_func, test, params,
                                 vm_process_status=vm_process_status)
    else:
        _process_images_serial(image_func, test, images, params,
                               vm_process_status=vm_process_status)


def process_fs_sources(fs_source_func, test, params, vm_process_status=None):
    """
    Wrapper which chooses the best way to process filesystem sources.

    :param fs_source_func: Process function
    :param test: An Autotest test object.
    :param params: A dict containing all VM and filesystem parameters.
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    for filesystem in params.objects("filesystems"):
        fs_params = params.object_params(filesystem)
        fs_source_func(test, fs_params, filesystem, vm_process_status)


def _process_images_serial(image_func, test, images, params, exit_event=None,
                           vm_process_status=None):
    """
    Original process_image function, which allows custom set of images
    :param image_func: Process function
    :param test: An Autotest test object.
    :param images: List of images (usually params.objects("images"))
    :param params: A dict containing all VM and image parameters.
    :param exit_event: (optional) exit event which interrupts the processing
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    for image_name in images:
        image_params = params.object_params(image_name)
        image_func(test, image_params, image_name, vm_process_status)
        if exit_event and exit_event.is_set():
            LOG.error("Received exit_event, stop processing of images.")
            break


def _process_images_parallel(image_func, test, params, vm_process_status=None):
    """
    The same as _process_images but in parallel.
    :param image_func: Process function
    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param vm_process_status: (optional) vm process status like running, dead
                              or None for no vm exist.
    """
    images = params.objects("images")
    no_threads = min(len(images) // 5,
                     2 * multiprocessing.cpu_count())
    exit_event = threading.Event()
    threads = []
    for i in xrange(no_threads):
        imgs = images[i::no_threads]
        threads.append(_CreateImages(image_func, test, imgs, params,
                                     exit_event, vm_process_status))
        threads[-1].start()

    for thread in threads:
        thread.join()

    if exit_event.is_set():     # Failure in some thread
        LOG.error("Image processing failed:")
        for thread in threads:
            if thread.exc_info:     # Throw the first failure
                six.reraise(thread.exc_info[1], None, thread.exc_info[2])
    del exit_event
    del threads[:]


def process(test, params, env, image_func, vm_func, vm_first=False, fs_source_func=None):
    """
    Pre- or post-process VMs and images according to the instructions in params.
    Call image_func for each image listed in params and vm_func for each VM.

    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param env: The environment (a dict-like object).
    :param image_func: A function to call for each image.
    :param vm_func: A function to call for each VM.
    :param vm_first: Call vm_func first or not.
    :param fs_source_func: A function to call for each filesystem source.
    """
    def _call_vm_func():
        for vm_name in params.objects("vms"):
            vm_params = params.object_params(vm_name)
            vm_func(test, vm_params, env, vm_name)

    def _call_image_func():
        if params.get("skip_image_processing") == "yes":
            return

        if params.objects("vms"):
            for vm_name in params.objects("vms"):
                vm_params = params.object_params(vm_name)
                vm = env.get_vm(vm_name)
                unpause_vm = False
                if vm is None or vm.is_dead():
                    vm_process_status = 'dead'
                else:
                    vm_process_status = 'running'
                if vm is not None and vm.is_alive() and not vm.is_paused():
                    vm.pause()
                    unpause_vm = True
                    vm_params['skip_cluster_leak_warn'] = "yes"
                try:
                    process_images(image_func, test, vm_params,
                                   vm_process_status)
                finally:
                    if unpause_vm:
                        vm.resume()
        else:
            process_images(image_func, test, params)

    def _call_fs_source_func():
        if params.get("skip_fs_source_processing") == "yes":
            return

        if params.objects("vms"):
            for vm_name in params.objects("vms"):
                vm_params = params.object_params(vm_name)
                if not vm_params.get('filesystems'):
                    continue
                vm = env.get_vm(vm_name)
                unpause_vm = False
                if vm is None or vm.is_dead():
                    vm_process_status = 'dead'
                else:
                    vm_process_status = 'running'
                if vm is not None and vm.is_alive() and not vm.is_paused():
                    vm.pause()
                    unpause_vm = True
                try:
                    process_fs_sources(fs_source_func, test, vm_params,
                                       vm_process_status)
                finally:
                    if unpause_vm:
                        vm.resume()

    def _call_check_image_func():
        if params.get("skip_image_processing") == "yes":
            return

        if params.objects("vms"):
            for vm_name in params.objects("vms"):
                vm_params = params.object_params(vm_name)
                vm = env.get_vm(vm_name)
                unpause_vm = False
                if vm is None or vm.is_dead():
                    vm_process_status = 'dead'
                else:
                    vm_process_status = 'running'
                if vm is not None and vm.is_alive() and not vm.is_paused():
                    vm.pause()
                    unpause_vm = True
                    vm_params['skip_cluster_leak_warn'] = "yes"
                try:
                    images = params.objects("images")
                    _process_images_serial(
                        check_image, test, images, vm_params,
                        vm_process_status=vm_process_status)
                finally:
                    if unpause_vm:
                        vm.resume()
        else:
            images = params.objects("images")
            _process_images_serial(check_image, test, images, params)

    # preprocess
    if not vm_first:
        _call_image_func()
        if fs_source_func:
            _call_fs_source_func()

    _call_vm_func()

    # postprocess
    if vm_first:
        try:
            _call_check_image_func()
        finally:
            _call_image_func()
            if fs_source_func:
                _call_fs_source_func()


@error_context.context_aware
def preprocess(test, params, env):
    """
    Preprocess all VMs and images according to the instructions in params.
    Also, collect some host information, such as the KVM version.

    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param env: The environment (a dict-like object).
    """
    error_context.context("preprocessing")

    # Run this hook before any network setup stage and vm creation.
    if callable(preprocess_vm_off_hook):
        preprocess_vm_off_hook(test, params, env)  # pylint: disable=E1102

    # Check if code coverage for qemu is enabled and
    # if coverage reset is enabled too, reset coverage report
    gcov_qemu = params.get("gcov_qemu", "no") == "yes"
    gcov_qemu_reset = params.get("gcov_qemu_reset", "no") == "yes"
    if gcov_qemu and gcov_qemu_reset:
        qemu_builddir = os.path.join(test.bindir, "build", "qemu")
        qemu_bin = os.path.join(test.bindir, "bin", "qemu")
        if os.path.isdir(qemu_builddir) and os.path.isfile(qemu_bin):
            os.chdir(qemu_builddir)
            # Looks like libvirt process does not have permissions to write to
            # coverage files, hence give write for all files in qemu source
            reset_cmd = 'make clean-coverage;%s -version;' % qemu_bin
            reset_cmd += 'find %s -name "*.gcda" -exec chmod a=rwx {} \;' % qemu_builddir
            a_process.system(reset_cmd, shell=True)

    # Check host for any errors to start with and just report and
    # clear it off, so that we do not get the false test failures.
    if params.get("verify_host_dmesg", "yes") == "yes":
        utils_misc.verify_dmesg(ignore_result=True)

    # For KVM to work in Power8 and Power9(compat guests)(<DD2.2)
    # systems we need to have SMT=off and it needs to be
    # done as root, here we do a check whether
    # we satisfy that condition, if not try to make it off
    # otherwise throw TestError with respective error message
    cpu_family = "unknown"
    try:
        cpu_family = cpu_utils.get_family() if hasattr(cpu_utils, 'get_family') else cpu_utils.get_cpu_arch()
    except Exception:
        LOG.warning("Could not get host cpu family")
    migration_setup = params.get("migration_setup", "no") == "yes"
    if cpu_family is not None and "power" in cpu_family:
        pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
        pvr = float(a_process.system_output(pvr_cmd, shell=True).strip())
        power9_compat = "yes" == params.get("power9_compat", "no")

        if "power8" in cpu_family:
            test_setup.switch_smt(state="off")
        elif "power9" in cpu_family and power9_compat and pvr < 2.2:
            test_setup.switch_indep_threads_mode(state="N")
            test_setup.switch_smt(state="off")

        # Perform the above configuration in remote Power8 and Power9 hosts
        if migration_setup:
            power9_compat_remote = "yes" == params.get("power9_compat_remote", "no")
            cpu_cmd = "grep cpu /proc/cpuinfo | awk '{print $3}' | head -n 1"
            remote_host = {'server_ip': params.get("remote_ip"),
                           'server_pwd': params.get("remote_pwd"),
                           'server_user': params.get("remote_user", "root")}
            server_session = test_setup.remote_session(remote_host)
            cmd_output = server_session.cmd_status_output(cpu_cmd)
            if (cmd_output[0] == 0):
                remote_cpu = cmd_output[1].strip().lower()
            cmd_output = server_session.cmd_status_output(pvr_cmd)
            if (cmd_output[0] == 0):
                remote_pvr = float(cmd_output[1].strip())
            server_session.close()
            if "power8" in remote_cpu:
                test_setup.switch_smt(state="off", params=params)
            elif "power9" in remote_cpu and power9_compat_remote and remote_pvr < 2.2:
                test_setup.switch_indep_threads_mode(state="N", params=params)
                test_setup.switch_smt(state="off", params=params)
            if pvr != remote_pvr:
                LOG.warning("Source and destinations system PVR "
                            "does not match\n PVR:\nSource: %s"
                            "\nDestination: %s", pvr, remote_pvr)
    # First, let's verify if this test does require root or not. If it
    # does and the test suite is running as a regular user, we shall just
    # throw a TestSkipError exception, which will skip the test.
    if params.get('requires_root', 'no') == 'yes':
        utils_misc.verify_running_as_root()

    # throw a TestSkipError exception if command requested by test is not
    # installed.
    if params.get("cmds_installed_host"):
        for cmd in params.get("cmds_installed_host").split():
            try:
                path.find_command(cmd)
            except path.CmdNotFoundError as msg:
                raise exceptions.TestSkipError(msg.message)

    _setup_manager.initialize(test, params, env)
    _setup_manager.register(test_setup.UlimitConfig)
    _setup_manager.do_setup()

    # enable network proxies setting in urllib2
    if params.get("network_proxies"):
        proxies = {}
        for proxy in re.split(r"[,;]\s*", params["network_proxies"]):
            proxy = dict([re.split(r"_proxy:\s*", proxy)])
            proxies.update(proxy)
        handler = ProxyHandler(proxies)
        opener = build_opener(handler)
        install_opener(opener)

    vm_type = params.get('vm_type')

    if vm_type == 'libvirt':
        if params.get("enable_libvirtd_debug_log", "yes") == "yes":
            # By default log the info level
            log_level = params.get("libvirtd_debug_level", "2")
            log_file = params.get("libvirtd_debug_file", "")
            libvirtd_debug_log = test_setup.LibvirtdDebugLog(test,
                                                             log_level,
                                                             log_file)
            libvirtd_debug_log.enable()

    setup_pb = False
    ovs_pb = False
    for nic in params.get('nics', "").split():
        nic_params = params.object_params(nic)
        if nic_params.get('netdst') == 'private':
            setup_pb = True
            params_pb = nic_params
            params['netdst_%s' % nic] = nic_params.get("priv_brname", 'atbr0')
            if nic_params.get("priv_br_type") == "openvswitch":
                ovs_pb = True

    if setup_pb:
        if ovs_pb:
            brcfg = test_setup.PrivateOvsBridgeConfig(params_pb)
        else:
            brcfg = test_setup.PrivateBridgeConfig(params_pb)
        brcfg.setup()

    base_dir = data_dir.get_data_dir()
    if params.get("storage_type") == "iscsi":
        iscsidev = qemu_storage.Iscsidev(params, base_dir, "iscsi")
        params["image_name"] = iscsidev.setup()
        params["image_raw_device"] = "yes"

    if params.get("storage_type") == "lvm":
        lvmdev = qemu_storage.LVMdev(params, base_dir, "lvm")
        params["image_name"] = lvmdev.setup()
        params["image_raw_device"] = "yes"
        env.register_lvmdev("lvm_%s" % params["main_vm"], lvmdev)

    if params.get("storage_type") == "nfs":
        selinux_local = params.get('set_sebool_local', 'yes') == "yes"
        selinux_remote = params.get('set_sebool_remote', 'no') == "yes"
        image_nfs = nfs.Nfs(params)
        image_nfs.setup()
        if migration_setup:
            # Configure NFS client on remote host
            params["server_ip"] = params.get("remote_ip")
            params["server_user"] = params.get("remote_user", "root")
            params["server_pwd"] = params.get("remote_pwd")
            params["client_ip"] = params.get("local_ip")
            params["client_user"] = params.get("local_user", "root")
            params["client_pwd"] = params.get("local_pwd")
            params["nfs_client_ip"] = params.get("remote_ip")
            params["nfs_server_ip"] = params.get("local_ip")
            nfs_client = nfs.NFSClient(params)
            nfs_client.setup()
        distro_details = distro.detect()
        if distro_details.name.upper() != 'UBUNTU':
            if selinux_local:
                params['set_sebool_local'] = "yes"
                params['local_boolean_varible'] = "virt_use_nfs"
                params['local_boolean_value'] = "on"
        # configure selinux on remote host to permit migration
        if migration_setup:
            cmd = "cat /etc/os-release | grep '^PRETTY_NAME'"
            session = test_setup.remote_session(params)
            if 'UBUNTU' not in str(session.cmd_output(cmd)).upper():
                params["set_sebool_remote"] = "yes"
                params["remote_boolean_varible"] = "virt_use_nfs"
                params["remote_boolean_value"] = "on"
        if selinux_local or selinux_remote:
            seLinuxBool = utils_misc.SELinuxBoolean(params)
            seLinuxBool.setup()

        image_name_only = os.path.basename(params["image_name"])
        for image_name in params.objects("images"):
            name_tag = "image_name_%s" % image_name
            if params.get(name_tag):
                image_name_only = os.path.basename(params[name_tag])
                params[name_tag] = os.path.join(image_nfs.mount_dir,
                                                image_name_only)

    firewalld_service = params.get('firewalld_service')
    if firewalld_service == 'disable':
        firewalld = service.Service("firewalld")
        if firewalld.status():
            firewalld.stop()
            if firewalld.status():
                test.log.warning('Failed to stop firewalld')
    else:
        if firewalld_service == 'enable':
            firewalld = service.Service("firewalld")
            if not firewalld.status():
                firewalld.start()
                if not firewalld.status():
                    test.log.warning('Failed to start firewalld')

        if distro.detect().name == 'Ubuntu':
            params['firewalld_dhcp_workaround'] = "no"

        # Workaround know issue where firewall blocks dhcp from guest
        # through virbr0
        if params.get('firewalld_dhcp_workaround', "no") == "yes":
            firewall_cmd = utils_iptables.Firewall_cmd()
            if not firewall_cmd.add_service('dhcp', permanent=True):
                test.log.warning('Failed to add dhcp service to be permitted')

    # Start ip sniffing if it isn't already running
    # The fact it has to be started here is so that the test params
    # have to be honored.
    env.start_ip_sniffing(params)

    # Add migrate_vms to vms
    migrate_vms = params.objects("migrate_vms")
    if migrate_vms:
        vms = list(set(params.objects("vms") + migrate_vms))
        params["vms"] = ' '.join(vms)

    # Permit iptables to permit 49152-49216 ports to libvirt for
    # migration and if arch is ppc with power8 then switch off smt
    # will be taken care in remote machine for migration to succeed
    if migration_setup:
        dest_uri = libvirt_vm.complete_uri(params.get("server_ip",
                                                      params.get("remote_ip")))
        migrate_setup = migration.MigrationTest()
        migrate_setup.migrate_pre_setup(dest_uri, params)
        # Map hostname and IP address of the hosts to avoid virsh
        # to error out of resolving
        hostname_ip = {str(virsh.hostname()): params['local_ip']}
        session = test_setup.remote_session(params)
        _, remote_hostname = session.cmd_status_output('hostname')
        hostname_ip[str(remote_hostname.strip())] = params['remote_ip']
        if not utils_net.map_hostname_ipaddress(hostname_ip):
            test.cancel("Failed to map hostname and ipaddress of source host")
        if not utils_net.map_hostname_ipaddress(hostname_ip, session=session):
            session.close()
            test.cancel("Failed to map hostname and ipaddress of target host")
        session.close()
        if params.get("setup_ssh") == "yes":
            ssh_conn_obj = SSHConnection(params)
            ssh_conn_obj.conn_setup()
            ssh_conn_obj.auto_recover = True
            params.update({"ssh_conn_obj": ssh_conn_obj})

    # Destroy and remove VMs that are no longer needed in the environment or
    # leave them untouched if they have to be disregarded only for this test
    requested_vms = params.objects("vms")
    keep_unrequested_vms = params.get_boolean("keep_env_vms", False)
    for key in list(env.keys()):
        vm = env[key]
        if not isinstance(vm, virt_vm.BaseVM):
            continue
        if vm.name not in requested_vms:
            if keep_unrequested_vms:
                LOG.debug("The vm %s is registered in the env and disregarded "
                          "in the current test", vm.name)
            else:
                vm.destroy()
                del env[key]

    global KVM_MODULE_HANDLERS
    kvm_modules = arch.get_kvm_module_list()
    for module in reversed(kvm_modules):
        param_prefix = module if module == "kvm" else "kvm_probe"
        module_force_load = params.get_boolean("%s_module_force_load"
                                               % param_prefix)
        module_parameters = params.get("%s_module_parameters" % param_prefix,
                                       "")
        module_handler = utils_kernel_module.reload(module, module_force_load,
                                                    module_parameters)
        if module_handler is not None:
            KVM_MODULE_HANDLERS.append(module_handler)

    version_info = {}
    # Get the KVM kernel module version
    if os.path.exists("/dev/kvm"):
        kvm_version = os.uname()[2]
    else:
        warning_msg = "KVM module not loaded"
        if params.get("enable_kvm", "yes") == "yes":
            test.cancel(warning_msg)
        LOG.warning(warning_msg)
        kvm_version = "Unknown"

    LOG.debug("KVM version: %s" % kvm_version)
    version_info["kvm_version"] = str(kvm_version)

    # Checking required kernel, if not satisfied, cancel test
    if params.get("required_kernel"):
        required_kernel = params.get("required_kernel")
        LOG.info("Test requires kernel version: %s" % required_kernel)
        match = re.search(r'[0-9]+\.[0-9]+\.[0-9]+(\-[0-9]+)?', kvm_version)
        if match is None:
            test.cancel("Can not get host kernel version.")
        host_kernel = match.group(0)
        if host_kernel not in VersionInterval(required_kernel):
            test.cancel("Got host kernel version:%s, which is not in %s" %
                        (host_kernel, required_kernel))

    # Get the KVM userspace version
    kvm_userspace_ver_cmd = params.get("kvm_userspace_ver_cmd", "")

    if kvm_userspace_ver_cmd:
        try:
            kvm_userspace_version = a_process.run(
                kvm_userspace_ver_cmd, shell=True).stdout_text.strip()
        except a_process.CmdError:
            kvm_userspace_version = "Unknown"
    else:
        qemu_path = utils_misc.get_qemu_binary(params)
        kvm_userspace_version = _get_qemu_version(qemu_path)
        qemu_dst_path = utils_misc.get_qemu_dst_binary(params)
        if qemu_dst_path and qemu_dst_path != qemu_path:
            LOG.debug("KVM userspace dst version(qemu): %s",
                      _get_qemu_version(qemu_dst_path))

    LOG.debug("KVM userspace version(qemu): %s", kvm_userspace_version)
    version_info["qemu_version"] = str(kvm_userspace_version)

    # Checking required qemu, if not satisfied, cancel test
    if params.get("required_qemu"):
        required_qemu = params.get("required_qemu")
        LOG.info("Test requires qemu version: %s" % required_qemu)
        match = re.search(r'[0-9]+\.[0-9]+\.[0-9]+(\-[0-9]+)?',
                          kvm_userspace_version)
        if match is None:
            test.cancel("Can not get host qemu version.")
        host_qemu = match.group(0)
        if host_qemu not in VersionInterval(required_qemu):
            test.cancel("Got host qemu version:%s, which is not in %s" %
                        (host_qemu, required_qemu))

    # Get the Libvirt version
    if vm_type == "libvirt":
        libvirt_ver_cmd = params.get("libvirt_ver_cmd", "libvirtd -V|awk -F' ' '{print $3}'")
        try:
            libvirt_version = a_process.run(
                libvirt_ver_cmd, shell=True).stdout_text.strip()
        except a_process.CmdError:
            libvirt_version = "Unknown"
        version_info["libvirt_version"] = str(libvirt_version)
        LOG.debug("KVM userspace version(libvirt): %s" % libvirt_version)

    # Write it as a keyval
    test.write_test_keyval(version_info)

    libvirtd_inst = None

    # If guest is configured to be backed by hugepages, setup hugepages in host
    if params.get("hugepage") == "yes":
        params["setup_hugepages"] = "yes"

    if params.get("setup_hugepages") == "yes":
        global _pre_hugepages_surp
        h = test_setup.HugePageConfig(params)
        _pre_hugepages_surp = h.ext_hugepages_surp
        suggest_mem = h.setup()
        if suggest_mem is not None:
            params['mem'] = suggest_mem
        if not params.get("hugepage_path"):
            params["hugepage_path"] = h.hugepage_path
        if vm_type == "libvirt":
            if libvirtd_inst is None:
                libvirtd_inst = utils_libvirtd.Libvirtd()
            libvirtd_inst.restart()

    if params.get("setup_thp") == "yes":
        thp = test_setup.TransparentHugePageConfig(test, params)
        thp.setup()

    if params.get("setup_ksm") == "yes":
        ksm = test_setup.KSMConfig(params, env)
        ksm.setup(env)

    if params.get("setup_egd") == "yes":
        egd = test_setup.EGDConfig(params, env)
        egd.setup()

    if vm_type == "libvirt":
        connect_uri = params.get("connect_uri")
        connect_uri = libvirt_vm.normalize_connect_uri(connect_uri)
        # Set the LIBVIRT_DEFAULT_URI to make virsh command
        # work on connect_uri as default behavior.
        os.environ['LIBVIRT_DEFAULT_URI'] = connect_uri
        if params.get("setup_libvirt_polkit") == "yes":
            pol = test_setup.LibvirtPolkitConfig(params)
            try:
                pol.setup()
            except test_setup.PolkitWriteLibvirtdConfigError as e:
                LOG.error(str(e))
            except test_setup.PolkitRulesSetupError as e:
                LOG.error(str(e))
            except Exception as e:
                LOG.error("Unexpected error: '%s'" % str(e))

    # Execute any pre_commands
    if params.get("pre_command"):
        process_command(test, params, env, params.get("pre_command"),
                        int(params.get("pre_command_timeout", "600")),
                        params.get("pre_command_noncritical") == "yes")

    # Sysprep the master image if requested, to customize image before cloning
    if params.get("sysprep_required", "no") == "yes":
        image_filename = storage.get_image_filename(params, base_dir)
        sysprep_options = params.get("sysprep_options", "--operations machine-id")
        # backup the original master image before customization
        LOG.info("Backup the master image before sysprep")
        image_obj = qemu_storage.QemuImg(params, base_dir, image_filename)
        image_obj.backup_image(params, base_dir, "backup", True, True)
        LOG.info("Syspreping the image as requested before cloning.")
        try:
            utils_libguestfs.virt_sysprep_cmd(
                image_filename, options=sysprep_options, ignore_status=False)
        except utils_libguestfs.LibguestfsCmdError as detail:
            # when virt-sysprep fails the original master image is unchanged.
            # We can remove backup image, so that test would not spend much time
            # in restoring disk back during postprocess.
            image_obj.rm_backup_image()
            test.error("Sysprep failed: %s" % detail)

    # Clone master image from vms.
    if params.get("master_images_clone"):
        for vm_name in params.get("vms").split():
            vm = env.get_vm(vm_name)
            if vm:
                vm.destroy()
                env.unregister_vm(vm_name)

            vm_params = params.object_params(vm_name)
            for image in vm_params.get("master_images_clone").split():
                image_obj = qemu_storage.QemuImg(vm_params, base_dir, image)
                image_obj.clone_image(vm_params, vm_name, image, base_dir)
            params["image_name_%s" % vm_name] = vm_params["image_name_%s" % vm_name]
            params["image_name_%s_%s" % (image, vm_name)] = vm_params["image_name_%s_%s" % (image, vm_name)]

    if params.get("auto_cpu_model") == "yes" and vm_type == "qemu":
        policy_map = {"libvirt_host_model": cpu.get_cpu_info_from_virsh,
                      "virttest": cpu.get_qemu_best_cpu_info}
        auto_cpu_policy = params.get("auto_cpu_policy", "virttest").split()
        for policy in auto_cpu_policy:
            try:
                cpu_info = policy_map[policy](params)
                if cpu_info:
                    break
            except Exception as err:
                LOG.error("Failed to get cpu info with policy %s: %s"
                          % (policy, err))
                continue
        else:
            raise exceptions.TestCancel("Failed to get cpu info with "
                                        "policy %s" % auto_cpu_policy)
        params["cpu_model"] = cpu_info["model"]
        if cpu_info["flags"]:
            cpu_flags = params.get("cpu_model_flags")
            params["cpu_model_flags"] = cpu.recombine_qemu_cpu_flags(cpu_info["flags"],
                                                                     cpu_flags)

    if vm_type == "qemu":
        qemu_path = utils_misc.get_qemu_binary(params)
        if (utils_qemu.has_device_category(qemu_path, "CPU")
                and params.get("cpu_driver") is None):
            cpu_model = params.get("cpu_model")
            if cpu_model:
                search_pattern = r"%s-\w+-cpu" % cpu_model
                cpu_driver = utils_qemu.find_supported_devices(qemu_path,
                                                               search_pattern,
                                                               "CPU")
                if cpu_driver:
                    env["cpu_driver"] = cpu_driver[0]
                    params["cpu_driver"] = env.get("cpu_driver")

    # Preprocess all VMs and images
    if params.get("not_preprocess", "no") == "no":
        process(test, params, env, preprocess_image, preprocess_vm,
                fs_source_func=preprocess_fs_source)

    # Start the screendump thread
    if params.get("take_regular_screendumps") == "yes":
        global _screendump_thread, _screendump_thread_termination_event
        _screendump_thread_termination_event = threading.Event()
        _screendump_thread = threading.Thread(target=_take_screendumps,
                                              name='ScreenDump',
                                              args=(test, params, env))
        _screendump_thread.start()

    # Start the register query thread
    if params.get("store_vm_info") == "yes":
        global _vm_info_thread, _vm_info_thread_termination_event
        _vm_info_thread_termination_event = threading.Event()
        _vm_info_thread = threading.Thread(target=_store_vm_info,
                                           name='VmMonInfo',
                                           args=(test, params, env))
        _vm_info_thread.start()

    # start test in nested guest
    if params.get("run_nested_guest_test", "no") == "yes":
        def thread_func(obj):
            """
            Thread method to trigger nested VM test

            :param obj: AvocadoGuest Object of the VM
            """
            global THREAD_ERROR
            try:
                obj.run_avocado()
            except Exception as info:
                LOG.error(info)
                THREAD_ERROR = True
        nest_params = params.copy()
        nested_params = eval(nest_params.get("nested_params", "{}"))
        # update the current level's param with nested params sent
        # from previous level
        nest_params.update(nested_params)
        current_level = nest_params.get("nested_guest_level", "L1")
        max_level = nest_params.get("nested_guest_max_level", "L1")
        if int(current_level.lstrip("L")) < int(max_level.lstrip("L")):
            threads = []
            nest_timeout = int(nest_params.get("nested_guest_timeout", "3600"))
            install_type = nest_params.get("avocado_guest_install_type", "git")
            nest_vms = env.get_all_vms()
            # Have buffer memory 1G for VMs to work seamlessly
            nest_memory = (int(nest_params.get("mem")) // len(nest_vms)) - 1024
            if nest_memory < 512:
                raise exceptions.TestCancel("Memory is not sufficient for "
                                            "VMs to boot and perform nested "
                                            "virtualization tests")
            # set memory for the nested VM
            nest_params["vt_extra_params"] = "mem=\"%s\"" % nest_memory
            # pass the params current level to next level
            nest_params["vt_extra_params"] += " nested_params=\"%s\"" % nested_params
            # update the current_level for next_level guest
            nest_params["vt_extra_params"] += (" nested_guest_level=\"L%s\"" %
                                               (int(current_level.lstrip("L")) +
                                                1))
            # persist the max_level in every level of guest
            nest_params["vt_extra_params"] += (" nested_guest_max_level=\"L%s\"" %
                                               int(max_level.lstrip("L")))
            nest_params["vt_extra_params"] += " run_nested_guest_test=\"yes\""
            LOG.debug("Test is running in Guest level: %s", current_level)
            for vm in nest_vms:
                # params with nested level specific configuration
                new_params = nest_params.object_params(current_level)
                # params with VM name specific in that particular level
                new_params = new_params.object_params(vm.name)
                testlist = [new_params.get("avocado_guest_vt_test",
                                           "boot")]
                avocadotestargs = new_params.get("avocado_guest_add_args", "")
                obj = utils_test.AvocadoGuest(vm, new_params, test, testlist,
                                              testrepo='',
                                              timeout=nest_timeout,
                                              installtype=install_type,
                                              avocado_vt=True,
                                              reinstall=False,
                                              add_args=avocadotestargs)
                thread = threading.Thread(target=thread_func, args=(obj,))
                threads.append(thread)
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            if THREAD_ERROR:
                raise exceptions.TestFail("Test inside nested guest "
                                          "reported failure")

    # Run this hook after any network setup stage and vm creation.
    if callable(preprocess_vm_on_hook):
        preprocess_vm_on_hook(test, params, env)  # pylint: disable=E1102

    return params


@error_context.context_aware
def postprocess(test, params, env):
    """
    Postprocess all VMs and images according to the instructions in params.

    :param test: An Autotest test object.
    :param params: Dict containing all VM and image parameters.
    :param env: The environment (a dict-like object).
    """
    error_context.context("postprocessing")
    err = ""

    # Run this hook before closing the connections to the qemu monitors
    # and possibly destroying the vms.
    if callable(postprocess_vm_on_hook):
        try:
            postprocess_vm_on_hook(test, params, env)  # pylint: disable=E1102
        except Exception as details:
            err += "\nPostprocessing living vm hook: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    migration_setup = params.get("migration_setup", "no") == "yes"
    if params.get("verify_guest_dmesg", "yes") == "yes" and params.get("start_vm", "no") == "yes":
        guest_dmesg_log_file = params.get("guest_dmesg_logfile", "guest_dmesg.log")
        guest_dmesg_log_file = utils_misc.get_path(test.debugdir, guest_dmesg_log_file)
        living_vms = [vm for vm in env.get_all_vms() if (vm.is_alive() and not vm.is_paused())]
        for vm in living_vms:
            if params.get("guest_dmesg_dump_console") == "yes":
                guest_dmesg_log_file = None
            else:
                guest_dmesg_log_file += ".%s" % vm.name
            try:
                vm.verify_dmesg(dmesg_log_file=guest_dmesg_log_file)
            except Exception as details:
                err += ("\n: Guest %s dmesg verification failed: %s"
                        % (vm.name, details))

    base_dir = data_dir.get_data_dir()
    # if sysprep was requested in preprocess then restore back the original image
    if params.get("sysprep_required", "no") == "yes":
        LOG.info("Restoring the original master image.")
        image_filename = storage.get_image_filename(params, base_dir)
        image_obj = qemu_storage.QemuImg(params, base_dir, image_filename)
        image_obj.backup_image(params, base_dir, "restore", True)
        image_obj.rm_backup_image()

    # collect sosreport of guests during postprocess if enabled
    if params.get("enable_guest_sosreport", "no") == "yes":
        living_vms = [vm for vm in env.get_all_vms() if (vm.is_alive() and not vm.is_paused())]
        for vm in living_vms:
            sosreport_path = vm.sosreport()
            LOG.info("Sosreport for guest: %s", sosreport_path)

    # Collect code coverage report for qemu if enabled
    if params.get("gcov_qemu", "no") == "yes":
        qemu_builddir = os.path.join(test.bindir, "build", "qemu")
        if os.path.isdir(qemu_builddir) and utils_package.package_install("gcovr"):
            gcov_qemu_dir = utils_misc.get_path(test.debugdir, "gcov_qemu")
            os.makedirs(gcov_qemu_dir)
            os.chdir(qemu_builddir)
            collect_cmd_opts = params.get("gcov_qemu_collect_cmd_opts", "--html")
            online_count = cpu_utils.online_count() if hasattr(cpu_utils, 'online_count') else cpu_utils.online_cpus_count()
            collect_cmd = "gcovr -j %s -o %s -s %s ." % (online_count,
                                                         os.path.join(gcov_qemu_dir, "gcov.html"),
                                                         collect_cmd_opts)
            a_process.system(collect_cmd, shell=True)
            if params.get("gcov_qemu_compress", "no") == "yes":
                os.chdir(test.debugdir)
                archive.compress("gcov_qemu.tar.gz", gcov_qemu_dir)
                shutil.rmtree(gcov_qemu_dir, ignore_errors=True)
        else:
            LOG.warning("Check either qemu build directory availablilty"
                        " or install gcovr package for qemu coverage report")
    # Postprocess all VMs and images
    try:
        process(test, params, env, postprocess_image,
                postprocess_vm, True, postprocess_fs_source)
    except Exception as details:
        err += "\nPostprocess: %s" % str(details).replace('\\n', '\n  ')
        LOG.error(details)

    # Terminate the screendump thread
    global _screendump_thread, _screendump_thread_termination_event
    if _screendump_thread is not None:
        _screendump_thread_termination_event.set()
        _screendump_thread.join(10)
        _screendump_thread = None

    # Encode an HTML 5 compatible video from the screenshots produced
    dir_rex = "(screendump\S*_[0-9]+_iter%s)" % test.iteration
    for screendump_dir in re.findall(dir_rex, str(os.listdir(test.debugdir))):
        screendump_dir = os.path.join(test.debugdir, screendump_dir)
        if (params.get("encode_video_files", "yes") == "yes" and
                glob.glob("%s/*" % screendump_dir)):
            try:
                # Loading video_maker at the top level is causing
                # gst to be loaded at the top level, generating
                # side effects in the loader plugins. So, let's
                # move the import to the precise place where it's
                # needed.
                from . import video_maker
                video = video_maker.get_video_maker_klass()
                if ((video.has_element('vp8enc') and
                     video.has_element('webmmux'))):
                    video_file = "%s.webm" % screendump_dir
                else:
                    video_file = "%s.ogg" % screendump_dir
                video_file = os.path.join(test.debugdir, video_file)
                LOG.debug("Encoding video file %s", video_file)
                video.encode(screendump_dir, video_file)

            except Exception as detail:
                LOG.info(
                    "Video creation failed for %s: %s", screendump_dir, detail)

    # Warn about corrupt PPM files
    screendump_temp_dir = params.get("screendump_temp_dir")
    if screendump_temp_dir:
        screendump_temp_dir = utils_misc.get_path(
            test.bindir, screendump_temp_dir)
    else:
        screendump_temp_dir = test.debugdir
    ppm_file_rex = "*_iter%s.ppm" % test.iteration
    for f in glob.glob(os.path.join(screendump_temp_dir, ppm_file_rex)):
        if not ppm_utils.image_verify_ppm_file(f):
            LOG.warn("Found corrupt PPM file: %s", f)

    # Should we convert PPM files to PNG format?
    if params.get("convert_ppm_files_to_png", "no") == "yes":
        try:
            for f in glob.glob(
                    os.path.join(screendump_temp_dir, ppm_file_rex)):
                if ppm_utils.image_verify_ppm_file(f):
                    new_path = f.replace(".ppm", ".png")
                    image = PIL.Image.open(f)
                    image.save(new_path, format='PNG')
        except NameError:
            pass

    # Should we keep the PPM files?
    if params.get("keep_ppm_files", "no") != "yes":
        for f in glob.glob(os.path.join(screendump_temp_dir, ppm_file_rex)):
            os.unlink(f)

    # Should we keep the screendump dirs?
    if params.get("keep_screendumps", "no") != "yes":
        for d in glob.glob(os.path.join(test.debugdir, "screendumps_*")):
            if os.path.isdir(d) and not os.path.islink(d):
                shutil.rmtree(d, ignore_errors=True)

    # Should we keep the video files?
    if params.get("keep_video_files", "yes") != "yes":
        for f in (glob.glob(os.path.join(test.debugdir, '*.ogg')) +
                  glob.glob(os.path.join(test.debugdir, '*.webm'))):
            os.unlink(f)

    # Terminate the register query thread
    global _vm_info_thread, _vm_info_thread_termination_event
    if _vm_info_thread is not None:
        _vm_info_thread_termination_event.set()
        _vm_info_thread.join(10)
        _vm_info_thread = None

    # Kill all unresponsive VMs
    if params.get("kill_unresponsive_vms") == "yes":
        for vm in env.get_all_vms():
            if vm.is_dead() or vm.is_paused():
                continue
            try:
                # Test may be fast, guest could still be booting
                if len(vm.virtnet) > 0:
                    session = vm.wait_for_login(timeout=vm.LOGIN_WAIT_TIMEOUT)
                    session.close()
                else:
                    session = vm.wait_for_serial_login(
                        timeout=vm.LOGIN_WAIT_TIMEOUT)
                    session.close()
            except (remote.LoginError, virt_vm.VMError, IndexError) as e:
                LOG.warn(e)
                vm.destroy(gracefully=False)

    # Kill VMs with deleted disks
    for vm in env.get_all_vms():
        destroy = False
        vm_params = params.object_params(vm.name)
        for image in vm_params.objects('images'):
            if params.object_params(image).get('remove_image') == 'yes':
                destroy = True
        if destroy and not vm.is_dead():
            LOG.debug(
                'Image of VM %s was removed, destroying it.',
                vm.name)
            vm.destroy()

    # Terminate the ip sniffer thread
    env.stop_ip_sniffing()

    # Kill all aexpect tail threads
    aexpect.kill_tail_threads()

    # collect sosreport of host/remote host during postprocess if enabled
    if params.get("enable_host_sosreport", "no") == "yes":
        sosreport_path = utils_misc.get_sosreport(sosreport_name="host")
        LOG.info("Sosreport for host: %s", sosreport_path)
    if params.get("enable_remote_host_sosreport", "no") == "yes":
        remote_params = {'server_ip': params['remote_ip'], 'server_pwd': params['remote_pwd']}
        remote_params['server_user'] = params['remote_user']
        session = test_setup.remote_session(remote_params)
        sosreport_path = utils_misc.get_sosreport(session=session,
                                                  remote_ip=params['remote_ip'],
                                                  remote_pwd=params['remote_pwd'],
                                                  remote_user=params['remote_user'],
                                                  sosreport_name="host_remote")
        LOG.info("Sosreport for remote host: %s", sosreport_path)
    living_vms = [vm for vm in env.get_all_vms() if vm.is_alive()]
    # Close all monitor socket connections of living vm.
    if not params.get_boolean("keep_env_vms", False):
        for vm in living_vms:
            if hasattr(vm, "monitors"):
                for m in vm.monitors:
                    try:
                        m.close()
                    except Exception:
                        pass
            # Close the serial console session, as it'll help
            # keeping the number of filedescriptors used by avocado-vt honest.
            vm.cleanup_serial_console()

    libvirtd_inst = None
    vm_type = params.get("vm_type")
    cpu_family = "unknown"
    try:
        cpu_family = cpu_utils.get_family() if hasattr(cpu_utils, 'get_family') else cpu_utils.get_cpu_arch()
    except Exception:
        LOG.warning("Could not get host cpu family")
    if cpu_family is not None and "power" in cpu_family:
        pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
        pvr = float(a_process.system_output(pvr_cmd, shell=True).strip())
        # Restore SMT changes in the powerpc host is set
        if params.get("restore_smt", "no") == "yes":
            power9_compat = "yes" == params.get("power9_compat", "no")
            if "power9" in cpu_family and power9_compat and pvr < 2.2:
                test_setup.switch_indep_threads_mode(state="Y")
                test_setup.switch_smt(state="on")

        if migration_setup:
            power9_compat_remote = params.get("power9_compat_remote", "no") == "yes"
            cpu_cmd = "grep cpu /proc/cpuinfo | awk '{print $3}' | head -n 1"
            server_session = test_setup.remote_session(params)
            cmd_output = server_session.cmd_status_output(cpu_cmd)
            if (cmd_output[0] == 0):
                remote_cpu = cmd_output[1].strip().lower()
            cmd_output = server_session.cmd_status_output(pvr_cmd)
            if (cmd_output[0] == 0):
                remote_pvr = float(cmd_output[1].strip())
            server_session.close()
            if ("power9" in remote_cpu) and power9_compat_remote and remote_pvr < 2.2:
                test_setup.switch_indep_threads_mode(state="Y", params=params)
                test_setup.switch_smt(state="on", params=params)

    if params.get("setup_hugepages") == "yes":
        global _post_hugepages_surp
        try:
            h = test_setup.HugePageConfig(params)
            h.cleanup()
            if vm_type == "libvirt":
                if libvirtd_inst is None:
                    libvirtd_inst = utils_libvirtd.Libvirtd()
                libvirtd_inst.restart()
        except Exception as details:
            err += "\nHP cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)
        else:
            _post_hugepages_surp = h.ext_hugepages_surp

    if params.get("setup_thp") == "yes":
        try:
            thp = test_setup.TransparentHugePageConfig(test, params)
            thp.cleanup()
        except Exception as details:
            err += "\nTHP cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    for kvm_module in KVM_MODULE_HANDLERS:
        kvm_module.restore()

    if params.get("setup_ksm") == "yes":
        try:
            ksm = test_setup.KSMConfig(params, env)
            ksm.cleanup(env)
        except Exception as details:
            err += "\nKSM cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    if params.get("setup_egd") == "yes" and params.get("kill_vm") == "yes":
        try:
            egd = test_setup.EGDConfig(params, env)
            egd.cleanup()
        except Exception as details:
            err += "\negd.pl cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    if vm_type == "libvirt":
        if params.get("setup_libvirt_polkit") == "yes":
            try:
                pol = test_setup.LibvirtPolkitConfig(params)
                pol.cleanup()
                if libvirtd_inst is None:
                    libvirtd_inst = utils_libvirtd.Libvirtd(all_daemons=True)
                libvirtd_inst.restart()
            except test_setup.PolkitConfigCleanupError as e:
                err += "\nPolkit cleanup: %s" % str(e).replace('\\n', '\n  ')
                LOG.error(e)
            except Exception as details:
                err += "\nPolkit cleanup: %s" % str(details
                                                    ).replace('\\n', '\n  ')
                LOG.error("Unexpected error: %s" % details)
        if params.get("enable_libvirtd_debug_log", "yes") == "yes":
            libvirtd_debug_log = test_setup.LibvirtdDebugLog(test)
            libvirtd_debug_log.disable()

    # Execute any post_commands
    if params.get("post_command"):
        try:
            process_command(test, params, env, params.get("post_command"),
                            int(params.get("post_command_timeout", "600")),
                            params.get("post_command_noncritical") == "yes")
        except Exception as details:
            err += "\nPostprocess command: %s" % str(details).replace('\n',
                                                                      '\n  ')
            LOG.error(details)

    if params.get("storage_type") == "iscsi":
        try:
            iscsidev = qemu_storage.Iscsidev(params, base_dir, "iscsi")
            iscsidev.cleanup()
        except Exception as details:
            err += "\niscsi cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    if params.get("storage_type") == "lvm":
        try:
            lvmdev = env.get_lvmdev("lvm_%s" % params["main_vm"])
            lvmdev.cleanup()
        except Exception as details:
            err += "\nLVM cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)
        env.unregister_lvmdev("lvm_%s" % params["main_vm"])

    if params.get("storage_type") == "nfs":
        try:
            image_nfs = nfs.Nfs(params)
            image_nfs.cleanup()
            if migration_setup:
                # Cleanup NFS client on remote host
                nfs_client = nfs.NFSClient(params)
                nfs_client.cleanup(ssh_auto_recover=False)
                # Cleanup selinux on remote host
                seLinuxBool = utils_misc.SELinuxBoolean(params)
                seLinuxBool.cleanup(keep_authorized_keys=True)
        except Exception as details:
            err += "\nnfs cleanup: %s" % str(details).replace('\\n', '\n  ')

    # cleanup migration presetup in post process
    if migration_setup:
        dest_uri = libvirt_vm.complete_uri(params.get("server_ip",
                                                      params.get("remote_ip")))
        migrate_setup = migration.MigrationTest()
        migrate_setup.migrate_pre_setup(dest_uri, params, cleanup=True)
        if params.get("setup_ssh") == "yes" and params.get("ssh_conn_obj"):
            del params["ssh_conn_obj"]

    setup_pb = False
    ovs_pb = False
    for nic in params.get('nics', "").split():
        nic_params = params.object_params(nic)
        if params.get('netdst_%s' % nic) == 'private':
            setup_pb = True
            params_pb = nic_params
            break
    else:
        setup_pb = params.get("netdst") == 'private'
        params_pb = params

    if params_pb.get("priv_br_type") == "openvswitch":
        ovs_pb = True

    if setup_pb:
        try:
            if ovs_pb:
                brcfg = test_setup.PrivateOvsBridgeConfig(params_pb)
            else:
                brcfg = test_setup.PrivateBridgeConfig(params_pb)
            brcfg.cleanup()
        except Exception as details:
            err += "\nPB cleanup: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    if params.get("verify_host_dmesg", "yes") == "yes":
        dmesg_log_file = params.get("host_dmesg_logfile", "host_dmesg.log")
        level = params.get("host_dmesg_level", 3)
        ignore_result = params.get("host_dmesg_ignore", "no") == "yes"
        dmesg_log_file = utils_misc.get_path(test.debugdir, dmesg_log_file)
        try:
            utils_misc.verify_dmesg(dmesg_log_file=dmesg_log_file,
                                    ignore_result=ignore_result,
                                    level_check=level)
        except exceptions.TestFail as details:
            err += "\nHost dmesg verification failed: %s" % details

    err += "\n".join(_setup_manager.do_cleanup())

    # Run this hook after any vms are actually off to ensure data is
    # written to disk.
    if callable(postprocess_vm_off_hook):
        try:
            postprocess_vm_off_hook(test, params, env)  # pylint: disable=E1102
        except Exception as details:
            err += "\nPostprocessing dead vm hook: %s" % str(details).replace('\\n', '\n  ')
            LOG.error(details)

    if err:
        raise RuntimeError("Failures occurred while postprocess:\n%s" % err)
    elif _post_hugepages_surp > _pre_hugepages_surp:
        leak_num = _post_hugepages_surp - _pre_hugepages_surp
        raise exceptions.TestFail("%d huge pages leaked!" % leak_num)


def postprocess_on_error(test, params, env):
    """
    Perform postprocessing operations required only if the test failed.

    :param test: An Autotest test object.
    :param params: A dict containing all VM and image parameters.
    :param env: The environment (a dict-like object).
    """
    params.update(params.object_params("on_error"))


def _take_screendumps(test, params, env):
    global _screendump_thread_termination_event
    temp_dir = test.debugdir
    if params.get("screendump_temp_dir"):
        temp_dir = utils_misc.get_path(test.bindir,
                                       params.get("screendump_temp_dir"))
        try:
            os.makedirs(temp_dir)
        except OSError:
            pass
    random_id = utils_misc.generate_random_string(6)
    temp_filename = "scrdump-%s-iter%s.ppm" % (random_id, test.iteration)
    temp_filename = os.path.join(temp_dir, temp_filename)
    delay = float(params.get("screendump_delay", 5))
    quality = int(params.get("screendump_quality", 30))
    inactivity_treshold = float(params.get("inactivity_treshold", 1800))
    inactivity_watcher = params.get("inactivity_watcher", "log")

    cache = {}
    counter = {}
    inactivity = {}

    while True:
        for vm in env.get_all_vms():
            if vm.instance not in list(counter.keys()):
                counter[vm.instance] = 0
            if vm.instance not in list(inactivity.keys()):
                inactivity[vm.instance] = time.time()
            if not vm.is_alive():
                continue
            vm_pid = vm.get_pid()
            try:
                vm.screendump(filename=temp_filename, debug=False)
            except qemu_monitor.MonitorError as e:
                LOG.warn(e)
                continue
            except AttributeError as e:
                LOG.warn(e)
                continue
            if not os.path.exists(temp_filename):
                LOG.warn("VM '%s' failed to produce a screendump", vm.name)
                continue
            if not ppm_utils.image_verify_ppm_file(temp_filename):
                LOG.warn("VM '%s' produced an invalid screendump", vm.name)
                os.unlink(temp_filename)
                continue
            screendump_dir = "screendumps_%s_%s_iter%s" % (vm.name, vm_pid,
                                                           test.iteration)
            screendump_dir = os.path.join(test.debugdir, screendump_dir)
            try:
                os.makedirs(screendump_dir)
            except OSError:
                pass
            counter[vm.instance] += 1
            filename = "%04d.jpg" % counter[vm.instance]
            screendump_filename = os.path.join(screendump_dir, filename)
            vm.verify_bsod(screendump_filename)
            image_hash = crypto.hash_file(temp_filename)
            if image_hash in cache:
                time_inactive = time.time() - inactivity[vm.instance]
                if time_inactive > inactivity_treshold:
                    msg = (
                        "%s screen is inactive for more than %d s (%d min)" %
                        (vm.name, time_inactive, time_inactive // 60))
                    if inactivity_watcher == "error":
                        try:
                            raise virt_vm.VMScreenInactiveError(vm,
                                                                time_inactive)
                        except virt_vm.VMScreenInactiveError:
                            LOG.error(msg)
                            # Let's reset the counter
                            inactivity[vm.instance] = time.time()
                            test.background_errors.put(sys.exc_info())
                    elif inactivity_watcher == 'log':
                        LOG.debug(msg)
            else:
                inactivity[vm.instance] = time.time()
            cache[image_hash] = screendump_filename
            try:
                try:
                    timestamp = os.stat(temp_filename).st_ctime
                    image = PIL.Image.open(temp_filename)
                    image = ppm_utils.add_timestamp(image, timestamp)
                    image.save(screendump_filename, format="JPEG",
                               quality=quality)
                except (IOError, OSError) as error_detail:
                    LOG.warning("VM '%s' failed to produce a "
                                "screendump: %s", vm.name, error_detail)
                    # Decrement the counter as we in fact failed to
                    # produce a converted screendump
                    counter[vm.instance] -= 1
            except NameError:
                pass
            os.unlink(temp_filename)

        if _screendump_thread_termination_event is not None:
            if _screendump_thread_termination_event.isSet():
                _screendump_thread_termination_event = None
                break
            _screendump_thread_termination_event.wait(delay)
        else:
            # Exit event was deleted, exit this thread
            break


def store_vm_info(vm, log_filename, info_cmd='registers',
                  append=False, vmtype='qemu'):
    """
    Store the info information of vm into a log file

    :param vm: VM object
    :type vm: vm object
    :info_cmd: monitor info cmd
    :type info_cmd: string
    :param log_filename: log file name
    :type log_filename: string
    :param append: Add the log to the end of the log file or not
    :type append: bool
    :param vmtype: VM Type
    :type vmtype: string
    :return: Store the vm register information to log file or not
    :rtype: bool
    """
    timestamp = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    if vmtype == "qemu":
        try:
            output = vm.catch_monitor.info(info_cmd, debug=False)
        except qemu_monitor.MonitorError as err:
            LOG.warn(err)
            return False
        except AttributeError as err:
            LOG.warn(err)
            return False
    elif vmtype == "libvirt":
        try:
            result = virsh.qemu_monitor_command(vm.name,
                                                "info %s" % info_cmd,
                                                "--hmp", debug=False)
            output = result.stdout
        except Exception as details:
            LOG.warn(details)
            return False

    log_filename = "%s_%s" % (log_filename, timestamp)
    if append:
        vr_log = open(log_filename, 'r+')
        vr_log.seek(0, 2)
        output += "\n"
    else:
        vr_log = open(log_filename, 'w')
    vr_log.write(str(output))
    vr_log.close()
    return True


def _store_vm_info(test, params, env):
    def report_result(status, cmd, results):
        msg = "%s." % status
        for vm_instance in list(results.keys()):
            if results[vm_instance] > 0:
                msg += " Used to failed to get %s info from guest" % cmd
                msg += " %s for %s times." % (vm_instance,
                                              results[vm_instance])

        if msg != "%s." % status:
            LOG.debug(msg)

    global _vm_info_thread_termination_event
    delay = float(params.get("vm_info_delay", 5))
    cmds = params.get('vm_info_cmds', 'registers').split(',')
    cmd_details = {}
    for cmd in cmds:
        cmd_details.update({cmd: {'counter': {},
                                  'vm_info_error_count': {}}
                            })
    while True:
        for cmd in cmds:
            for vm in env.get_all_vms():
                if vm.instance not in cmd_details[cmd]['vm_info_error_count']:
                    cmd_details[cmd]['vm_info_error_count'][vm.instance] = 0

                if not vm.is_alive():
                    if cmd_details[cmd]['vm_info_error_count'][vm.instance] < 1:
                        LOG.warning(
                            "%s is not alive. Can't query the %s status", cmd, vm.name)
                    cmd_details[cmd]['vm_info_error_count'][vm.instance] += 1
                    continue
                vm_pid = vm.get_pid()
                vr_dir = utils_misc.get_path(test.debugdir,
                                             "vm_info_%s_%s" % (vm.name,
                                                                vm_pid))
                try:
                    os.makedirs(vr_dir)
                except OSError:
                    pass

                if vm.instance not in cmd_details[cmd]['counter']:
                    cmd_details[cmd]['counter'][vm.instance] = 1
                vr_filename = "%04d_%s" % (cmd_details[cmd]['counter'][vm.instance], cmd)
                vr_filename = utils_misc.get_path(vr_dir, vr_filename)
                vmtype = params.get("vm_type")
                stored_log = store_vm_info(vm, vr_filename, cmd, vmtype=vmtype)
                if cmd_details[cmd]['vm_info_error_count'][vm.instance] >= 1:
                    LOG.debug("%s alive now. Used to failed to get register"
                              " info from guest %s"
                              " times", vm.name, cmd_details[cmd]['vm_info_error_count'][vm.instance])
                    cmd_details[cmd]['vm_info_error_count'][vm.instance] = 0
                if stored_log:
                    cmd_details[cmd]['counter'][vm.instance] += 1

        if _vm_info_thread_termination_event is not None:
            if _vm_info_thread_termination_event.isSet():
                _vm_info_thread_termination_event = None
                for cmd in cmds:
                    report_result("Thread quit", cmd,
                                  cmd_details[cmd]['vm_info_error_count'])
                break
            _vm_info_thread_termination_event.wait(delay)
        else:
            for cmd in cmds:
                report_result("Thread quit", cmd,
                              cmd_details[cmd]['vm_info_error_count'])
            # Exit event was deleted, exit this thread
            break
