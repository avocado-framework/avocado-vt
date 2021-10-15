"""
Classes and functions to handle block/disk images for KVM.

This exports:
  - two functions for get image/blkdebug filename
  - class for image operates and basic parameters
"""
import collections
import json
import logging
import os
import re
import six
import string

from avocado.core import exceptions
from avocado.utils import process

from virttest import utils_misc
from virttest import virt_vm
from virttest import storage
from virttest import nvme
from virttest import data_dir
from virttest import error_context

LOG = logging.getLogger('avocado.' + __name__)


def filename_to_file_opts(filename):
    """Convert filename into file opts, used by both qemu-img and qemu-kvm"""
    file_opts = {}
    if not filename:
        file_opts = {}
    elif filename.startswith('iscsi:'):
        filename_pattern = re.compile(
            r'iscsi://((?P<user>.+?):(?P<password>.+?)@)?(?P<portal>.+)/(?P<target>.+?)/(?P<lun>\d+)')
        matches = filename_pattern.match(filename)
        if matches:
            if (matches.group('portal') is not None
                    and matches.group('target') is not None
                    and matches.group('lun') is not None):
                # required options for iscsi
                file_opts = {'driver': 'iscsi',
                             'transport': 'tcp',
                             'portal': matches.group('portal'),
                             'target': matches.group('target'),
                             'lun': int(matches.group('lun'))}
                if matches.group('user') is not None:
                    # optional option
                    file_opts['user'] = matches.group('user')
    elif filename.startswith('rbd:'):
        filename_pattern = re.compile(
            r'rbd:(?P<pool>.+?)/(?P<namespace>.+?(?=/))?/?(?P<image>[^:]+)'
            r'(:conf=(?P<conf>.+))?'
        )
        matches = filename_pattern.match(filename)
        if matches:
            if (matches.group('pool') is not None
                    and matches.group('image') is not None):
                # required options for rbd
                file_opts = {'driver': 'rbd',
                             'pool': matches.group('pool'),
                             'image': matches.group('image')}
                if matches.group('conf') is not None:
                    # optional option
                    file_opts['conf'] = matches.group('conf')
                if matches.group('namespace') is not None:
                    # optional option
                    file_opts['namespace'] = matches.group('namespace')
    elif filename.startswith('gluster'):
        filename_pattern = re.compile(
            r'gluster\+?(?P<type>.+)?://((?P<host>[^/]+?)(:(?P<port>\d+))?)?/'
            r'(?P<volume>.+?)/(?P<path>[^,?]+)'
            r'(\?socket=(?P<socket>[^,]+))?'
        )
        matches = filename_pattern.match(filename)
        if matches:
            servers = []
            transport = 'inet' if not matches.group('type') or matches.group('type') == 'tcp' else matches.group('type')

            if matches.group('host'):
                # 'IPv4/hostname' or '[IPv6 address]'
                host = matches.group('host').strip('[]')

                # port should be set for both qemu-img and qemu-kvm
                port = matches.group('port') if matches.group('port') else '0'

                servers.append({'type': transport,
                                'host': host,
                                'port': port})
            elif matches.group('socket'):
                servers.append({'type': transport,
                                'path': matches.group('socket')})

            if matches.group('volume') and matches.group('path') and servers:
                # required options for gluster
                file_opts = {'driver': 'gluster',
                             'volume': matches.group('volume'),
                             'path': matches.group('path')}
                file_opts.update({'server.{i}.{k}'.format(i=i, k=k): v
                                  for i, server in enumerate(servers)
                                  for k, v in six.iteritems(server)})
    elif re.match(r'nbd(\+\w+)?://', filename):
        filename_pattern = re.compile(
            r'nbd(\+(?:.+))?://((?P<host>[^/:?]+)(:(?P<port>\d+))?)?'
            r'(/(?P<export>[^?]+))?'
            r'(\?socket=(?P<socket>.+))?'
        )
        matches = filename_pattern.match(filename)
        if matches:
            server = {}
            host = matches.group('host')
            sock = matches.group('socket')

            if host:
                # 10890 is the default port for tcp connection
                port = matches.group('port') if matches.group(
                    'port') else '10809'
                server = {'server.type': 'inet',
                          'server.host': host,
                          'server.port': port}
            elif sock:
                server = {'server.type': 'unix', 'server.path': sock}

            if server:
                # server is required
                file_opts = {'driver': 'nbd'}
                file_opts.update(server)

                if matches.group('export'):
                    file_opts['export'] = matches.group('export')
    elif filename.startswith('nvme:'):
        addr, namespace = nvme.parse_uri(filename)
        file_opts = {'driver': 'nvme', 'device': addr, 'namespace': int(namespace)}
    elif filename.startswith('ssh:'):
        filename_pattern = re.compile(
            r'ssh://((?P<user>.+)@)?(?P<host>[^/:?]+)(:(?P<port>\d+))?'
            r'(?P<path>/[^?]+)'
            r'(\?host_key_check=(?P<host_key_check>.+))?'
        )
        matches = filename_pattern.match(filename)
        if matches:
            matches = matches.groupdict()
            if matches['host'] is not None and matches['path'] is not None:
                # required ssh options
                file_opts = {
                    'driver': 'ssh',
                    'server.host': matches['host'],
                    'server.port': matches['port'] if matches['port'] else 22,
                    'path': matches['path']
                }

                if matches['user'] is not None:
                    file_opts['user'] = matches['user']

                # options in qemu-kvm are different from uri
                if matches['host_key_check'] is not None:
                    if matches['host_key_check'] == 'no':
                        file_opts['host-key-check.mode'] = 'none'
                    elif matches['host_key_check'] == 'yes':
                        file_opts['host-key-check.mode'] = 'known_hosts'
                    else:
                        m = re.match(r'(?P<type>md5|sha1):(?P<hash>.+)',
                                     matches['host_key_check']).groupdict()
                        file_opts.update({
                            'host-key-check.mode': 'hash',
                            'host-key-check.type': m['type'],
                            'host-key-check.hash': m['hash']
                        })
    elif re.match(r'(http|https|ftp|ftps)://', filename):
        filename_pattern = re.compile(
            r'(?P<protocol>.+?)://((?P<user>.+?)(:(?P<password>.+?))?@)?'
            r'(?P<server>.+?)/(?P<path>.+)')
        matches = filename_pattern.match(filename)
        if matches:
            matches = matches.groupdict()
            if all((matches['protocol'], matches['server'], matches['path'])):
                # required libcurl options, note server can be hostname:port
                file_opts = {
                    'driver': matches['protocol'],
                    'url': '{protocol}://{server}/{path}'.format(
                        protocol=matches['protocol'],
                        server=matches['server'],
                        path=matches['path']
                    )
                }

                if matches['user'] is not None:
                    file_opts['username'] = matches['user']
    # FIXME: Judge the host device by the string starts with "/dev/".
    elif filename.startswith('/dev/'):
        file_opts = {'driver': 'host_device', 'filename': filename}
    else:
        file_opts = {'driver': 'file', 'filename': filename}

    if not file_opts:
        raise ValueError("Wrong filename %s" % filename)

    return file_opts


