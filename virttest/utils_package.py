"""
Package utility for manage package operation on host
"""
import logging
import aexpect

from avocado.core import exceptions
from avocado.utils import software_manager
from six import string_types

from virttest import utils_misc
from virttest import vt_console

LOG = logging.getLogger('avocado.' + __name__)

PACKAGE_MANAGERS = ['apt-get',
                    'yum',
                    'zypper',
                    'dnf']

PKG_MGR_TIMEOUT = 300


class RemotePackageMgr(object):
    """
    The remote package manage class
    """

    def __init__(self, session, pkg):
        """
        :param session: session object
        :param pkg: package name or list
        """
        if not isinstance(session,
                          (aexpect.ShellSession,
                           aexpect.Expect,
                           vt_console.ConsoleSession)):
            raise exceptions.TestError("Parameters exception on session")
        if not isinstance(pkg, list):
            if not isinstance(pkg, string_types):
                raise exceptions.TestError("pkg %s must be list or str" % pkg)
            else:
                self.pkg_list = [pkg, ]
        else:
            self.pkg_list = pkg
        self.package_manager = None
        self.cmd = None
        self.query_cmd = None
        self.install_cmd = None
        self.remove_cmd = None
        self.clean_cmd = None
        self.session = session

        # Inspect and set package manager
        for pkg_mgr in PACKAGE_MANAGERS:
            cmd = 'which ' + pkg_mgr
            if not self.session.cmd_status(cmd):
                self.package_manager = pkg_mgr
                break

        if not self.package_manager:
            raise exceptions.TestError("Package manager not in %s" %
                                       PACKAGE_MANAGERS)
        elif self.package_manager == 'apt-get':
            self.query_cmd = "dpkg -s "
            self.remove_cmd = "apt-get --purge remove -y "
            self.install_cmd = "apt-get install -y "
            self.clean_cmd = "apt-get clean"
        else:
            self.query_cmd = "rpm -q "
            self.remove_cmd = self.package_manager + " remove -y "
            self.install_cmd = self.package_manager + " install -y "
            self.clean_cmd = self.package_manager + " clean all"

    def clean(self):
        """
        Run clean command to refresh repo db

        :return: True or False
        """
        return not self.session.cmd_status(self.clean_cmd, timeout=PKG_MGR_TIMEOUT)

    def is_installed(self, pkg_name):
        """
        Check the package installed status

        :param pkg_name: package name
        :return: True or False
        """
        cmd = self.query_cmd + pkg_name
        return not self.session.cmd_status(cmd, timeout=PKG_MGR_TIMEOUT)

    def operate(self, timeout, default_status, internal_timeout=2):
        """
        Run command and return status

        :param timeout: command timeout
        :param default_status: package default installed status
        :param internal_timeout: internal_timeout to pass to cmd_status
        :return: True of False
        """
        for pkg in self.pkg_list:
            need = False
            if '*' not in pkg:
                if self.is_installed(pkg) == default_status:
                    need = True
            else:
                need = True
            if need:
                cmd = self.cmd + pkg
                status, output = self.session.cmd_status_output(cmd,
                                                                timeout,
                                                                internal_timeout)
                if status:
                    LOG.error("'%s' execution failed with %s", cmd, output)
                    # Try to clean the repo db and re-try installation
                    if not self.clean():
                        LOG.error("Package %s was broken", self.package_manager)
                        return False
                    status, output = self.session.cmd_status_output(cmd, timeout)
                    if status:
                        LOG.error("'%s' execution failed with %s", cmd, output)
                        return False
        return True

    def install(self, timeout=PKG_MGR_TIMEOUT):
        """
        Use package manager install packages

        :param timeout: install timeout
        :return: if install succeed return True, else False
        """
        self.cmd = self.install_cmd
        return self.operate(timeout, False)

    def remove(self, timeout=PKG_MGR_TIMEOUT):
        """
        Use package manager remove packages

        :param timeout: remove timeout
        :return: if remove succeed return True, else False
        """
        self.cmd = self.remove_cmd
        return self.operate(timeout, True)


class LocalPackageMgr(software_manager.SoftwareManager):

    """
    Local package manage class
    """

    def __init__(self, pkg):
        """
        :param pkg: package name or list
        """
        if not isinstance(pkg, list):
            if not isinstance(pkg, string_types):
                raise exceptions.TestError("pkg %s must be list or str" % pkg)
            else:
                self.pkg_list = [pkg, ]
        else:
            self.pkg_list = pkg
        super(LocalPackageMgr, self).__init__()
        self.func = None

    def operate(self, default_status):
        """
        Use package manager to operate packages

        :param default_status: package default installed status
        """
        for pkg in self.pkg_list:
            need = False
            if '*' not in pkg:
                if self.check_installed(pkg) == default_status:
                    need = True
            else:
                need = True
            if need:
                if not self.func(pkg):
                    LOG.error("Operate %s on host failed", pkg)
                    return False
        return True

    def install(self):
        """
        Use package manager install packages

        :return: if install succeed return True, else False
        """
        self.func = super(LocalPackageMgr, self).__getattr__('install')
        return self.operate(False)

    def remove(self):
        """
        Use package manager remove packages

        :return: if remove succeed return True, else False
        """
        self.func = super(LocalPackageMgr, self).__getattr__('remove')
        return self.operate(True)


def package_manager(session, pkg):
    """
    Package manager function

    :param session: session object
    :param pkg: pkg name or list
    :return: package manager class object
    """
    if session:
        mgr = RemotePackageMgr(session, pkg)
    else:
        mgr = LocalPackageMgr(pkg)
    return mgr


def package_install(pkg, session=None, timeout=PKG_MGR_TIMEOUT):
    """
    Try to install packages on system with package manager.

    :param pkg: package name or list of packages
    :param session: session Object
    :param timeout: timeout for install with session
    :return: True if all packages installed, False if any error
    """
    mgr = package_manager(session, pkg)
    return utils_misc.wait_for(mgr.install, timeout)


def package_remove(pkg, session=None, timeout=PKG_MGR_TIMEOUT):
    """
    Try to remove packages on system with package manager.

    :param pkg: package name or list of packages
    :param session: session Object
    :param timeout: timeout for remove with session
    :return: True if all packages removed, False if any error
    """
    mgr = package_manager(session, pkg)
    return utils_misc.wait_for(mgr.remove, timeout)
