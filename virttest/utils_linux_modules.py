"""
Linux kernel modules APIs
"""

import logging

from avocado.utils import linux_modules

LOG = logging.getLogger(__name__)


def check_kernel_config(config_name, session=None):
    """
    Reports the configuration of $config_name of the current kernel

    :param config_name: Name of kernel config to search
                        E.g. CONFIG_VIRTIO_IOMMU
    :type config_name: str
    :param session: guest session, command is run on host if None
    :type session: aexpect.ShellSession
    :return: Config status in running kernel (NOT_SET, BUILTIN, MODULE)
    :rtype: :class:`ModuleConfig`
    """

    def check_session_kernel_config(config_name, session):
        """
        Reports the configuration of $config_name of session's kernel

        :param config_name: Name of kernel config to search
                            E.g. CONFIG_VIRTIO_IOMMU
        :type config_name: str
        :param session: remote session
        :type session: aexpect.ShellSession
        :return: Config status in running kernel (NOT_SET, BUILTIN, MODULE)
        :rtype: :class:`ModuleConfig`
        """
        config_file = "/boot/config-" + session.cmd_output("uname -r").strip()
        config_info = session.cmd_output(
            f'grep ^"{config_name}"= \
                                         {config_file}'
        ).strip()

        LOG.debug("Get config info %s", config_info)
        line = config_info.split("=")
        if len(line) != 2:
            return linux_modules.ModuleConfig.NOT_SET

        LOG.debug("Get config %s, target is %s", line[0].strip(), config_name)
        if line[0].strip() == config_name:
            if line[1].strip() == "m":
                return linux_modules.ModuleConfig.MODULE
            else:
                return linux_modules.ModuleConfig.BUILTIN
        return linux_modules.ModuleConfig.NOT_SET

    return (
        linux_modules.check_kernel_config(config_name)
        if session is None
        else check_session_kernel_config(config_name, session)
    )


def kconfig_is_builtin(config_name, session=None):
    """
    Check if the kernel config is BUILTIN

    :param config_name: Name of kernel config to check
                        E.g. CONFIG_VIRTIO_IOMMU
    :type config_name: str
    :param session: Guest session, command is run on host if None
    :type session: aexpect.ShellSession

    :return: Return True if kernel config is BUILTIN, otherwise False.
    :rtype: Bool
    """
    return (
        check_kernel_config(config_name, session) is linux_modules.ModuleConfig.BUILTIN
    )


def kconfig_is_module(config_name, session=None):
    """
    Check if the kernel config is MODULE

    :param config_name: Name of kernel config to check
                        E.g. CONFIG_VIRTIO_IOMMU
    :type config_name: str
    :param session: Guest session, command is run on host if None
    :type session: aexpect.ShellSession

    :return: Return True if kernel config is MODULE, otherwise False.
    :rtype: Bool
    """
    return (
        check_kernel_config(config_name, session) is linux_modules.ModuleConfig.MODULE
    )


def kconfig_is_not_set(config_name, session=None):
    """
    Check if the kernel config is NOT_SET

    :param config_name: Name of kernel config to check
                        E.g. CONFIG_VIRTIO_IOMMU
    :type config_name: str
    :param session: Guest session, command is run on host if None
    :type session: aexpect.ShellSession
    :return: Return True if kernel config is NOT_SET, otherwise False.
    :rtype: Bool
    """
    return (
        check_kernel_config(config_name, session) is linux_modules.ModuleConfig.NOT_SET
    )
