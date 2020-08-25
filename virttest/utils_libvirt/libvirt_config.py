"""
libvirt configuration related utility functions
"""

import logging

from avocado.core import exceptions

from virttest import utils_config
from virttest import utils_libvirtd
from virttest import remote
from virttest.utils_test import libvirt


def remove_key_in_conf(value_list, conf_type="libvirtd",
                       remote_params=None, restart_libvirt=False):
    """
    Remove settings in configuration file on local or remote
    and restart libvirtd if needed

    :param value_list: A list of settings to delete, like ["log_level", "log_outputs"]
    :param conf_type: The configuration type to update on localhost,
        eg, "libvirt", "virtqemud"
    :param remote_params: The params for remote access
    :param restart_libvirt: True to restart libvirtd
    :return: remote.RemoteFile object for remote file or
        utils_config.LibvirtConfigCommon object for local configuration file
    """

    if remote_params:
        remote_ip = remote_params.get("server_ip",
                                      remote_params.get("remote_ip"))
        remote_pwd = remote_params.get("server_pwd",
                                       remote_params.get("remote_pwd"))
        remote_user = remote_params.get("server_user",
                                        remote_params.get("remote_user"))
        file_path = remote_params.get("file_path")
        if not all([remote_ip, remote_pwd, remote_user, file_path]):
            raise exceptions.TestError("remote_[ip|user|pwd] and file_path "
                                       "are necessary!")
        remote_file_obj = remote.RemoteFile(address=remote_ip, client='scp',
                                            username=remote_user,
                                            password=remote_pwd,
                                            port='22', remote_path=file_path)
        remote_file_obj.remove(value_list)

        if restart_libvirt:
            libvirt.remotely_control_libvirtd(remote_ip, remote_user,
                                              remote_pwd, action='restart',
                                              status_error='no')
        return remote_file_obj
    else:
        target_conf = utils_config.get_conf_obj(conf_type)
        for item in value_list:
            try:
                del target_conf[item]
            except utils_config.ConfigNoOptionError as err:
                logging.error(err)
        if restart_libvirt:
            libvirtd = utils_libvirtd.Libvirtd()
            libvirtd.restart()
        return target_conf
