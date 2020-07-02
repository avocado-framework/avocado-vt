"""
libguestfs tools test utility functions.
"""

import logging
import signal
import os
import re

import aexpect
from avocado.utils import path
from avocado.utils import process

from . import propcan


class LibguestfsCmdError(Exception):

    """
    Error of libguestfs-tool command.
    """

    def __init__(self, details=''):
        self.details = details
        Exception.__init__(self)

    def __str__(self):
        return str(self.details)


def lgf_cmd_check(cmd):
    """
    To check whether the cmd is supported on this host.

    :param cmd: the cmd to use a libguest tool.
    :return: None if the cmd is not exist, otherwise return its path.
    """
    libguestfs_cmds = ['libguestfs-test-tool', 'guestfish', 'guestmount',
                       'virt-alignment-scan', 'virt-cat', 'virt-copy-in',
                       'virt-copy-out', 'virt-df', 'virt-edit',
                       'virt-filesystems', 'virt-format', 'virt-inspector',
                       'virt-list-filesystems', 'virt-list-partitions',
                       'virt-ls', 'virt-make-fs', 'virt-rescue',
                       'virt-resize', 'virt-sparsify', 'virt-sysprep',
                       'virt-tar', 'virt-tar-in', 'virt-tar-out',
                       'virt-win-reg', 'virt-inspector2']

    if cmd not in libguestfs_cmds:
        raise LibguestfsCmdError(
            "Command %s is not supported by libguestfs yet." % cmd)

    try:
        return path.find_command(cmd)
    except path.CmdNotFoundError:
        logging.warning("You have not installed %s on this host.", cmd)
        return None


def lgf_command(cmd, ignore_status=True, debug=False, timeout=60):
    """
    Interface of libguestfs tools' commands.

    :param cmd: Command line to execute.
    :return: CmdResult object.
    :raise: LibguestfsCmdError if non-zero exit status
            and ignore_status=False
    """
    if debug:
        logging.debug("Running command %s in debug mode.", cmd)

    # Raise exception if ignore_status is False
    try:
        ret = process.run(cmd, ignore_status=ignore_status,
                          verbose=debug, timeout=timeout)
    except process.CmdError as detail:
        raise LibguestfsCmdError(detail)

    if debug:
        logging.debug("status: %s", ret.exit_status)
        logging.debug("stdout: %s", ret.stdout_text.strip())
        logging.debug("stderr: %s", ret.stderr_text.strip())

    # Return CmdResult instance when ignore_status is True
    ret.stdout = ret.stdout_text
    ret.stderr = ret.stderr_text
    return ret


class LibguestfsBase(propcan.PropCanBase):

    """
    Base class of libguestfs tools.
    """

    __slots__ = ['ignore_status', 'debug', 'timeout', 'uri', 'lgf_exec']

    def __init__(self, lgf_exec="/bin/true", ignore_status=True,
                 debug=False, timeout=60, uri=None):
        init_dict = {}
        init_dict['ignore_status'] = ignore_status
        init_dict['debug'] = debug
        init_dict['timeout'] = timeout
        init_dict['uri'] = uri
        init_dict['lgf_exec'] = lgf_exec
        super(LibguestfsBase, self).__init__(init_dict)

    def set_ignore_status(self, ignore_status):
        """
        Enforce setting ignore_status as a boolean.
        """
        if bool(ignore_status):
            self.__dict_set__('ignore_status', True)
        else:
            self.__dict_set__('ignore_status', False)

    def set_debug(self, debug):
        """
        Accessor method for 'debug' property that logs message on change
        """
        if not self.INITIALIZED:
            self.__dict_set__('debug', debug)
        else:
            current_setting = self.__dict_get__('debug')
            desired_setting = bool(debug)
            if not current_setting and desired_setting:
                self.__dict_set__('debug', True)
                logging.debug("Libguestfs debugging enabled")
            # current and desired could both be True
            if current_setting and not desired_setting:
                self.__dict_set__('debug', False)
                logging.debug("Libguestfs debugging disabled")

    def set_timeout(self, timeout):
        """
        Accessor method for 'timeout' property, timeout should be digit
        """
        if type(timeout) is int:
            self.__dict_set__('timeout', timeout)
        else:
            try:
                timeout = int(str(timeout))
                self.__dict_set__('timeout', timeout)
            except ValueError:
                logging.debug("Set timeout failed.")

    def get_uri(self):
        """
        Accessor method for 'uri' property that must exist
        """
        # self.get() would call get_uri() recursivly
        try:
            return self.__dict_get__('uri')
        except KeyError:
            return None


# There are two ways to call guestfish:
# 1.Guestfish classies provided below(shell session)
# 2.guestfs module provided in system libguestfs package

class Guestfish(LibguestfsBase):

    """
    Execute guestfish, using a new guestfish shell each time.
    """

    __slots__ = []

    def __init__(self, disk_img=None, ro_mode=False,
                 libvirt_domain=None, inspector=False,
                 uri=None, mount_options=None, run_mode="interactive"):
        """
        Initialize guestfish command with options.

        :param disk_img: if it is not None, use option '-a disk'.
        :param ro_mode: only for disk_img. add option '--ro' if it is True.
        :param libvirt_domain: if it is not None, use option '-d domain'.
        :param inspector: guestfish mounts vm's disks automatically
        :param uri: guestfish's connect uri
        :param mount_options: Mount the named partition or logical volume
                               on the given mountpoint.
        """
        guestfs_exec = "guestfish"
        if lgf_cmd_check(guestfs_exec) is None:
            raise LibguestfsCmdError

        if run_mode not in ['remote', 'interactive']:
            raise AssertionError("run_mode should be remote or interactive")

        # unset GUESTFISH_XXX environment parameters
        # to avoid color of guestfish shell session for testing
        color_envs = ["GUESTFISH_PS1", "GUESTFISH_OUTPUT",
                      "GUESTFISH_RESTORE", "GUESTFISH_INIT"]
        unset_cmd = ""
        for env in color_envs:
            unset_cmd += "unset %s;" % env
        if run_mode == "interactive" and unset_cmd:
            guestfs_exec = unset_cmd + " " + guestfs_exec

        if run_mode == "remote":
            guestfs_exec += " --listen"
        else:
            if uri:
                guestfs_exec += " -c '%s'" % uri
            if disk_img:
                guestfs_exec += " -a '%s'" % disk_img
            if libvirt_domain:
                guestfs_exec += " -d '%s'" % libvirt_domain
            if ro_mode:
                guestfs_exec += " --ro"
            if inspector:
                guestfs_exec += " -i"
            if mount_options is not None:
                guestfs_exec += " --mount %s" % mount_options

        super(Guestfish, self).__init__(guestfs_exec)

    def complete_cmd(self, command):
        """
        Execute built-in command in a complete guestfish command
        (Not a guestfish session).
        command: guestfish [--options] [commands]
        """
        guestfs_exec = self.__dict_get__('lgf_exec')
        ignore_status = self.__dict_get__('ignore_status')
        debug = self.__dict_get__('debug')
        timeout = self.__dict_get__('timeout')
        if command:
            guestfs_exec += " %s" % command
            return lgf_command(guestfs_exec, ignore_status, debug, timeout)
        else:
            raise LibguestfsCmdError("No built-in command was passed.")


class GuestfishSession(aexpect.ShellSession):

    """
    A shell session of guestfish.
    """

    # Check output against list of known error-status strings
    ERROR_REGEX_LIST = ['libguestfs: error:\s*']

    def __init__(self, guestfs_exec=None, a_id=None, prompt=r"><fs>\s*"):
        """
        Initialize guestfish session server, or client if id set.

        :param guestfs_cmd: path to guestfish executable
        :param id: ID of an already running server, if accessing a running
                server, or None if starting a new one.
        :param prompt: Regular expression describing the shell's prompt line.
        """
        # aexpect tries to auto close session because no clients connected yet
        super(GuestfishSession, self).__init__(guestfs_exec, a_id,
                                               prompt=prompt,
                                               auto_close=False)

    def cmd_status_output(self, cmd, timeout=60, internal_timeout=None,
                          print_func=None):
        """
        Send a guestfish command and return its exit status and output.

        :param cmd: guestfish command to send
                    (must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to
                return
        :param internal_timeout: The timeout to pass to read_nonblocking
        :param print_func: A function to be used to print the data being read
                (should take a string parameter)
        :return: A tuple (status, output) where status is the exit status and
                output is the output of cmd
        :raise ShellTimeoutError: Raised if timeout expires
        :raise ShellProcessTerminatedError: Raised if the shell process
                terminates while waiting for output
        :raise ShellStatusError: Raised if the exit status cannot be obtained
        :raise ShellError: Raised if an unknown error occurs
        """
        out = self.cmd_output(cmd, timeout, internal_timeout, print_func)
        for line in out.splitlines():
            if self.match_patterns(line, self.ERROR_REGEX_LIST) is not None:
                return 1, out
        return 0, out

    def cmd_result(self, cmd, ignore_status=False):
        """Mimic process.run()"""
        exit_status, stdout = self.cmd_status_output(cmd)
        stderr = ''  # no way to retrieve this separately
        result = process.CmdResult(cmd, stdout, stderr, exit_status)
        if not ignore_status and exit_status:
            raise process.CmdError(cmd, result,
                                   "Guestfish Command returned non-zero exit status")
        return result


class GuestfishRemote(object):

    """
    Remote control of guestfish.
    """

    # Check output against list of known error-status strings
    ERROR_REGEX_LIST = ['libguestfs: error:\s*']

    def __init__(self, guestfs_exec=None, a_id=None):
        """
        Initialize guestfish session server, or client if id set.

        :param guestfs_cmd: path to guestfish executable
        :param a_id: guestfish remote id
        """
        if a_id is None:
            try:
                ret = process.run(guestfs_exec, ignore_status=False,
                                  verbose=True, timeout=60)
            except process.CmdError as detail:
                raise LibguestfsCmdError(detail)
            self.a_id = re.search(b"\d+", ret.stdout.strip()).group()
        else:
            self.a_id = a_id

    def get_id(self):
        return self.a_id

    def cmd_status_output(self, cmd, ignore_status=None, verbose=None, timeout=60):
        """
        Send a guestfish command and return its exit status and output.

        :param cmd: guestfish command to send(must not contain newline characters)
        :param timeout: The duration (in seconds) to wait for the prompt to return
        :return: A tuple (status, output) where status is the exit status
                 and output is the output of cmd
        :raise LibguestfsCmdError: Raised if commands execute failed
        """
        guestfs_exec = "guestfish --remote=%s " % self.a_id
        cmd = guestfs_exec + cmd
        try:
            ret = process.run(cmd, ignore_status=ignore_status,
                              verbose=verbose, timeout=timeout)
        except process.CmdError as detail:
            raise LibguestfsCmdError(detail)

        for line in self.ERROR_REGEX_LIST:
            if re.search(line, ret.stdout_text.strip()):
                e_msg = ('Error pattern %s found on output of %s: %s' %
                         (line, cmd, ret.stdout_text.strip()))
                raise LibguestfsCmdError(e_msg)

        logging.debug("command: %s", cmd)
        logging.debug("stdout: %s", ret.stdout_text.strip())

        return 0, ret.stdout_text.strip()

    def cmd(self, cmd, ignore_status=False):
        """Mimic process.run()"""
        exit_status, stdout = self.cmd_status_output(cmd)
        stderr = ''  # no way to retrieve this separately
        result = process.CmdResult(cmd, stdout, stderr, exit_status)
        result.stdout = result.stdout_text
        result.stderr = result.stderr_text
        if not ignore_status and exit_status:
            raise process.CmdError(cmd, result,
                                   "Guestfish Command returned non-zero exit status")
        return result

    def cmd_result(self, cmd, ignore_status=False):
        """Mimic process.run()"""
        exit_status, stdout = self.cmd_status_output(cmd)
        stderr = ''  # no way to retrieve this separately
        result = process.CmdResult(cmd, stdout, stderr, exit_status)
        result.stdout = result.stdout_text
        result.stderr = result.stderr_text
        if not ignore_status and exit_status:
            raise process.CmdError(cmd, result,
                                   "Guestfish Command returned non-zero exit status")
        return result


