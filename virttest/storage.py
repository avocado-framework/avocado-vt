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
import collections
import json

from avocado.core import exceptions
from avocado.utils import process

from virttest import storage_ssh
from virttest import nbd
from virttest import curl
from virttest import iscsi
from virttest import utils_misc
from virttest import utils_numeric
from virttest import utils_params
from virttest import virt_vm
from virttest import gluster
from virttest import lvm
from virttest import ceph
from virttest import nvme
from virttest import data_dir

LOG = logging.getLogger('avocado.' + __name__)


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
    enable_gluster = params.get("enable_gluster") == "yes"
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
    if params.get("enable_gluster") == "yes":
        return gluster.file_exists(params, filename_path)

    if params.get("enable_ceph") == "yes":
        image_name = params.get("image_name")
        image_format = params.get("image_format", "qcow2")
        ceph_monitor = params.get("ceph_monitor")
        rbd_pool_name = params["rbd_pool_name"]
        rbd_namespace_name = params.get("rbd_namespace_name")
        rbd_image_name = "%s.%s" % (image_name.split("/")[-1], image_format)
        ceph_conf = params.get("ceph_conf")
        keyring_conf = params.get("image_ceph_keyring_conf")
        return ceph.rbd_image_exist(ceph_monitor, rbd_pool_name, rbd_image_name,
                                    ceph_conf, keyring_conf, rbd_namespace_name)

    if params.get('enable_nvme') == 'yes':
        return nvme.file_exists(params, filename_path)

    if params.get('enable_ssh') == 'yes':
        return storage_ssh.file_exists(params, filename_path)

    if params.get('enable_curl') == 'yes':
        return curl.file_exists(params, filename_path)

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
        rbd_namespace_name = params.get("rbd_namespace_name")
        rbd_image_name = "%s.%s" % (image_name.split("/")[-1], image_format)
        ceph_conf = params.get("ceph_conf")
        keyring_conf = params.get("image_ceph_keyring_conf")
        return ceph.rbd_image_rm(ceph_monitor, rbd_pool_name, rbd_image_name,
                                 ceph_conf, keyring_conf, rbd_namespace_name)

    if params.get("gluster_brick"):
        # TODO: Add implementation for gluster_brick
        return

    if params.get('storage_type') in ('iscsi', 'lvm', 'iscsi-direct'):
        # TODO: Add implementation for iscsi/lvm
        return

    # skip removing raw device
    if params.get('image_raw_device') == 'yes':
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
    enable_ssh = params.get("enable_ssh") == "yes"
    enable_curl = params.get("enable_curl") == "yes"
    enable_nbd = params.get("enable_nbd") == "yes"
    enable_gluster = params.get("enable_gluster") == "yes"
    enable_ceph = params.get("enable_ceph") == "yes"
    enable_iscsi = params.get("enable_iscsi") == "yes"
    enable_nvme = params.get("enable_nvme") == "yes"
    image_name = params.get("image_name")
    storage_type = params.get("storage_type")
    if image_name:
        image_format = params.get("image_format", "qcow2")
        if enable_curl:
            # required libcurl params
            curl_protocol = params['curl_protocol']
            curl_server = params['curl_server']
            curl_path = params['curl_path']

            # optional libcurl params
            curl_user = params.get('curl_username')
            curl_passwd = params.get('curl_password')

            return curl.get_image_filename(curl_protocol, curl_server,
                                           curl_path, curl_user, curl_passwd)
        if enable_nbd:
            return nbd.get_image_filename(params)
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
            rbd_namespace_name = params.get("rbd_namespace_name")
            rbd_image_name = "%s.%s" % (image_name.split("/")[-1],
                                        image_format)
            ceph_conf = params.get('ceph_conf')
            ceph_monitor = params.get('ceph_monitor')
            return ceph.get_image_filename(ceph_monitor, rbd_pool_name,
                                           rbd_image_name, ceph_conf,
                                           rbd_namespace_name)
        if enable_nvme:
            address = params['nvme_pci_address']
            namespace = params.get('nvme_namespace', 1)
            return nvme.get_image_filename(address, namespace)
        if enable_ssh:
            # required libssh options
            server = params['image_ssh_host']
            ssh_image_path = params['image_ssh_path']

            # optional libssh options
            user = params.get('image_ssh_user')
            port = params.get('image_ssh_port')
            host_key_check = params.get('image_ssh_host_key_check')

            return storage_ssh.get_image_filename(server, ssh_image_path,
                                                  user, port, host_key_check)
        return get_image_filename_filesytem(params, root_dir, basename=basename)
    else:
        LOG.warn("image_name parameter not set.")


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
        matching_images = process.run("ls -1d %s" % re_name,
                                      shell=True).stdout_text
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


