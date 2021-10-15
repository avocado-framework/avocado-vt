"""
libvirt disk related utility functions
"""
import collections
import logging
import os
import re

from avocado.core import exceptions
from avocado.utils import process

from virttest import libvirt_storage
from virttest import remote as remote_old
from virttest import utils_misc
from virttest import utils_disk
from virttest import virsh
from virttest import utils_package

from virttest.libvirt_xml import vm_xml
from virttest.utils_test import libvirt

from virttest.libvirt_xml.devices.disk import Disk

LOG = logging.getLogger('avocado.' + __name__)


def create_disk(disk_type, path=None, size="500M", disk_format="raw", extra='',
                session=None):
    """
    Create disk on local or remote

    :param disk_type: Disk type
    :param path: The path of disk
    :param size: The size of disk
    :param disk_format: The format of disk
    :param extra: Extra parameters
    :param session： Session object to a remote host or guest
    :return: The path of disk
    :raise: TestError if the disk can't be created
    """
    if session:
        if disk_type == "file":
            disk_cmd = ("qemu-img create -f %s %s %s %s"
                        % (disk_format, extra, path, size))
        else:
            # TODO: Add implementation for other types
            raise exceptions.TestError("Unknown disk type %s" % disk_type)

        status, stdout = utils_misc.cmd_status_output(disk_cmd, session=session)
        if status:
            raise exceptions.TestError("Failed to create img on remote: cmd: {} "
                                       "status: {}, stdout: {}"
                                       .format(disk_cmd, status, stdout))
        return path
    else:
        return libvirt.create_local_disk(disk_type, path=path, size=size,
                                         disk_format=disk_format, extra=extra)


def create_primitive_disk_xml(type_name, disk_device, device_target, device_bus,
                              device_format, disk_src_dict, disk_auth_dict):
    """
    Creates primitive disk xml

    :param type_name: disk type
    :param disk_device: disk device
    :param device_target: target device
    :param device_bus: device bus
    :param device_format: device format
    :param disk_src_dict: disk source, dict format like below
           disk_src_dict = {"attrs": {"protocol": "rbd",
                                   "name": disk_name},
                            "hosts":  [{"name": host_ip,
                                     "port": host_port}]}
    :param disk_auth_dict: disk auth information, dict format like below
           disk_auth_dict = {"auth_user": auth_user,
                             "secret_type": auth_sec_usage_type,
                             "secret_uuid": auth_sec_uuid}
    :return: disk xml object
    """
    disk_xml = Disk(type_name=type_name)
    disk_xml.device = disk_device
    disk_xml.target = {"dev": device_target, "bus": device_bus}
    driver_dict = {"name": "qemu", "type": device_format}
    disk_xml.driver = driver_dict
    if disk_src_dict:
        LOG.debug("disk src dict is: %s" % disk_src_dict)
        disk_source = disk_xml.new_disk_source(**disk_src_dict)
        disk_xml.source = disk_source
    if disk_auth_dict:
        LOG.debug("disk auth dict is: %s" % disk_auth_dict)
        disk_xml.auth = disk_xml.new_auth(**disk_auth_dict)
    LOG.debug("new disk xml in create_primitive_disk is: %s", disk_xml)
    return disk_xml


def create_custom_metadata_disk(disk_path, disk_format,
                                disk_device, device_target, device_bus, max_size, disk_inst=None):
    """
    Create another disk for a given path,customize driver metadata attribute

    :param disk_path: the path of disk
    :param disk_format: the format to disk image
    :param disk_device: the disk device type
    :param device_target: the target of disk
    :param device_bus: device bus
    :param max_size: metadata_cache max size
    :param disk_inst: disk instance
    :return: disk object if created or updated successfully
    """
    if disk_inst:
        custom_disk = disk_inst
    else:
        custom_disk = Disk(type_name='file')
    if disk_device:
        custom_disk.device = disk_device
    source_dict = {}
    if disk_path:
        source_dict.update({'file': disk_path})
    custom_disk.source = custom_disk.new_disk_source(
        **{"attrs": source_dict})
    if device_target:
        target_dict = {"dev": device_target, "bus": device_bus}
        custom_disk.target = target_dict
    driver_dict = {"name": "qemu", 'type': disk_format}
    # Create drivermetadata object
    new_one_drivermetadata = custom_disk.new_drivermetadata(**{"attrs": driver_dict})
    metadata_cache_dict = {"max_size": max_size, "max_size_unit": "bytes"}
    # Attach metadatacache into drivermetadata object
    new_one_drivermetadata.metadata_cache = custom_disk.DriverMetadata().new_metadatacache(**metadata_cache_dict)
    custom_disk.drivermetadata = new_one_drivermetadata
    LOG.debug("disk xml in create_custom_metadata_disk: %s\n", custom_disk)
    return custom_disk