class GuestfishPersistent(Guestfish):

    """
    Execute operations using persistent guestfish session.
    """

    __slots__ = ['session_id', 'run_mode']

    # Help detect leftover sessions
    SESSION_COUNTER = 0

    def __init__(self, disk_img=None, ro_mode=False,
                 libvirt_domain=None, inspector=False,
                 uri=None, mount_options=None, run_mode="interactive"):
        super(GuestfishPersistent, self).__init__(disk_img, ro_mode,
                                                  libvirt_domain, inspector,
                                                  uri, mount_options, run_mode)
        self.__dict_set__('run_mode', run_mode)

        if self.get('session_id') is None:
            # set_uri does not call when INITIALIZED = False
            # and no session_id passed to super __init__
            self.new_session()

        # Check whether guestfish session is prepared.
        guestfs_session = self.open_session()
        if run_mode != "remote":
            status, output = guestfs_session.cmd_status_output(
                'is-config', timeout=60)
            if status != 0:
                logging.debug(
                    "Persistent guestfish session is not responding.")
                raise aexpect.ShellStatusError(self.lgf_exec, 'is-config')

    def close_session(self):
        """
        If a persistent session exists, close it down.
        """
        try:
            run_mode = self.get('run_mode')
            existing = self.open_session()
            # except clause exits function
            # Try to end session with inner command 'quit'
            try:
                existing.cmd("quit")
            # It should jump to exception followed normally
            except aexpect.ShellProcessTerminatedError:
                self.__class__.SESSION_COUNTER -= 1
                self.__dict_del__('session_id')
                return  # guestfish session was closed normally
            # Close with 'quit' did not respond
            # So close with aexpect functions
            if run_mode != "remote":
                if existing.is_alive():
                    # try nicely first
                    existing.close()
                    if existing.is_alive():
                        # Be mean, incase it's hung
                        existing.close(sig=signal.SIGTERM)
                    # Keep count:
                    self.__class__.SESSION_COUNTER -= 1
                    self.__dict_del__('session_id')
        except LibguestfsCmdError:
            # Allow other exceptions to be raised
            pass  # session was closed already

    def new_session(self):
        """
        Open new session, closing any existing
        """
        # Accessors may call this method, avoid recursion
        # Must exist, can't be None
        guestfs_exec = self.__dict_get__('lgf_exec')
        self.close_session()
        # Always create new session
        run_mode = self.get('run_mode')
        if run_mode == "remote":
            new_session = GuestfishRemote(guestfs_exec)
        else:
            new_session = GuestfishSession(guestfs_exec)
        # Keep count
        self.__class__.SESSION_COUNTER += 1
        session_id = new_session.get_id()
        self.__dict_set__('session_id', session_id)

    def open_session(self):
        """
        Return session with session_id in this class.
        """
        try:
            session_id = self.__dict_get__('session_id')
            run_mode = self.get('run_mode')
            if session_id:
                try:
                    if run_mode == "remote":
                        return GuestfishRemote(a_id=session_id)
                    else:
                        return GuestfishSession(a_id=session_id)
                except aexpect.ShellStatusError:
                    # session was already closed
                    self.__dict_del__('session_id')
                    raise LibguestfsCmdError(
                        "Open session '%s' failed." % session_id)
        except KeyError:
            raise LibguestfsCmdError("No session id.")

    # Inner command for guestfish should be executed in a guestfish session
    def inner_cmd(self, command):
        """
        Execute inner command of guestfish in a pesistent session.

        :param command: inner command to be executed.
        """
        session = self.open_session()
        # Allow to raise error by default.
        ignore_status = self.__dict_get__('ignore_status')
        return session.cmd_result(command, ignore_status=ignore_status)

    def add_drive(self, filename):
        """
        add-drive - add an image to examine or modify

        This function is the equivalent of calling "add_drive_opts" with no
        optional parameters, so the disk is added writable, with the format
        being detected automatically.
        """
        return self.inner_cmd("add-drive %s" % filename)

    def add_drive_opts(self, filename, readonly=False, format=None,
                       iface=None, name=None, label=None, protocol=None,
                       server=None, username=None, secret=None,
                       cachemode=None, discard=None, copyonread=False):
        """
        add-drive-opts - add an image to examine or modify.

        This function adds a disk image called "filename" to the handle.
        "filename" may be a regular host file or a host device.
        """
        cmd = "add-drive-opts %s" % filename

        if readonly:
            cmd += " readonly:true"
        else:
            cmd += " readonly:false"
        if format:
            cmd += " format:%s" % format
        if iface:
            cmd += " iface:%s" % iface
        if name:
            cmd += " name:%s" % name
        if label:
            cmd += " label:%s" % label
        if protocol:
            cmd += " protocol:%s" % protocol
        if server:
            cmd += " server:%s" % server
        if username:
            cmd += " username:%s" % username
        if secret:
            cmd += " secret:%s" % secret
        if cachemode:
            cmd += " cachemode:%s" % cachemode
        if discard:
            cmd += " discard:%s" % discard
        if copyonread:
            cmd += " copyonread:true"
        else:
            # The default is false for copyonread.
            # If copyonread param is false,
            # It's no need to set " copyonread:false" explicitly.
            pass

        return self.inner_cmd(cmd)

    def add_drive_ro(self, filename):
        """
        add-ro/add-drive-ro - add a drive in snapshot mode (read-only)

        This function is the equivalent of calling "add_drive_opts" with the
        optional parameter "GUESTFS_ADD_DRIVE_OPTS_READONLY" set to 1, so the
        disk is added read-only, with the format being detected automatically.
        """
        return self.inner_cmd("add-drive-ro %s" % filename)

    def add_domain(self, domain, libvirturi=None, readonly=False, iface=None,
                   live=False, allowuuid=False, readonlydisk=None):
        """
        domain/add-domain - add the disk(s) from a named libvirt domain

        This function adds the disk(s) attached to the named libvirt domain
        "dom". It works by connecting to libvirt, requesting the domain and
        domain XML from libvirt, parsing it for disks, and calling
        "add_drive_opts" on each one.
        """
        cmd = "add-domain %s" % domain

        if libvirturi:
            cmd += " libvirturi:%s" % libvirturi
        if readonly:
            cmd += " readonly:true"
        else:
            cmd += " readonly:false"
        if iface:
            cmd += " iface:%s" % iface
        if live:
            cmd += " live:true"
        if allowuuid:
            cmd += " allowuuid:true"
        if readonlydisk:
            cmd += " readonlydisk:%s" % readonlydisk

        return self.inner_cmd(cmd)

    def run(self):
        """
        run/launch - launch the qemu subprocess

        Internally libguestfs is implemented by running a virtual machine
        using qemu.
        """
        return self.inner_cmd("launch")

    def df(self):
        """
        df - report file system disk space usage

        This command runs the "df" command to report disk space used.
        """
        return self.inner_cmd("df")

    def df_h(self):
        """
        df-h - report file system disk space usage (human readable)

        This command runs the "df -h" command to report disk space used in
        human-readable format.
        """
        return self.inner_cmd("df-h")

    def dd(self, src, dest):
        """
        dd - copy from source to destination using dd

        This command copies from one source device or file "src" to another
        destination device or file "dest".Normally you would use this to copy
        to or from a device or partition,for example to duplicate a filesystem
        """
        return self.inner_cmd("dd %s %s" % (src, dest))

    def copy_size(self, src, dest, size):
        """
        copy-size - copy size bytes from source to destination using dd

        This command copies exactly "size" bytes from one source device or file
        "src" to another destination device or file "dest".
        """
        return self.inner_cmd("copy-size %s %s %s" % (src, dest, size))

    def list_partitions(self):
        """
        list-partitions - list the partitions

        List all the partitions detected on all block devices.
        """
        return self.inner_cmd("list-partitions")

    def mount(self, device, mountpoint):
        """
        mount - mount a guest disk at a position in the filesystem

        Mount a guest disk at a position in the filesystem.
        """
        return self.inner_cmd("mount %s %s" % (device, mountpoint))

    def mount_ro(self, device, mountpoint):
        """
        mount-ro - mount a guest disk, read-only

        This is the same as the "mount" command, but it mounts the
        filesystem with the read-only (*-o ro*) flag.
        """
        return self.inner_cmd("mount-ro %s %s" % (device, mountpoint))

    def mount_options(self, options, device, mountpoint):
        """
        mount - mount a guest disk at a position in the filesystem

        Mount a guest disk at a position in the filesystem.
        """
        return self.inner_cmd("mount-options %s %s %s" % (options, device, mountpoint))

    def mounts(self):
        """
        mounts - show mounted filesystems

        This returns the list of currently mounted filesystems.
        """
        return self.inner_cmd("mounts")

    def mountpoints(self):
        """
        mountpoints - show mountpoints

        This call is similar to "mounts".
        That call returns a list of devices.
        """
        return self.inner_cmd("mountpoints")

    def do_mount(self, mountpoint):
        """
        do_mount - Automaticly mount

        Mount a lvm or physical partation to '/'
        """
        partition_type = self.params.get("partition_type")
        if partition_type == "lvm":
            vg_name = self.params.get("vg_name", "vol_test")
            lv_name = self.params.get("lv_name", "vol_file")
            device = "/dev/%s/%s" % (vg_name, lv_name)
            logging.info("mount lvm partition...%s" % device)
        elif partition_type == "physical":
            pv_name = self.params.get("pv_name", "/dev/sdb")
            device = pv_name + "1"
            logging.info("mount physical partition...%s" % device)
        self.mount(device, mountpoint)

    def read_file(self, path):
        """
        read-file - read a file

        This calls returns the contents of the file "path" as a buffer.
        """
        return self.inner_cmd("read-file %s" % path)

    def cat(self, path):
        """
        cat - list the contents of a file

        Return the contents of the file named "path".
        """
        return self.inner_cmd("cat %s" % path)

    def write(self, path, content):
        """
        write - create a new file

        This call creates a file called "path". The content of the file
        is the string "content" (which can contain any 8 bit data).
        """
        return self.inner_cmd("write '%s' \"%s\"" % (path, content))

    def write_append(self, path, content):
        """
        write-append - append content to end of file

        This call appends "content" to the end of file "path".
        If "path" does not exist, then a new file is created.
        """
        return self.inner_cmd("write-append '%s' \"%s\"" % (path, content))

    def inspect_os(self):
        """
        inspect-os - inspect disk and return list of operating systems found

        This function uses other libguestfs functions and certain heuristics to
        inspect the disk(s) (usually disks belonging to a virtual machine),
        looking for operating systems.
        """
        return self.inner_cmd("inspect-os")

    def inspect_get_roots(self):
        """
        inspect-get-roots - return list of operating systems found by
        last inspection

        This function is a convenient way to get the list of root devices
        """
        return self.inner_cmd("inspect-get-roots")

    def inspect_get_arch(self, root):
        """
        inspect-get-arch - get architecture of inspected operating system

        This returns the architecture of the inspected operating system.
        """
        return self.inner_cmd("inspect-get-arch %s" % root)

    def inspect_get_distro(self, root):
        """
        inspect-get-distro - get distro of inspected operating system

        This returns the distro (distribution) of the inspected
        operating system.
        """
        return self.inner_cmd("inspect-get-distro %s" % root)

    def inspect_get_filesystems(self, root):
        """
        inspect-get-filesystems - get filesystems associated with inspected
        operating system

        This returns a list of all the filesystems that we think are associated
        with this operating system.
        """
        return self.inner_cmd("inspect-get-filesystems %s" % root)

    def inspect_get_hostname(self, root):
        """
        inspect-get-hostname - get hostname of the operating system

        This function returns the hostname of the operating system as found by
        inspection of the guest's configuration files.
        """
        return self.inner_cmd("inspect-get-hostname %s" % root)

    def inspect_get_major_version(self, root):
        """
        inspect-get-major-version - get major version of inspected operating
        system

        This returns the major version number of the inspected
        operating system.
        """
        return self.inner_cmd("inspect-get-major-version %s" % root)

    def inspect_get_minor_version(self, root):
        """
        inspect-get-minor-version - get minor version of inspected operating
        system

        This returns the minor version number of the inspected operating system
        """
        return self.inner_cmd("inspect-get-minor-version %s" % root)

    def inspect_get_mountpoints(self, root):
        """
        inspect-get-mountpoints - get mountpoints of inspected operating system

        This returns a hash of where we think the filesystems associated with
        this operating system should be mounted.
        """
        return self.inner_cmd("inspect-get-mountpoints %s" % root)

    def list_filesystems(self):
        """
        list-filesystems - list filesystems

        This inspection command looks for filesystems on partitions, block
        devices and logical volumes, returning a list of devices containing
        filesystems and their type.
        """
        return self.inner_cmd("list-filesystems")

    def list_devices(self):
        """
        list-devices - list the block devices

        List all the block devices.
        """
        return self.inner_cmd("list-devices")

    def tar_out(self, directory, tarfile):
        """
        tar-out - pack directory into tarfile

        This command packs the contents of "directory" and downloads it
        to local file "tarfile".
        """
        return self.inner_cmd("tar-out %s %s" % (directory, tarfile))

    def tar_in(self, tarfile, directory):
        """
        tar-in - unpack tarfile to directory

        This command uploads and unpacks local file "tarfile"
        (an *uncompressed* tar file) into "directory".
        """
        return self.inner_cmd("tar-in %s %s" % (tarfile, directory))

    def tar_in_opts(self, tarfile, directory, compress=None):
        """
        tar-in-opts - unpack tarfile to directory

        This command uploads and unpacks local file "tarfile"
        (an *compressed* tar file) into "directory".
        """
        if compress:
            return self.inner_cmd("tar-in-opts %s %s compress:%s" % (tarfile, directory, compress))
        else:
            return self.inner_cmd("tar-in-opts %s %s" % (tarfile, directory))

    def file_architecture(self, filename):
        """
        file-architecture - detect the architecture of a binary file

        This detects the architecture of the binary "filename", and returns it
        if known.
        """
        return self.inner_cmd("file-architecture %s" % filename)

    def filesize(self, file):
        """
        filesize - return the size of the file in bytes

        This command returns the size of "file" in bytes.
        """
        return self.inner_cmd("filesize %s" % file)

    def stat(self, path):
        """
        stat - get file information

        Returns file information for the given "path".
        """
        return self.inner_cmd("stat %s" % path)

    def lstat(self, path):
        """
        lstat - get file information for a symbolic link

        Returns file information for the given "path".
        """
        return self.inner_cmd("lstat %s" % path)

    def lstatlist(self, path, names):
        """
        lstatlist - lstat on multiple files

        This call allows you to perform the "lstat" operation on multiple files,
        where all files are in the directory "path". "names" is the list of
        files from this directory.
        """
        return self.inner_cmd("lstatlist %s %s" % (path, names))

    def umask(self, mask):
        """
        umask - set file mode creation mask (umask)

        This function sets the mask used for creating new files and device nodes
        to "mask & 0777".
        """
        return self.inner_cmd("umask %s" % mask)

    def get_umask(self):
        """
        get-umask - get the current umask

        Return the current umask. By default the umask is 022 unless it has been
        set by calling "umask".
        """
        return self.inner_cmd("get-umask")

    def mkdir(self, path):
        """
        mkdir - create a directory

        Create a directory named "path".
        """
        return self.inner_cmd("mkdir %s" % path)

    def mkdir_p(self, path):
        """
        mkdir-p - create a directory and parents

        Create a directory named "path", creating any parent directories as necessary.
        This is like the "mkdir -p" shell command.
        """
        return self.inner_cmd("mkdir-p %s" % path)

    def mkdir_mode(self, path, mode):
        """
        mkdir-mode - create a directory with a particular mode

        This command creates a directory, setting the initial permissions of the
        directory to "mode".
        """
        return self.inner_cmd("mkdir-mode %s %s" % (path, mode))

    def mknod(self, mode, devmajor, devminor, path):
        """
        mknod - make block, character or FIFO devices

        This call creates block or character special devices, or named pipes
        (FIFOs).
        """
        return self.inner_cmd("mknod %s %s %s %s" % (mode, devmajor, devminor, path))

    def rm_rf(self, path):
        """
        rm-rf - remove a file or directory recursively

        Remove the file or directory "path", recursively removing the contents
        if its a directory. This is like the "rm -rf" shell command.
        """
        return self.inner_cmd("rm-rf %s" % path)

    def copy_out(self, remote, localdir):
        """
        copy-out - copy remote files or directories out of an image

        "copy-out" copies remote files or directories recursively out of the
        disk image, placing them on the host disk in a local directory called
        "localdir" (which must exist).
        """
        return self.inner_cmd("copy-out %s %s" % (remote, localdir))

    def copy_in(self, local, remotedir):
        """
        copy-in - copy local files or directories into an image

        "copy-in" copies local files or directories recursively into the disk
        image, placing them in the directory called "/remotedir" (which must
        exist).
        """
        return self.inner_cmd("copy-in %s /%s" % (local, remotedir))

    def chmod(self, mode, path):
        """
        chmod - change file mode

        Change the mode (permissions) of "path" to "mode". Only numeric modes
        are supported.
        """
        return self.inner_cmd("chmod %s %s" % (mode, path))

    def chown(self, owner, group, path):
        """
        chown - change file owner and group

        Change the file owner to "owner" and group to "group".
        """
        return self.inner_cmd("chown %s %s %s" % (owner, group, path))

    def lchown(self, owner, group, path):
        """
        lchown - change file owner and group

        Change the file owner to "owner" and group to "group". This is like
        "chown" but if "path" is a symlink then the link itself is changed, not
        the target.
        """
        return self.inner_cmd("lchown %s %s %s" % (owner, group, path))

    def du(self, path):
        """
        du - estimate file space usage

        This command runs the "du -s" command to estimate file space usage for
        "path".
        """
        return self.inner_cmd("du %s" % path)

    def file(self, path):
        """
        file - determine file type

        This call uses the standard file(1) command to determine the type or
        contents of the file.
        """
        return self.inner_cmd("file %s" % path)

    def rm(self, path):
        """
        rm - remove a file

        Remove the single file "path".
        """
        return self.inner_cmd("rm %s" % path)

    def is_file(self, path, followsymlinks=None):
        """
        is-file - test if a regular file

        This returns "true" if and only if there is a regular file with the
        given "path" name.
        """
        cmd = "is-file %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_file_opts(self, path, followsymlinks=None):
        """
        is-file_opts - test if a regular file

        This returns "true" if and only if there is a regular file with the
        given "path" name.

        An alias of command is-file
        """
        cmd = "is-file-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_blockdev(self, path, followsymlinks=None):
        """
        is-blockdev - test if block device

        This returns "true" if and only if there is a block device with the
        given "path" name
        """
        cmd = "is-blockdev %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_blockdev_opts(self, path, followsymlinks=None):
        """
        is-blockdev_opts - test if block device

        This returns "true" if and only if there is a block device with the
        given "path" name

        An alias of command is-blockdev
        """
        cmd = "is-blockdev-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_chardev(self, path, followsymlinks=None):
        """
        is-chardev - test if character device

        This returns "true" if and only if there is a character device with the
        given "path" name.
        """
        cmd = "is-chardev %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_chardev_opts(self, path, followsymlinks=None):
        """
        is-chardev_opts - test if character device

        This returns "true" if and only if there is a character device with the
        given "path" name.

        An alias of command is-chardev
        """
        cmd = "is-chardev-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_dir(self, path, followsymlinks=None):
        """
        is-dir - test if a directory

        This returns "true" if and only if there is a directory with the given
        "path" name. Note that it returns false for other objects like files.
        """
        cmd = "is-dir %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_dir_opts(self, path, followsymlinks=None):
        """
        is-dir-opts - test if character device

        This returns "true" if and only if there is a character device with the
        given "path" name.

        An alias of command is-dir
        """
        cmd = "is-dir-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_fifo(self, path, followsymlinks=None):
        """
        is-fifo - test if FIFO (named pipe)

        This returns "true" if and only if there is a FIFO (named pipe) with
        the given "path" name.
        """
        cmd = "is-fifo %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_fifo_opts(self, path, followsymlinks=None):
        """
        is-fifo-opts - test if FIFO (named pipe)

        This returns "true" if and only if there is a FIFO (named pipe) with
        the given "path" name.

        An alias of command is-fifo
        """
        cmd = "is-fifo-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_lv(self, device):
        """
        is-lv - test if device is a logical volume

        This command tests whether "device" is a logical volume, and returns
        true iff this is the case.
        """
        return self.inner_cmd("is-lv %s" % device)

    def is_socket(self, path, followsymlinks=None):
        """
        is-socket - test if socket

        This returns "true" if and only if there is a Unix domain socket with
        the given "path" name.
        """
        cmd = "is-socket %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_socket_opts(self, path, followsymlinks=None):
        """
        is-socket-opts - test if socket

        This returns "true" if and only if there is a Unix domain socket with
        the given "path" name.

        An alias of command is-socket
        """
        cmd = "is-socket-opts %s" % path

        if followsymlinks:
            cmd += " followsymlinks:%s" % followsymlinks

        return self.inner_cmd(cmd)

    def is_symlink(self, path):
        """
        is-symlink - test if symbolic link

        This returns "true" if and only if there is a symbolic link with the
        given "path" name.
        """
        return self.inner_cmd("is-symlink %s" % path)

    def is_whole_device(self, device):
        """
        is_whole_device - test if a device is a whole device

        This returns "true" if and only if "device" refers to a whole block
        device. That is, not a partition or a logical device.
        """
        return self.inner_cmd("is-whole-device %s" % device)

    def is_zero(self, path):
        """
        is-zero - test if a file contains all zero bytes

        This returns true iff the file exists and the file is empty or it
        contains all zero bytes.
        """
        return self.inner_cmd("is-zero %s" % path)

    def is_zero_device(self, device):
        """
        is-zero-device - test if a device contains all zero bytes

        This returns true iff the device exists and contains all zero bytes.
        Note that for large devices this can take a long time to run.
        """
        return self.inner_cmd("is-zero-device %s" % device)

    def cp(self, src, dest):
        """
        cp - copy a file

        This copies a file from "src" to "dest" where "dest" is either a
        destination filename or destination directory.
        """
        return self.inner_cmd("cp %s %s" % (src, dest))

    def exists(self, path):
        """
        exists - test if file or directory exists

        This returns "true" if and only if there is a file, directory (or
        anything) with the given "path" name
        """
        return self.inner_cmd("exists %s" % path)

    def cp_a(self, src, dest):
        """
        cp-a - copy a file or directory recursively

        This copies a file or directory from "src" to "dest" recursively using
        the "cp -a" command.
        """
        return self.inner_cmd("cp-a %s %s" % (src, dest))

    def equal(self, file1, file2):
        """
        equal - test if two files have equal contents

        This compares the two files "file1" and "file2" and returns true if
        their content is exactly equal, or false otherwise.
        """
        return self.inner_cmd("equal %s %s" % (file1, file2))

    def fill(self, c, len, path):
        """
        fill - fill a file with octets

        This command creates a new file called "path". The initial content of
        the file is "len" octets of "c", where "c" must be a number in the range
        "[0..255]".
        """
        return self.inner_cmd("fill %s %s %s" % (c, len, path))

    def fill_dir(self, dir, nr):
        """
        fill-dir - fill a directory with empty files

        This function, useful for testing filesystems, creates "nr" empty files
        in the directory "dir" with names 00000000 through "nr-1" (ie. each file
        name is 8 digits long padded with zeroes).
        """
        return self.inner_cmd("fill-dir %s %s" % (dir, nr))

    def fill_pattern(self, pattern, len, path):
        """
        fill-pattern - fill a file with a repeating pattern of bytes

        This function is like "fill" except that it creates a new file of length
        "len" containing the repeating pattern of bytes in "pattern". The
        pattern is truncated if necessary to ensure the length of the file is
        exactly "len" bytes.
        """
        return self.inner_cmd("fill-pattern %s %s %s" % (pattern, len, path))

    def strings(self, path):
        """
        strings - print the printable strings in a file

        This runs the strings(1) command on a file and returns the list of
        printable strings found.
        """
        return self.inner_cmd("strings %s" % path)

    def head(self, path):
        """
        head - return first 10 lines of a file

        This command returns up to the first 10 lines of a file as a list of
        strings.
        """
        return self.inner_cmd("head %s" % path)

    def head_n(self, nrlines, path):
        """
        head-n - return first N lines of a file

        If the parameter "nrlines" is a positive number, this returns the first
        "nrlines" lines of the file "path".
        """
        return self.inner_cmd("head-n %s %s" % (nrlines, path))

    def tail(self, path):
        """
        tail - return last 10 lines of a file

        This command returns up to the last 10 lines of a file as a list of
        strings.
        """
        return self.inner_cmd("tail %s" % path)

    def pread(self, path, count, offset):
        """
        pread - read part of a file

        This command lets you read part of a file. It reads "count" bytes of the
        file, starting at "offset", from file "path".
        """
        return self.inner_cmd("pread %s %s %s" % (path, count, offset))

    def hexdump(self, path):
        """
        hexdump - dump a file in hexadecimal

        This runs "hexdump -C" on the given "path". The result is the
        human-readable, canonical hex dump of the file.
        """
        return self.inner_cmd("hexdump %s" % path)

    def more(self, filename):
        """
        more - view a file

        This is used to view a file.
        """
        return self.inner_cmd("more %s" % filename)

    def download(self, remotefilename, filename):
        """
        download - download a file to the local machine

        Download file "remotefilename" and save it as "filename" on the local
        machine.
        """
        return self.inner_cmd("download %s %s" % (remotefilename, filename))

    def download_offset(self, remotefilename, filename, offset, size):
        """
        download-offset - download a file to the local machine with offset and
        size

        Download file "remotefilename" and save it as "filename" on the local
        machine.
        """
        return self.inner_cmd("download-offset %s %s %s %s" % (remotefilename, filename, offset, size))

    def upload(self, filename, remotefilename):
        """
        upload - upload a file from the local machine

        Upload local file "filename" to "remotefilename" on the filesystem.
        """
        return self.inner_cmd("upload %s %s" % (filename, remotefilename))

    def upload_offset(self, filename, remotefilename, offset):
        """
        upload - upload a file from the local machine with offset

        Upload local file "filename" to "remotefilename" on the filesystem.
        """
        return self.inner_cmd("upload-offset %s %s %s" % (filename, remotefilename, offset))

    def fallocate(self, path, len):
        """
        fallocate - preallocate a file in the guest filesystem

        This command preallocates a file (containing zero bytes) named "path" of
        size "len" bytes. If the file exists already, it is overwritten.
        """
        return self.inner_cmd("fallocate %s %s" % (path, len))

    def fallocate64(self, path, len):
        """
        fallocate - preallocate a file in the guest filesystem

        This command preallocates a file (containing zero bytes) named "path" of
        size "len" bytes. If the file exists already, it is overwritten.
        """
        return self.inner_cmd("fallocate64 %s %s" % (path, len))

    def part_init(self, device, parttype):
        """
        part-init - create an empty partition table

        This creates an empty partition table on "device" of one of the
        partition types listed below. Usually "parttype" should be either
        "msdos" or "gpt" (for large disks).
        """
        return self.inner_cmd("part-init %s %s" % (device, parttype))

    def part_add(self, device, prlogex, startsect, endsect):
        """
        part-add - add a partition to the device

        This command adds a partition to "device". If there is no partition
        table on the device, call "part_init" first.
        """
        cmd = "part-add %s %s %s %s" % (device, prlogex, startsect, endsect)
        return self.inner_cmd(cmd)

    def part_del(self, device, partnum):
        """
        part-del device partnum

        This command deletes the partition numbered "partnum" on "device".

        Note that in the case of MBR partitioning, deleting an extended
        partition also deletes any logical partitions it contains.
        """
        return self.inner_cmd("part_del %s %s" % (device, partnum))

    def part_set_bootable(self, device, partnum, bootable):
        """
        part-set-bootable device partnum bootable

        This sets the bootable flag on partition numbered "partnum" on device
        "device". Note that partitions are numbered from 1.
        """
        return self.inner_cmd("part-set-bootable %s %s %s" % (device, partnum, bootable))

    def part_set_mbr_id(self, device, partnum, idbyte):
        """
        part-set-mbr-id - set the MBR type byte (ID byte) of a partition

        Sets the MBR type byte (also known as the ID byte) of the numbered
        partition "partnum" to "idbyte". Note that the type bytes quoted in
        most documentation are in fact hexadecimal numbers, but usually documented
        without any leading "0x" which might be confusing.
        """
        return self.inner_cmd("part-set-mbr-id %s %s %s" % (device, partnum, idbyte))

    def part_set_name(self, device, partnum, name):
        """
        part-set-name - set partition name

        This sets the partition name on partition numbered "partnum" on device
        "device". Note that partitions are numbered from 1.
        """
        return self.inner_cmd("part-set-name %s %s %s" % (device, partnum, name))

    def part_to_dev(self, partition):
        """
        part-to-dev - convert partition name to device name

        This function takes a partition name (eg. "/dev/sdb1") and removes the
        partition number, returning the device name (eg. "/dev/sdb").

        The named partition must exist, for example as a string returned from
        "list_partitions".
        """
        return self.inner_cmd("part-to-dev %s" % partition)

    def part_to_partnum(self, partition):
        """
        part-to-partnum - convert partition name to partition number

        This function takes a partition name (eg. "/dev/sdb1") and returns the
        partition number (eg. 1).

        The named partition must exist, for example as a string returned from
        "list_partitions".
        """
        return self.inner_cmd("part_to_partnum %s" % partition)

    def checksum(self, csumtype, path):
        """
        checksum - compute MD5, SHAx or CRC checksum of file

        This call computes the MD5, SHAx or CRC checksum of the file named
        "path".
        """
        return self.inner_cmd("checksum %s %s" % (csumtype, path))

    def checksum_device(self, csumtype, device):
        """
        checksum-device - compute MD5, SHAx or CRC checksum of the contents of a
        device

        This call computes the MD5, SHAx or CRC checksum of the contents of the
        device named "device". For the types of checksums supported see the
        "checksum" command.
        """
        return self.inner_cmd("checksum-device %s %s" % (csumtype, device))

    def checksums_out(self, csumtype, directory, sumsfile):
        """
        checksums-out - compute MD5, SHAx or CRC checksum of files in a
        directory

        This command computes the checksums of all regular files in "directory"
        and then emits a list of those checksums to the local output file
        "sumsfile".
        """
        return self.inner_cmd("checksums-out %s %s %s" % (csumtype, directory, sumsfile))

    def is_config(self):
        """
        is-config - is ready to accept commands

        This returns true if this handle is in the "CONFIG" state
        """
        return self.inner_cmd("is-config")

    def is_ready(self):
        """
        is-ready - is ready to accept commands

        This returns true if this handle is ready to accept commands
        (in the "READY" state).
        """
        return self.inner_cmd("is-ready")

    def part_list(self, device):
        """
        part-list - list partitions on a device

        This command parses the partition table on "device" and
        returns the list of partitions found.
        """
        return self.inner_cmd("part-list %s" % device)

    def mkfs(self, fstype, device, blocksize=None, features=None,
             inode=None, sectorsize=None):
        """
        mkfs - make a filesystem
        This function creates a filesystem on "device". The filesystem type is
        "fstype", for example "ext3".
        """
        cmd = 'mkfs %s %s' % (fstype, device)
        if blocksize:
            cmd += ' blocksize:%s ' % blocksize
        if features:
            cmd += ' features:%s ' % features
        if inode:
            cmd += ' inode:%s ' % inode
        if sectorsize:
            cmd += ' sectorsize:%s ' % sectorsize

        return self.inner_cmd(cmd)

    def mkfs_opts(self, fstype, device, blocksize=None, features=None,
                  inode=None, sectorsize=None):
        """
        same with mkfs
        """
        return self.mkfs(fstype, device, blocksize, features,
                         inode, sectorsize)

    def part_disk(self, device, parttype):
        """
        part-disk - partition whole disk with a single primary partition

        This command is simply a combination of "part_init" followed by
        "part_add" to create a single primary partition covering
        the whole disk.
        """
        return self.inner_cmd("part-disk %s %s" % (device, parttype))

    def part_get_bootable(self, device, partnum):
        """
        part-get-bootable - return true if a partition is bootable

        This command returns true if the partition "partnum" on "device"
        has the bootable flag set.
        """
        return self.inner_cmd("part-get-bootable %s %s" % (device, partnum))

    def part_get_mbr_id(self, device, partnum):
        """
        part-get-mbr-id - get the MBR type byte (ID byte) from a partition

        Returns the MBR type byte (also known as the ID byte) from the
        numbered partition "partnum".
        """
        return self.inner_cmd("part-get-mbr-id %s %s" % (device, partnum))

    def part_get_parttype(self, device):
        """
        part-get-parttype - get the partition table type

        This command examines the partition table on "device" and returns the
        partition table type (format) being used.
        """
        return self.inner_cmd("part-get-parttype %s" % device)

    def fsck(self, fstype, device):
        """
        fsck - run the filesystem checker

        This runs the filesystem checker (fsck) on "device" which should have
        filesystem type "fstype".
        """
        return self.inner_cmd("fsck %s %s" % (fstype, device))

    def blockdev_getss(self, device):
        """
        blockdev-getss - get sectorsize of block device

        This returns the size of sectors on a block device. Usually 512,
        but can be larger for modern devices.
        """
        return self.inner_cmd("blockdev-getss %s" % device)

    def blockdev_getsz(self, device):
        """
        blockdev-getsz - get total size of device in 512-byte sectors

        This returns the size of the device in units of 512-byte sectors
        (even if the sectorsize isn't 512 bytes ... weird).
        """
        return self.inner_cmd("blockdev-getsz %s" % device)

    def blockdev_getbsz(self, device):
        """
        blockdev-getbsz - get blocksize of block device

        This returns the block size of a device.
        """
        return self.inner_cmd("blockdev-getbsz %s" % device)

    def blockdev_getsize64(self, device):
        """
        blockdev-getsize64 - get total size of device in bytes

        This returns the size of the device in bytes
        """
        return self.inner_cmd("blockdev-getsize64 %s" % device)

    def blockdev_setbsz(self, device, blocksize):
        """
        blockdev-setbsz - set blocksize of block device

        This sets the block size of a device.
        """
        return self.inner_cmd("blockdev-setbsz %s %s" % (device, blocksize))

    def blockdev_getro(self, device):
        """
        blockdev-getro - is block device set to read-only

        Returns a boolean indicating if the block device is read-only
        (true if read-only, false if not).
        """
        return self.inner_cmd("blockdev-getro %s" % device)

    def blockdev_setro(self, device):
        """
        blockdev-setro - set block device to read-only

        Sets the block device named "device" to read-only.
        """
        return self.inner_cmd("blockdev-setro %s" % device)

    def blockdev_setrw(self, device):
        """
        blockdev-setrw - set block device to read-write

        Sets the block device named "device" to read-write.
        """
        return self.inner_cmd("blockdev-setrw %s" % device)

    def blockdev_flushbufs(self, device):
        """
        blockdev-flushbufs - flush device buffers

        This tells the kernel to flush internal buffers associated with
        "device".
        """
        return self.inner_cmd("blockdev-flushbufs %s" % device)

    def blockdev_rereadpt(self, device):
        """
        blockdev-rereadpt - reread partition table

        Reread the partition table on "device".
        """
        return self.inner_cmd("blockdev-rereadpt %s" % device)

    def canonical_device_name(self, device):
        """
        canonical-device-name - return canonical device name

        This utility function is useful when displaying device names to
        the user.
        """
        return self.inner_cmd("canonical-device-name %s" % device)

    def device_index(self, device):
        """
        device-index - convert device to index

        This function takes a device name (eg. "/dev/sdb") and returns the
        index of the device in the list of devices
        """
        return self.inner_cmd("device-index %s" % device)

    def disk_format(self, filename):
        """
        disk-format - detect the disk format of a disk image

        Detect and return the format of the disk image called "filename",
        "filename" can also be a host device, etc
        """
        return self.inner_cmd("disk-format %s" % filename)

    def disk_has_backing_file(self, filename):
        """
        disk-has-backing-file - return whether disk has a backing file

        Detect and return whether the disk image "filename" has a backing file
        """
        return self.inner_cmd("disk-has-backing-file %s" % filename)

    def disk_virtual_size(self, filename):
        """
        disk-virtual-size - return virtual size of a disk

        Detect and return the virtual size in bytes of the disk image"
        """
        return self.inner_cmd("disk-virtual-size %s" % filename)

    def max_disks(self):
        """
        max-disks - maximum number of disks that may be added

        Return the maximum number of disks that may be added to a handle
        """
        return self.inner_cmd("max-disks")

    def nr_devices(self):
        """
        nr-devices - return number of whole block devices (disks) added

        This returns the number of whole block devices that were added
        """
        return self.inner_cmd("nr-devices")

    def scrub_device(self, device):
        """
        scrub-device - scrub (securely wipe) a device

        This command writes patterns over "device" to make data retrieval more
        difficult
        """
        return self.inner_cmd("scrub-device %s" % device)

    def scrub_file(self, file):
        """
        scrub-file - scrub (securely wipe) a file

        This command writes patterns over a file to make data retrieval more
        difficult
        """
        return self.inner_cmd("scrub-file %s" % file)

    def scrub_freespace(self, dir):
        """
        scrub-freespace - scrub (securely wipe) free space

        This command creates the directory "dir" and then fills it with files
        until the filesystem is full,and scrubs the files as for "scrub_file",
        and deletes them. The intention is to scrub any free space on the
        partition containing "dir"
        """
        return self.inner_cmd("scrub-freespace %s" % dir)

    def md_create(self, name, device, missingbitmap=None, nrdevices=None,
                  spare=None, chunk=None, level=None):
        """
        md-create - create a Linux md (RAID) device

        Create a Linux md (RAID) device named "name" on the devices in the list
        "devices".
        """
        cmd = "md-create %s %s" % (name, device)

        if missingbitmap:
            cmd += " missingbitmap:%s" % missingbitmap
        if nrdevices:
            cmd += " nrdevices:%s" % nrdevices
        if spare:
            cmd += " spare:%s" % spare
        if chunk:
            cmd += " chunk:%s" % chunk
        if level:
            cmd += " level:%s" % level

        return self.inner_cmd(cmd)

    def list_md_devices(self):
        """
        list-md-devices - list Linux md (RAID) devices

        List all Linux md devices.
        """
        return self.inner_cmd("list-md-devices")

    def md_stop(self, md):
        """
        md-stop - stop a Linux md (RAID) device

        This command deactivates the MD array named "md".
        The device is stopped, but it is not destroyed or zeroed.
        """
        return self.inner_cmd("md-stop %s" % md)

    def md_stat(self, md):
        """
        md-stat - get underlying devices from an MD device

        This call returns a list of the underlying devices which make up the
        single software RAID array device "md".
        """
        return self.inner_cmd("md-stat %s" % md)

    def md_detail(self, md):
        """
        md-detail - obtain metadata for an MD device

        This command exposes the output of 'mdadm -DY <md>'. The following
        fields are usually present in the returned hash. Other fields may also
        be present.
        """
        return self.inner_cmd("md-detail %s" % md)

    def sfdisk(self, device, cyls, heads, sectors, lines):
        """
        sfdisk - create partitions on a block device

        This is a direct interface to the sfdisk(8) program for creating
        partitions on block devices.

        *This function is deprecated.* In new code, use the "part-add" call
        instead.

        Deprecated functions will not be removed from the API, but the fact
        that they are deprecated indicates that there are problems with correct
        use of these functions.
        """
        return self.inner_cmd("sfdisk %s %s %s %s %s"
                              % (device, cyls, heads, sectors, lines))

    def sfdisk_l(self, device):
        """
        sfdisk-l - display the partition table

        This displays the partition table on "device", in the human-readable
        output of the sfdisk(8) command. It is not intended to be parsed.

        *This function is deprecated.* In new code, use the "part-list" call
        instead.
        """
        return self.inner_cmd("sfdisk-l %s" % device)

    def sfdiskM(self, device, lines):
        """
        sfdiskM - create partitions on a block device

        This is a simplified interface to the "sfdisk" command, where partition
        sizes are specified in megabytes only (rounded to the nearest cylinder)
        and you don't need to specify the cyls, heads and sectors parameters
        which were rarely if ever used anyway.

        *This function is deprecated.* In new code, use the "part-add" call
        instead.
        """
        return self.inner_cmd("sfdiskM %s %s" % (device, lines))

    def sfdisk_N(self, device, partnum, cyls, heads, sectors, line):
        """
        sfdisk-N - modify a single partition on a block device

        This runs sfdisk(8) option to modify just the single partition "n"
        (note: "n" counts from 1).

        For other parameters, see "sfdisk". You should usually pass 0 for the
        cyls/heads/sectors parameters.

        *This function is deprecated.* In new code, use the "part-add" call
        instead.
        """
        return self.inner_cmd("sfdisk-N %s %s %s %s %s %s"
                              % (device, partnum, cyls, heads, sectors, line))

    def sfdisk_disk_geometry(self, device):
        """
        sfdisk-disk-geometry - display the disk geometry from the partition
        table

        This displays the disk geometry of "device" read from the partition
        table. Especially in the case where the underlying block device has
        been resized, this can be different from the kernel's idea of the
        geometry
        """
        return self.inner_cmd("sfdisk-disk-geometry %s" % device)

    def sfdisk_kernel_geometry(self, device):
        """
        sfdisk-kernel-geometry - display the kernel geometry

        This displays the kernel's idea of the geometry of "device".
        """
        return self.inner_cmd("sfdisk-kernel-geometry %s" % device)

    def pvcreate(self, physvols):
        """
        pvcreate - create an LVM physical volume

        This creates an LVM physical volume called "physvols".
        """
        return self.inner_cmd("pvcreate %s" % (physvols))

    def pvs(self):
        """
        pvs - list the LVM physical volumes (PVs)

        List all the physical volumes detected. This is the equivalent of the
        pvs(8) command.
        """
        return self.inner_cmd("pvs")

    def pvs_full(self):
        """
        pvs-full - list the LVM physical volumes (PVs)

        List all the physical volumes detected. This is the equivalent of the
        pvs(8) command. The "full" version includes all fields.
        """
        return self.inner_cmd("pvs-full")

    def pvresize(self, device):
        """
        pvresize - resize an LVM physical volume

        This resizes (expands or shrinks) an existing LVM physical volume to
        match the new size of the underlying device
        """
        return self.inner_cmd("pvresize %s" % device)

    def pvresize_size(self, device, size):
        """
        pvresize-size - resize an LVM physical volume (with size)

        This command is the same as "pvresize" except that it allows you to
        specify the new size (in bytes) explicitly.
        """
        return self.inner_cmd("pvresize-size %s %s" % (device, size))

    def pvremove(self, device):
        """
        pvremove - remove an LVM physical volume

        This wipes a physical volume "device" so that LVM will no longer
        recognise it.

        The implementation uses the "pvremove" command which refuses to wipe
        physical volumes that contain any volume groups, so you have to remove
        those first.
        """
        return self.inner_cmd("pvremove %s" % device)

    def pvuuid(self, device):
        """
        pvuuid - get the UUID of a physical volume

        This command returns the UUID of the LVM PV "device".
        """
        return self.inner_cmd("pvuuid %s" % device)

    def vgcreate(self, volgroup, physvols):
        """
        vgcreate - create an LVM volume group

        This creates an LVM volume group called "volgroup" from the
        non-empty list of physical volumes "physvols".
        """
        return self.inner_cmd("vgcreate %s %s" % (volgroup, physvols))

    def vgs(self):
        """
        vgs - list the LVM volume groups (VGs)

        List all the volumes groups detected.
        """
        return self.inner_cmd("vgs")

    def vgs_full(self):
        """
        vgs-full - list the LVM volume groups (VGs)

        List all the volumes groups detected. This is the equivalent of the
        vgs(8) command. The "full" version includes all fields.
        """
        return self.inner_cmd("vgs-full")

    def vgrename(self, volgroup, newvolgroup):
        """
        vgrename - rename an LVM volume group

        Rename a volume group "volgroup" with the new name "newvolgroup".
        """
        return self.inner_cmd("vgrename %s %s" % (volgroup, newvolgroup))

    def vgremove(self, vgname):
        """
        vgremove - remove an LVM volume group

        Remove an LVM volume group "vgname", (for example "VG").
        """
        return self.inner_cmd("vgremove %s" % vgname)

    def vgscan(self):
        """
        vgscan - rescan for LVM physical volumes, volume groups and logical
        volumes

        This rescans all block devices and rebuilds the list of LVM physical
        volumes, volume groups and logical volumes.
        """
        return self.inner_cmd("vgscan")

    def vguuid(self, vgname):
        """
        vguuid - get the UUID of a volume group

        This command returns the UUID of the LVM VG named "vgname"
        """
        return self.inner_cmd("vguuid %s" % vgname)

    def vg_activate(self, activate, volgroups):
        """
        vg-activate - activate or deactivate some volume groups

        This command activates or (if "activate" is false) deactivates all
        logical volumes in the listed volume groups "volgroups"
        """
        return self.inner_cmd("vg-activate %s %s" % (activate, volgroups))

    def vg_activate_all(self, activate):
        """
        vg-activate-all - activate or deactivate all volume groups

        This command activates or (if "activate" is false) deactivates all
        logical volumes in all volume groups.
        """
        return self.inner_cmd("vg-activate-all %s" % activate)

    def vglvuuids(self, vgname):
        """
        vglvuuids - get the LV UUIDs of all LVs in the volume group

        Given a VG called "vgname", this returns the UUIDs of all the logical
        volumes created in this volume group.
        """
        return self.inner_cmd("vglvuuids %s" % vgname)

    def vgpvuuids(self, vgname):
        """
        vgpvuuids - get the PV UUIDs containing the volume group

        Given a VG called "vgname", this returns the UUIDs of all the physical
        volumes that this volume group resides on.
        """
        return self.inner_cmd("vgpvuuids %s" % vgname)

    def lvcreate(self, logvol, volgroup, mbytes):
        """
        lvcreate - create an LVM logical volume

        This creates an LVM logical volume called "logvol" on the
        volume group "volgroup", with "size" megabytes.
        """
        return self.inner_cmd("lvcreate %s %s %s" % (logvol, volgroup, mbytes))

    def lvuuid(self, device):
        """
        lvuuid - get the UUID of a logical volume

        This command returns the UUID of the LVM LV "device".
        """
        return self.inner_cmd("lvuuid %s" % device)

    def lvm_canonical_lv_name(self, lvname):
        """
        lvm-canonical-lv-name - get canonical name of an LV

        This converts alternative naming schemes for LVs that you might
        find to the canonical name.
        """
        return self.inner_cmd("lvm-canonical-lv-name %s" % lvname)

    def lvremove(self, device):
        """
        lvremove - remove an LVM logical volume

        Remove an LVM logical volume "device", where "device" is the path
        to the LV, such as "/dev/VG/LV".
        """
        return self.inner_cmd("lvremove %s" % device)

    def lvresize(self, device, mbytes):
        """
        lvresize - resize an LVM logical volume

        This resizes (expands or shrinks) an existing LVM logical volume to
        "mbytes".
        """
        return self.inner_cmd("lvresize %s %s" % (device, mbytes))

    def lvs(self):
        """
        lvs - list the LVM logical volumes (LVs)

        List all the logical volumes detected.
        """
        return self.inner_cmd("lvs")

    def lvs_full(self):
        """
        lvs-full - list the LVM logical volumes (LVs)

        List all the logical volumes detected. This is the equivalent of the
        lvs(8) command. The "full" version includes all fields.
        """
        return self.inner_cmd("lvs-full")

    def lvm_clear_filter(self):
        """
        lvm-clear-filter - clear LVM device filter

        This undoes the effect of "lvm_set_filter". LVM will be able to see
        every block device.
        This command also clears the LVM cache and performs a volume group scan.
        """
        return self.inner_cmd("lvm-clear-filter")

    def lvm_remove_all(self):
        """
        lvm-remove-all - remove all LVM LVs, VGs and PVs

        This command removes all LVM logical volumes, volume groups and physical
        volumes.
        """
        return self.inner_cmd("lvm-remove-all")

    def lvm_set_filter(self, device):
        """
        lvm-set-filter - set LVM device filter

        This sets the LVM device filter so that LVM will only be able to "see"
        the block devices in the list "devices", and will ignore all other
        attached block devices.
        """
        return self.inner_cmd("lvm-set-filter %s" % device)

    def lvresize_free(self, lv, percent):
        """
        lvresize-free - expand an LV to fill free space

        This expands an existing logical volume "lv" so that it fills "pc"% of
        the remaining free space in the volume group. Commonly you would call
        this with pc = 100 which expands the logical volume as much as possible,
        using all remaining free space in the volume group.
        """
        return self.inner_cmd("lvresize-free %s %s" % (lv, percent))

    def lvrename(self, logvol, newlogvol):
        """
        lvrename - rename an LVM logical volume

        Rename a logical volume "logvol" with the new name "newlogvol"
        """
        return self.inner_cmd("lvrename %s %s" % (logvol, newlogvol))

    def vfs_type(self, mountable):
        """
        vfs-type - get the Linux VFS type corresponding to a mounted device

        Gets the filesystem type corresponding to the filesystem on "mountable"
        """
        return self.inner_cmd("vfs-type %s" % (mountable))

    def touch(self, path):
        """
        touch - update file timestamps or create a new file

        Touch acts like the touch(1) command. It can be used to update the
        timestamps on a file, or, if the file does not exist, to create a new
        zero-length file.
        """
        return self.inner_cmd("touch %s" % (path))

    def umount_all(self):
        """
        umount-all - unmount all filesystems

        This unmounts all mounted filesystems.
        Some internal mounts are not unmounted by this call.
        """
        return self.inner_cmd("umount-all")

    def ls(self, directory):
        """
        ls - list the files in a directory

        List the files in "directory" (relative to the root directory, there is
        no cwd). The '.' and '..' entries are not returned, but hidden files are
        shown.
        """
        return self.inner_cmd("ls %s" % (directory))

    def ll(self, directory):
        """
        ll - list the files in a directory (long format)

        List the files in "directory" (relative to the root directory, there is
        no cwd) in the format of 'ls -la'.
        """
        return self.inner_cmd("ll %s" % (directory))

    def sync(self):
        """
        lsync - sync disks, writes are flushed through to the disk image

        This syncs the disk, so that any writes are flushed through to the
        underlying disk image.
        """
        return self.inner_cmd("sync")

    def debug(self, subcmd, extraargs):
        """
        debug - debugging and internals

        The "debug" command exposes some internals of "guestfsd" (the guestfs
        daemon) that runs inside the hypervisor.
        """
        return self.inner_cmd("debug %s %s" % (subcmd, extraargs))

    def set_e2uuid(self, device, uuid):
        """
        set-e2uuid - set the ext2/3/4 filesystem UUID

        This sets the ext2/3/4 filesystem UUID of the filesystem on "device" to
        "uuid". The format of the UUID and alternatives such as "clear",
        "random" and "time" are described in the tune2fs(8) manpage.
        """
        return self.inner_cmd("set_e2uuid %s %s" % (device, uuid))

    def get_e2uuid(self, device):
        """
        get-e2uuid - get the ext2/3/4 filesystem UUID

        This returns the ext2/3/4 filesystem UUID of the filesystem on "device".
        """
        return self.inner_cmd("get_e2uuid %s" % (device))

    def vfs_uuid(self, mountable):
        """
        vfs-uuid - get the filesystem UUID

        This returns the filesystem UUID of the filesystem on "mountable".
        """
        return self.inner_cmd("vfs_uuid %s" % (mountable))

    def findfs_uuid(self, uuid):
        """
        findfs-uuid - find a filesystem by UUID

        This command searches the filesystems and returns the one which has the
        given UUID. An error is returned if no such filesystem can be found.
        """
        return self.inner_cmd("findfs_uuid %s" % (uuid))

    def set_uuid(self, device, uuid):
        """
        set-uuid - set the filesystem UUID

        Set the filesystem UUID on "device" to "uuid".
        """
        return self.inner_cmd("set_uuid %s %s" % (device, uuid))

    def set_e2label(self, device, label):
        """
        set-e2label - set the ext2/3/4 filesystem label

        This sets the ext2/3/4 filesystem label of the filesystem on "device" to
        "label". Filesystem labels are limited to 16 characters.
        """
        return self.inner_cmd("set_e2label %s %s" % (device, label))

    def get_e2label(self, device):
        """
        get-e2label - get the ext2/3/4 filesystem label

        This returns the ext2/3/4 filesystem label of the filesystem on
        "device".
        """
        return self.inner_cmd("get_e2label %s" % (device))

    def vfs_label(self, mountable):
        """
        vfs-label - get the filesystem label

        This returns the label of the filesystem on "mountable".
        """
        return self.inner_cmd("vfs_label %s" % (mountable))

    def findfs_label(self, label):
        """
        findfs-label - find a filesystem by label

        This command searches the filesystems and returns the one which has the
        given label. An error is returned if no such filesystem can be found.
        """
        return self.inner_cmd("findfs_label %s" % (label))

    def set_label(self, mountable, label):
        """
        set-label - set filesystem label

        Set the filesystem label on "mountable" to "label".
        """
        return self.inner_cmd("set_label %s %s" % (mountable, label))

    def set_e2attrs(self, file, attrs, clear=None):
        """
        set-e2attrs - set ext2 file attributes of a file

        This sets or clears the file attributes "attrs" associated with the
        inode "file".
        """
        cmd = "set_e2attrs %s %s" % (file, attrs)

        if clear:
            cmd += " clear:%s" % clear
        return self.inner_cmd(cmd)

    def get_e2attrs(self, file):
        """
        get-e2attrs - get ext2 file attributes of a file

        This returns the file attributes associated with "file".
        """
        return self.inner_cmd("get_e2attrs %s" % (file))

    def set_e2generation(self, file, generation):
        """
        set-e2generation - set ext2 file generation of a file

        This sets the ext2 file generation of a file.
        """
        return self.inner_cmd("set_e2generation %s %s" % (file, generation))

    def get_e2generation(self, file):
        """
        get-e2generation - get ext2 file generation of a file

        This returns the ext2 file generation of a file. The generation (which
        used to be called the "version") is a number associated with an inode.
        This is most commonly used by NFS servers.
        """
        return self.inner_cmd("get_e2generation %s" % (file))

    def statvfs(self, path):
        """
        statvfs - get file system statistics

        Returns file system statistics for any mounted file system. "path"
        should be a file or directory in the mounted file system (typically it
        is the mount point itself, but it doesn't need to be).
        """
        return self.inner_cmd("statvfs %s" % (path))

    def tune2fs_l(self, device):
        """
        tune2fs-l - get ext2/ext3/ext4 superblock details

        This returns the contents of the ext2, ext3 or ext4 filesystem
        superblock on "device".
        """
        return self.inner_cmd("tune2fs_l %s" % (device))

    def tune2fs(self, device, force=None, maxmountcount=None, mountcount=None,
                errorbehavior=None, group=None, intervalbetweenchecks=None,
                reservedblockspercentage=None, lastmounteddirectory=None,
                reservedblockscount=None, user=None):
        """
        tune2fs - adjust ext2/ext3/ext4 filesystem parameters

        This call allows you to adjust various filesystem parameters of an
        ext2/ext3/ext4 filesystem called "device".
        """
        cmd = "tune2fs %s" % device

        if force:
            cmd += ' force:%s' % force
        if maxmountcount:
            cmd += ' maxmountcount:%s' % maxmountcount
        if mountcount:
            cmd += ' mountcount:%s' % mountcount
        if errorbehavior:
            cmd += ' errorbehavior:%s' % errorbehavior
        if group:
            cmd += ' group:%s' % group
        if intervalbetweenchecks:
            cmd += ' intervalbetweenchecks:%s' % intervalbetweenchecks
        if reservedblockspercentage:
            cmd += ' reservedblockspercentage:%s' % reservedblockspercentage
        if lastmounteddirectory:
            cmd += ' lastmounteddirectory:%s' % lastmounteddirectory
        if reservedblockscount:
            cmd += ' reservedblockscount:%s' % reservedblockscount
        if user:
            cmd += ' user:%s' % user
        return self.inner_cmd(cmd)

    def umount(self, pathordevice, force=None, lazyunmount=None):
        """
        umount - unmount a filesystem

        This unmounts the given filesystem. The filesystem may be specified
        either by its mountpoint (path) or the device which contains the
        filesystem.
        """
        cmd = 'umount %s' % pathordevice
        if force:
            cmd += ' force:%s ' % force
        if lazyunmount:
            cmd += ' lazyunmount:%s ' % lazyunmount

        return self.inner_cmd(cmd)

    def blkid(self, device):
        """
        blkid - print block device attributes

        This command returns block device attributes for "device". The following
        fields are usually present in the returned hash. Other fields may also
        be present.
        """
        return self.inner_cmd("blkid %s" % device)

    def filesystem_available(self, filesystem):
        """
        filesystem-available - check if filesystem is available

        Check whether libguestfs supports the named filesystem. The argument
        "filesystem" is a filesystem name, such as "ext3".
        """
        return self.inner_cmd("filesystem_available %s" % filesystem)

    def e2fsck(self, device, correct=None, forceall=None):
        """
        e2fsck - check an ext2/ext3 filesystem

        This runs the ext2/ext3 filesystem checker on "device". It can take the
        following optional arguments:
        """
        cmd = 'e2fsck %s' % device
        if correct:
            cmd += ' correct:%s ' % correct
        if forceall:
            cmd += ' forceall:%s ' % forceall
        return self.inner_cmd(cmd)

    def mkfifo(self, mode, path):
        """
        mkfifo - make FIFO (named pipe)

        This call creates a FIFO (named pipe) called "path" with mode "mode". It
        is just a convenient wrapper around "mknod".
        """
        return self.inner_cmd('mkfifo %s %s' % (mode, path))

    def mklost_and_found(self, mountpoint):
        """
        mklost-and-found - make lost+found directory on an ext2/3/4 filesystem

        Make the "lost+found" directory, normally in the root directory of an
        ext2/3/4 filesystem. "mountpoint" is the directory under which we try to
        create the "lost+found" directory.
        """
        return self.inner_cmd('mklost_and_found %s' % mountpoint)

    def mknod_b(self, mode, devmajor, devminor, path):
        """
        mknod-b - make block device node

        This call creates a block device node called "path" with mode "mode" and
        device major/minor "devmajor" and "devminor". It is just a convenient
        wrapper around "mknod".
        """
        return self.inner_cmd('mknod_b %s %s %s %s' % (mode, devmajor, devminor, path))

    def mknod_c(self, mode, devmajor, devminor, path):
        """
        mknod-c - make char device node

        This call creates a char device node called "path" with mode "mode" and
        device major/minor "devmajor" and "devminor". It is just a convenient
        wrapper around "mknod".
        """
        return self.inner_cmd('mknod_c %s %s %s %s' % (mode, devmajor, devminor, path))

    def ntfsresize_opts(self, device, size=None, force=None):
        """
        ntfsresize - resize an NTFS filesystem

        This command resizes an NTFS filesystem, expanding or shrinking it to
        the size of the underlying device.
        """
        cmd = 'ntfsresize-opts %s' % device
        if size:
            cmd += ' size:%s ' % size
        if force:
            cmd += ' force:%s ' % force
        return self.inner_cmd(cmd)

    def resize2fs(self, device):
        """
        resize2fs - resize an ext2, ext3 or ext4 filesystem

        This resizes an ext2, ext3 or ext4 filesystem to match the size of the
        underlying device.
        """
        return self.inner_cmd('resize2fs %s' % device)

    def resize2fs_M(self, device):
        """
        resize2fs-M - resize an ext2, ext3 or ext4 filesystem to the minimum size

        This command is the same as "resize2fs", but the filesystem is resized
        to its minimum size. This works like the *-M* option to the "resize2fs"
        command.
        """
        return self.inner_cmd('resize2fs_M %s' % device)

    def resize2fs_size(self, device, size):
        """
        resize2fs-size - resize an ext2, ext3 or ext4 filesystem (with size)

        This command is the same as "resize2fs" except that it allows you to
        specify the new size (in bytes) explicitly.
        """
        return self.inner_cmd('resize2fs_size %s %s' % (device, size))

    def e2fsck_f(self, device):
        """
        e2fsck-f - check an ext2/ext3 filesystem

        This runs "e2fsck -p -f device", ie. runs the ext2/ext3 filesystem
        checker on "device", noninteractively (*-p*), even if the filesystem
        appears to be clean (*-f*).
        """
        return self.inner_cmd('e2fsck_f %s' % (device))

    def readdir(self, dir):
        """
        readdir - read directories entries

        This returns the list of directory entries in directory "dir"
        """
        return self.inner_cmd('readdir %s' % (dir))

    def mount_loop(self, file, mountpoint):
        """
        mount-loop - mount a file using the loop device

        This command lets you mount "file" (a filesystem image in a file) on a
        mount point. It is entirely equivalent to the command "mount -o loop
        file mountpoint".
        """
        return self.inner_cmd('mount_loop %s %s' % (file, mountpoint))

    def mount_vfs(self, options, vfstype, mountable, mountpoint):
        """
        mount-vfs - mount a guest disk with mount options and vfstype

        This is the same as the "mount" command, but it allows you to set both
        the mount options and the vfstype as for the mount(8) *-o* and *-t*
        flags.
        """
        return self.inner_cmd('mount_vfs %s %s %s %s' % (options, vfstype, mountable, mountpoint))

    def mkswap(self, device, label=None, uuid=None):
        """
        mkswap - create a swap partition

        Create a Linux swap partition on "device"
        """
        cmd = 'mkswap %s ' % device
        if label:
            cmd += ' label:%s ' % label
        if uuid:
            cmd += ' uuid:%s ' % uuid
        return self.inner_cmd(cmd)

    def swapon_device(self, device):
        """
        swapon-device - enable swap on device

        This command enables the libguestfs appliance to use the swap device or
        partition named "device". The increased memory is made available for all
        commands, for example those run using "command" or "sh".
        """
        return self.inner_cmd('swapon_device %s' % device)

    def swapoff_device(self, device):
        """
        swapoff-device - disable swap on device

        This command disables the libguestfs appliance swap device or partition
        named "device". See "swapon_device".
        """
        return self.inner_cmd('swapoff_device %s' % device)

    def mkswap_L(self, label, device):
        """
        mkswap-L - create a swap partition with a label

        Create a swap partition on "device" with label "label".
        """
        return self.inner_cmd('mkswap_L %s %s' % (label, device))

    def swapon_label(self, label):
        """
        swapon-label - enable swap on labeled swap partition

        This command enables swap to a labeled swap partition. See
        "swapon_device" for other notes.
        """
        return self.inner_cmd("swapon_label %s" % label)

    def swapoff_label(self, label):
        """
        swapoff-label - disable swap on labeled swap partition

        This command disables the libguestfs appliance swap on labeled swap
        partition.
        """
        return self.inner_cmd("swapoff_label %s" % label)

    def mkswap_U(self, uuid, device):
        """
        mkswap-U - create a swap partition with an explicit UUID

        Create a swap partition on "device" with UUID "uuid".
        """
        return self.inner_cmd('mkswap_U %s %s' % (uuid, device))

    def swapon_uuid(self, uuid):
        """
        swapon-uuid - enable swap on swap partition by UUID

        This command enables swap to a swap partition with the given UUID. See
        "swapon_device" for other notes.
        """
        return self.inner_cmd('swapon_uuid %s' % uuid)

    def swapoff_uuid(self, uuid):
        """
        swapoff-uuid - disable swap on swap partition by UUID

        This command disables the libguestfs appliance swap partition with the
        given UUID.
        """
        return self.inner_cmd('swapoff_uuid %s' % uuid)

    def mkswap_file(self, file):
        """
        mkswap-file - create a swap file

        Create a swap file.
        """
        return self.inner_cmd("mkswap_file %s" % file)

    def swapon_file(self, file):
        """
        swapon-file - enable swap on file

        This command enables swap to a file. See "swapon_device" for other
        notes.
        """
        return self.inner_cmd('swapon_file %s' % file)

    def swapoff_file(self, file):
        """
        swapoff-file - disable swap on file

        This command disables the libguestfs appliance swap on file.
        """
        return self.inner_cmd('swapoff_file %s' % file)

    def alloc(self, filename, size):
        """
        alloc - allocate and add a disk file

        This creates an empty (zeroed) file of the given size, and then adds so
        it can be further examined.
        """
        return self.inner_cmd('alloc %s %s' % (filename, size))

    def list_disk_labels(self):
        """
        list-disk-labels - mapping of disk labels to devices

        If you add drives using the optional "label" parameter of
        "add_drive_opts", you can use this call to map between disk labels, and
        raw block device and partition names (like "/dev/sda" and "/dev/sda1").
        """
        return self.inner_cmd('list_disk_labels')

    def add_drive_ro_with_if(self, filename, iface):
        """
        add-drive-ro-with-if - add a drive read-only specifying the QEMU block
        emulation to use

        This is the same as "add_drive_ro" but it allows you to specify the QEMU
        interface emulation to use at run time.
        """
        return self.inner_cmd('add_drive_ro_with_if %s %s' % (filename, iface))

    def add_drive_with_if(self, filename, iface):
        """
        add-drive-with-if - add a drive specifying the QEMU block emulation to
        use

        This is the same as "add_drive" but it allows you to specify the QEMU
        interface emulation to use at run time.
        """
        return self.inner_cmd('add_drive_with_if %s %s' % (filename, iface))

    def available(self, groups):
        """
        available - test availability of some parts of the API

        This command is used to check the availability of some groups of
        functionality in the appliance, which not all builds of the libguestfs
        appliance will be able to provide.
        """
        return self.inner_cmd('available %s' % groups)

    def available_all_groups(self):
        """
        available-all-groups - return a list of all optional groups

        This command returns a list of all optional groups that this daemon
        knows about. Note this returns both supported and unsupported groups. To
        find out which ones the daemon can actually support you have to call
        "available" / "feature_available" on each member of the returned list.
        """
        return self.inner_cmd('available_all_groups')

    def help(self, orcmd=None):
        """
        help - display a list of commands or help on a command
        """
        cmd = 'help'
        if orcmd:
            cmd += ' %s' % orcmd
        return self.inner_cmd(cmd)

    def quit(self):
        """
        quit - quit guestfish
        """
        return self.inner_cmd('quit')

    def echo(self, params=None):
        """
        echo - display a line of text

        This echos the parameters to the terminal.
        """
        cmd = 'echo'
        if params:
            cmd += ' %s' % params
        return self.inner_cmd(cmd)

    def echo_daemon(self, words):
        """
        echo-daemon - echo arguments back to the client

        This command concatenates the list of "words" passed with single spaces
        between them and returns the resulting string.
        """
        return self.inner_cmd('echo_daemon %s' % words)

    def launch(self):
        """
        launch - launch the backend

        You should call this after configuring the handle (eg. adding drives)
        but before performing any actions.
        """
        return self.inner_cmd('launch')

    def dmesg(self):
        """
        dmesg - return kernel messages

        This returns the kernel messages ("dmesg" output) from the guest kernel.
        This is sometimes useful for extended debugging of problems.
        """
        return self.inner_cmd('dmesg')

    def version(self):
        """
        version - get the library version number

        Return the libguestfs version number that the program is linked against.
        """
        return self.inner_cmd('version')

    def sparse(self, filename, size):
        """
        sparse - create a sparse disk image and add

        This creates an empty sparse file of the given size, and then adds so it
        can be further examined.
        """
        return self.inner_cmd('sparse %s %s' % (filename, size))

    def modprobe(self, modulename):
        """
        modprobe - load a kernel module

        This loads a kernel module in the appliance.
        """
        return self.inner_cmd('modprobe %s' % modulename)

    def ping_daemon(self):
        """
        ping-daemon - ping the guest daemon

        This is a test probe into the guestfs daemon running inside the
        hypervisor. Calling this function checks that the daemon responds to the
        ping message, without affecting the daemon or attached block device(s)
        in any other way.
        """
        return self.inner_cmd('ping_daemon')

    def sleep(self, secs):
        """
        sleep - sleep for some seconds

        Sleep for "secs" seconds.
        """
        return self.inner_cmd('sleep %s' % secs)

    def reopen(self):
        """
        reopen - close and reopen libguestfs handle

        Close and reopen the libguestfs handle. It is not necessary to use this
        normally, because the handle is closed properly when guestfish exits.
        However this is occasionally useful for testing.
        """
        return self.inner_cmd('reopen')

    def time(self, command, args=None):
        """
        time - print elapsed time taken to run a command

        Run the command as usual, but print the elapsed time afterwards. This
        can be useful for benchmarking operations.
        """
        cmd = 'time %s' % command
        if args:
            cmd += args
        return self.inner_cmd(cmd)

    def config(self, hvparam, hvvalue):
        """
        config - add hypervisor parameters

        This can be used to add arbitrary hypervisor parameters of the form
        *-param value*. Actually it's not quite arbitrary - we prevent you from
        setting some parameters which would interfere with parameters that we
        use.
        """
        return self.inner_cmd('config %s %s' % (hvparam, hvvalue))

    def kill_subprocess(self):
        """
        kill-subprocess - kill the hypervisor

        This kills the hypervisor.
        """
        return self.inner_cmd('kill_subprocess')

    def set_backend(self, backend):
        """
        set-backend - set the backend

        Set the method that libguestfs uses to connect to the backend guestfsd
        daemon.
        """
        return self.inner_cmd('set_backend %s' % backend)

    def get_backend(self):
        """
        get-backend - get the backend

        Return the current backend.
        """
        return self.inner_cmd('get_backend')

    def shutdown(self):
        """
        shutdown - shutdown the hypervisor

        This is the opposite of "launch". It performs an orderly shutdown of the
        backend process(es). If the autosync flag is set (which is the default)
        then the disk image is synchronized.
        """
        return self.inner_cmd('shutdown')

    def ntfs_3g_probe(self, rw, device):
        """
        ntfs-3g-probe - probe NTFS volume

        This command runs the ntfs-3g.probe(8) command which probes an NTFS
        "device" for mountability. (Not all NTFS volumes can be mounted
        read-write, and some cannot be mounted at all).
        """
        return self.inner_cmd('ntfs_3g_probe %s %s' % (rw, device))

    def event(self, name, eventset, script):
        """
        event - register a handler for an event or events

        Register a shell script fragment which is executed when an event is
        raised. See "guestfs_set_event_callback" in guestfs(3) for a discussion
        of the event API in libguestfs.
        """
        return self.inner_cmd('event %s %s %s' % (name, eventset, script))

    def list_events(self):
        """
        list-events - list event handlers

        List the event handlers registered using the guestfish "event" command.
        """
        return self.inner_cmd('list_events')

    def delete_event(self, name):
        """
        delete-event - delete a previously registered event handler

        Delete the event handler which was previously registered as "name". If
        multiple event handlers were registered with the same name, they are all
        deleted.
        """
        return self.inner_cmd('delete_event %s' % name)

    def set_append(self, append):
        """
        set-append - add options to kernel command line

        This function is used to add additional options to the libguestfs
        appliance kernel command line.
        """
        return self.inner_cmd('set_append %s' % append)

    def get_append(self):
        """
        get-append - get the additional kernel options

        Return the additional kernel options which are added to the libguestfs
        appliance kernel command line.
        """
        return self.inner_cmd('get_append')

    def set_smp(self, smp):
        """
        set-smp - set number of virtual CPUs in appliance

        Change the number of virtual CPUs assigned to the appliance. The default
        is 1. Increasing this may improve performance, though often it has no
        effect.
        """
        return self.inner_cmd('set_smp %s' % smp)

    def get_smp(self):
        """
        get-smp - get number of virtual CPUs in appliance

        This returns the number of virtual CPUs assigned to the appliance.
        """
        return self.inner_cmd('get_smp')

    def set_pgroup(self, pgroup):
        """
        set-pgroup - set process group flag

        If "pgroup" is true, child processes are placed into their own process
        group.
        """
        return self.inner_cmd('set_pgroup %s' % pgroup)

    def get_pgroup(self):
        """
        get-pgroup - get process group flag

        This returns the process group flag.
        """
        return self.inner_cmd('get_pgroup')

    def set_attach_method(self, backend):
        """
        set-attach-method - set the backend

        Set the method that libguestfs uses to connect to the backend guestfsd
        daemon.
        """
        return self.inner_cmd('set_attach_method %s' % backend)

    def get_attach_method(self):
        """
        get-attach-method - get the backend

        Return the current backend.
        """
        return self.inner_cmd('get_attach_method')

    def set_autosync(self, autosync):
        """
        set-autosync autosync

        If "autosync" is true, this enables autosync. Libguestfs will make a
        best effort attempt to make filesystems consistent and synchronized when
        the handle is closed (also if the program exits without closing
        handles).
        """
        return self.inner_cmd('set_autosync %s' % autosync)

    def get_autosync(self):
        """
        get-autosync - get autosync mode

        Get the autosync flag.
        """
        return self.inner_cmd('get_autosync')

    def set_direct(self, direct):
        """
        set-direct - enable or disable direct appliance mode

        If the direct appliance mode flag is enabled, then stdin and stdout are
        passed directly through to the appliance once it is launched.
        """
        return self.inner_cmd('set_direct %s' % direct)

    def get_direct(self):
        """
        get-direct - get direct appliance mode flag

        Return the direct appliance mode flag.
        """
        return self.inner_cmd('get_direct')

    def set_memsize(self, memsize):
        """
        set-memsize - set memory allocated to the hypervisor

        This sets the memory size in megabytes allocated to the hypervisor. This
        only has any effect if called before "launch".
        """
        return self.inner_cmd('set_memsize %s' % memsize)

    def get_memsize(self):
        """
        get-memsize - get memory allocated to the hypervisor

        This gets the memory size in megabytes allocated to the hypervisor.
        """
        return self.inner_cmd('get_memsize')

    def set_path(self, searchpath):
        """
        set-path - set the search path

        Set the path that libguestfs searches for kernel and initrd.img.
        """
        return self.inner_cmd('set_path %s' % searchpath)

    def get_path(self):
        """
        get-path - get the search path

        Return the current search path.
        """
        return self.inner_cmd('get_path')

    def set_qemu(self, hv):
        """
        set-qemu - set the hypervisor binary (usually qemu)

        Set the hypervisor binary (usually qemu) that we will use.
        """
        return self.inner_cmd('set_qemu %s' % hv)

    def get_qemu(self):
        """
        get-qemu - get the hypervisor binary (usually qemu)

        Return the current hypervisor binary (usually qemu).
        """
        return self.inner_cmd('get_qemu')

    def set_recovery_proc(self, recoveryproc):
        """
        set-recovery-proc - enable or disable the recovery process

        If this is called with the parameter "false" then "launch" does not
        create a recovery process. The purpose of the recovery process is to
        stop runaway hypervisor processes in the case where the main program
        aborts abruptly.
        """
        return self.inner_cmd('set_recovery_proc %s' % recoveryproc)

    def get_recovery_proc(self):
        """
        get-recovery-proc - get recovery process enabled flag

        Return the recovery process enabled flag.
        """
        return self.inner_cmd('get_recovery_proc')

    def set_trace(self, trace):
        """
        set-trace - enable or disable command traces

        If the command trace flag is set to 1, then libguestfs calls, parameters
        and return values are traced.
        """
        return self.inner_cmd('set_trace %s' % trace)

    def get_trace(self):
        """
        get-trace - get command trace enabled flag

        Return the command trace flag.
        """
        return self.inner_cmd('get_trace')

    def set_verbose(self, verbose):
        """
        set-verbose - set verbose mode

        If "verbose" is true, this turns on verbose messages.
        """
        return self.inner_cmd('set_verbose %s' % verbose)

    def get_verbose(self):
        """
        get-verbose - get verbose mode

        This returns the verbose messages flag.
        """
        return self.inner_cmd('get_verbose')

    def get_pid(self):
        """
        get-pid - get PID of hypervisor

        Return the process ID of the hypervisor. If there is no hypervisor
        running, then this will return an error.
        """
        return self.inner_cmd('get_pid')

    def set_network(self, network):
        """
        set-network - set enable network flag

        If "network" is true, then the network is enabled in the libguestfs
        appliance. The default is false.
        """
        return self.inner_cmd('set_network %s' % network)

    def get_network(self):
        """
        get-network - get enable network flag

        This returns the enable network flag.
        """
        return self.inner_cmd('get_network')

    def setenv(self, VAR, value):
        """
        setenv - set an environment variable

        Set the environment variable "VAR" to the string "value".
        """
        return self.inner_cmd('setenv %s %s' % (VAR, value))

    def unsetenv(self, VAR):
        """
        unsetenv - unset an environment variable

        Remove "VAR" from the environment.
        """
        return self.inner_cmd('unsetenv %s' % VAR)

    def lcd(self, directory):
        """
        lcd - change working directory

        Change the local directory, ie. the current directory of guestfish
        itself.
        """
        return self.inner_cmd('lcd %s' % directory)

    def man(self):
        """
        man - open the manual

        Opens the manual page for guestfish.
        """
        return self.inner_cmd('man')

    def supported(self):
        """
        supported - list supported groups of commands

        This command returns a list of the optional groups known to the daemon,
        and indicates which ones are supported by this build of the libguestfs
        appliance.
        """
        return self.inner_cmd('supported')

    def extlinux(self, directory):
        """
        extlinux - install the SYSLINUX bootloader on an ext2/3/4 or btrfs
        filesystem

        Install the SYSLINUX bootloader on the device mounted at "directory".
        Unlike "syslinux" which requires a FAT filesystem, this can be used on
        an ext2/3/4 or btrfs filesystem.
        """
        return self.inner_cmd('extlinux %s' % directory)

    def syslinux(self, device, directory=None):
        """
        syslinux - install the SYSLINUX bootloader

        Install the SYSLINUX bootloader on "device".
        """
        cmd = 'syslinux %s' % device
        if directory:
            cmd += ' directory:%s' % directory
        return self.inner_cmd(cmd)

    def feature_available(self, groups):
        """
        feature-available - test availability of some parts of the API

        This is the same as "available", but unlike that call it returns a
        simple true/false boolean result, instead of throwing an exception if a
        feature is not found. For other documentation see "available".
        """
        return self.inner_cmd('feature_available %s' % groups)

    def get_program(self):
        """
        get-program - get the program name

        Get the program name. See "set_program".
        """
        return self.inner_cmd('get_program')

    def set_program(self, program):
        """
        set-program - set the program name

        Set the program name. This is an informative string which the main
        program may optionally set in the handle.
        """
        return self.inner_cmd('set_program %s' % program)

    def add_drive_scratch(self, size, name=None, label=None):
        """
        add-drive-scratch - add a temporary scratch drive

        This command adds a temporary scratch drive to the handle. The "size"
        parameter is the virtual size (in bytes). The scratch drive is blank
        initially (all reads return zeroes until you start writing to it). The
        drive is deleted when the handle is closed.
        """
        cmd = 'add_drive_scratch %s' % size
        if name:
            cmd += ' name:%s' % name
        if label:
            cmd += ' label:%s' % label
        return self.inner_cmd(cmd)

    def drop_caches(self, whattodrop):
        """
        drop-caches - drop kernel page cache, dentries and inodes

        The "drop-caches" command instructs the guest kernel to drop its page
        cache, and/or dentries and inode caches. The parameter "whattodrop"
        tells the kernel what precisely to drop.
        """
        return self.inner_cmd("drop-caches %s" % whattodrop)

    def case_sensitive_path(self, path):
        """
        case-sensitive-path - return true path on case-insensitive filesystem

        The "drop-caches" command can be used to resolve case insensitive
        paths on a filesystem which is case sensitive. The use case is to
        resolve paths which you have read from Windows configuration files or
        the Windows Registry, to the true path.
        """
        return self.inner_cmd("case-sensitive-path '%s'" % path)

    def command(self, cmd):
        """
        command - run a command from the guest filesystem

        This call runs a command from the guest filesystem. The filesystem must
        be mounted, and must contain a compatible operating system (ie.
        something Linux, with the same or compatible processor architecture).
        """
        return self.inner_cmd("command '%s'" % cmd)

    def command_lines(self, cmd):
        """
        command-lines - run a command, returning lines

        This is the same as "command", but splits the result into a list of
        lines.
        """
        return self.inner_cmd("command-lines '%s'" % cmd)

    def sh(self, cmd):
        """
        sh - run a command via the shell

        This call runs a command from the guest filesystem via the guest's
        "/bin/sh".
        """
        return self.inner_cmd("sh '%s'" % cmd)

    def sh_lines(self, cmd):
        """
        sh-lines - run a command via the shell returning lines

        This is the same as "sh", but splits the result into a list of
        lines.
        """
        return self.inner_cmd("sh-lines '%s'" % cmd)

    def zero(self, device):
        """
        zero - write zeroes to the device

        This command writes zeroes over the first few blocks of "device".
        """
        return self.inner_cmd("zero '%s'" % device)

    def zero_device(self, device):
        """
        zero-device - write zeroes to an entire device

        This command writes zeroes over the entire "device". Compare with "zero"
        which just zeroes the first few blocks of a device.
        """
        return self.inner_cmd("zero-device '%s'" % device)

    def grep(self, regex, path):
        """
        grep - return lines matching a pattern

        This calls the external "grep" program and returns the matching lines.
        """
        return self.inner_cmd("grep '%s' '%s'" % (regex, path))

    def grepi(self, regex, path):
        """
        grepi - return lines matching a pattern

        This calls the external "grep -i" program and returns the matching lines.
        """
        return self.inner_cmd("grepi '%s' '%s'" % (regex, path))

    def fgrep(self, pattern, path):
        """
        fgrep - return lines matching a pattern

        This calls the external "fgrep" program and returns the matching lines.
        """
        return self.inner_cmd("fgrep '%s' '%s'" % (pattern, path))

    def fgrepi(self, pattern, path):
        """
        fgrepi - return lines matching a pattern

        This calls the external "fgrep -i" program and returns the matching lines.
        """
        return self.inner_cmd("fgrepi '%s' '%s'" % (pattern, path))

    def egrep(self, regex, path):
        """
        egrep - return lines matching a pattern

        This calls the external "egrep" program and returns the matching lines.
        """
        return self.inner_cmd("egrep '%s' '%s'" % (regex, path))

    def egrepi(self, regex, path):
        """
        egrepi - return lines matching a pattern

        This calls the external "egrep -i" program and returns the matching lines.
        """
        return self.inner_cmd("egrepi '%s' '%s'" % (regex, path))

    def zgrep(self, regex, path):
        """
        zgrep - return lines matching a pattern

        This calls the external "zgrep" program and returns the matching lines.
        """
        return self.inner_cmd("zgrep '%s' '%s'" % (regex, path))

    def zgrepi(self, regex, path):
        """
        zgrepi - return lines matching a pattern

        This calls the external "zgrep -i" program and returns the matching lines.
        """
        return self.inner_cmd("zgrepi '%s' '%s'" % (regex, path))

    def zfgrep(self, pattern, path):
        """
        zfgrep - return lines matching a pattern

        This calls the external "zfgrep" program and returns the matching lines.
        """
        return self.inner_cmd("zfgrep '%s' '%s'" % (pattern, path))

    def zfgrepi(self, pattern, path):
        """
        zfgrepi - return lines matching a pattern

        This calls the external "zfgrep -i" program and returns the matching lines.
        """
        return self.inner_cmd("zfgrepi '%s' '%s'" % (pattern, path))

    def zegrep(self, regex, path):
        """
        zegrep - return lines matching a pattern

        This calls the external "zegrep" program and returns the matching lines.
        """
        return self.inner_cmd("zegrep '%s' '%s'" % (regex, path))

    def zegrepi(self, regex, path):
        """
        zegrepi - return lines matching a pattern

        This calls the external "zegrep -i" program and returns the matching lines.
        """
        return self.inner_cmd("zegrepi '%s' '%s'" % (regex, path))

    def compress_out(self, ctype, file, zfile):
        """
        compress-out - output compressed file

        This command compresses "file" and writes it out to the local file
        "zfile".

        The compression program used is controlled by the "ctype" parameter.
        Currently this includes: "compress", "gzip", "bzip2", "xz" or "lzop".
        Some compression types may not be supported by particular builds of
        libguestfs, in which case you will get an error containing the substring
        "not supported".

        The optional "level" parameter controls compression level. The meaning
        and default for this parameter depends on the compression program being
        used.
        """
        return self.inner_cmd("compress-out '%s' '%s' '%s'" % (ctype, file, zfile))

    def compress_device_out(self, ctype, device, zdevice):
        """
        compress-device-out - output compressed device

        This command compresses "device" and writes it out to the local file
        "zdevice".

        The "ctype" and optional "level" parameters have the same meaning as in
        "compress_out".
        """
        return self.inner_cmd("compress-device-out '%s' '%s' '%s'" % (ctype, device, zdevice))

    def glob(self, command, args):
        """
        glob - expand wildcards in command

        Expand wildcards in any paths in the args list, and run "command"
        repeatedly on each matching path.
        """
        return self.inner_cmd("glob '%s' '%s'" % (command, args))

    def glob_expand(self, path):
        """
        glob-expand - expand a wildcard path

        This command searches for all the pathnames matching "pattern" according
        to the wildcard expansion rules used by the shell.
        """
        return self.inner_cmd("glob-expand '%s'" % path)

    def mkmountpoint(self, exemptpath):
        """
        mkmountpoint - create a mountpoint

        "mkmountpoint" and "rmmountpoint" are specialized calls that can be used
        to create extra mountpoints before mounting the first filesystem.
        """
        return self.inner_cmd("mkmountpoint '%s'" % exemptpath)

    def rmmountpoint(self, exemptpath):
        """
        rmmountpoint - remove a mountpoint

        This calls removes a mountpoint that was previously created with
        "mkmountpoint". See "mkmountpoint" for full details.
        """
        return self.inner_cmd("rmmountpoint '%s'" % exemptpath)

    def parse_environment(self):
        """
        parse-environment - parse the environment and set handle flags
        accordingly

        Parse the program's environment and set flags in the handle accordingly.
        For example if "LIBGUESTFS_DEBUG=1" then the 'verbose' flag is set in
        the handle.
        """
        return self.inner_cmd("parse_environment")

    def parse_environment_list(self, environment):
        """
        parse-environment-list - parse the environment and set handle flags
        accordingly

        Parse the list of strings in the argument "environment" and set flags in
        the handle accordingly. For example if "LIBGUESTFS_DEBUG=1" is a string
        in the list, then the 'verbose' flag is set in the handle.
        """
        return self.inner_cmd("parse_environment_list '%s'" % environment)

    def rsync(self, src, dest, args):
        """
        rsync - synchronize the contents of two directories

        This call may be used to copy or synchronize two directories under the
        same libguestfs handle. This uses the rsync(1) program which uses a fast
        algorithm that avoids copying files unnecessarily.
        """
        return self.inner_cmd("rsync %s %s %s" % (src, dest, args))

    def rsync_in(self, src, dest, args):
        """
        rsync-in - synchronize host or remote filesystem with filesystem

        This call may be used to copy or synchronize the filesystem on the host
        or on a remote computer with the filesystem within libguestfs. This uses
        the rsync(1) program which uses a fast algorithm that avoids copying
        files unnecessarily.
        """
        return self.inner_cmd("rsync-in %s %s %s" % (src, dest, args))

    def rsync_out(self, src, dest, args):
        """
        rsync-out - synchronize filesystem with host or remote filesystem

        This call may be used to copy or synchronize the filesystem within
        libguestfs with a filesystem on the host or on a remote computer. This
        uses the rsync(1) program which uses a fast algorithm that avoids
        copying files unnecessarily.
        """
        return self.inner_cmd("rsync-out %s %s %s" % (src, dest, args))

    def utimens(self, path, atsecs, atnsecs, mtsecs, mtnsecs):
        """
        utimens - set timestamp of a file with nanosecond precision

        This command sets the timestamps of a file with nanosecond precision.
        """
        return self.inner_cmd("utimens '%s' '%s' '%s' '%s' '%s'" % (path,
                                                                    atsecs, atnsecs, mtsecs, mtnsecs))

    def utsname(self):
        """
        utsname - appliance kernel version

        This returns the kernel version of the appliance, where this is
        available. This information is only useful for debugging. Nothing in the
        returned structure is defined by the API.
        """
        return self.inner_cmd("utsname")

    def grub_install(self, root, device):
        """
        grub-install root device

        This command installs GRUB 1 (the Grand Unified Bootloader) on "device",
        with the root directory being "root".
        """
        return self.inner_cmd("grub-install %s %s" % (root, device))

    def initrd_cat(self, initrdpath, filename):
        """
        initrd-cat - list the contents of a single file in an initrd

        This command unpacks the file "filename" from the initrd file called
        "initrdpath". The filename must be given *without* the initial "/"
        character.
        """
        return self.inner_cmd("initrd-cat %s %s" % (initrdpath, filename))

    def initrd_list(self, path):
        """
        initrd-list - list files in an initrd

        This command lists out files contained in an initrd.
        """
        return self.inner_cmd("initrd-list %s" % path)

    def aug_init(self, root, flags):
        """
        aug-init - create a new Augeas handle

        Create a new Augeas handle for editing configuration files. If
        there was any previous Augeas handle associated with this guestfs
        session, then it is closed.
        """
        return self.inner_cmd("aug-init %s %s" % (root, flags))

    def aug_clear(self, augpath):
        """
        aug-clear - clear Augeas path

        Set the value associated with "path" to "NULL". This is the same as the
        augtool(1) "clear" command.

        """
        return self.inner_cmd("aug-clear %s" % augpath)

    def aug_set(self, augpath, val):
        """
        aug-set - set Augeas path to value

        Set the value associated with "path" to "val".

        In the Augeas API, it is possible to clear a node by setting the value
        to NULL. Due to an oversight in the libguestfs API you cannot do that
        with this call. Instead you must use the "aug_clear" call.
        """
        return self.inner_cmd("aug-set %s %s" % (augpath, val))

    def aug_get(self, augpath):
        """
        aug-get - look up the value of an Augeas path

        Look up the value associated with "path". If "path" matches exactly one
        node, the "value" is returned.
        """
        return self.inner_cmd("aug-get %s" % augpath)

    def aug_close(self):
        """
        aug-close - close the current Augeas handle and free up any resources
        used by it.

        After calling this, you have to call "aug_init" again before you can
        use any other Augeas functions.
        """
        return self.inner_cmd("aug-close")

    def aug_defnode(self, node, expr, value):
        """
        aug-defnode - defines a variable "name" whose value is the result
        of evaluating "expr".

        If "expr" evaluates to an empty nodeset, a node is created, equivalent
        to calling "aug_set" "expr", "value". "name" will be the nodeset
        containing that single node.

        On success this returns a pair containing the number of nodes in the
        nodeset, and a boolean flag if a node was created.
        """
        return self.inner_cmd("aug-defnode %s %s %s" % (node, expr, value))

    def aug_defvar(self, name, expr):
        """
        aug-defvar - define an Augeas variable

        Defines an Augeas variable "name" whose value is the result of evaluating "expr".
        If "expr" is NULL, then "name" is undefined.

        On success this returns the number of nodes in "expr", or 0 if "expr" evaluates to
        something which is not a nodeset.
        """
        return self.inner_cmd("aug-defvar %s %s" % (name, expr))

    def aug_ls(self, augpath):
        """
        aug-ls - list Augeas nodes under augpath

        This is just a shortcut for listing "aug_match" "path/\*" and sorting the resulting nodes
        into alphabetical order.
        """
        return self.inner_cmd("aug-ls %s" % augpath)

    def aug_insert(self, augpath, label, before):
        """
        aug-insert - insert a sibling Augeas node

        Create a new sibling "label" for "path", inserting it into the tree before or after
        "path" (depending on the boolean flag "before").

        "path" must match exactly one existing node in the tree, and "label"
        must be a label, ie. not contain "/", "*" or end with a bracketed index "[N]".
        """
        return self.inner_cmd("aug-insert %s %s %s" % (augpath, label, before))

    def aug_match(self, augpath):
        """
        aug-match - return Augeas nodes which match augpath

        Returns a list of paths which match the path expression "path". The returned
        paths are sufficiently qualified so that they match exactly one node in the current tree.
        """
        return self.inner_cmd("aug-match %s" % augpath)

    def aug_mv(self, src, dest):
        """
        aug-mv - move Augeas node

        Move the node "src" to "dest". "src" must match exactly one node. "dest" is overwritten
        if it exists.
        """
        return self.inner_cmd("aug-mv %s %s" % (src, dest))

    def aug_rm(self, augpath):
        """
        aug-rm - remove an Augeas path

        Remove "path" and all of its children.
        On success this returns the number of entries which were removed.
        """
        return self.inner_cmd("aug-rm %s" % augpath)

    def aug_label(self, augpath):
        """
        aug-label - return the label from an Augeas path expression

        The label (name of the last element) of the Augeas path expression "augpath" is returned.
        "augpath" must match exactly one node, else this function returns an error.
        """
        return self.inner_cmd("aug-label %s" % augpath)

    def aug_setm(self, base, sub, val):
        """
        aug-setm - set multiple Augeas nodes
        """
        return self.inner_cmd("aug-setm %s %s %s" % (base, sub, val))

    def aug_load(self):
        """
        aug-load - load files into the tree

        Load files into the tree.
        See "aug_load" in the Augeas documentation for the full gory details.
        """
        return self.inner_cmd("aug-load")

    def aug_save(self):
        """
        aug-save - write all pending Augeas changes to disk

        This writes all pending changes to disk.
        The flags which were passed to "aug_init" affect exactly how files are saved.
        """
        return self.inner_cmd("aug-save")