def get_iso_filename(cdrom_params, root_dir, basename=False):
    """
    Generate an iso image path from params and root_dir.

    :param cdrom_params: Dictionary containing the test parameters.
    :param root_dir: Base directory for relative iso image.
    :param basename: True to use only basename of iso image.
    :return: iso filename
    """
    enable_nvme = cdrom_params.get("enable_nvme") == "yes"
    enable_nbd = cdrom_params.get("enable_nbd") == "yes"
    enable_gluster = cdrom_params.get("enable_gluster") == "yes"
    enable_ceph = cdrom_params.get("enable_ceph") == "yes"
    enable_iscsi = cdrom_params.get("enable_iscsi") == "yes"
    enable_curl = cdrom_params.get("enable_curl") == "yes"
    enable_ssh = cdrom_params.get("enable_ssh") == "yes"

    if enable_nvme:
        return None
    elif any((enable_nbd, enable_gluster, enable_ceph,
              enable_iscsi, enable_curl, enable_ssh)):
        return get_image_filename(cdrom_params, None, basename)
    else:
        iso = cdrom_params.get("cdrom")
        if iso:
            iso = os.path.basename(iso) if basename else utils_misc.get_path(
                root_dir, iso)
        return iso


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


class Cookie(object):
    """
    Cookie data stored in secret object
    """

    def __init__(self, image, cookie_data, cookie_data_format):
        """
        :param image: image tag name
        :param cookie_data: cookie data string
        :param cookie_data_format: raw or base64
        """
        self.image = image
        self.data = cookie_data
        self.data_format = cookie_data_format
        self.aid = '%s_cookie_secret' % self.image
        self.filename = os.path.join(secret_dir, "%s.secret" % self.aid)
        self.save_to_file()

    def save_to_file(self):
        """Save secret data to file."""
        _make_secret_dir()
        with open(self.filename, "w") as fd:
            fd.write(self.data)


class StorageAuth(object):
    """
    Image storage authentication class.
    iscsi auth: initiator + password
    ceph auth: ceph key
    nbd auth: tls creds
    libcurl auth: password sslverify timeout readahead cookie
    """

    def __init__(self, image, data, data_format, storage_type, **info):
        """
        :param image: image tag name
        :param data: sensitive data like password
        :param data_format: raw or base64
        :param storage_type: ceph, glusterfs-direct, iscsi-direct, nbd, curl
        :param info: other access information, such as:
                     iscsi-direct: initiator
                     gluster-direct: debug, logfile, peers
                     nbd: tls creds path for client access
                     libcurl: password, sslverify, timeout, readahead, cookie
        """
        self.image = image
        self.aid = '%s_access' % self.image
        self.storage_type = storage_type
        self.filename = os.path.join(secret_dir, "%s.secret" % self.aid)
        self.data_format = data_format

        if self.storage_type == 'iscsi-direct':
            self._chap_passwd = data
            self.iscsi_initiator = info.get('initiator')
        elif self.storage_type == 'ceph':
            self._ceph_key = data
        elif self.storage_type == 'glusterfs-direct':
            self.peers = info['peers']

            # TODO: logfile and debug will be moved to a class,
            # they'll be defined as common options for all backends
            self.debug = info['debug']
            self.logfile = info['logfile']
        elif self.storage_type == 'nbd':
            # TODO: now we only support tls-creds-x509, we can add a
            # param 'nbd_tls_creds_object' to differentiate objects,
            # e.g. tls-creds-psk
            self.tls_creds = info['tls_creds']
            self.reconnect_delay = info['reconnect_delay']
        elif self.storage_type == 'curl':
            self._password = data
            self.cookie = info['cookie']
            self.sslverify = info['sslverify']
            self.readahead = info['readahead']
            self.timeout = info['timeout']

        if self.data is not None:
            self.filename = os.path.join(secret_dir, "%s.secret" % self.aid)
            self.save_to_file()

    @property
    def data(self):
        if self.storage_type == 'iscsi-direct':
            return self._chap_passwd
        elif self.storage_type == 'ceph':
            return self._ceph_key
        elif self.storage_type == 'curl':
            return self._password
        else:
            return None

    def save_to_file(self):
        """Save secret data to file."""
        _make_secret_dir()
        with open(self.filename, "w") as fd:
            fd.write(self.data)

    @classmethod
    def auth_info_define_by_params(cls, image, params):
        """
        :param image: image tag name
        :param params: image specified parmas, i.e. params.object_params(image)
        """
        auth = None
        storage_type = params.get("storage_type")
        enable_ceph = params.get("enable_ceph") == "yes"
        enable_iscsi = params.get("enable_iscsi") == "yes"
        enable_gluster = params.get("enable_gluster") == "yes"
        enable_nbd = params.get("enable_nbd") == "yes"
        enable_curl = params.get("enable_curl") == "yes"

        if enable_iscsi:
            if storage_type == 'iscsi-direct':
                initiator = params.get('initiator')
                data = params.get('chap_passwd')
                data_format = params.get('data_format', 'raw')
                auth = cls(image, data, data_format, storage_type,
                           initiator=initiator) if data or initiator else None
        elif enable_ceph:
            data = params.get('ceph_key')
            data_format = params.get('data_format', 'base64')
            auth = cls(image, data, data_format,
                       storage_type) if data else None
        elif enable_gluster:
            if storage_type == 'glusterfs-direct':
                peers = json.loads(params.get('gluster_peers', '[]'))
                debug = params.get('gluster_debug')
                logfile = params.get('gluster_logfile')
                auth = cls(image, None, None, storage_type,
                           debug=debug, logfile=logfile,
                           peers=peers) if debug or logfile or peers else None
        elif enable_nbd:
            # tls-creds is supported for ip only
            tls_creds = params.get(
                'nbd_client_tls_creds') if params.get('nbd_server') else None
            reconnect_delay = params.get('nbd_reconnect_delay')
            auth = cls(
                image, None, None, storage_type,
                tls_creds=tls_creds, reconnect_delay=reconnect_delay
            ) if tls_creds or reconnect_delay else None
        elif enable_curl:
            # cookie data in a secure way, only for http/https
            cookie = Cookie(
                image, params['curl_cookie_secret'],
                params.get('curl_cookie_secret_format', 'raw'),
            ) if params.get('curl_cookie_secret') else None

            # sslverify, only for https/ftps
            sslverify = params.get('curl_sslverify')

            # size of the read-ahead cache
            readahead = int(float(
                utils_numeric.normalize_data_size(params['curl_readahead'],
                                                  order_magnitude="B")
            )) if params.get('curl_readahead') else None

            # timeout for connections in seconds
            timeout = params.get('curl_timeout')

            # password
            data = params.get('curl_password')
            data_format = params.get('curl_password_format', 'raw')

            if any((data, cookie, sslverify, readahead, timeout)):
                auth = cls(image, data, data_format, storage_type,
                           cookie=cookie, sslverify=sslverify,
                           readahead=readahead, timeout=timeout)

        return auth