def _get_image_meta(image, params, root_dir):
    """Retrieve image meta dict."""
    meta = collections.OrderedDict()
    meta["file"] = collections.OrderedDict()

    filename = storage.get_image_filename(params, root_dir)
    meta_file = filename_to_file_opts(filename)
    meta["file"].update(meta_file)

    image_format = params.get("image_format", "qcow2")
    meta["driver"] = image_format

    secret = storage.ImageSecret.image_secret_define_by_params(image, params)
    if image_format == "luks":
        meta["key-secret"] = secret.aid
    image_encryption = params.get("image_encryption", "off")
    if image_format == "qcow2" and image_encryption == "luks":
        meta["encrypt.key-secret"] = secret.aid

    auth_info = storage.StorageAuth.auth_info_define_by_params(image, params)
    if auth_info is not None:
        if auth_info.storage_type == 'ceph':
            if auth_info.data:
                # qemu-img needs secret object only for ceph access
                meta['file']['password-secret'] = auth_info.aid
        elif auth_info.storage_type == 'iscsi-direct':
            if auth_info.data:
                # '-b json' demands password
                # note that image creation doesn't support secret object
                meta['file']['password'] = auth_info.data
            if auth_info.iscsi_initiator:
                meta['file']['initiator-name'] = auth_info.iscsi_initiator
        elif auth_info.storage_type == 'glusterfs-direct':
            if auth_info.debug:
                meta['file']['debug'] = int(auth_info.debug)
            if auth_info.logfile:
                meta['file']['logfile'] = auth_info.logfile

            peers = []
            for peer in auth_info.peers:
                if 'path' in peer:
                    # access storage with unix domain socket
                    peers.append({'type': 'unix', 'path': peer['path']})
                else:
                    # access storage with hostname/ip + port
                    peers.append({'host': peer['host'],
                                  'type': peer.get('type', 'inet'),
                                  'port': '%s' % peer.get('port', '0')})
            meta['file'].update({'server.{i}.{k}'.format(i=i + 1, k=k): v
                                 for i, server in enumerate(peers)
                                 for k, v in six.iteritems(server)})
        elif auth_info.storage_type == 'nbd':
            # qemu-img, as a client, accesses nbd storage
            if auth_info.tls_creds:
                meta['file']['tls-creds'] = auth_info.aid
            if auth_info.reconnect_delay:
                meta['file']['reconnect-delay'] = auth_info.reconnect_delay
        elif auth_info.storage_type == 'curl':
            mapping = {
                'password-secret': (auth_info.data, auth_info.aid),
                'sslverify': (auth_info.sslverify, auth_info.sslverify),
                'cookie-secret': (auth_info.cookie,
                                  auth_info.cookie.aid
                                  if auth_info.cookie else ''),
                'readahead': (auth_info.readahead, auth_info.readahead),
                'timeout': (auth_info.timeout, auth_info.timeout)
            }
            meta['file'].update({
                k: v[1] for k, v in six.iteritems(mapping) if v[0]
            })

    return meta


def get_image_json(image, params, root_dir):
    """Generate image json representation."""
    return "json:%s" % json.dumps(_get_image_meta(image, params, root_dir))


def get_image_opts(image, params, root_dir):
    """Generate image-opts."""
    def _dict_to_dot(dct):
        """Convert dictionary to dot representation."""
        flat = []
        prefix = []
        stack = [six.iteritems(dct)]
        while stack:
            it = stack[-1]
            try:
                key, value = next(it)
            except StopIteration:
                if prefix:
                    prefix.pop()
                stack.pop()
                continue
            if isinstance(value, collections.Mapping):
                prefix.append(key)
                stack.append(six.iteritems(value))
            else:
                flat.append((".".join(prefix + [key]), value))
        return flat

    meta = _get_image_meta(image, params, root_dir)
    return ",".join(["%s=%s" % (attr, value) for
                     attr, value in _dict_to_dot(meta)])


def get_image_repr(image, params, root_dir, representation=None):
    """Get image representation."""
    mapping = {"filename": lambda i, p, r: storage.get_image_filename(p, r),
               "json": get_image_json,
               "opts": get_image_opts}
    func = mapping.get(representation, None)
    if func is None:
        image_secret = storage.ImageSecret.image_secret_define_by_params(
            image, params)

        access_needed = False
        auth_info = storage.StorageAuth.auth_info_define_by_params(image,
                                                                   params)
        if auth_info is not None:
            if auth_info.storage_type == 'ceph':
                # only ceph access needs secret object
                if auth_info.data:
                    access_needed = True
            elif auth_info.storage_type == 'iscsi-direct':
                # url with u/p is used to access iscsi image,
                # besides u/p, iscsi access may need initiator
                if auth_info.iscsi_initiator:
                    access_needed = True
            elif auth_info.storage_type == 'glusterfs-direct':
                # debug, logfile and other servers represent in json
                if auth_info.debug or auth_info.logfile or auth_info.peers:
                    access_needed = True
            elif auth_info.storage_type == 'nbd':
                # tls-creds, reconnect_delay represent in json
                access_needed = True
            elif auth_info.storage_type == 'curl':
                # u/p can be included in url, while the others should be
                # represented in json
                if any((auth_info.sslverify, auth_info.cookie,
                        auth_info.readahead, auth_info.timeout)):
                    access_needed = True

        func = mapping["json"] if image_secret or access_needed else mapping["filename"]
    return func(image, params, root_dir)


class _ParameterAssembler(string.Formatter):
    """
    Command line parameter assembler.

    This will automatically prepend parameter if corresponding value is passed
    to the format string.
    """
    sentinal = object()

    def __init__(self, cmd_params=None):
        string.Formatter.__init__(self)
        self.cmd_params = cmd_params or {}

    def format(self, format_string, *args, **kwargs):
        """Remove redundant whitespaces and return format string."""
        ret = string.Formatter.format(self, format_string, *args, **kwargs)
        return re.sub(" +", " ", ret)

    def get_value(self, key, args, kwargs):
        try:
            val = string.Formatter.get_value(self, key, args, kwargs)
        except KeyError:
            if key in self.cmd_params:
                val = None
            else:
                raise
        return (self.cmd_params.get(key, self.sentinal), val)

    def convert_field(self, value, conversion):
        """
        Do conversion on the resulting object.

        supported conversions:
            'b': keep the parameter only if bool(value) is True.
            'v': keep both the parameter and its corresponding value,
                 the default mode.
        """
        if value[0] is self.sentinal:
            return string.Formatter.convert_field(self, value[1], conversion)
        if conversion is None:
            conversion = "v"
        if conversion == "v":
            return "" if value[1] is None else " ".join(value)
        if conversion == "b":
            return value[0] if bool(value[1]) else ""
        raise ValueError("Unknown conversion specifier {}".format(conversion))