def get_images_with_xattr(vm):
    """
    Get the image path(s) which still having xattr left of a vm

    :param vm: The vm to be checked
    :return: The image path list which having xattr left
    """
    disks = vm.get_disk_devices()
    dirty_images = []
    for disk in disks:
        disk_path = disks[disk]['source']
        getfattr_result = get_image_xattr(disk_path)
        if "selinux" in getfattr_result:
            dirty_images.append(disk_path)
            LOG.debug("Image '%s' having xattr left: %s",
                      disk_path, getfattr_result.stdout)
    return dirty_images


def clean_images_with_xattr(dirty_images):
    """
    Clean the images' xattr

    :param dirty_images: The image list to be cleaned
    """
    for image in dirty_images:
        output = get_image_xattr(image)
        attr_list = [line.split("=")[0] for line in output.split("\n") if len(line.split("=")) == 2
                     and "trusted.libvirt" in line.split("=")[0]]
        for attr in attr_list:
            clean_cmd = "setfattr -x $s" % attr
            process.run(clean_cmd, shell=True)


def get_image_xattr(image):
    """
    Get the image's xattr

    :param image: The image to be operated
    """
    get_attr_cmd = "getfattr -m trusted.libvirt.security -d %s" % image
    output = process.run(get_attr_cmd, shell=True).stdout_text
    return output


def get_first_disk_source(vm):
    """
    Get disk source of first device

    :param vm: VM instance
    :return: first disk of first device.
    """
    first_device = vm.get_first_disk_devices()
    first_disk_src = first_device['source']
    return first_disk_src


def make_relative_path_backing_files(vm, pre_set_root_dir=None, origin_image=None, origin_image_format="qcow2",
                                     created_image_format="qcow2", back_chain_lenghth=4):
    """
    Create backing chain files of relative path for one image

    :param vm: VM instance
    :param pre_set_root_dir: preset root dir
    :param origin_image: origin image
    :param origin_image_format: original image format
    :param created_image_format: created image format
    :param back_chain_lenghth: back chain length
    :return: absolute path of top active file and back chain files list
    """
    if pre_set_root_dir is None:
        first_disk_source = get_first_disk_source(vm)
        root_dir = os.path.dirname(first_disk_source)
        basename = os.path.basename(first_disk_source)
    else:
        root_dir = pre_set_root_dir
        basename = origin_image
    sub_folders = [chr(letter) for letter in range(ord('a'), ord('a') + back_chain_lenghth)]
    # Make external relative path backing files.
    backing_files_dict = collections.OrderedDict()
    for index in range(len(sub_folders)):
        key = sub_folders[index]
        os.makedirs(os.path.join(root_dir, key), exist_ok=True)
        if index == 0:
            backing_files_dict[key] = "%s" % basename
        else:
            backing_key = sub_folders[index-1]
            backing_files_dict[key] = "../%s/%s.img" % (backing_key, backing_key)
    backing_file_path = _execute_create_backend_file(backing_files_dict, pre_set_root_dir,
                                                     origin_image_format, created_image_format)
    return os.path.join(backing_file_path, "%s.img" % sub_folders[-1]), list(backing_files_dict.values())