class ImageAccessInfo(object):
    """
    Access info to the logical image, which can include the network
    storage image only, or the image and its backing images.
    """

    def __init__(self, image, image_auth, image_backing_auth):
        """
        :param image: image tag name
        :param image_auth: StorageAuth object to access image itself
        :param image_backing_auth: a dict({image: StorageAuth object}),
                                   used for accessing the backing images
        """
        self.image = image
        self.image_auth = image_auth
        self.image_backing_auth = image_backing_auth

    @classmethod
    def access_info_define_by_params(cls, image, params):
        """
        :param image: image tag name
        :param params: a dict containing the test parameters

        :return: an ImageAccessInfo object or None
        """
        access_info = None
        info = retrieve_access_info(image, params)

        if info:
            access = info.pop(image, None)
            access_info = cls(image, access, info)

        return access_info


def retrieve_access_info(image, params):
    """
    Create the image and its backing images' access info objects,
    keep the same order as the images in the image_chain.

    :param image: image tag name
    :param params: a dict containing the test parameters

    :return: A dict({image: StorageAuth object or None})
    """
    access_info = collections.OrderedDict()
    image_chain = params.objects("image_chain")
    images = image_chain if image_chain else [image]

    for img in images:
        auth = StorageAuth.auth_info_define_by_params(
            img, params.object_params(img))
        if auth is not None:
            access_info[img] = auth

        if img == image:
            # ignore image's snapshot images
            break

    return access_info


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
        base_dir = params["nfs_mount_dir"]
        dst = get_image_filename(params, base_dir, basename=basename)
        if(not os.path.isfile(dst) or
           utils_misc.get_image_info(dst)['lcounts'].lower() == "true"):
            source = get_image_filename(params, root_dir)
            LOG.debug("Checking for image available in image data "
                      "path - %s", source)
            # check for image availability in images data directory
            if(os.path.isfile(source) and not
               utils_misc.get_image_info(source)['lcounts'].lower() == "true"):
                LOG.debug("Copying guest image from %s to %s", source, dst)
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
        self.remote_keywords = params.get(
            "remote_image",
            "gluster iscsi rbd nbd nvme http https ftp ftps"
        ).split()
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

        self.image_access = ImageAccessInfo.access_info_define_by_params(
            self.tag, self.params)

        self.data_file = self.external_data_file_defined_by_params(
            params, root_dir, tag)

    @classmethod
    def external_data_file_defined_by_params(cls, params, root_dir, tag):
        """Link image to an external data file."""
        enable_data_file = params.get("enable_data_file", "no") == "yes"
        image_format = params.get("image_format", "qcow2")
        if not enable_data_file:
            return
        if image_format != "qcow2":
            raise ValueError("The %s format does not support external "
                             "data file" % image_format)
        image_size = params["image_size"]
        base_name = os.path.basename(params["image_name"])
        data_file_path = params.get("image_data_file_path",
                                    os.path.join(root_dir, "images",
                                                 "%s.data_file"
                                                 % base_name))
        data_file_params = utils_params.Params(
            {"image_name": data_file_path,
             "image_format": "raw",
             "image_size": image_size,
             "image_raw_device": "yes"})
        return cls(data_file_params, root_dir, "%s_data_file" % tag)

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
                LOG.error("No backup sets for action: %s, state: %s",
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
        backup_set = get_backup_set(self.image_filename, backup_dir,
                                    action, good)
        if self.is_remote_image():
            backup_func = self.copy_data_remote
        elif params.get('image_raw_device') == 'yes':
            backup_func = self.copy_data_raw
        else:
            backup_func = self.copy_data_file

        if action == 'backup':
            backup_size = 0
            for src, dst in backup_set:
                if os.path.isfile(src):
                    backup_size += os.path.getsize(src)
                else:
                    # TODO: get the size of block/remote images
                    if self.size:
                        backup_size += int(
                            float(utils_numeric.normalize_data_size(
                                self.size, order_magnitude="B"))
                        )

            s = os.statvfs(backup_dir)
            image_dir_free_disk_size = s.f_bavail * s.f_bsize
            LOG.info("backup image size: %d, available size: %d.",
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

        # backup external data file
        if self.data_file:
            self.data_file.backup_image(self.data_file.params, root_dir,
                                        action, good, skip_existing)

        for src, dst in backup_set:
            if action == 'backup' and skip_existing and os.path.exists(dst):
                LOG.debug("Image backup %s already exists, skipping...", dst)
                continue
            backup_func(src, dst)

    def rm_backup_image(self):
        """
        Remove backup image
        """
        # remove external data file backup
        if self.data_file:
            self.data_file.rm_backup_image()

        backup_dir = utils_misc.get_path(self.root_dir,
                                         self.params.get("backup_dir", ""))
        image_name = os.path.join(backup_dir, "%s.backup" %
                                  os.path.basename(self.image_filename))
        LOG.debug("Removing image file %s as requested", image_name)
        if os.path.exists(image_name):
            os.unlink(image_name)
        else:
            LOG.warning("Image file %s not found", image_name)

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
            backup_func = self.copy_data_raw

        backup_size = 0
        if os.path.isfile(src):
            backup_size = os.path.getsize(src)
        else:
            # TODO: get the size of block/remote images
            if self.size:
                backup_size += int(
                    float(utils_numeric.normalize_data_size(
                        self.size, order_magnitude="B"))
                )
        s = os.statvfs(root_dir)
        image_dir_free_disk_size = s.f_bavail * s.f_bsize
        LOG.info("Checking disk size on %s.", root_dir)
        if not self.is_disk_size_enough(backup_size,
                                        image_dir_free_disk_size):
            return

        backup_func(src, utils_misc.get_path(root_dir, filename))

    @staticmethod
    def is_disk_size_enough(required, available):
        """Check if available disk size is enough for the data copy."""
        minimum_disk_free = 1.2 * required
        if available < minimum_disk_free:
            LOG.error("Free space: %s MB", (available / 1048576.))
            LOG.error("Backup size: %s MB", (required / 1048576.))
            LOG.error("Minimum free space acceptable: %s MB",
                      (minimum_disk_free / 1048576.))
            LOG.error("Available disk space is not enough. Skipping...")
            return False
        return True

    def copy_data_remote(self, src, dst):
        pass

    @staticmethod
    def copy_data_raw(src, dst):
        """Using dd for raw device."""
        if os.path.exists(src):
            process.system("dd if=%s of=%s bs=4k conv=sync" % (src, dst))
        else:
            LOG.info("No source %s, skipping dd...", src)

    @staticmethod
    def copy_data_file(src, dst):
        """Copy for files."""
        if os.path.isfile(src):
            LOG.debug("Copying %s -> %s", src, dst)
            _dst = dst + '.part'
            shutil.copy(src, _dst)
            os.rename(_dst, dst)
        else:
            LOG.info("No source file %s, skipping copy...", src)

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
                    LOG.info("Clone master image for vms.")
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

                LOG.debug("Removing vm specific image file %s", image_fn)
                if os.path.exists(image_fn):
                    process.run(params.get("image_remove_command") % (image_fn))
                else:
                    LOG.debug("Image file %s not found", image_fn)


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
