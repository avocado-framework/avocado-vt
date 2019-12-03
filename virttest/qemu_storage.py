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
from virttest import data_dir
from virttest import error_context
from virttest.compat_52lts import (results_stdout_52lts,
                                   results_stderr_52lts,
                                   decode_to_text)


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
                             'lun': matches.group('lun')}
                if matches.group('user') is not None:
                    # optional option
                    file_opts['user'] = matches.group('user')
    elif filename.startswith('rbd:'):
        filename_pattern = re.compile(
            r'rbd:(?P<pool>.+?)/(?P<image>[^:]+)(:conf=(?P<conf>.+))?')
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

    image_access = storage.ImageAccessInfo.access_info_define_by_params(image,
                                                                        params)
    if image_access is not None:
        if image_access.auth is not None:
            if image_access.storage_type == 'ceph':
                # qemu-img needs secret object only for ceph access
                meta['file']['password-secret'] = image_access.auth.aid

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
        if storage.ImageSecret.image_secret_define_by_params(image, params):
            func = mapping["json"]
        else:
            func = mapping["filename"]
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
        "commit_drop": "-d",
        "compare_strict_mode": "-s",
        "compare_second_image_format": "-F"
        }
    create_cmd = ("create {secret_object} {image_format} {backing_file} "
                  "{backing_format} {unsafe!b} {options} {image_filename} "
                  "{image_size}")
    check_cmd = ("check {secret_object} {image_opts} {image_format} "
                 "{output_format} {check_repair} {force_share!b} "
                 "{image_filename}")
    convert_cmd = ("convert {secret_object} {convert_compressed!b} "
                   "{image_format} {cache_mode} {source_cache_mode} "
                   "{target_image_format} {options} {convert_sparse_size} "
                   "{image_filename} {target_image_filename}")
    commit_cmd = ("commit {secret_object} {image_format} {cache_mode} "
                  "{backing_file} {commit_drop!b} {image_filename}")
    resize_cmd = ("resize {secret_object} {image_opts} {resize_shrink!b} "
                  "{resize_preallocation} {image_filename} {image_size}")
    rebase_cmd = ("rebase {secret_object} {image_format} {cache_mode} "
                  "{source_cache_mode} {unsafe!b} {backing_file} "
                  "{backing_format} {image_filename}")
    dd_cmd = ("dd {secret_object} {image_format} {target_image_format} "
              "{block_size} {count} {skip} "
              "if={image_filename} of={target_image_filename}")
    compare_cmd = ("compare {secret_object} {image_format} "
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
        self.help_text = results_stdout_52lts(q_result)
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

        access_secret, secret_type = self._get_access_secret_info()
        if access_secret is not None:
            if secret_type == 'password':
                options.append("password-secret=%s" % access_secret.aid)
            elif secret_type == 'key':
                options.append("key-secret=%s" % access_secret.aid)

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

    @property
    def _secret_objects(self):
        """All secret objects str needed for command line."""
        secret_objects = self.encryption_config.image_key_secrets
        secret_obj_str = "--object secret,id={s.aid},data={s.data}"
        return [secret_obj_str.format(s=s) for s in secret_objects]

    @property
    def _storage_secret_object(self):
        secret_obj_str = ''
        access_secret, secret_type = self._get_access_secret_info()
        if access_secret is not None:
            if secret_type == 'password':
                secret_obj_str = "--object secret,id={s.aid},format={s.data_format},file={s.filename}"
                return secret_obj_str.format(s=access_secret)
            elif secret_type == 'key':
                secret_obj_str = "--object secret,id={s.aid},format={s.data_format},data={s.data}"
                return secret_obj_str.format(s=access_secret)
        return secret_obj_str

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
                if self.base_tag in [s.image_id for s in base_key_secrets]:
                    base_params = params.object_params(self.base_tag)
                    cmd_dict["backing_file"] = "'%s'" % \
                        get_image_json(self.base_tag, base_params,
                                       self.root_dir)
                else:
                    cmd_dict["backing_file"] = self.base_image_filename
                    if self.base_format:
                        cmd_dict["backing_format"] = self.base_format

            secret_objects = []
            storage_secret_object = self._storage_secret_object
            if storage_secret_object:
                secret_objects.append(storage_secret_object)
            image_secret_objects = self._secret_objects
            if image_secret_objects:
                secret_objects.extend(image_secret_objects)
            if secret_objects:
                cmd_dict["secret_object"] = " ".join(secret_objects)

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
                logging.error(e_msg)
                logging.error("This usually means a serious setup exceptions.")
                logging.error("Please verify if your data dir contains the "
                              "expected directory structure")
                logging.error("Backing data dir: %s",
                              data_dir.get_backing_data_dir())
                logging.error("Directory structure:")
                for root, _, _ in os.walk(data_dir.get_backing_data_dir()):
                    logging.error(root)

                logging.warning("We'll try to proceed by creating the dir. "
                                "Other errors may ensue")
                os.makedirs(image_dirname)

        msg = "Create image by command: %s" % qemu_img_cmd
        error_context.context(msg, logging.info)
        cmd_result = process.run(
            qemu_img_cmd, shell=True, verbose=False, ignore_status=True)
        if cmd_result.exit_status != 0 and not ignore_errors:
            raise exceptions.TestError("Failed to create image %s\n%s" %
                                       (self.image_filename, cmd_result))
        if self.encryption_config.key_secret:
            self.encryption_config.key_secret.save_to_file()
        cmd_result.stdout = results_stdout_52lts(cmd_result)
        cmd_result.stderr = results_stderr_52lts(cmd_result)
        return self.image_filename, cmd_result

    def convert(self, params, root_dir, cache_mode=None,
                source_cache_mode=None):
        """
        Convert image

        :param params: dictionary containing the test parameters
        :param root_dir: dir for save the convert image
        :param cache_mode: The cache mode used to write the output disk image.
                           Valid options are: ``none``, ``writeback``
                           (default), ``writethrough``, ``directsync`` and
                           ``unsafe``.
        :param source_cache_mode: the cache mode used with source image file
        :note: params should contain:
            convert_target
                the convert target image tag
            compressed
                indicates that target image must be compressed
            sparse_size
                indicate the consecutive number of bytes contains zeros to
                create sparse image during conversion
        """
        convert_target = params["convert_target"]
        convert_params = params.object_params(convert_target)
        convert_image = QemuImg(convert_params, root_dir, convert_target)

        convert_compressed = convert_params.get("convert_compressed")
        sparse_size = convert_params.get("sparse_size")

        cmd_dict = {
            "convert_compressed": convert_compressed == "yes",
            "convert_sparse_size": sparse_size,
            "image_filename": self.image_filename,
            "image_format": self.image_format,
            "target_image_format": convert_image.image_format,
            "target_image_filename": convert_image.image_filename,
            "cache_mode": cache_mode,
            "source_cache_mode": source_cache_mode,
        }

        options = convert_image._parse_options(convert_params)
        if options:
            cmd_dict["options"] = ",".join(options)

        if self.encryption_config.key_secret:
            cmd_dict["image_filename"] = "'%s'" % get_image_json(
                self.tag, self.params, self.root_dir)
            cmd_dict.pop("image_format")
        secret_objects = self._secret_objects

        if convert_image.encryption_config.key_secret:
            secret_objects.extend(convert_image._secret_objects)
        if secret_objects:
            cmd_dict["secret_object"] = " ".join(secret_objects)

        convert_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.convert_cmd, **cmd_dict)

        logging.info("Convert image %s from %s to %s", self.image_filename,
                     self.image_format, convert_image.image_format)
        process.system(convert_cmd)
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

        logging.info("Rebase snapshot %s to %s..." % (self.image_filename,
                                                      self.base_image_filename))
        rebase_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.rebase_cmd, **cmd_dict)
        process.system(rebase_cmd)

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
        cmd_dict = {"image_format": self.image_format,
                    "image_filename": self.image_filename,
                    "cache_mode": cache_mode, "commit_drop": drop}
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
        logging.info("Commit image %s" % self.image_filename)
        process.system(commit_cmd)

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

        decode_to_text(process.system_output(cmd))

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

        decode_to_text(process.system_output(cmd))

    def snapshot_list(self):
        """
        List all snapshots in the given image
        """
        cmd = self.image_cmd
        cmd += " snapshot -l %s" % self.image_filename

        return decode_to_text(process.system_output(cmd))

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

        decode_to_text(process.system_output(cmd))

    def remove(self):
        """
        Remove an image file.
        """
        logging.debug("Removing image file %s", self.image_filename)
        storage.file_remove(self.params, self.image_filename)

        secret_files = []
        if self.encryption_config.key_secret:
            secret_files.append(self.encryption_config.key_secret.filename)
        access_secret, _ = self._get_access_secret_info()
        if access_secret is not None:
            secret_files.append(access_secret.filename)
        for f in secret_files:
            if os.path.exists(f):
                os.unlink(f)

    def info(self, force_share=False, output="human"):
        """
        Run qemu-img info command on image file and return its output.

        :param output: string of output format(`human`, `json`)
        """
        logging.debug("Run qemu-img info command on %s", self.image_filename)
        backing_chain = self.params.get("backing_chain")
        force_share &= self.cap_force_share
        cmd = self.image_cmd
        cmd += " info"
        if force_share:
            cmd += " -U"
        if backing_chain == "yes":
            if "--backing-chain" in self.help_text:
                cmd += " --backing-chain"
            else:
                logging.warn("'--backing-chain' option is not supported")
        if os.path.exists(self.image_filename) or self.is_remote_image():
            cmd += " %s --output=%s" % (self.image_filename, output)
            output = decode_to_text(process.system_output(cmd, verbose=True))
        else:
            logging.debug("Image file %s not found", self.image_filename)
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
            logging.error("%s does not support command '%s'", self.image_cmd,
                          cmd)
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
            logging.warn("sub-command compare not supported by qemu-img")
            return None
        else:
            logging.info("Comparing images %s and %s", image1, image2)
            compare_cmd = "%s compare" % self.image_cmd
            if force_share:
                compare_cmd += " -U"
            if strict_mode:
                compare_cmd += " -s"
            compare_cmd += " %s %s" % (image1, image2)
            cmd_result = process.run(compare_cmd, ignore_status=True,
                                     shell=True)

            if verbose:
                logging.debug("Output from command: %s",
                              results_stdout_52lts(cmd_result))

            if cmd_result.exit_status == 0:
                logging.info("Compared images are equal")
            elif cmd_result.exit_status == 1:
                raise exceptions.TestFail("Compared images differ")
            else:
                raise exceptions.TestError("Error in image comparison")

            cmd_result.stdout = results_stdout_52lts(cmd_result)
            cmd_result.stderr = results_stderr_52lts(cmd_result)
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
            logging.warn("qemu-img subcommand compare not supported")
            return
        force_share &= self.cap_force_share
        logging.info("compare image %s to image %s",
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
        # if compared images are in the same snapshot chain,
        # needs to remove duplicated secrets
        secret_objects = list(set(secret_objects))
        cmd_dict["secret_object"] = " ".join(secret_objects)

        if self.encryption_config.key_secret:
            cmd_dict["image_filename"] = "'%s'" % \
                get_image_json(self.tag, self.params, self.root_dir)
        if target_image.encryption_config.key_secret:
            cmd_dict["compare_second_image_filename"] = "'%s'" % \
                get_image_json(target_image.tag, target_image.params,
                               target_image.root_dir)

        compare_cmd = self.image_cmd + " " + \
            self._cmd_formatter.format(self.compare_cmd, **cmd_dict)
        result = process.run(compare_cmd, ignore_status=True, shell=True)

        if verbose:
            logging.debug("compare output:\n%s", results_stdout_52lts(result))

        return result

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
        logging.debug("Checking image file %s", image_filename)
        image_is_checkable = self.image_format in ['qcow2', 'qed']
        force_share &= self.cap_force_share

        if (storage.file_exists(params, image_filename) or
                self.is_remote_image()) and image_is_checkable:
            check_img = self.support_cmd("check") and self.support_cmd("info")
            if not check_img:
                logging.debug("Skipping image check "
                              "(lack of support in qemu-img)")
            else:
                try:
                    # FIXME: do we really need it?
                    self.info(force_share)
                except process.CmdError:
                    logging.error("Error getting info from image %s",
                                  image_filename)
                cmd_dict = {"image_filename": image_filename,
                            "force_share": force_share}
                if self.encryption_config.key_secret:
                    cmd_dict["image_filename"] = "'%s'" % \
                        get_image_json(self.tag, params, root_dir)

                secret_objects = []
                storage_secret_object = self._storage_secret_object
                if storage_secret_object:
                    secret_objects.append(storage_secret_object)
                image_secret_objects = self._secret_objects
                if image_secret_objects:
                    secret_objects.extend(image_secret_objects)
                if secret_objects:
                    cmd_dict["secret_object"] = " ".join(secret_objects)

                check_cmd = self.image_cmd + " " + \
                    self._cmd_formatter.format(self.check_cmd, **cmd_dict)
                cmd_result = process.run(check_cmd, ignore_status=True,
                                         shell=True, verbose=False)
                # Error check, large chances of a non-fatal problem.
                # There are chances that bad data was skipped though
                if cmd_result.exit_status == 1:
                    stdout = results_stdout_52lts(cmd_result)
                    for e_line in stdout.splitlines():
                        logging.error("[stdout] %s", e_line)
                    stderr = results_stderr_52lts(cmd_result)
                    for e_line in stderr.splitlines():
                        logging.error("[stderr] %s", e_line)
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
                    stdout = results_stdout_52lts(cmd_result)
                    for e_line in stdout.splitlines():
                        logging.error("[stdout] %s", e_line)
                    stderr = results_stderr_52lts(cmd_result)
                    for e_line in stderr.splitlines():
                        logging.error("[stderr] %s", e_line)
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
                logging.debug("Image file %s not found, skipping check",
                              image_filename)
            elif not image_is_checkable:
                logging.debug(
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
               amend_extra_params
                   additional options, used for extending amend

        :return: process.CmdResult object containing the result of the
                command
        """
        cmd_list = [self.image_cmd, 'amend']
        options = ["%s=%s" % (key[6:], val) for key, val in six.iteritems(params)
                   if key.startswith('amend_')]
        if cache_mode:
            cmd_list.append("-t %s" % cache_mode)
        if options:
            cmd_list.append("-o %s" %
                            ",".join(options).replace("extra_params=", ""))
        cmd_list.append("-f %s %s" % (self.image_format, self.image_filename))
        logging.info("Amend image %s" % self.image_filename)
        cmd_result = process.run(" ".join(cmd_list), ignore_status=False)
        cmd_result.stdout = results_stdout_52lts(cmd_result)
        cmd_result.stderr = results_stderr_52lts(cmd_result)
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
        if size:
            cmd_list.append(("--size %s" % size))
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
        access_secret, _ = self._get_access_secret_info()
        meta = _get_image_meta(
            self.tag, self.params, self.root_dir) if access_secret else None
        if meta is not None:
            if raw_copy:
                # drop image secret from meta
                for key in ['encrypt.key-secret', 'key-secret']:
                    if key in meta:
                        meta.pop(key)
            meta['driver'] = cmd_dict.pop("image_format")
            cmd_dict["image_filename"] = "'json:%s'" % json.dumps(meta)

        if self._storage_secret_object:
            cmd_dict["secret_object"] = self._storage_secret_object

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
            logging.warn("Session already present. Don't need to"
                         " login again")
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
                logging.debug("Removing file %s", self.emulated_image)
                if os.path.exists(self.emulated_image):
                    os.unlink(self.emulated_image)
                else:
                    logging.debug("File %s not found", self.emulated_image)


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