def create_reuse_external_snapshots(vm, pre_set_root_dir=None, skip_first_one=False,
                                    disk_target="vda", snapshot_chain_lenghth=4):
    """
    Create reuse external snapshots

    :param vm: VM instance
    :param pre_set_root_dir: preset root directory
    :param skip_first_one: whether skip first image file
    :param disk_target: disk target
    :param snapshot_chain_lenghth : snapshot length
    :return: absolute root path of backing files and snapshot list
    """
    if pre_set_root_dir is None:
        first_disk_source = get_first_disk_source(vm)
        root_dir = os.path.dirname(first_disk_source)
    else:
        root_dir = pre_set_root_dir
    meta_options = " --reuse-external --disk-only --no-metadata"
    # Make four external relative path backing files.
    relative_sub_folders = [chr(letter) for letter in range(ord('a'), ord('a') + snapshot_chain_lenghth)]
    backing_file_dict = collections.OrderedDict()
    snapshot_external_disks = []
    for index in range(len(relative_sub_folders)):
        key = relative_sub_folders[index]
        if index == 0 and skip_first_one:
            continue
        else:
            backing_file_dict[key] = "%s.img" % key
    for key, value in list(backing_file_dict.items()):
        backing_file_path = os.path.join(root_dir, key)
        external_snap_shot = "%s/%s" % (backing_file_path, value)
        snapshot_external_disks.append(external_snap_shot)
        options = "%s --diskspec %s,file=%s" % (meta_options, disk_target, external_snap_shot)
        virsh.snapshot_create_as(vm.name, options,
                                 ignore_status=False,
                                 debug=True)
    LOG.debug('reuse external snapshots:%s' % snapshot_external_disks)
    return root_dir, snapshot_external_disks


def make_syslink_path_backing_files(pre_set_root_dir, volume_path_list, origin_image_format="qcow2",
                                    created_image_format="qcow2", syslink_back_chain_lenghth=4):
    """
    Create backing chain files of syslink path for one image

    :param pre_set_root_dir: preset root dir
    :param volume_path_list: volume path list
    :param origin_image: origin image
    :param origin_image_format: original image format
    :param created_image_format: created image format
    :param syslink_back_chain_lenghth: syslink back chain length
    :return: absolute path of top active file and syslink back chain files list
    """
    root_dir = pre_set_root_dir
    syslink_folder_list = [chr(letter) for letter in range(ord('a'), ord('a') + syslink_back_chain_lenghth)]
    backing_files_dict = collections.OrderedDict()
    # Make external relative path backing files.
    for index in range(len(syslink_folder_list)):
        key = syslink_folder_list[index]
        folder_path = os.path.join(root_dir, key)
        os.makedirs(folder_path, exist_ok=True)
        #Create syslink
        link_cmd = "ln -s  %s %s" % (volume_path_list[index], os.path.join(folder_path, "%s.img" % key))
        process.run(link_cmd, shell=True, ignore_status=False)
        if index == 0:
            continue
        else:
            backing_key = syslink_folder_list[index-1]
            backing_files_dict[key] = "../%s/%s.img" % (backing_key, backing_key)
    backing_file_path = _execute_create_backend_file(backing_files_dict, pre_set_root_dir,
                                                     origin_image_format, created_image_format)
    return os.path.join(backing_file_path, "%s.img" % syslink_folder_list[-1]), list(backing_files_dict.values())


def _execute_create_backend_file(backing_files_dict, pre_set_root_dir, origin_image_format, created_image_format):
    """
    Execute create backing chain files

    :param backing_files_dict: backing chain files
    :param pre_set_root_dir: preset root dir
    :param origin_image_format: original image format
    :param created_image_format: created image format
    :return: backing file path
    """
    root_dir = pre_set_root_dir
    disk_format = origin_image_format
    for key, value in list(backing_files_dict.items()):
        backing_file_path = os.path.join(root_dir, key)
        cmd = ("cd %s && qemu-img create -f %s -o backing_file=%s,backing_fmt=%s %s.img"
               % (backing_file_path, created_image_format, value, disk_format, key))
        process.run(cmd, shell=True, ignore_status=False)
        disk_format = created_image_format
    return backing_file_path


def do_blockcommit_repeatedly(vm, device_target, options, repeated_counts):
    """
    Do blockcommit repeatedly

    :param vm: VM instance
    :param device_target: device target
    :param options: blockcommit options
    :param repeated_counts: repeated counts for executing blockcommit
    """
    for count in range(repeated_counts):
        virsh.blockcommit(vm.name, device_target,
                          options, ignore_status=False, debug=True)