def libguest_test_tool_cmd(qemuarg=None, qemudirarg=None,
                           timeoutarg=None, ignore_status=True,
                           debug=False, timeout=60):
    """
    Execute libguest-test-tool command.

    :param qemuarg: the qemu option
    :param qemudirarg: the qemudir option
    :param timeoutarg: the timeout option
    :return: a CmdResult object
    :raise: raise LibguestfsCmdError
    """
    cmd = "libguestfs-test-tool"
    if qemuarg is not None:
        cmd += " --qemu '%s'" % qemuarg
    if qemudirarg is not None:
        cmd += " --qemudir '%s'" % qemudirarg
    if timeoutarg is not None:
        cmd += " --timeout %s" % timeoutarg

    # Allow to raise LibguestfsCmdError if ignore_status is False.
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_edit_cmd(disk_or_domain, file_path, is_disk=False, disk_format=None,
                  options=None, extra=None, expr=None, connect_uri=None,
                  ignore_status=True, debug=False, timeout=60):
    """
    Execute virt-edit command to check whether it is ok.

    Since virt-edit will need uses' interact, maintain and return
    a session if there is no raise after command has been executed.

    :param disk_or_domain: a img path or a domain name.
    :param file_path: the file need to be edited in img file.
    :param is_disk: whether disk_or_domain is disk or domain
    :param disk_format: when is_disk is true, add a format if it is set.
    :param options: the options of virt-edit.
    :param extra: additional suffix of command.
    :return: a session of executing virt-edit command.
    """
    # disk_or_domain and file_path are necessary parameters.
    cmd = "virt-edit"
    if connect_uri is not None:
        cmd += " -c %s" % connect_uri
    if is_disk:
        # For latest version, --format must exist before -a
        if disk_format is not None:
            cmd += " --format=%s" % disk_format
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s" % file_path
    if options is not None:
        cmd += " %s" % options
    if extra is not None:
        cmd += " %s" % extra
    if expr is not None:
        cmd += " -e '%s'" % expr

    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_clone_cmd(original, newname=None, autoclone=False, **dargs):
    """
    Clone existing virtual machine images.

    :param original: Name of the original guest to be cloned.
    :param newname: Name of the new guest virtual machine instance.
    :param autoclone: Generate a new guest name, and paths for new storage.
    :param dargs: Standardized function API keywords. There are many
                  options not listed, they can be passed in dargs.
    """
    def storage_config(cmd, options):
        """Configure options for storage"""
        # files should be a list
        files = options.get("files", [])
        if len(files):
            for file in files:
                cmd += " --file '%s'" % file
        if options.get("nonsparse") is not None:
            cmd += " --nonsparse"
        return cmd

    def network_config(cmd, options):
        """Configure options for network"""
        mac = options.get("mac")
        if mac is not None:
            cmd += " --mac '%s'" % mac
        return cmd

    cmd = "virt-clone --original '%s'" % original
    if newname is not None:
        cmd += " --name '%s'" % newname
    if autoclone is True:
        cmd += " --auto-clone"
    # Many more options can be added if necessary.
    cmd = storage_config(cmd, dargs)
    cmd = network_config(cmd, dargs)

    ignore_status = dargs.get("ignore_status", True)
    debug = dargs.get("debug", False)
    timeout = dargs.get("timeout", 180)

    return lgf_command(cmd, ignore_status, debug, float(timeout))


