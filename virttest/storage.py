"""
Classes and functions to handle storage devices.

This exports:
  - two functions for get image/blkdebug filename
  - class for image operates and basic parameters
"""
from __future__ import division
import errno
import logging
import os
import shutil
import re
import functools

from avocado.core import exceptions
from avocado.utils import process

from virttest import iscsi
from virttest import utils_misc
from virttest import utils_numeric
from virttest import virt_vm
from virttest import gluster
from virttest import lvm
from virttest import ceph
from virttest import data_dir
from virttest.compat_52lts import decode_to_text


def preprocess_images(bindir, params, env):
    # Clone master image form vms.
    for vm_name in params.get("vms").split():
        vm = env.get_vm(vm_name)
        if vm:
            vm.destroy(free_mac_addresses=False)
        vm_params = params.object_params(vm_name)
        for image in vm_params.get("master_images_clone").split():
            image_obj = QemuImg(vm_params, bindir, image)
            image_obj.clone_image(vm_params, vm_name, image, bindir)


def preprocess_image_backend(bindir, params, env):
    enable_gluster = params.get("enable_gluster")
    gluster_image = params.get("gluster_brick")
    if enable_gluster and gluster_image:
        return gluster.create_gluster_vol(params)

    return True


def postprocess_images(bindir, params):
    for vm in params.get("vms").split():
        vm_params = params.object_params(vm)
        for image in vm_params.get("master_images_clone").split():
            image_obj = QemuImg(vm_params, bindir, image)
            image_obj.rm_cloned_image(vm_params, vm, image, bindir)


def file_exists(params, filename_path):
    """
    Check if image_filename exists.

    :param params: Dictionary containing the test parameters.
    :param filename_path: path to file
    :type filename_path: str
    :param root_dir: Base directory for relative filenames.
    :type root_dir: str

    :return: True if image file exists else False
    """
    gluster_image = params.get("gluster_brick")
    if gluster_image:
        return gluster.file_exists(params, filename_path)

    if params.get("enable_ceph") == "yes":
        image_name = params.get("image_name")
        image_format = params.get("image_format", "qcow2")
        ceph_monitor = params.get("ceph_monitor")
        rbd_pool_name = params["rbd_pool_name"]
        rbd_image_name = "%s.%s" % (image_name.split("/")[-1], image_format)
        ceph_conf = params.get("ceph_conf")
        return ceph.rbd_image_exist(ceph_monitor, rbd_pool_name,
                                    rbd_image_name, ceph_conf)
    return os.path.exists(filename_path)


def file_remove(params, filename_path):
    """
    Remove the image
    :param params: Dictionary containing the test parameters.
    :param filename_path: path to file
    """
    if params.get("enable_ceph") == "yes":
        image_name = params.get("image_name")
        image_format = params.get("image_format", "qcow2")
        ceph_monitor = params.get("ceph_monitor")
        rbd_pool_name = params["rbd_pool_name"]
        rbd_image_name = "%s.%s" % (image_name.split("/")[-1], image_format)
        ceph_conf = params.get("ceph_conf")
        return ceph.rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name,
                                 ceph_conf)

    if params.get("gluster_brick"):
        # TODO: Add implementation for gluster_brick
        return

    if params.get('storage_type') in ('iscsi', 'lvm', 'iscsi-direct'):
        # TODO: Add implementation for iscsi/lvm
        return

    if os.path.exists(filename_path):
        os.unlink(filename_path)
        return


def get_image_blkdebug_filename(params, root_dir):
    """
    Generate an blkdebug file path from params and root_dir.

    blkdebug files allow error injection in the block subsystem.

    :param params: Dictionary containing the test parameters.
    :param root_dir: Base directory for relative filenames.

    :note: params should contain:
           blkdebug -- the name of the debug file.
    """
    blkdebug_name = params.get("drive_blkdebug", None)
    if blkdebug_name is not None:
        blkdebug_filename = utils_misc.get_path(root_dir, blkdebug_name)
    else:
        blkdebug_filename = None
    return blkdebug_filename