def make_external_disk_snapshots(vm, device_target, postfix_n, snapshot_take):
    """
    Make external snapshots for disks only.

    :param vm: VM instance
    :param device_target: device target
    :param postfix_n: postfix option
    :param snapshot_take: snapshots taken.
    :return: list containing absolute root path of snapshot files
    """
    first_disk_source = get_first_disk_source(vm)
    root_dir = os.path.dirname(first_disk_source)
    basename = os.path.basename(first_disk_source)
    disk = device_target
    external_snapshot_disks = []
    # Make external snapshots for disks only
    for count in range(1, snapshot_take + 1):
        options = "%s_%s %s%s-desc " % (postfix_n, count,
                                        postfix_n, count)
        options += "--diskspec "
        diskname = basename.split(".")[0]
        snap_name = "%s.%s%s" % (diskname, postfix_n, count)
        disk_external = os.path.join(root_dir, snap_name)
        external_snapshot_disks.append(disk_external)
        options += " %s,snapshot=external,file=%s" % (disk,
                                                      disk_external)
        options += "  --disk-only --atomic"
        virsh.snapshot_create_as(vm.name, options,
                                 ignore_status=False,
                                 debug=True)
    return external_snapshot_disks


def cleanup_snapshots(vm, snap_del_disks=None):
    """
    clean up snapshots

    :param vm: VM instance
    :param snap_del_disks: list containing snapshot files
    """
    snapshot_list_cmd = "virsh snapshot-list %s --tree" % vm.name
    result_output = process.run(snapshot_list_cmd,
                                ignore_status=False, shell=True).stdout_text
    for line in result_output.rsplit("\n"):
        strip_line = line.strip()
        if strip_line and "|" not in strip_line:
            if '+-' in strip_line:
                strip_line = strip_line.split()[-1]
            virsh.snapshot_delete(vm.name, strip_line, "--metadata", ignore_status=False, debug=True)
    # delete actual snapshot files if exists
    if snap_del_disks:
        for disk in snap_del_disks:
            if os.path.exists(disk):
                os.remove(disk)


def get_chain_backing_files(disk_src_file):
    """
    Get backing chain files list

    :param disk_src_file: original image file
    :return: backing chain list
    """
    cmd = "qemu-img info %s --backing-chain" % disk_src_file
    if libvirt_storage.check_qemu_image_lock_support():
        cmd = "qemu-img info -U %s --backing-chain" % disk_src_file
    ret = process.run(cmd, shell=True).stdout_text.strip()
    LOG.debug("The actual qemu-img output:%s\n", ret)
    match = re.findall(r'(backing file: )(.+\n)', ret)
    qemu_img_info_backing_chain = []
    for i in range(len(match)):
        qemu_img_info_backing_chain.append(match[i][1].strip().split("(")[0].strip())
    qemu_img_info_backing_chain = qemu_img_info_backing_chain[::-1]
    return qemu_img_info_backing_chain


def get_mirror_part_in_xml(vm, disk_target):
    """
    Get mirror part contents in disk xml

    :param vm: VM instance
    :param disk_target: target disk
    """
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm.name)
    disks = vmxml.devices.by_device_tag('disk')
    disk_xml = None
    for disk in disks:
        if disk.target['dev'] != disk_target:
            continue
        else:
            disk_xml = disk.xmltreefile
            break
    LOG.debug("disk xml in mirror: %s\n", disk_xml)
    disk_mirror = disk_xml.find('mirror')
    job_details = []
    if disk_mirror is not None:
        job_details.append(disk_mirror.get('job'))
        job_details.append(disk_mirror.get('ready'))
        job_details.append(disk_mirror.find('type'))
    return job_details


def create_mbxml(mb_params):
    """
    Create memoryBacking xml

    :param mb_params: dict containing memory backing attributes
    :return memoryBacking xml
    """
    mb_xml = vm_xml.VMMemBackingXML()
    for attr_key in mb_params:
        setattr(mb_xml, attr_key,
                mb_params[attr_key])
    LOG.debug(mb_xml)
    return mb_xml.copy()


