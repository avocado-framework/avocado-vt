"""
Classes and functions to handle block/disk images for KVM.

This exports:
  - two functions for get image/blkdebug filename
  - class for image operates and basic parameters
"""
import logging
import os
import re
import six

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


class QemuImg(storage.QemuImg):

    """
    KVM class for handling operations of disk/block images.
    """

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
            qemu_img_cmd = self.image_cmd
            qemu_img_cmd += " create"

            qemu_img_cmd += " -f %s" % self.image_format

            image_cluster_size = params.get("image_cluster_size", None)
            preallocated = params.get("preallocated", "off")
            encrypted = params.get("encrypted", "off")
            image_extra_params = params.get("image_extra_params", "")
            has_backing_file = params.get('has_backing_file')

            qemu_img_cmd += " -o "
            if self.image_format == "qcow2":
                if preallocated != "off":
                    qemu_img_cmd += "preallocation=%s," % preallocated

                if encrypted != "off":
                    qemu_img_cmd += "encryption=%s," % encrypted

                if image_cluster_size:
                    qemu_img_cmd += "cluster_size=%s," % image_cluster_size

                if has_backing_file == "yes":
                    backing_param = params.object_params("backing_file")
                    backing_file = storage.get_image_filename(backing_param,
                                                              self.root_dir)
                    backing_fmt = backing_param.get("image_format")
                    qemu_img_cmd += "backing_file=%s," % backing_file

                    qemu_img_cmd += "backing_fmt=%s," % backing_fmt

            if image_extra_params:
                qemu_img_cmd += "%s," % image_extra_params

            qemu_img_cmd = qemu_img_cmd.rstrip(" -o")
            qemu_img_cmd = qemu_img_cmd.rstrip(",")

            if self.base_tag:
                qemu_img_cmd += " -b %s" % self.base_image_filename
                if self.base_format:
                    qemu_img_cmd += " -F %s" % self.base_format

            qemu_img_cmd += " %s" % self.image_filename

            qemu_img_cmd += " %s" % self.size

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
        cmd_result.stdout = results_stdout_52lts(cmd_result)
        cmd_result.stderr = results_stderr_52lts(cmd_result)
        return self.image_filename, cmd_result

    def convert(self, params, root_dir, cache_mode=None):
        """
        Convert image

        :param params: dictionary containing the test parameters
        :param root_dir: dir for save the convert image
        :param cache_mode: The cache mode used to write the output disk image.
                           Valid options are: ``none``, ``writeback``
                           (default), ``writethrough``, ``directsync`` and
                           ``unsafe``.

        :note: params should contain:

            convert_image_tag
                the image name of the convert image
            convert_filename
                the name of the image after convert
            convert_fmt
                the format after convert
            compressed
                indicates that target image must be compressed
            encrypted
                there are two value "off" and "on", default value is "off"
        """
        convert_image_tag = params["image_convert"]
        convert_image = params["convert_name_%s" % convert_image_tag]
        convert_compressed = params.get("convert_compressed")
        convert_encrypted = params.get("convert_encrypted", "off")
        preallocated = params.get("preallocated")
        compat = params.get("compat")
        lazy_refcounts = params.get("lazy_refcounts")
        cluster_size = params.get("cluster_size")
        sparse_size = params.get("sparse_size")
        convert_format = params["convert_format_%s" % convert_image_tag]
        params_convert = {"image_name": convert_image,
                          "image_format": convert_format}

        convert_image_filename = storage.get_image_filename(params_convert,
                                                            root_dir)

        cmd = self.image_cmd
        cmd += " convert"
        if convert_compressed == "yes":
            cmd += " -c"
        if sparse_size:
            cmd += " -S %s" % sparse_size

        options = []
        if convert_encrypted != "off":
            options.append("encryption=%s" % convert_encrypted)
        if preallocated:
            options.append("preallocation=%s" % preallocated)
        if cluster_size:
            options.append("cluster_size=%s" % cluster_size)
        if compat:
            options.append("compat=%s" % compat)
            if lazy_refcounts:
                options.append("lazy_refcounts=%s" % lazy_refcounts)
        if options:
            cmd += " -o %s" % ",".join(options)

        if self.image_format:
            cmd += " -f %s" % self.image_format
        cmd += " -O %s" % convert_format
        if cache_mode:
            cmd += " -t %s" % cache_mode
        cmd += " %s %s" % (self.image_filename, convert_image_filename)

        logging.info("Convert image %s from %s to %s", self.image_filename,
                     self.image_format, convert_format)

        process.system(cmd)

        return convert_image_tag

    def rebase(self, params, cache_mode=None):
        """
        Rebase image.

        :param params: dictionary containing the test parameters
        :param cache_mode: the cache mode used to write the output disk image,
                           the valid options are: 'none', 'writeback' (default),
                           'writethrough', 'directsync' and 'unsafe'.

        :note: params should contain:

            cmd
                qemu-img cmd
            snapshot_img
                the snapshot name
            base_img
                base image name
            base_fmt
                base image format
            snapshot_fmt
                the snapshot format
            mode
                there are two value, "safe" and "unsafe", default is "safe"
        """
        self.check_option("base_image_filename")
        self.check_option("base_format")

        rebase_mode = params.get("rebase_mode")
        cmd = self.image_cmd
        cmd += " rebase"
        if self.image_format:
            cmd += " -f %s" % self.image_format
        if cache_mode:
            cmd += " -t %s" % cache_mode
        if rebase_mode == "unsafe":
            cmd += " -u"
        if self.base_tag:
            if self.base_tag == "null":
                cmd += " -b \"\" -F %s %s" % (self.base_format,
                                              self.image_filename)
            else:
                cmd += " -b %s -F %s %s" % (self.base_image_filename,
                                            self.base_format, self.image_filename)
        else:
            raise exceptions.TestError("Can not find the image parameters need"
                                       " for rebase.")

        logging.info("Rebase snapshot %s to %s..." % (self.image_filename,
                                                      self.base_image_filename))
        process.system(cmd)

        return self.base_tag

    def commit(self, params={}, cache_mode=None):
        """
        Commit image to it's base file

        :param cache_mode: the cache mode used to write the output disk image,
            the valid options are: 'none', 'writeback' (default),
            'writethrough', 'directsync' and 'unsafe'.
        """
        cmd = self.image_cmd
        cmd += " commit"
        if cache_mode:
            cmd += " -t %s" % cache_mode
        cmd += " -f %s %s" % (self.image_format, self.image_filename)
        logging.info("Commit snapshot %s" % self.image_filename)
        process.system(cmd)

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
        if os.path.exists(self.image_filename):
            os.unlink(self.image_filename)
        else:
            logging.debug("Image file %s not found", self.image_filename)

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

                chk_cmd = "%s check" % self.image_cmd
                if force_share:
                    chk_cmd += " -U"
                chk_cmd += " %s" % image_filename
                cmd_result = process.run(chk_cmd, ignore_status=True,
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

    def resize(self, size, shrink=False):
        """
        Qemu image resize wrapper.

        :param size: string of size representations.(eg. +1G, -1k, 1T)
        :param shrink: boolean
        :return: process.CmdResult object containing the result of the
                 command
        """
        cmd_list = [self.image_cmd, "resize"]
        if shrink:
            cmd_list.append("--shrink")
        cmd_list.extend([self.image_filename, size])
        cmd_result = process.run(" ".join(cmd_list), ignore_status=True)
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
