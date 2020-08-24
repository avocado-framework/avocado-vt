import os
import re
import logging

from avocado.utils import process


class FS(object):
    """
    Base class for proc/sys FS set and get
    """
    def __init__(self, fs, session=None):
        """
        Initializes path, session and func to trigger cmd

        :param fs: proc/sys filesystem path
        :param session: ShellSession object of remote or VM
        """
        self.fs = fs
        self.func = process.getstatusoutput
        self.session = session
        if not self._check_isfile():
            raise AttributeError("%s is not available" % self.fs)
        if self.session:
            self.func = self.session.cmd_status_output

    def _check_isfile(self):
        """
        check whether the fs exist in local/remote host/VM
        """
        if self.session:
            return self.session.cmd_status("cat %s" % self.fs) == 0
        else:
            return os.path.isfile(self.fs)

    @property
    def fs_value(self):
        """
        Getter method for FS

        :return: String, current value in given filesystem
        """
        self.fs_val = str(self.func("cat %s" % self.fs)[1])
        return self.fs_val

    @fs_value.setter
    def fs_value(self, value):
        """
        Setter method for FS

        :param value: value to be set for given filesystem
        :return: Boolean, True on successfully set False on failure
        """
        # set the value
        cmd = "echo %s > %s" % (value, self.fs)
        status, output = self.func(cmd)
        if status != 0:
            logging.error("Failed to set %s to %s, error: %s", self.fs,
                          value, output.strip())
            return False
        return True


class ProcFS(FS):
    """
    class to get or set procfs values in host, remote host or in VM

    Example:
    >>> obj = ProcFS("/proc/sys/vm/nr_hugepages")
    >>> obj.proc_fs_value # To get the value
    >>> obj.proc_fs_value = 1 # To set the value
    """

    def __init__(self, proc_fs, session=None):
        """
        Initializes path, session and func to trigger cmd

        :param proc_fs: proc filesystem path
        :param session: ShellSession object of remote or VM
        """
        self.proc_fs = proc_fs
        super(ProcFS, self).__init__(self.proc_fs, session=session)

    @property
    def proc_fs_value(self):
        """
        Getter method for ProcFS

        :return: String, current value in given proc filesystem
        """
        try:
            return int(self.fs_value)
        except ValueError:
            return self.fs_val

    @proc_fs_value.setter
    def proc_fs_value(self, value):
        """
        Setter method for ProcFS

        :param value: value to be set for given proc filesystem
        :return: Boolean, True on successfully set False on failure
        """
        if str(value) != self.fs_value:
            self.fs_value = value
        # check if the value is reflected after set
        return str(value) == self.fs_value


class SysFS(FS):
    """
    class to get or set sysfs values in host, remote host or in VM

    Example:
    >>> obj = SysFS("/sys/kernel/mm/transparent_hugepage/enabled")
    >>> obj.sys_fs_value # To get the value
    >>> obj.sys_fs_value = "never" # To set the value
    """
    def __init__(self, sys_fs, session=None, regex=r"\[%s\]"):
        """
        Initializes path, session and func to trigger cmd

        :param sys_fs: sys filesystem path
        :param session: ShellSession object of remote or VM
        :param regex: delimiter to the sysfs enabled option.
        Example: # cat /sys/kernel/mm/transparent_hugepage/enabled
                 [always] madvise never
        """
        self.sys_fs = sys_fs
        self.regex = regex
        self.pattern = self.regex % ".*"
        super(SysFS, self).__init__(self.sys_fs, session=session)

    @property
    def sys_fs_value(self):
        """
        Getter method for SysFS

        :return: String, current value in given sys filesystem
        """
        output = re.search(self.pattern, self.fs_value)
        if output:
            return str(output.group()).strip()
        try:
            return int(self.fs_val)
        except ValueError:
            return self.fs_val

    @sys_fs_value.setter
    def sys_fs_value(self, value):
        """
        Setter method for SysFS

        :param value: value to be set for given sys filesystem
        :return: Boolean, True on successfully set False on failure
        """
        check_value = str(value)
        if re.search(self.pattern, str(self.sys_fs_value)):
            check_value = self.regex % value

        if check_value != self.fs_value:
            self.fs_value = value
            return check_value == self.fs_value
        return True