def get_image_filename(params, root_dir, basename=False):
    """
    Generate an image path from params and root_dir.

    :param params: Dictionary containing the test parameters.
    :param root_dir: Base directory for relative filenames.
    :param basename: True to use only basename of image_name

    :note: params should contain:
           image_name -- the name of the image file, without extension
           image_format -- the format of the image (qcow2, raw etc)
    :raise VMDeviceError: When no matching disk found (in indirect method).
    """
    enable_gluster = params.get("enable_gluster", "no") == "yes"
    enable_ceph = params.get("enable_ceph", "no") == "yes"
    enable_iscsi = params.get("enable_iscsi", "no") == "yes"
    image_name = params.get("image_name")
    storage_type = params.get("storage_type")
    if image_name:
        image_format = params.get("image_format", "qcow2")
        if enable_iscsi:
            if storage_type == 'iscsi-direct':
                portal = params.get('portal_ip')
                target = params.get('target')
                lun = params.get('lun', 0)
                user = params.get('chap_user')
                password = params.get('chap_passwd')
                return iscsi.get_image_filename(portal, target, lun,
                                                user, password)
        if enable_gluster:
            return gluster.get_image_filename(params, image_name, image_format)
        if enable_ceph:
            rbd_pool_name = params["rbd_pool_name"]
            rbd_image_name = "%s.%s" % (image_name.split("/")[-1],
                                        image_format)
            ceph_conf = params.get('ceph_conf')
            ceph_monitor = params.get('ceph_monitor')
            return ceph.get_image_filename(ceph_monitor, rbd_pool_name,
                                           rbd_image_name, ceph_conf)
        return get_image_filename_filesytem(params, root_dir, basename=basename)
    else:
        logging.warn("image_name parameter not set.")


def get_image_filename_filesytem(params, root_dir, basename=False):
    """
    Generate an image path from params and root_dir.

    :param params: Dictionary containing the test parameters.
    :param root_dir: Base directory for relative filenames.
    :param basename: True to use only basename of image_name

    :note: params should contain:
           image_name -- the name of the image file, without extension
           image_format -- the format of the image (qcow2, raw etc)
    :raise VMDeviceError: When no matching disk found (in indirect method).
    """
    def sort_cmp(first, second):
        """
        This function used for sort to suit for this test, first sort by len
        then by value.
        """
        def cmp(x, y):
            return (x > y) - (x < y)

        first_contains_digit = re.findall(r'[vhs]d[a-z]*[\d]+', first)
        second_contains_digit = re.findall(r'[vhs]d[a-z]*[\d]+', second)

        if not first_contains_digit and not second_contains_digit:
            if len(first) > len(second):
                return 1
            elif len(first) < len(second):
                return -1
        if len(first) == len(second):
            if first_contains_digit and second_contains_digit:
                return cmp(first, second)
            elif first_contains_digit:
                return -1
            elif second_contains_digit:
                return 1
        return cmp(first, second)

    image_name = params.get("image_name", "image")
    if basename:
        image_name = os.path.basename(image_name)
    indirect_image_select = params.get("indirect_image_select")
    if indirect_image_select:
        re_name = image_name
        indirect_image_select = int(indirect_image_select)
        matching_images = decode_to_text(process.system_output("ls -1d %s" % re_name,
                                                               shell=True))
        matching_images = sorted(matching_images.split('\n'),
                                 key=functools.cmp_to_key(sort_cmp))
        if matching_images[-1] == '':
            matching_images = matching_images[:-1]
        try:
            image_name = matching_images[indirect_image_select]
        except IndexError:
            raise virt_vm.VMDeviceError("No matching disk found for "
                                        "name = '%s', matching = '%s' and "
                                        "selector = '%s'" %
                                        (re_name, matching_images,
                                         indirect_image_select))
        for protected in params.get('indirect_image_blacklist', '').split(' '):
            match_image = re.match(protected, image_name)
            if match_image and match_image.group(0) == image_name:
                # We just need raise an error if it is totally match, such as
                # sda sda1 and so on, but sdaa should not raise an error.
                raise virt_vm.VMDeviceError("Matching disk is in blacklist. "
                                            "name = '%s', matching = '%s' and "
                                            "selector = '%s'" %
                                            (re_name, matching_images,
                                             indirect_image_select))

    image_format = params.get("image_format", "qcow2")
    if params.get("image_raw_device") == "yes":
        return image_name
    if image_format:
        image_filename = "%s.%s" % (image_name, image_format)
    else:
        image_filename = image_name

    image_filename = utils_misc.get_path(root_dir, image_filename)
    return image_filename