class QemuImg(storage.QemuImg):
    """KVM class for handling operations of disk/block images."""
    qemu_img_parameters = {
        "image_format": "-f",
        "backing_file": "-b",
        "backing_format": "-F",
        "unsafe": "-u",
        "options": "-o",
        "secret_object": "",
        "tls_creds_object": "",
        "image_opts": "",
        "check_repair": "-r",
        "output_format": "--output",
        "force_share": "-U",
        "resize_preallocation": "--preallocation",
        "resize_shrink": "--shrink",
        "convert_compressed": "-c",
        "cache_mode": "-t",
        "source_cache_mode": "-T",
        "target_image_format": "-O",
        "convert_sparse_size": "-S",
        "rate_limit": "-r",
        "convert_target_is_zero": "--target-is-zero",
        "convert_backing_file": "-B",
        "commit_drop": "-d",
        "compare_strict_mode": "-s",
        "compare_second_image_format": "-F"
    }
    create_cmd = ("create {secret_object} {tls_creds_object} {image_format} "
                  "{backing_file} {backing_format} {unsafe!b} {options} "
                  "{image_filename} {image_size}")
    check_cmd = ("check {secret_object} {tls_creds_object} "
                 "{image_opts} {image_format} "
                 "{output_format} {check_repair} {force_share!b} "
                 "{image_filename}")
    convert_cmd = ("convert {secret_object} {tls_creds_object} "
                   "{convert_compressed!b} {skip_target_image_creation} "
                   "{image_format} {cache_mode} {source_cache_mode} "
                   "{target_image_format} {options} {convert_sparse_size} "
                   "{rate_limit} {convert_target_is_zero!b} "
                   "{convert_backing_file} "
                   "{image_filename} {target_image_filename} "
                   "{target_image_opts}")
    commit_cmd = ("commit {secret_object} {image_format} {cache_mode} "
                  "{backing_file} {commit_drop!b} {image_filename} "
                  "{rate_limit}")
    resize_cmd = ("resize {secret_object} {image_opts} {resize_shrink!b} "
                  "{resize_preallocation} {image_filename} {image_size}")
    rebase_cmd = ("rebase {secret_object} {image_format} {cache_mode} "
                  "{source_cache_mode} {unsafe!b} {backing_file} "
                  "{backing_format} {image_filename}")
    dd_cmd = ("dd {secret_object} {tls_creds_object} {image_format} "
              "{target_image_format} {block_size} {count} {skip} "
              "if={image_filename} of={target_image_filename}")
    compare_cmd = ("compare {secret_object} {tls_creds_object} {image_format} "
                   "{compare_second_image_format} {source_cache_mode} "
                   "{compare_strict_mode!b} {force_share!b} "
                   "{image_filename} {compare_second_image_filename}")

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images
        """
        storage.QemuImg.__init__(self, params, root_dir, tag)
        self.image_cmd = utils_misc.get_qemu_img_binary(params)
        q_result = process.run(self.image_cmd + ' -h', ignore_status=True,
                               shell=True, verbose=False)
        self.help_text = q_result.stdout_text
        self.cap_force_share = '-U' in self.help_text
        self._cmd_formatter = _ParameterAssembler(self.qemu_img_parameters)

    def _parse_options(self, params):
        """Build options used for qemu-img amend, create, convert, measure."""
        options_mapping = {
            "preallocated": (None, "preallocation", ("qcow2", "raw", "luks")),
            "image_cluster_size": (None, "cluster_size", ("qcow2",)),
            "lazy_refcounts": (None, "lazy_refcounts", ("qcow2",)),
            "qcow2_compatible": (None, "compat", ("qcow2",))
        }
        image_format = params.get("image_format", "qcow2")
        options = []
        for key, (default, opt_key, support_fmt) in options_mapping.items():
            if image_format in support_fmt:
                value = params.get(key, default)
                if value is not None:
                    options.append("%s=%s" % (opt_key, value))

        if self.encryption_config.key_secret:
            opts = list(self.encryption_config)
            opts.remove("base_key_secrets")
            if image_format == "luks":
                opts.remove("format")
            for opt_key in opts:
                opt_val = getattr(self.encryption_config, opt_key)
                if opt_val:
                    if image_format == "qcow2":
                        opt_key = "encrypt.%s" % opt_key
                    options.append("%s=%s" % (opt_key.replace("_", "-"),
                                              str(opt_val)))

        if self.data_file:
            options.extend(
                ("data_file=%s" % self.data_file.image_filename,
                 "data_file_raw=%s" % params.get("image_data_file_raw", "off")))

        for access_secret, secret_type in self._image_access_secret:
            if secret_type == 'password':
                options.append("password-secret=%s" % access_secret.aid)
            elif secret_type == 'key':
                options.append("key-secret=%s" % access_secret.aid)
            elif secret_type == 'cookie':
                options.append("cookie-secret=%s" % access_secret.aid)

        image_extra_params = params.get("image_extra_params")
        if image_extra_params:
            options.append(image_extra_params.strip(','))
        if params.get("has_backing_file") == "yes":
            backing_param = params.object_params("backing_file")
            backing_file = storage.get_image_filename(backing_param,
                                                      self.root_dir)
            options.append("backing_file=%s" % backing_file)
            backing_fmt = backing_param.get("image_format")
            options.append("backing_fmt=%s" % backing_fmt)
        return options

    def _need_auth_info(self, image=None):
        """
        Check if a specified image's auth info is required.
        qemu-img's 'json:{}' instead of 'filename(uri)' should
        be used when auth info is required.
        The auth info includes sensitive data like password as
        well as other info like iscsi initiator.

        :param image: image name
        :return: True or False
        """
        needed = False

        if self.image_access is not None:
            tag = image if image else self.tag
            if tag == self.tag:
                needed = self.image_access.image_auth is not None
            else:
                needed = tag in self.image_access.image_backing_auth

        return needed

    @property
    def _image_access_tls_creds(self):
        tls_creds = None
        creds = self.image_access.image_auth if self.image_access else None

        if creds is not None:
            if creds.storage_type == 'nbd':
                if creds.tls_creds:
                    tls_creds = creds

        return tls_creds

    @property
    def _backing_access_tls_creds(self):
        tls_creds_list = []
        creds_list = self.image_access.image_backing_auth.values() if self.image_access else []

        for creds in creds_list:
            if creds.storage_type == 'nbd':
                if creds.tls_creds:
                    tls_creds_list.append(creds)

        return tls_creds_list

    @property
    def _image_access_secret(self):
        """
        Get the access secret object and its type of the image itself,
        the type can be 'key' or 'password' or 'cookie'

        :return: a list of tuple(StorageAuth object, secret type) or []
        :note: an image can have more than one secret objects, e.g.
               access secret object and cookie secret object for libcurl
        """
        secrets = []
        auth = self.image_access.image_auth if self.image_access else None

        if auth is not None:
            if auth.storage_type == 'ceph':
                # ceph image access requires secret object by
                # qemu-img and only 'password-secret' is supported
                if auth.data:
                    secrets.append((auth, 'password'))
            elif auth.storage_type == 'curl':
                # a libcurl image can have more than one secret object
                if auth.data:
                    secrets.append((auth, 'password'))
                if auth.cookie:
                    secrets.append((auth.cookie, 'cookie'))

        return secrets

    @property
    def _backing_access_secrets(self):
        """
        Get the backing images' access secret objects and types,
        the type can be 'key' or 'password'

        :return: a list of (StorageAuth object, secret type) or []
        """
        secrets = []
        info = self.image_access.image_backing_auth.values() if self.image_access else []

        for auth in info:
            if auth.storage_type == 'ceph':
                # ceph image access requires secret object by
                # qemu-img and only 'password-secret' is supported
                if auth.data:
                    secrets.append((auth, 'password'))
            elif auth.storage_type == 'curl':
                if auth.data:
                    secrets.append((auth, 'password'))
                if auth.cookie:
                    secrets.append((auth.cookie, 'cookie'))

        return secrets

    @property
    def _secret_objects(self):
        """All secret objects str needed for command line."""
        secret_objects = self.encryption_config.image_key_secrets
        secret_obj_str = "--object secret,id={s.aid},data={s.data}"
        return [secret_obj_str.format(s=s) for s in secret_objects]

    @property
    def _image_access_tls_creds_object(self):
        """Get the tls-creds object str of the image itself."""
        tls_obj_str = '--object tls-creds-x509,id={s.aid},endpoint=client,dir={s.tls_creds}'
        creds = self._image_access_tls_creds
        return tls_obj_str.format(s=creds) if creds else ''

    @property
    def _backing_access_tls_creds_objects(self):
        """Get all tls-creds object str of the backing images."""
        tls_creds = []
        tls_obj_str = '--object tls-creds-x509,id={s.aid},endpoint=client,dir={s.tls_creds}'

        for creds in self._backing_access_tls_creds:
            tls_creds.append(tls_obj_str.format(s=creds))

        return tls_creds

    @property
    def _image_access_secret_object(self):
        """Get the secret object str of the image itself."""
        secrets = []

        for access_secret, secret_type in self._image_access_secret:
            secret_obj_str = ''
            if secret_type == 'password':
                secret_obj_str = '--object secret,id={s.aid},format={s.data_format},file={s.filename}'
            elif secret_type == 'key' or secret_type == 'cookie':
                secret_obj_str = '--object secret,id={s.aid},format={s.data_format},data={s.data}'
            secrets.append(secret_obj_str.format(s=access_secret))

        return secrets

    @property
    def _backing_access_secret_objects(self):
        """Get all secret object str of the backing images."""
        secrets = []

        for access_secret, secret_type in self._backing_access_secrets:
            secret_obj_str = ''
            if secret_type == 'password':
                secret_obj_str = "--object secret,id={s.aid},format={s.data_format},file={s.filename}"
            elif secret_type == 'key' or secret_type == 'cookie':
                secret_obj_str = "--object secret,id={s.aid},format={s.data_format},data={s.data}"
            secrets.append(secret_obj_str.format(s=access_secret))

        return secrets

    @error_context.context_aware
    def create(self, params, ignore_errors=False):
        """
        Create an image using qemu_img or dd.

        :param params: Dictionary containing the test parameters.
        :param ignore_errors: Whether to ignore errors on the image creation
                              cmd.

        :note: params should contain:

               image_name
                   name of the image file, without extension
               image_format
                   format of the image (qcow2, raw etc)
               image_cluster_size (optional)
                   cluster size for the image
               image_size
                   requested size of the image (a string qemu-img can
                   understand, such as '10G')
               create_with_dd
                   use dd to create the image (raw format only)
               base_image(optional)
                   the base image name when create snapshot
               base_format(optional)
                   the format of base image
               encrypted(optional)
                   if the image is encrypted, allowed values: on and off.
                   Default is "off"
               preallocated(optional)
                   if preallocation when create image, allowed values: off,
                   metadata. Default is "off"

        :return: tuple (path to the image created, process.CmdResult object
                 containing the result of the creation command).
        """
        if params.get(
                "create_with_dd") == "yes" and self.image_format == "raw":
            # maps K,M,G,T => (count, bs)
            human = {'K': (1, 1),
                     'M': (1, 1024),
                     'G': (1024, 1024),
                     'T': (1024, 1048576),
                     }
            if self.size[-1] in human:
                block_size = human[self.size[-1]][1]
                size = int(self.size[:-1]) * human[self.size[-1]][0]
            qemu_img_cmd = ("dd if=/dev/zero of=%s count=%s bs=%sK"
                            % (self.image_filename, size, block_size))
        else:
            cmd_dict = {}
            cmd_dict["image_format"] = self.image_format
            if self.base_tag:
                # if base image has secret, use json representation
                base_key_secrets = self.encryption_config.base_key_secrets
                if (self.base_tag in [s.image_id for s in base_key_secrets]
                        or self._need_auth_info(self.base_tag)):
                    base_params = params.object_params(self.base_tag)
                    cmd_dict["backing_file"] = "'%s'" % \
                        get_image_json(self.base_tag, base_params,
                                       self.root_dir)
                else:
                    cmd_dict["backing_file"] = self.base_image_filename
                cmd_dict["backing_format"] = self.base_format

            # secret objects of the backing images
            secret_objects = self._backing_access_secret_objects

            # secret object of the image itself
            if self._image_access_secret_object:
                secret_objects.extend(self._image_access_secret_object)

            image_secret_objects = self._secret_objects
            if image_secret_objects:
                secret_objects.extend(image_secret_objects)
            if secret_objects:
                cmd_dict["secret_object"] = " ".join(secret_objects)

            # tls creds objects of the backing images of the source
            tls_creds_objects = self._backing_access_tls_creds_objects

            # tls creds object of the source image itself
            if self._image_access_tls_creds_object:
                tls_creds_objects.append(self._image_access_tls_creds_object)

            if tls_creds_objects:
                cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

            cmd_dict["image_filename"] = self.image_filename
            cmd_dict["image_size"] = self.size
            options = self._parse_options(params)
            if options:
                cmd_dict["options"] = ",".join(options)
            qemu_img_cmd = self.image_cmd + " " + \
                self._cmd_formatter.format(self.create_cmd, **cmd_dict)

        if (params.get("image_backend", "filesystem") == "filesystem"):
            image_dirname = os.path.dirname(self.image_filename)
            if image_dirname and not os.path.isdir(image_dirname):
                e_msg = ("Parent directory of the image file %s does "
                         "not exist" % self.image_filename)
                LOG.error(e_msg)
                LOG.error("This usually means a serious setup exceptions.")
                LOG.error("Please verify if your data dir contains the "
                          "expected directory structure")
                LOG.error("Backing data dir: %s",
                          data_dir.get_backing_data_dir())
                LOG.error("Directory structure:")
                for root, _, _ in os.walk(data_dir.get_backing_data_dir()):
                    LOG.error(root)

                LOG.warning("We'll try to proceed by creating the dir. "
                            "Other errors may ensue")
                os.makedirs(image_dirname)

        msg = "Create image by command: %s" % qemu_img_cmd
        error_context.context(msg, LOG.info)
        cmd_result = process.run(
            qemu_img_cmd, shell=True, verbose=False, ignore_status=True)
        if cmd_result.exit_status != 0 and not ignore_errors:
            raise exceptions.TestError("Failed to create image %s\n%s" %
                                       (self.image_filename, cmd_result))
        if self.encryption_config.key_secret:
            self.encryption_config.key_secret.save_to_file()
        cmd_result.stdout = cmd_result.stdout_text
        cmd_result.stderr = cmd_result.stderr_text
        return self.image_filename, cmd_result

    def convert(self, params, root_dir, cache_mode=None,
                source_cache_mode=None, skip_target_creation=False):
        """
        Convert image

        :param params: dictionary containing the test parameters
        :param root_dir: dir for save the convert image
        :param cache_mode: The cache mode used to write the output disk image.
                           Valid options are: ``none``, ``writeback``
                           (default), ``writethrough``, ``directsync`` and
                           ``unsafe``.
        :param source_cache_mode: the cache mode used with source image file
        :param skip_target_creation: qemu-img skips the creation of the target
                                     volume if True(-n), i.e. the target image
                                     should be created before image convert
        :note: params should contain:
            convert_target
                the convert target image tag
            compressed
                indicates that target image must be compressed
            sparse_size
                indicate the consecutive number of bytes contains zeros to
                create sparse image during conversion
            rate_limit
                indicate rate limit for the convert process,
                the unit is bytes per second
            convert_target_is_zero
                indicate that an existing target device will return
                zeros for all reads
            convert_backing_file
                indicate that setting backing file to target image
        """
        convert_target = params["convert_target"]
        convert_params = params.object_params(convert_target)
        convert_image = QemuImg(convert_params, root_dir, convert_target)

        convert_compressed = convert_params.get("convert_compressed")
        sparse_size = convert_params.get("sparse_size")
        rate_limit = convert_params.get("rate_limit")
        convert_target_is_zero = convert_params.get_boolean(
                "convert_target_is_zero")
        convert_backing_file = convert_params.get("convert_backing_file")

        cmd_dict = {
            "convert_compressed": convert_compressed == "yes",
            "convert_sparse_size": sparse_size,
            "rate_limit": rate_limit,
            "image_filename": self.image_filename,
            "image_format": self.image_format,
            "target_image_format": convert_image.image_format,
            "target_image_filename": convert_image.image_filename,
            "cache_mode": cache_mode,
            "source_cache_mode": source_cache_mode,
            "skip_target_image_creation": "-n" if skip_target_creation else "",
            "convert_target_is_zero": convert_target_is_zero,
            "convert_backing_file": convert_backing_file,
            "target_image_opts": ""
        }

        options = convert_image._parse_options(convert_params)
        if options:
            cmd_dict["options"] = ",".join(options)

        if skip_target_creation:
            # -o has no effect when skipping image creation
            # This will become an error in future QEMU versions
            if options:
                cmd_dict.pop("options")

            cmd_dict.pop("target_image_format")
            cmd_dict["target_image_filename"] = ""
            cmd_dict["target_image_opts"] = ("--target-image-opts '%s'"
                                             % get_image_opts(
                                                 convert_image.tag,
                                                 convert_image.params,
                                                 convert_image.root_dir))

        if (self.encryption_config.key_secret
                or self._need_auth_info(self.tag)):
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, self.params, self.root_dir)
            cmd_dict.pop("image_format")

        # source images secrets(luks)
        secret_objects = self._secret_objects

        # secret objects of the backing images of the source
        if self._backing_access_secret_objects:
            secret_objects.extend(self._backing_access_secret_objects)

        # secret object of the source image itself
        if self._image_access_secret_object:
            secret_objects.extend(self._image_access_secret_object)

        # target image access secret object
        # target image to be converted never has backing images
        if convert_image._image_access_secret_object:
            secret_objects.extend(convert_image._image_access_secret_object)

        # target image secret(luks)
        if convert_image.encryption_config.key_secret:
            secret_objects.extend(convert_image._secret_objects)

        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)

        # tls creds objects of the backing images of the source
        tls_creds_objects = self._backing_access_tls_creds_objects

        # tls creds object of the source image itself
        if self._image_access_tls_creds_object:
            tls_creds_objects.append(self._image_access_tls_creds_object)

        # tls creds object of the target image
        if convert_image._image_access_tls_creds_object:
            tls_creds_objects.append(
                convert_image._image_access_tls_creds_object)

        if tls_creds_objects:
            cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

        convert_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.convert_cmd, **cmd_dict)

        LOG.info("Convert image %s from %s to %s", self.image_filename,
                 self.image_format, convert_image.image_format)
        process.run(convert_cmd)
        if convert_image.encryption_config.key_secret:
            convert_image.encryption_config.key_secret.save_to_file()

        return convert_target

    def rebase(self, params, cache_mode=None, source_cache_mode=None):
        """
        Rebase image.

        :param params: dictionary containing the test parameters
        :param cache_mode: the cache mode used to write the output disk image,
                           the valid options are: 'none', 'writeback' (default),
                           'writethrough', 'directsync' and 'unsafe'.
        """
        self.check_option("base_image_filename")
        self.check_option("base_format")

        rebase_mode = params.get("rebase_mode")
        cmd_dict = {"image_format": self.image_format,
                    "image_filename": self.image_filename,
                    "cache_mode": cache_mode,
                    "source_cache_mode": source_cache_mode,
                    "unsafe": rebase_mode == "unsafe"}
        secret_objects = self._secret_objects
        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)
        if self.encryption_config.key_secret:
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, self.params, self.root_dir)
            cmd_dict.pop("image_format")
        if self.base_tag:
            if self.base_tag == "null":
                cmd_dict["backing_file"] = "''"
            else:
                base_params = self.params.object_params(self.base_tag)
                base_image = QemuImg(base_params, self.root_dir, self.base_tag)
                self.base_image_filename = base_image.image_filename
                self.base_format = base_image.image_format
                if base_image.encryption_config.key_secret:
                    cmd_dict["backing_file"] = "'%s'" % get_image_json(
                        base_image.tag, base_image.params, base_image.root_dir)
                else:
                    cmd_dict["backing_file"] = base_image.image_filename
                cmd_dict["backing_format"] = base_image.image_format
        else:
            raise exceptions.TestError("Can not find the image parameters need"
                                       " for rebase.")

        LOG.info("Rebase snapshot %s to %s..." % (self.image_filename,
                                                  self.base_image_filename))
        rebase_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.rebase_cmd, **cmd_dict)
        process.run(rebase_cmd)

        return self.base_tag

    def commit(self, params={}, cache_mode=None, base=None, drop=False):
        """
        Commit image to it's base file

        :param cache_mode: the cache mode used to write the output disk image,
            the valid options are: 'none', 'writeback' (default),
            'writethrough', 'directsync' and 'unsafe'.
        :param base: the backing file into which the changes will be committed
        :param drop: drop image after commit
        """
        rate_limit = self.params.get("rate_limit")
        cmd_dict = {"image_format": self.image_format,
                    "image_filename": self.image_filename,
                    "cache_mode": cache_mode,
                    "commit_drop": drop,
                    "rate_limit": rate_limit}
        secret_objects = self._secret_objects
        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)
        if base:
            base_params = self.params.object_params(base)
            base_image = QemuImg(base_params, self.root_dir, base)
            if base_image.encryption_config.key_secret:
                cmd_dict["backing_file"] = "'%s'" % get_image_json(
                    base, base_params, self.root_dir)
            else:
                cmd_dict["backing_file"] = base_image.image_filename
        if self.encryption_config.key_secret:
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, self.params, self.root_dir)
            cmd_dict.pop("image_format")
        commit_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.commit_cmd, **cmd_dict)
        LOG.info("Commit image %s" % self.image_filename)
        process.run(commit_cmd)

        return self.image_filename

    def snapshot_create(self):
        """
        Create a snapshot image.

        :note: params should contain:
               snapshot_image_name -- the name of snapshot image file
        """

        cmd = self.image_cmd
        if self.snapshot_tag:
            cmd += " snapshot -c %s" % self.snapshot_image_filename
        else:
            raise exceptions.TestError("Can not find the snapshot image"
                                       " parameters")
        cmd += " %s" % self.image_filename

        process.run(cmd)

        return self.snapshot_tag

    def snapshot_del(self, blkdebug_cfg=""):
        """
        Delete a snapshot image.

        :param blkdebug_cfg: The configure file of blkdebug

        :note: params should contain:
               snapshot_image_name -- the name of snapshot image file
        """

        cmd = self.image_cmd
        if self.snapshot_tag:
            cmd += " snapshot -d %s" % self.snapshot_image_filename
        else:
            raise exceptions.TestError("Can not find the snapshot image"
                                       " parameters")
        if blkdebug_cfg:
            cmd += " blkdebug:%s:%s" % (blkdebug_cfg, self.image_filename)
        else:
            cmd += " %s" % self.image_filename

        process.run(cmd)

    def snapshot_list(self):
        """
        List all snapshots in the given image
        """
        cmd = self.image_cmd
        cmd += " snapshot -l %s" % self.image_filename

        return process.run(cmd).stdout_text

    def snapshot_apply(self):
        """
        Apply a snapshot image.

        :note: params should contain:
               snapshot_image_name -- the name of snapshot image file
        """
        cmd = self.image_cmd
        if self.snapshot_tag:
            cmd += " snapshot -a %s %s" % (self.snapshot_image_filename,
                                           self.image_filename)
        else:
            raise exceptions.TestError("Can not find the snapshot image"
                                       " parameters")

        process.run(cmd)

    def remove(self):
        """
        Remove an image file.
        """
        LOG.debug("Removing image file %s", self.image_filename)
        storage.file_remove(self.params, self.image_filename)

        if self.data_file:
            LOG.debug("Removing external data file of image %s",
                      self.data_file.image_filename)
            storage.file_remove(self.data_file.params,
                                self.data_file.image_filename)

        secret_files = []
        if self.encryption_config.key_secret:
            secret_files.append(self.encryption_config.key_secret.filename)

        if self.image_access:
            secrets = []

            # image secret
            if self.image_access.image_auth:
                secrets.append(self.image_access.image_auth)

            # backing secrets
            secrets.extend(self.image_access.image_backing_auth.values())

            for auth in secrets:
                if auth.data:
                    secret_files.append(auth.filename)

        for f in secret_files:
            if os.path.exists(f):
                os.unlink(f)

    def info(self, force_share=False, output="human"):
        """
        Run qemu-img info command on image file and return its output.

        :param output: string of output format(`human`, `json`)
        """
        LOG.debug("Run qemu-img info command on %s", self.image_filename)
        backing_chain = self.params.get("backing_chain")
        force_share &= self.cap_force_share
        cmd = self.image_cmd
        cmd += " info"

        if self._image_access_secret_object:
            # secret object of the image itself
            cmd += " %s" % " ".join(self._image_access_secret_object)

        if self._image_access_tls_creds_object:
            # tls creds object of the image itself
            cmd += " %s" % self._image_access_tls_creds_object

        if backing_chain == "yes":
            if self._backing_access_secret_objects:
                # secret objects of the backing images
                cmd += " %s" % " ".join(self._backing_access_secret_objects)

            if self._backing_access_tls_creds_objects:
                # tls creds objects of the backing images
                cmd += " %s" % " ".join(self._backing_access_tls_creds_objects)

            if "--backing-chain" in self.help_text:
                cmd += " --backing-chain"
            else:
                LOG.warn("'--backing-chain' option is not supported")

        if force_share:
            cmd += " -U"

        image_filename = self.image_filename
        if self._need_auth_info(self.tag):
            # use json repr when access info is required
            image_filename = "'%s'" % get_image_json(self.tag, self.params,
                                                     self.root_dir)
        if os.path.exists(image_filename) or self.is_remote_image():
            cmd += " %s --output=%s" % (image_filename, output)
            output = process.run(cmd, verbose=True).stdout_text
        else:
            LOG.debug("Image file %s not found", image_filename)
            output = None
        return output

    def get_format(self):
        """
        Get the fimage file format.
        """
        image_info = self.info()
        if image_info:
            image_format = re.findall("file format: (\w+)", image_info)[0]
        else:
            image_format = None
        return image_format

    def support_cmd(self, cmd):
        """
        Verifies whether qemu-img supports command cmd.

        :param cmd: Command string.
        """
        supports_cmd = True

        if cmd not in self.help_text:
            LOG.error("%s does not support command '%s'", self.image_cmd, cmd)
            supports_cmd = False

        return supports_cmd

    def compare_images(self, image1, image2, strict_mode=False,
                       verbose=True, force_share=False):
        """
        Compare 2 images using the appropriate tools for each virt backend.

        :param image1: image path of first image
        :param image2: image path of second image
        :param strict_mode: Boolean value, True for strict mode,
                            False for default mode.
        :param verbose: Record output in debug file or not

        :return: process.CmdResult object containing the result of the command
        """
        compare_images = self.support_cmd("compare")
        force_share &= self.cap_force_share
        if not compare_images:
            LOG.warn("sub-command compare not supported by qemu-img")
            return None
        else:
            LOG.info("Comparing images %s and %s", image1, image2)
            compare_cmd = "%s compare" % self.image_cmd
            if force_share:
                compare_cmd += " -U"
            if strict_mode:
                compare_cmd += " -s"
            compare_cmd += " %s %s" % (image1, image2)
            cmd_result = process.run(compare_cmd, ignore_status=True,
                                     shell=True)

            if verbose:
                LOG.debug("Output from command: %s", cmd_result.stdout_text)

            if cmd_result.exit_status == 0:
                LOG.info("Compared images are equal")
            elif cmd_result.exit_status == 1:
                raise exceptions.TestFail("Compared images differ")
            else:
                raise exceptions.TestError("Error in image comparison")

            return cmd_result

    def compare_to(self, target_image, source_cache_mode=None,
                   strict_mode=False, force_share=False, verbose=True):
        """
        Compare to target image.

        :param target_image: target image object
        :param source_cache_mode: source cache used to open source image
        :param strict_mode: compare fails on sector allocation or image size
        :param force_share: open image in shared mode
        :return: compare result [process.CmdResult]
        """
        if not self.support_cmd("compare"):
            LOG.warn("qemu-img subcommand compare not supported")
            return
        force_share &= self.cap_force_share
        LOG.info("compare image %s to image %s",
                 self.image_filename, target_image.image_filename)

        cmd_dict = {
            "image_format": self.image_format,
            "compare_second_image_format": target_image.image_format,
            "source_cache_mode": source_cache_mode,
            "compare_strict_mode": strict_mode,
            "force_share": force_share,
            "image_filename": self.image_filename,
            "compare_second_image_filename": target_image.image_filename,
        }

        secret_objects = self._secret_objects + target_image._secret_objects

        # source image's backing access secret objects
        if self._backing_access_secret_objects:
            secret_objects.extend(self._backing_access_secret_objects)

        # source image access secret object
        if self._image_access_secret_object:
            secret_objects.extend(self._image_access_secret_object)

        # target image's backing access secret objects
        if target_image._backing_access_secret_objects:
            secret_objects.extend(target_image._backing_access_secret_objects)

        # target image access secret object
        if target_image._image_access_secret_object:
            secret_objects.extend(target_image._image_access_secret_object)

        # if compared images are in the same snapshot chain,
        # needs to remove duplicated secrets
        secret_objects = list(set(secret_objects))
        cmd_dict["secret_object"] = " ".join(secret_objects)

        # tls creds objects of the backing images of the source
        tls_creds_objects = self._backing_access_tls_creds_objects

        # tls creds object of the source image
        if self._image_access_tls_creds_object:
            tls_creds_objects.append(self._image_access_tls_creds_object)

        # tls creds objects of the backing images of the target
        if target_image._backing_access_tls_creds_objects:
            tls_creds_objects.extend(
                target_image._backing_access_tls_creds_objects)

        # tls creds object of the target image
        if target_image._image_access_tls_creds_object:
            tls_creds_objects.append(
                target_image._image_access_tls_creds_object)

        tls_creds_objects = list(set(tls_creds_objects))
        cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

        if (self.encryption_config.key_secret
                or self._need_auth_info(self.tag)):
            cmd_dict["image_filename"] = "'%s'" % \
                get_image_json(self.tag, self.params, self.root_dir)

        if (target_image.encryption_config.key_secret
                or target_image._need_auth_info(target_image.tag)):
            cmd_dict["compare_second_image_filename"] = "'%s'" % \
                get_image_json(target_image.tag, target_image.params,
                               target_image.root_dir)

        compare_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.compare_cmd, **cmd_dict)
        result = process.run(compare_cmd, ignore_status=True, shell=True)

        if verbose:
            LOG.debug("compare output:\n%s", result.stdout_text)

        return result

    def check(self, params, root_dir, force_share=False, output=None):
        """
        Check an image using the appropriate tools for each virt backend.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param output: The format of the output(json, human).

        :note: params should contain:
               image_name -- the name of the image file, without extension
               image_format -- the format of the image (qcow2, raw etc)

        :return: The output of check result if the image exists, or None.
        """
        image_filename = self.image_filename
        LOG.debug("Checking image file %s", image_filename)
        force_share &= self.cap_force_share

        cmd_dict = {"image_filename": image_filename,
                    "force_share": force_share,
                    "output_format": output}
        if (self.encryption_config.key_secret
                or self._need_auth_info(self.tag)):
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, params, root_dir)

        # access secret objects of the backing images
        secret_objects = self._backing_access_secret_objects

        # access secret object of the image itself
        if self._image_access_secret_object:
            secret_objects.extend(self._image_access_secret_object)

        # image(e.g. luks image) secret objects
        image_secret_objects = self._secret_objects
        if image_secret_objects:
            secret_objects.extend(image_secret_objects)

        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)

        # tls creds objects of the backing images
        tls_creds_objects = self._backing_access_tls_creds_objects

        # tls creds object of the image itself
        if self._image_access_tls_creds_object:
            tls_creds_objects.append(self._image_access_tls_creds_object)

        if tls_creds_objects:
            cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

        check_cmd = self.image_cmd + " " + self._cmd_formatter.format(
            self.check_cmd, **cmd_dict)
        cmd_result = process.run(check_cmd, ignore_status=True,
                                 shell=True, verbose=False)

        return cmd_result

    def check_image(self, params, root_dir, force_share=False):
        """
        Check an image using the appropriate tools for each virt backend.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.

        :note: params should contain:
               image_name -- the name of the image file, without extension
               image_format -- the format of the image (qcow2, raw etc)

        :raise VMImageCheckError: In case qemu-img check fails on the image.
        """
        image_filename = self.image_filename
        LOG.debug("Checking image file %s", image_filename)
        image_is_checkable = self.image_format in ['qcow2', 'qed']
        force_share &= self.cap_force_share

        if (storage.file_exists(params, image_filename) or
                self.is_remote_image()) and image_is_checkable:
            try:
                # FIXME: do we really need it?
                self.info(force_share)
            except process.CmdError:
                LOG.error("Error getting info from image %s", image_filename)
            cmd_result = self.check(params, root_dir, force_share)
            # Error check, large chances of a non-fatal problem.
            # There are chances that bad data was skipped though
            if cmd_result.exit_status == 1:
                stdout = cmd_result.stdout_text
                for e_line in stdout.splitlines():
                    LOG.error("[stdout] %s", e_line)
                stderr = cmd_result.stderr_text
                for e_line in stderr.splitlines():
                    LOG.error("[stderr] %s", e_line)
                chk = params.get("backup_image_on_check_error", "no")
                if chk == "yes":
                    self.backup_image(params, root_dir, "backup", False)
                raise exceptions.TestWarn(
                    "qemu-img check not completed because of internal "
                    "errors. Some bad data in the image may have gone "
                    "unnoticed (%s)" % image_filename)
            # Exit status 2 is data corruption for sure,
            # so fail the test
            elif cmd_result.exit_status == 2:
                stdout = cmd_result.stdout_text
                for e_line in stdout.splitlines():
                    LOG.error("[stdout] %s", e_line)
                stderr = cmd_result.stderr_text
                for e_line in stderr.splitlines():
                    LOG.error("[stderr] %s", e_line)
                chk = params.get("backup_image_on_check_error", "no")
                if chk == "yes":
                    self.backup_image(params, root_dir, "backup", False)
                raise virt_vm.VMImageCheckError(image_filename)
            # Leaked clusters, they are known to be harmless to data
            # integrity
            elif cmd_result.exit_status == 3:
                raise exceptions.TestWarn("Leaked clusters were noticed"
                                          " during image check. No data "
                                          "integrity problem was found "
                                          "though. (%s)" % image_filename)
        else:
            if not storage.file_exists(params, image_filename):
                LOG.debug("Image file %s not found, skipping check",
                          image_filename)
            elif not image_is_checkable:
                LOG.debug(
                    "Image format %s is not checkable, skipping check",
                    self.image_format)

    def amend(self, params, cache_mode=None, ignore_status=False):
        """
        Amend the image format specific options for the image

        :param params: dictionary containing the test parameters
        :param cache_mode: the cache mode used to write the output disk image,
                           the valid options are: 'none', 'writeback'
                           (default), 'writethrough', 'directsync' and
                           'unsafe'.
        :param ignore_status: Whether to raise an exception when command
                              returns =! 0 (False), or not (True).

        :note: params may contain amend options:

               amend_size
                   virtual disk size of the image (a string qemu-img can
                   understand, such as '10G')
               amend_compat
                   compatibility level (0.10 or 1.1)
               amend_backing_file
                   file name of a base image
               amend_backing_fmt
                   image format of the base image
               amend_encryption
                   encrypt the image, allowed values: on and off.
                   Default is "off"
               amend_cluster_size
                   cluster size for the image
               amend_preallocation
                   preallocation mode when create image, allowed values: off,
                   metadata. Default is "off"
               amend_lazy_refcounts
                   postpone refcount updates, allowed values: on and off.
                   Default is "off"
               amend_refcount_bits
                   width of a reference count entry in bits
               amend_keyslot
                   keyslot for the password, allowed values: between 0 and 7
               amend_state
                   the state for the keyslot,
                   allowed values: active and inactive
               amend_new-secret
                   the new secret object for the password,
                   used for adding a new password
               amend_old-secret
                   the old secret object for the password,
                   used for erasing an existing password
               amend_extra_params
                   additional options, used for extending amend

        :return: process.CmdResult object containing the result of the
                command
        """
        cmd_list = [self.image_cmd, 'amend']
        secret_objects = self._secret_objects
        if secret_objects:
            # add a secret object, use for adding and erasing password
            sec_id = params["amend_secret_id"]
            sec_data = params["amend_secret_data"]
            secret_obj_str = "--object secret,id=%s,data=%s" % (sec_id, sec_data)
            secret_objects.append(secret_obj_str)
            cmd_list.append(" ".join(secret_objects))
        options = []
        for key, val in six.iteritems(params):
            if key.startswith('amend_') and \
                    key not in ["amend_secret_id", "amend_secret_data"]:
                options.append("%s=%s" % (key[6:], val))
        if cache_mode:
            cmd_list.append("-t %s" % cache_mode)
        if options:
            cmd_list.append("-o %s" %
                            ",".join(options).replace("extra_params=", ""))
        if self.encryption_config.key_secret:
            cmd_list.append("'%s'" % get_image_json(self.tag,
                                                    self.params, self.root_dir))
        else:
            cmd_list.append("-f %s %s" % (self.image_format, self.image_filename))
        LOG.info("Amend image %s" % self.image_filename)
        cmd_result = process.run(" ".join(cmd_list), ignore_status=ignore_status)
        return cmd_result

    def resize(self, size, shrink=False, preallocation=None):
        """
        Qemu image resize wrapper.

        :param size: string of size representations.(eg. +1G, -1k, 1T)
        :param shrink: boolean
        :param preallocation: preallocation mode
        :return: process.CmdResult object containing the result of the
                 command
        """
        cmd_dict = {
            "resize_shrink": shrink,
            "resize_preallocation": preallocation,
            "image_filename": self.image_filename,
            "image_size": size,
        }
        if self.encryption_config.key_secret:
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, self.params, self.root_dir)
        secret_objects = self._secret_objects
        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)
        resize_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.resize_cmd, **cmd_dict)
        cmd_result = process.run(resize_cmd, ignore_status=True)
        return cmd_result

    def map(self, output="human"):
        """
        Qemu image map wrapper.

        :param output: string, the map command output format(`human`, `json`)
        :return: process.CmdResult object containing the result of the
                 command
        """
        cmd_list = [self.image_cmd, "map",
                    ("--output=%s" % output), self.image_filename]
        cmd_result = process.run(" ".join(cmd_list), ignore_status=True)
        return cmd_result

    def measure(self, target_fmt, size=None, output="human"):
        """
        Qemu image measure wrapper.

        :param target_fmt: string, the target image format
        :param size: string, the benchmark size of a target_fmt, if `None` it
                     will measure the image object itself with target_fmt
        :param output: string, the measure command output format
                       (`human`, `json`)
        :return: process.CmdResult object containing the result of the
                 command
        """
        cmd_list = [self.image_cmd, "measure", ("--output=%s" % output),
                    ("-O %s" % target_fmt)]

        if target_fmt == "luks":
            target_image = self.params.get("image_measure_target", "tgt")
            target_image_secret = self.params.get("image_secret_%s" %
                                                  target_image, "measure")
            target_image_params = self.params.object_params(target_image)
            target_image_params["image_format"] = "luks"
            target_image_params["image_secret"] = target_image_secret
            target_image_object = QemuImg(
                target_image_params, self.root_dir, target_image)
            cmd_list.append(target_image_object._secret_objects[-1])
            cmd_list.append('-o key-secret=%s' %
                            target_image_object.encryption_config.key_secret.aid)

        if size:
            cmd_list.append(("--size %s" % size))
        else:
            if self.encryption_config.key_secret:
                cmd_list.append(self._secret_objects[-1])
                image_json_str = get_image_json(self.tag,
                                                self.params,
                                                self.root_dir)
                cmd_list.append("'%s'" % image_json_str)
            else:
                cmd_list.extend([("-f %s" % self.image_format),
                                 self.image_filename])

        cmd_result = process.run(" ".join(cmd_list), ignore_status=True)
        return cmd_result

    def dd(self, output, bs=None, count=None, skip=None):
        """
        Qemu image dd wrapper, like dd command, clone the image.
        Please use convert to convert one format of image to another.
        :param output: of=output
        :param bs: bs=bs, the block size in bytes
        :param count: count=count, count of blocks copied
        :param skip: skip=skip, count of blocks skipped
        :return: process.CmdResult object containing the result of the
                 command
        """
        cmd_dict = {
            "image_filename": self.image_filename,
            "target_image_filename": output,
            "image_format": self.image_format,
            "target_image_format": self.image_format
        }

        cmd_dict['block_size'] = 'bs=%d' % bs if bs is not None else ''
        cmd_dict['count'] = 'count=%d' % count if count is not None else ''
        cmd_dict['skip'] = 'skip=%d' % skip if skip is not None else ''

        # TODO: use raw copy(-f raw -O raw) and ignore image secret and format
        # for we cannot set secret for the output
        raw_copy = True if self.encryption_config.key_secret else False
        if raw_copy:
            cmd_dict['image_format'] = cmd_dict['target_image_format'] = 'raw'

        # use 'json:{}' instead when accessing storage with auth
        meta = _get_image_meta(self.tag,
                               self.params,
                               self.root_dir) if self._need_auth_info(self.tag) else None
        if meta is not None:
            if raw_copy:
                # drop image secret from meta
                for key in ['encrypt.key-secret', 'key-secret']:
                    if key in meta:     # pylint: disable=E1135
                        meta.pop(key)
            meta['driver'] = cmd_dict.pop("image_format")   # pylint: disable=E1137
            cmd_dict["image_filename"] = "'json:%s'" % json.dumps(meta)

        # access secret objects of the backing images
        secret_objects = self._backing_access_secret_objects

        # access secret object of the image itself
        if self._image_access_secret_object:
            secret_objects.extend(self._image_access_secret_object)

        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)

        # tls creds objects of the backing images
        tls_creds_objects = self._backing_access_tls_creds_objects

        # tls creds object of the image itself
        if self._image_access_tls_creds_object:
            tls_creds_objects.append(self._image_access_tls_creds_object)

        if tls_creds_objects:
            cmd_dict["tls_creds_object"] = " ".join(tls_creds_objects)

        dd_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.dd_cmd, **cmd_dict)

        return process.run(dd_cmd, ignore_status=True)

    def copy_data_remote(self, src, dst):
        bs = 1024 * 1024  # 1M, faster copy
        self.dd(dst, bs)


class Iscsidev(storage.Iscsidev):

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
        super(Iscsidev, self).__init__(params, root_dir, tag)

    def setup(self):
        """
        Access the iscsi target. And return the local raw device name.
        """
        if self.iscsidevice.logged_in():
            LOG.warn("Session already present. Don't need to login again")
        else:
            self.iscsidevice.login()

        if utils_misc.wait_for(self.iscsidevice.get_device_name,
                               self.iscsi_init_timeout):
            device_name = self.iscsidevice.get_device_name()
        else:
            raise exceptions.TestError("Can not get iscsi device name in host"
                                       " in %ss" % self.iscsi_init_timeout)

        if self.device_id:
            device_name += self.device_id
        return device_name

    def cleanup(self):
        """
        Logout the iscsi target and clean up the config and image.
        """
        if self.exec_cleanup:
            self.iscsidevice.cleanup()
            if self.emulated_file_remove:
                LOG.debug("Removing file %s", self.emulated_image)
                if os.path.exists(self.emulated_image):
                    os.unlink(self.emulated_image)
                else:
                    LOG.debug("File %s not found", self.emulated_image)


class LVMdev(storage.LVMdev):

    """
    Class for handle lvm devices for VM
    """

    def __init__(self, params, root_dir, tag):
        """
        Init the default value for image object.

        :param params: Dictionary containing the test parameters.
        :param root_dir: Base directory for relative filenames.
        :param tag: Image tag defined in parameter images
        """
        super(LVMdev, self).__init__(params, root_dir, tag)

    def setup(self):
        """
        Get logical volume path;
        """
        return self.lvmdevice.setup()

    def cleanup(self):
        """
        Cleanup useless volumes;
        """
        return self.lvmdevice.cleanup()