def virt_sparsify_cmd(indisk, outdisk, compress=False, convert=None,
                      format=None, ignore_status=True, debug=False,
                      timeout=60):
    """
    Make a virtual machine disk sparse.

    :param indisk: The source disk to be sparsified.
    :param outdisk: The destination disk.
    """
    cmd = "virt-sparsify"
    if compress is True:
        cmd += " --compress"
    if format is not None:
        cmd += " --format '%s'" % format
    cmd += " '%s'" % indisk

    if convert is not None:
        cmd += " --convert '%s'" % convert
    cmd += " '%s'" % outdisk
    # More options can be added if necessary.

    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_resize_cmd(indisk, outdisk, **dargs):
    """
    Resize a virtual machine disk.

    :param indisk: The source disk to be resized
    :param outdisk: The destination disk.
    """
    cmd = "virt-resize"
    ignore_status = dargs.get("ignore_status", True)
    debug = dargs.get("debug", False)
    timeout = dargs.get("timeout", 60)
    resize = dargs.get("resize")
    resized_size = dargs.get("resized_size", "0")
    expand = dargs.get("expand")
    shrink = dargs.get("shrink")
    ignore = dargs.get("ignore")
    delete = dargs.get("delete")
    if resize is not None:
        cmd += " --resize %s=%s" % (resize, resized_size)
    if expand is not None:
        cmd += " --expand %s" % expand
    if shrink is not None:
        cmd += " --shrink %s" % shrink
    if ignore is not None:
        cmd += " --ignore %s" % ignore
    if delete is not None:
        cmd += " --delete %s" % delete
    cmd += " %s %s" % (indisk, outdisk)

    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_list_partitions_cmd(disk_or_domain, long=False, total=False,
                             human_readable=False, ignore_status=True,
                             debug=False, timeout=60):
    """
    "virt-list-partitions" is a command line tool to list the partitions
    that are contained in a virtual machine or disk image.

    :param disk_or_domain: a disk or a domain to be mounted
    """
    cmd = "virt-list-partitions %s" % disk_or_domain
    if long is True:
        cmd += " --long"
    if total is True:
        cmd += " --total"
    if human_readable is True:
        cmd += " --human-readable"
    return lgf_command(cmd, ignore_status, debug, timeout)


