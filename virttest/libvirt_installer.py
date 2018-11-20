"""
Installer code that implement KVM specific bits.

See BaseInstaller class in base_installer.py for interface details.
"""

import os
import platform
import logging

from avocado.utils import process
from virttest import base_installer


__all__ = ['GitRepoInstaller', 'LocalSourceDirInstaller',
           'LocalSourceTarInstaller', 'RemoteSourceTarInstaller']


class LIBVIRTBaseInstaller(base_installer.BaseInstaller):

    '''
    Base class for libvirt installations
    '''

    def _set_install_prefix(self):
        """
        Prefix for installation of application built from source

        When installing virtualization software from *source*, this is where
        the resulting binaries will be installed. Usually this is the value
        passed to the configure script, ie: ./configure --prefix=<value>
        """
        prefix = self.test_builddir
        self.install_prefix = os.path.abspath(prefix)

    def _install_phase_package(self):
        """
        Create libvirt package
        """
        self.rpmbuild_path = self.params.get("rpmbuild_path", "/root/rpmbuild/")
        if os.path.isdir(self.rpmbuild_path):
            process.system("rm -rf %s/*" % self.rpmbuild_path)
        logging.debug("Build libvirt rpms")
        process.system("make rpm", allow_output_check="combined")

    def _install_phase_package_verify(self):
        """
        Check if rpms are generated
        """
        logging.debug("Check for libvirt rpms")
        found = False
        for fl in os.listdir('%s/RPMS/%s/' % (self.rpmbuild_path,
                                              platform.machine())):
            if fl.endswith('.rpm'):
                found = True
        if not found:
            self.test.fail("Failed to build rpms")

    def _install_phase_install(self):
        """
        Install libvirt package
        """
        logging.debug("Install libvirt rpms")
        package_install_cmd = "rpm -Uvh --nodeps --replacepkgs"
        package_install_cmd += " --replacefiles --oldpackage"
        package_install_cmd += " %s/RPMS/%s/libvirt*" % (self.rpmbuild_path,
                                                         platform.machine())
        process.system(package_install_cmd, allow_output_check="combined")

    def _install_phase_init(self):
        """
        Initializes the built and installed software

        :return: None
        """
        logging.debug("Initialize installed libvirt package")
        process.system("service libvirtd restart", allow_output_check="combined")

    def _install_phase_init_verify(self):
        """
        Check if package install is success

        :return: None
        """
        logging.debug("Check libvirt package install")
        process.system("service libvirtd status", allow_output_check="combined")
        process.system("virsh capabilities", allow_output_check="combined")

    def uninstall(self):
        '''
        Performs the uninstallation of KVM userspace component

        :return: None
        '''
        self._cleanup_links()
        super(LIBVIRTBaseInstaller, self).uninstall()

    def install(self):
        super(LIBVIRTBaseInstaller, self).install(package=True)


class GitRepoInstaller(LIBVIRTBaseInstaller,
                       base_installer.GitRepoInstaller):

    '''
    Installer that deals with source code on Git repositories
    '''
    pass


class LocalSourceDirInstaller(LIBVIRTBaseInstaller,
                              base_installer.LocalSourceDirInstaller):

    """
    Installer that deals with source code on local directories
    """
    pass


class LocalSourceTarInstaller(LIBVIRTBaseInstaller,
                              base_installer.LocalSourceTarInstaller):

    """
    Installer that deals with source code on local tarballs
    """
    pass


class RemoteSourceTarInstaller(LIBVIRTBaseInstaller,
                               base_installer.RemoteSourceTarInstaller):

    """
    Installer that deals with source code on remote tarballs
    """
    pass