secret_dir = os.path.join(data_dir.get_data_dir(), "images/secrets")


def _make_secret_dir():
    """Create image secret directory."""
    try:
        os.makedirs(secret_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class ImageSecret(object):
    """Image secret object."""

    def __init__(self, image, data):
        if not data:
            raise ValueError("Empty image secret for %s" % image)
        self.image_id = image
        self.data = data
        self.filename = os.path.join(secret_dir, "%s.secret" % image)
        self.aid = "%s_%s" % (self.image_id, "encrypt0")

    def __str__(self):
        return self.aid

    @classmethod
    def image_secret_define_by_params(cls, image, params):
        """Get image secret from vt params."""
        image_secret = params.get("image_secret")
        image_format = params.get("image_format")
        image_encryption = params.get("image_encryption")
        if ((image_format == "qcow2" and image_encryption == "luks") or
                image_format == "luks"):
            return cls(image, image_secret)

    def save_to_file(self):
        """Save secret data to file."""
        _make_secret_dir()
        with open(self.filename, "w") as fd:
            fd.write(self.data)


class StorageAuth(object):
    """Image storage authentication class"""

    def __init__(self, image, data, data_format, auth_type):
        self.aid = '%s_access_secret' % image
        self._auth_type = auth_type
        self.filename = os.path.join(secret_dir, "%s.secret" % self.aid)

        if self._auth_type == 'chap':
            self._chap_passwd = data
        elif self._auth_type == 'cephx':
            self._ceph_key = data
        self.data_format = data_format

        if self.data is not None:
            self.save_to_file()

    @property
    def data(self):
        if self._auth_type == 'chap':
            return self._chap_passwd
        elif self._auth_type == 'cephx':
            return self._ceph_key
        else:
            return None

    def save_to_file(self):
        """Save secret data to file."""
        _make_secret_dir()
        with open(self.filename, "w") as fd:
            fd.write(self.data)


class ImageAccessInfo(object):
    """
    iscsi image access: initiator + StorageAuth(u/p)
    ceph image access: StorageAuth(u/p)
    """
    def __init__(self, image, data, data_format, storage_type, initiator=None):
        self.image = image
        self.storage_type = storage_type
        auth_type = None
        if self.storage_type == 'iscsi-direct':
            auth_type = 'chap'
            self.iscsi_initiator = initiator
        elif self.storage_type == 'ceph':
            auth_type = 'cephx'
        self.auth = StorageAuth(self.image, data, data_format,
                                auth_type) if data is not None else None

    @classmethod
    def access_info_define_by_params(cls, image, params):
        enable_ceph = params.get("enable_ceph", "no") == "yes"
        enable_iscsi = params.get("enable_iscsi", "no") == "yes"
        storage_type = params.get("storage_type")
        access_info = None

        if enable_iscsi:
            if storage_type == 'iscsi-direct':
                initiator = params.get('initiator')
                data = params.get('chap_passwd')
                data_format = params.get("data_format", "raw")
                access_info = cls(image, data, data_format, storage_type,
                                  initiator) if data or initiator else None
        elif enable_ceph:
            data = params.get('ceph_key')
            data_format = params.get("data_format", "base64")
            access_info = cls(image, data, data_format,
                              storage_type) if data else None
        return access_info


def retrieve_access_info(image, params):
    """Create image access info object"""
    img_params = params.object_params(image)
    # TODO: get all image access info
    return ImageAccessInfo.access_info_define_by_params(image, img_params)


def retrieve_secrets(image, params):
    """Get all image secrets in image_chain, up to image."""
    secrets = []
    # use image instead if image_chain is empty
    # or no backing image available
    image_chain = params.get("image_chain", "")
    if image not in image_chain:
        image_chain = image
    for img in image_chain.split():
        img_params = params.object_params(img)
        secret = ImageSecret.image_secret_define_by_params(img, img_params)
        if secret:
            secrets.append(secret)
        # NOTE: break here to exclude secrets of snapshots.
        if img == image:
            break
    return secrets


class ImageEncryption(object):
    """Image encryption configuration."""

    __slots__ = ("format", "key_secret", "base_key_secrets",
                 "cipher_alg", "cipher_mode", "ivgen_alg",
                 "ivgen_hash_alg", "hash_alg", "iter_time")

    def __init__(self, encryption_format, key_secret, base_key_secrets,
                 cipher_alg, cipher_mode, ivgen_alg, ivgen_hash_alg, hash_alg,
                 iter_time):
        """
        Initialize image encryption configuration.

        :param encrypt_format: encryption format
        :param key_secret: ImageSecret object for this image
        :param base_key_secrets: ImageSecret objects from its backing images
        :param cipher_alg: name of encryption cipher algorithm
        :param cipher_mode: name of encryption cipher mode
        :param ivgen_alg: name of iv generator algorithm
        :param ivgen_hash_alg: name of iv generator hash algorithm
        :param hash_alg: name of encryption hash algorithm
        :param iter_time: time to spend in PBKDF in milliseconds
        """
        self.format = encryption_format
        self.key_secret = key_secret
        self.base_key_secrets = base_key_secrets
        self.cipher_alg = cipher_alg
        self.cipher_mode = cipher_mode
        self.ivgen_alg = ivgen_alg
        self.ivgen_hash_alg = ivgen_hash_alg
        self.hash_alg = hash_alg
        self.iter_time = iter_time

    def __iter__(self):
        return iter(self.__slots__)

    @classmethod
    def encryption_define_by_params(cls, image, params):
        """Get image encryption from vt params."""
        encryption_format = params.get("image_encryption")
        key_secrets = retrieve_secrets(image, params)
        key_secret = None
        if key_secrets and key_secrets[-1].image_id == image:
            key_secret = key_secrets.pop()
        cipher_alg = params.get("image_cipher_alg")
        cipher_mode = params.get("image_cipher_mode")
        ivgen_alg = params.get("image_ivgen_alg")
        ivgen_hash_alg = params.get("image_ivgen_hash_alg")
        hash_alg = params.get("image_hash_alg")
        iter_time = params.get("image_iter_time")
        return cls(encryption_format, key_secret, key_secrets, cipher_alg,
                   cipher_mode, ivgen_alg, ivgen_hash_alg, hash_alg, iter_time)

    @property
    def image_key_secrets(self):
        """All image secrets required to use this image."""
        if self.key_secret:
            return self.base_key_secrets + [self.key_secret]
        return self.base_key_secrets


def copy_nfs_image(params, root_dir, basename=False):
    """
    copy image from image_path to nfs mount dir if image is not available
    or corrupted.

    :param params: Test dict params
    :param root_dir: Base directory for relative filenames.
    :param basename: True to use only basename of image name
    :raise: TestSetupFail if image is unavailable/corrupted
    """
    if params.get("setup_local_nfs", "no") == "yes":
        # check for image availability in NFS shared path
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        dst = get_image_filename(params, base_dir, basename=basename)
        if(not os.path.isfile(dst) or
           utils_misc.get_image_info(dst)['lcounts'].lower() == "true"):
            source = get_image_filename(params, root_dir)
            logging.debug("Checking for image available in image data "
                          "path - %s", source)
            # check for image availability in images data directory
            if(os.path.isfile(source) and not
               utils_misc.get_image_info(source)['lcounts'].lower() == "true"):
                logging.debug("Copying guest image from %s to %s", source,
                              dst)
                shutil.copy(source, dst)
            else:
                raise exceptions.TestSetupFail("Guest image is unavailable"
                                               "/corrupted in %s and %s" %
                                               (source, dst))


class OptionMissing(Exception):

    """
    Option not found in the odbject
    """

    def __init__(self, option):
        self.option = option

    def __str__(self):
        return "%s is missing. Please check your parameters" % self.option


class QemuImg(object):

    """
    A basic class for handling operations of disk/block images.
    """

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images.
        """
        self.params = params
        self.image_filename = get_image_filename(params, root_dir)
        self.image_format = params.get("image_format", "qcow2")
        self.size = params.get("image_size", "10G")
        self.storage_type = params.get("storage_type", "local fs")
        self.check_output = params.get("check_output") == "yes"
        self.image_blkdebug_filename = get_image_blkdebug_filename(params,
                                                                   root_dir)
        self.remote_keywords = params.get("remote_image",
                                          "gluster iscsi rbd").split()
        self.encryption_config = ImageEncryption.encryption_define_by_params(
            tag, params)
        image_chain = params.get("image_chain")
        self.tag = tag
        self.root_dir = root_dir
        self.base_tag = None
        self.snapshot_tag = None
        if image_chain:
            image_chain = re.split(r"\s+", image_chain)
            if tag in image_chain:
                index = image_chain.index(tag)
                if index < len(image_chain) - 1:
                    self.snapshot_tag = image_chain[index + 1]
                if index > 0:
                    self.base_tag = image_chain[index - 1]
        if self.base_tag:
            base_params = params.object_params(self.base_tag)
            self.base_image_filename = get_image_filename(base_params,
                                                          root_dir)
            self.base_format = base_params.get("image_format")
        if self.snapshot_tag:
            ss_params = params.object_params(self.snapshot_tag)
            self.snapshot_image_filename = get_image_filename(ss_params,
                                                              root_dir)
            self.snapshot_format = ss_params.get("image_format")

        self.image_access = retrieve_access_info(self.tag, self.params)

    def _get_access_secret_info(self):
        access_secret, secret_type = None, None
        if self.image_access is not None:
            if self.image_access.auth is not None:
                if self.image_access.storage_type == 'ceph':
                    # Only ceph image access requires secret object by
                    # qemu-img and only 'password-secret' is supported
                    access_secret = self.image_access.auth
                    secret_type = 'password'
        return access_secret, secret_type

    def check_option(self, option):
        """
        Check if object has the option required.

        :param option: option should be checked
        """
        if option not in self.__dict__:
            raise OptionMissing(option)

    def is_remote_image(self):
        """
        Check if image is from a remote server or not
        """

        for keyword in self.remote_keywords:
            if self.image_filename.startswith(keyword):
                return True

        return False

    def backup_image(self, params, root_dir, action, good=True,
                     skip_existing=False):
        """
        Backup or restore a disk image, depending on the action chosen.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param action: Whether we want to backup or restore the image.
        :param good: If we are backing up a good image(we want to restore it)
            or a bad image (we are saving a bad image for posterior analysis).

        :note: params should contain:
               image_name -- the name of the image file, without extension
               image_format -- the format of the image (qcow2, raw etc)
        """
        def get_backup_set(filename, backup_dir, action, good):
            """
            Get all sources and destinations required for each backup.
            """
            if not os.path.isdir(backup_dir):
                os.makedirs(backup_dir)
            basename = os.path.basename(filename)
            bkp_set = []
            if action not in ('backup', 'restore'):
                logging.error("No backup sets for action: %s, state: %s",
                              action, good)
                return bkp_set
            if good:
                src = filename
                dst = os.path.join(backup_dir, "%s.backup" % basename)
                if action == 'backup':
                    bkp_set = [[src, dst]]
                elif action == 'restore':
                    bkp_set = [[dst, src]]
            else:
                # We have to make 2 backups, one of the bad image, another one
                # of the good image
                src_bad = filename
                src_good = os.path.join(backup_dir, "%s.backup" % basename)
                hsh = utils_misc.generate_random_string(4)
                dst_bad = (os.path.join(backup_dir, "%s.bad.%s" %
                                        (basename, hsh)))
                dst_good = (os.path.join(backup_dir, "%s.good.%s" %
                                         (basename, hsh)))
                if action == 'backup':
                    bkp_set = [[src_bad, dst_bad], [src_good, dst_good]]
                elif action == 'restore':
                    bkp_set = [[src_good, src_bad]]
            return bkp_set

        backup_dir = params.get("backup_dir", "")
        if not os.path.isabs(backup_dir):
            backup_dir = os.path.join(root_dir, backup_dir)
        if self.is_remote_image():
            backup_set = get_backup_set(self.image_filename, backup_dir,
                                        action, good)
            backup_func = self.copy_data_remote
        elif params.get('image_raw_device') == 'yes':
            ifmt = params.get("image_format", "qcow2")
            ifilename = utils_misc.get_path(root_dir, ("raw_device.%s" % ifmt))
            backup_set = get_backup_set(ifilename, backup_dir, action, good)
            backup_func = self.copy_data_raw
        else:
            backup_set = get_backup_set(self.image_filename, backup_dir,
                                        action, good)
            backup_func = self.copy_data_file

        if action == 'backup':
            backup_size = 0
            for src, dst in backup_set:
                if os.path.isfile(src):
                    backup_size += os.path.getsize(src)
                else:
                    # TODO: get the size of block/remote images
                    backup_size += int(float(utils_numeric.normalize_data_size(
                                             self.size, order_magnitude="B")))

            s = os.statvfs(backup_dir)
            image_dir_free_disk_size = s.f_bavail * s.f_bsize
            logging.info("backup image size: %d, available size: %d.",
                         backup_size, image_dir_free_disk_size)
            if not self.is_disk_size_enough(backup_size,
                                            image_dir_free_disk_size):
                return

        # backup secret file if presented
        if self.encryption_config.key_secret:
            bk_set = get_backup_set(self.encryption_config.key_secret.filename,
                                    secret_dir, action, good)
            for src, dst in bk_set:
                self.copy_data_file(src, dst)

        for src, dst in backup_set:
            if action == 'backup' and skip_existing and os.path.exists(dst):
                logging.debug("Image backup %s already exists, skipping...",
                              dst)
                continue
            backup_func(src, dst)

    def rm_backup_image(self):
        """
        Remove backup image
        """
        backup_dir = utils_misc.get_path(self.root_dir,
                                         self.params.get("backup_dir", ""))
        image_name = os.path.join(backup_dir, "%s.backup" %
                                  os.path.basename(self.image_filename))
        logging.debug("Removing image file %s as requested", image_name)
        if os.path.exists(image_name):
            os.unlink(image_name)
        else:
            logging.warning("Image file %s not found", image_name)

    def save_image(self, params, filename, root_dir=None):
        """
        Save images to a path for later debugging.

        :param params: Dictionary containing the test parameters.
        :param filename: new filename for saved images.
        :param root_dir: directory for saved images.

        """
        src = self.image_filename
        if root_dir is None:
            root_dir = os.path.dirname(src)
        backup_func = self.copy_data_file
        if self.is_remote_image():
            backup_func = self.copy_data_remote
        elif params.get('image_raw_device') == 'yes':
            ifmt = params.get("image_format", "qcow2")
            src = utils_misc.get_path(root_dir, ("raw_device.%s" % ifmt))
            backup_func = self.copy_data_raw

        backup_size = 0
        if os.path.isfile(src):
            backup_size = os.path.getsize(src)
        else:
            # TODO: get the size of block/remote images
            backup_size += int(float(utils_numeric.normalize_data_size(
                                     self.size, order_magnitude="B")))
        s = os.statvfs(root_dir)
        image_dir_free_disk_size = s.f_bavail * s.f_bsize
        logging.info("Checking disk size on %s.", root_dir)
        if not self.is_disk_size_enough(backup_size,
                                        image_dir_free_disk_size):
            return

        backup_func(src, utils_misc.get_path(root_dir, filename))

    @staticmethod
    def is_disk_size_enough(required, available):
        """Check if available disk size is enough for the data copy."""
        minimum_disk_free = 1.2 * required
        if available < minimum_disk_free:
            logging.error("Free space: %s MB", (available / 1048576.))
            logging.error("Backup size: %s MB", (required / 1048576.))
            logging.error("Minimum free space acceptable: %s MB",
                          (minimum_disk_free / 1048576.))
            logging.error("Available disk space is not enough. Skipping...")
            return False
        return True

    def copy_data_remote(self, src, dst):
        pass

    @staticmethod
    def copy_data_raw(src, dst):
        """Using dd for raw device."""
        if os.path.exists(src):
            _dst = dst + '.part'
            process.system("dd if=%s of=%s bs=4k conv=sync" % (src, _dst))
            os.rename(_dst, dst)
        else:
            logging.info("No source %s, skipping dd...", src)

    @staticmethod
    def copy_data_file(src, dst):
        """Copy for files."""
        if os.path.isfile(src):
            logging.debug("Copying %s -> %s", src, dst)
            _dst = dst + '.part'
            shutil.copy(src, _dst)
            os.rename(_dst, dst)
        else:
            logging.info("No source file %s, skipping copy...", src)

    @staticmethod
    def clone_image(params, vm_name, image_name, root_dir):
        """
        Clone master image to vm specific file.

        :param params: Dictionary containing the test parameters.
        :param vm_name: Vm name.
        :param image_name: Master image name.
        :param root_dir: Base directory for relative filenames.
        """
        if not params.get("image_name_%s_%s" % (image_name, vm_name)):
            m_image_name = params.get("image_name", "image")
            vm_image_name = params.get("image_name_%s" % vm_name, "%s_%s" % (m_image_name, vm_name))
            if params.get("clone_master", "yes") == "yes":
                image_params = params.object_params(image_name)
                image_params["image_name"] = vm_image_name

                master_image = params.get("master_image_name")
                if master_image:
                    image_format = params.get("image_format", "qcow2")
                    m_image_fn = "%s.%s" % (master_image, image_format)
                    m_image_fn = utils_misc.get_path(root_dir, m_image_fn)
                else:
                    m_image_fn = get_image_filename(params, root_dir)
                image_fn = get_image_filename(image_params, root_dir)
                force_clone = params.get("force_image_clone", "no")
                if not os.path.exists(image_fn) or force_clone == "yes":
                    logging.info("Clone master image for vms.")
                    process.run(params.get("image_clone_command") %
                                (m_image_fn, image_fn))
            params["image_name_%s" % vm_name] = vm_image_name
            params["image_name_%s_%s" % (image_name, vm_name)] = vm_image_name

    @staticmethod
    def rm_cloned_image(params, vm_name, image_name, root_dir):
        """
        Remove vm specific file.

        :param params: Dictionary containing the test parameters.
        :param vm_name: Vm name.
        :param image_name: Master image name.
        :param root_dir: Base directory for relative filenames.
        """
        if params.get("image_name_%s_%s" % (image_name, vm_name)):
            m_image_name = params.get("image_name", "image")
            vm_image_name = "%s_%s" % (m_image_name, vm_name)
            if params.get("clone_master", "yes") == "yes":
                image_params = params.object_params(image_name)
                image_params["image_name"] = vm_image_name

                image_fn = get_image_filename(image_params, root_dir)

                logging.debug("Removing vm specific image file %s", image_fn)
                if os.path.exists(image_fn):
                    process.run(params.get("image_remove_command") % (image_fn))
                else:
                    logging.debug("Image file %s not found", image_fn)


class Rawdev(object):

    """
    Base class for raw storage devices such as iscsi and local disks
    """

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images
        """
        host_set_flag = params.get("host_setup_flag")
        if host_set_flag is not None:
            self.exec_cleanup = int(host_set_flag) & 2 == 2
        else:
            self.exec_cleanup = False
        if params.get("force_cleanup") == "yes":
            self.exec_cleanup = True
        self.image_name = tag


class Iscsidev(Rawdev):

    """
    Class for handle iscsi devices for VM
    """

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images
        """
        Rawdev.__init__(self, params, root_dir, tag)
        self.emulated_file_remove = False
        self.emulated_image = params.get("emulated_image")
        if self.emulated_image:
            self.emulated_image = os.path.join(root_dir, self.emulated_image)
            if params.get("emulated_file_remove", "no") == "yes":
                self.emulated_file_remove = True
        params["iscsi_thread_id"] = self.image_name
        self.iscsidevice = iscsi.Iscsi.create_iSCSI(params, root_dir=root_dir)
        self.device_id = params.get("device_id")
        self.iscsi_init_timeout = int(params.get("iscsi_init_timeout", 10))


class LVMdev(Rawdev):

    """
    Class for handle LVM devices for VM
    """

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images
        """
        super(LVMdev, self).__init__(params, root_dir, tag)
        if params.get("emulational_device", "yes") == "yes":
            self.lvmdevice = lvm.EmulatedLVM(params, root_dir=root_dir)
        else:
            self.lvmdevice = lvm.LVM(params)