def check_in_vm(vm, target, old_parts, is_equal=False):
    """
    Check mount/read/write disk in VM.

    :param vm: VM guest.
    :param target: Disk dev in VM.
    :param old_parts: old part partitions
    :param is_equal: whether two are equals
    :return: True if check successfully.
    """
    try:
        session = vm.wait_for_login()
        rpm_stat, out_put = session.cmd_status_output("rpm -q parted || "
                                                      "yum install -y parted", 300)
        if rpm_stat != 0:
            raise exceptions.TestFail("Failed to query/install parted:\n%s", out_put)

        added_parts = utils_disk.get_added_parts(session, old_parts)
        if is_equal:
            if len(added_parts) != 0:
                LOG.error("new added parts are not equal the old one")
                return False
            else:
                return True
        if len(added_parts) != 1:
            LOG.error("The number of new partitions is invalid in VM")
            return False

        added_part = None
        if target.startswith("vd"):
            if added_parts[0].startswith("vd"):
                added_part = added_parts[0]
        elif target.startswith("hd"):
            if added_parts[0].startswith("sd"):
                added_part = added_parts[0]

        if not added_part:
            LOG.error("Can't see added partition in VM")
            return False

        device_source = os.path.join(os.sep, 'dev', added_part)
        libvirt.mk_label(device_source, session=session)
        libvirt.mk_part(device_source, size="10M", session=session)
        # Run partprobe to make the change take effect.
        process.run("partprobe", ignore_status=True, shell=True)
        libvirt.mkfs("/dev/%s1" % added_part, "ext3", session=session)

        cmd = ("mount /dev/%s1 /mnt && echo '123' > /mnt/testfile"
               " && cat /mnt/testfile && umount /mnt" % added_part)
        s, o = session.cmd_status_output(cmd)
        LOG.info("Check disk operation in VM:\n%s", o)
        session.close()
        if s != 0:
            LOG.error("error happened when execute command:\n%s", cmd)
            return False
        return True
    except Exception as e:
        LOG.error(str(e))
        return False


def create_remote_disk_by_same_metadata(vm, params):
    """
    Create an empty file image on remote host using same name/vsize/path/format
    as the first disk of the vm on local host

    :param vm:  the VM object
    :param params:  dict, parameters used
    :return:  str, the path of newly created image
    """
    disk_format = params.get("disk_format", "qcow2")
    server_ip = params.get('server_ip', params.get('migrate_dest_host'))
    server_user = params.get('server_user', params.get('remote_user'))
    server_pwd = params.get('server_pwd', params.get('migrate_dest_pwd'))

    blk_source = get_first_disk_source(vm)
    vsize = utils_misc.get_image_info(blk_source).get("vsize")
    remote_session = remote_old.remote_login("ssh", server_ip, "22",
                                             server_user, server_pwd,
                                             r'[$#%]')
    utils_misc.make_dirs(os.path.dirname(blk_source), remote_session)
    create_disk('file', path=blk_source, size=vsize,
                disk_format=disk_format, extra='',
                session=remote_session)

    remote_session.close()
    return blk_source


def fill_null_in_vm(vm, target, size_value=500):
    """
    File something in the disk of VM

    :param vm: VM guest
    :param target: disk dev in VM
    :param size_value: number in MiB
    """
    try:
        session = vm.wait_for_login()
        if not utils_package.package_install(["parted"], session, timeout=300):
            LOG.error("Failed to install the required 'parted' package")
        device_source = os.path.join(os.sep, 'dev', target)
        libvirt.mk_label(device_source, session=session)
        libvirt.mk_part(device_source, size="%sM" % size_value, session=session)
        # Run partprobe to make the change take effect.
        process.run("partprobe", ignore_status=True, shell=True)
        libvirt.mkfs("/dev/%s1" % target, "ext3", session=session)
        count_number = size_value - 100
        cmd = ("mount /dev/%s1 /mnt && dd if=/dev/zero of=/mnt/testfile bs=1024 count=1024x%s "
               " && umount /mnt" % (target, count_number))
        s, o = session.cmd_status_output(cmd)
        LOG.info("Check disk operation in VM:\n%s", o)
        session.close()
        if s != 0:
            raise exceptions.TestError("Error happened when executing command:\n%s" % cmd)
    except Exception as e:
        raise exceptions.TestError(str(e))