def guestmount(disk_or_domain, mountpoint, inspector=False,
               readonly=False, **dargs):
    """
    guestmount - Mount a guest filesystem on the host using
                 FUSE and libguestfs.

    :param disk_or_domain: a disk or a domain to be mounted
           If you need to mount a disk, set is_disk to True in dargs
    :param mountpoint: the mountpoint of filesystems
    :param inspector: mount all filesystems automatically
    :param readonly: if mount filesystem with readonly option
    """
    def get_special_mountpoint(cmd, options):
        special_mountpoints = options.get("special_mountpoints", [])
        for mountpoint in special_mountpoints:
            cmd += " -m %s" % mountpoint
        return cmd

    cmd = "guestmount"
    ignore_status = dargs.get("ignore_status", True)
    debug = dargs.get("debug", False)
    timeout = dargs.get("timeout", 60)
    # If you need to mount a disk, set is_disk to True
    is_disk = dargs.get("is_disk", False)
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    if inspector is True:
        cmd += " -i"
    if readonly is True:
        cmd += " --ro"
    cmd = get_special_mountpoint(cmd, dargs)
    cmd += " %s" % mountpoint
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_filesystems(disk_or_domain, **dargs):
    """
    virt-filesystems - List filesystems, partitions, block devices,
    LVM in a virtual machine or disk image

    :param disk_or_domain: a disk or a domain to be mounted
           If you need to mount a disk, set is_disk to True in dargs
    """
    def get_display_type(cmd, options):
        all = options.get("all", False)
        filesystems = options.get("filesystems", False)
        extra = options.get("extra", False)
        partitions = options.get("partitions", False)
        block_devices = options.get("block_devices", False)
        logical_volumes = options.get("logical_volumes", False)
        volume_groups = options.get("volume_groups", False)
        physical_volumes = options.get("physical_volumes", False)
        long_format = options.get("long_format", False)
        human_readable = options.get("human_readable", False)
        if all is True:
            cmd += " --all"
        if filesystems is True:
            cmd += " --filesystems"
        if extra is True:
            cmd += " --extra"
        if partitions is True:
            cmd += " --partitions"
        if block_devices is True:
            cmd += " --block_devices"
        if logical_volumes is True:
            cmd += " --logical_volumes"
        if volume_groups is True:
            cmd += " --volume_groups"
        if physical_volumes is True:
            cmd += " --physical_volumes"
        if long_format is True:
            cmd += " --long"
        if human_readable is True:
            cmd += " -h"
        return cmd

    cmd = "virt-filesystems"
    # If you need to mount a disk, set is_disk to True
    is_disk = dargs.get("is_disk", False)
    ignore_status = dargs.get("ignore_status", True)
    debug = dargs.get("debug", False)
    timeout = dargs.get("timeout", 60)

    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd = get_display_type(cmd, dargs)
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_list_partitions(disk_or_domain, long=False, total=False,
                         human_readable=False, ignore_status=True,
                         debug=False, timeout=60):
    """
    "virt-list-partitions" is a command line tool to list the partitions
    that are contained in a virtual machine or disk image.

    :param disk_or_domain: a disk or a domain to be mounted
    """
    cmd = "virt-list-partitions %s" % disk_or_domain
    if long is True:
        cmd += " --long"
    if total is True:
        cmd += " --total"
    if human_readable is True:
        cmd += " --human-readable"
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_list_filesystems(disk_or_domain, format=None, long=False,
                          all=False, ignore_status=True, debug=False,
                          timeout=60):
    """
    "virt-list-filesystems" is a command line tool to list the filesystems
    that are contained in a virtual machine or disk image.

    :param disk_or_domain: a disk or a domain to be mounted
    """
    cmd = "virt-list-filesystems %s" % disk_or_domain
    if format is not None:
        cmd += " --format %s" % format
    if long is True:
        cmd += " --long"
    if all is True:
        cmd += " --all"
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_df(disk_or_domain, ignore_status=True, debug=False, timeout=60):
    """
    "virt-df" is a command line tool to display free space on
    virtual machine filesystems.
    """
    cmd = "virt-df %s" % disk_or_domain
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_sysprep_cmd(disk_or_domain, options=None,
                     extra=None, ignore_status=True,
                     debug=False, timeout=600):
    """
    Execute virt-sysprep command to reset or unconfigure a virtual machine.

    :param disk_or_domain: a img path or a domain name.
    :param options: the options of virt-sysprep.
    :return: a CmdResult object.
    """
    if os.path.isfile(disk_or_domain):
        disk_or_domain = "-a " + disk_or_domain
    else:
        disk_or_domain = "-d " + disk_or_domain
    cmd = "virt-sysprep %s" % (disk_or_domain)
    if options is not None:
        cmd += " %s" % options
    if extra is not None:
        cmd += " %s" % extra

    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_cat_cmd(disk_or_domain, file_path, options=None, ignore_status=True,
                 debug=False, timeout=60):
    """
    Execute virt-cat command to print guest's file detail.

    :param disk_or_domain: a img path or a domain name.
    :param file_path: the file to print detail
    :param options: the options of virt-cat.
    :return: a CmdResult object.
    """
    # disk_or_domain and file_path are necessary parameters.
    if os.path.isfile(disk_or_domain):
        disk_or_domain = "-a " + disk_or_domain
    else:
        disk_or_domain = "-d " + disk_or_domain
    cmd = "virt-cat %s '%s'" % (disk_or_domain, file_path)
    if options is not None:
        cmd += " %s" % options

    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_tar_in(disk_or_domain, tar_file, destination, is_disk=False,
                ignore_status=True, debug=False, timeout=60):
    """
    "virt-tar-in" unpacks an uncompressed tarball into a virtual machine
    disk image or named libvirt domain.
    """
    cmd = "virt-tar-in"
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s %s" % (tar_file, destination)
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_tar_out(disk_or_domain, directory, tar_file, is_disk=False,
                 ignore_status=True, debug=False, timeout=60):
    """
    "virt-tar-out" packs a virtual machine disk image directory into a tarball.
    """
    cmd = "virt-tar-out"
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s %s" % (directory, tar_file)
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_copy_in(disk_or_domain, file, destination, is_disk=False,
                 ignore_status=True, debug=False, timeout=60):
    """
    "virt-copy-in" copies files and directories from the local disk into a
    virtual machine disk image or named libvirt domain.
    #TODO: expand file to files
    """
    cmd = "virt-copy-in"
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s %s" % (file, destination)
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_copy_out(disk_or_domain, file_path, localdir, is_disk=False,
                  ignore_status=True, debug=False, timeout=60):
    """
    "virt-copy-out" copies files and directories out of a virtual machine
    disk image or named libvirt domain.
    """
    cmd = "virt-copy-out"
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s %s" % (file_path, localdir)
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_format(disk, filesystem=None, image_format=None, lvm=None,
                partition=None, wipe=False, ignore_status=False,
                debug=False, timeout=60):
    """
    Virt-format takes an existing disk file (or it can be a host partition,
    LV etc), erases all data on it, and formats it as a blank disk.
    """
    cmd = "virt-format"
    if filesystem is not None:
        cmd += " --filesystem=%s" % filesystem
    if image_format is not None:
        cmd += " --format=%s" % image_format
    if lvm is not None:
        cmd += " --lvm=%s" % lvm
    if partition is not None:
        cmd += " --partition=%s" % partition
    if wipe is True:
        cmd += " --wipe"
    cmd += " -a %s" % disk
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_inspector(disk_or_domain, is_disk=False, ignore_status=True,
                   debug=False, timeout=60):
    """
    virt-inspector2 examines a virtual machine or disk image and tries to
    determine the version of the operating system and other information
    about the virtual machine.
    """
    # virt-inspector has been replaced by virt-inspector2 in RHEL7
    # Check it here to choose which one to be used.
    cmd = lgf_cmd_check("virt-inspector2")
    if cmd is None:
        cmd = "virt-inspector"

    # If you need to mount a disk, set is_disk to True
    if is_disk is True:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    return lgf_command(cmd, ignore_status, debug, timeout)


def virt_sysprep_operations():
    """Get virt-sysprep support operation"""
    sys_list_cmd = "virt-sysprep --list-operations"
    result = lgf_command(sys_list_cmd, ignore_status=False)
    oper_info = result.stdout_text.strip()
    oper_dict = {}
    for oper_item in oper_info.splitlines():
        oper = oper_item.split("*")[0].strip()
        desc = oper_item.split("*")[-1].strip()
        oper_dict[oper] = desc
    return oper_dict


def virt_cmd_contain_opt(virt_cmd, opt):
    """ Check if opt is supported by virt-command"""
    if lgf_cmd_check(virt_cmd) is None:
        raise LibguestfsCmdError
    if not opt.startswith('-'):
        raise ValueError("Format should be '--a' or '-a', not '%s'" % opt)
    virt_help_cmd = virt_cmd + " --help"
    result = lgf_command(virt_help_cmd, ignore_status=False)
    # "--add" will not equal to "--addxxx"
    opt = " " + opt.strip() + " "
    return (result.stdout_text.count(opt) != 0)


def virt_ls_cmd(disk_or_domain, file_dir_path, is_disk=False, options=None,
                extra=None, connect_uri=None, ignore_status=True,
                debug=False, timeout=60):
    """
    Execute virt-ls command to check whether file exists.

    :param disk_or_domain: a img path or a domain name.
    :param file_dir_path: the file or directory need to check.
    """
    # disk_or_domain and file_dir_path are necessary parameters.
    cmd = "virt-ls"
    if connect_uri is not None:
        cmd += " -c %s" % connect_uri
    if is_disk:
        cmd += " -a %s" % disk_or_domain
    else:
        cmd += " -d %s" % disk_or_domain
    cmd += " %s" % file_dir_path
    if options is not None:
        cmd += " %s" % options
    if extra is not None:
        cmd += " %s" % extra

    return lgf_command(cmd, ignore_status, debug, timeout)
