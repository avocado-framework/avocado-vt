"""
libvirt configuration related utility functions
"""

import logging
import re

from avocado.core import exceptions

from virttest import utils_config
from virttest import utils_libvirtd
from virttest import utils_split_daemons
from virttest import remote
from virttest.utils_test import libvirt

LOG = logging.getLogger('avocado.' + __name__)


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
                LOG.error(err)
        if restart_libvirt:
            libvirtd = utils_libvirtd.Libvirtd()
            libvirtd.restart()
        return target_conf


def remove_key_for_modular_daemon(params, remote_dargs=None):
    """
    Remove some configuration keys if the modular daemon is enabled.
    If you set "do_search" or/and "do_not_search" in params, it first
    checks the values and then removes the keys from the config file.

    :param param: The param to use
    :param remote_dargs: The params for remote access
    :return: remote.RemoteFile object for remote file or
        utils_config.LibvirtConfigCommon object for local configuration file
    """

    conf_obj = None
    session = None
    if remote_dargs:
        server_ip = remote_dargs.get("server_ip", remote_dargs.get("remote_ip"))
        server_pwd = remote_dargs.get("server_pwd", remote_dargs.get("remote_pwd"))
        server_user = remote_dargs.get("server_user", remote_dargs.get("remote_user"))
        if not all([server_ip, server_pwd, server_user]):
            raise exceptions.TestError("server_[ip|user|pwd] are necessary!")
        session = remote.wait_for_login('ssh', server_ip, '22', server_user,
                                        server_pwd, r"[\#\$]\s*$")

    if utils_split_daemons.is_modular_daemon(session):
        remove_key = eval(params.get("remove_key", "['remote_mode']"))
        conf_type = params.get("conf_type", "libvirt")
        search_cond = eval(params.get("do_search", '{}'))
        no_search_cond = eval(params.get("no_search", '{}'))
        for k, v in search_cond.items():
            if not re.search(v, k, re.IGNORECASE):
                LOG.debug("The key '%s' does not contain '%s', "
                          "no need to remove %s in %s conf file.",
                          k, v, remove_key, conf_type)
                return
        for k, v in no_search_cond.items():
            if re.search(v, k, re.IGNORECASE):
                LOG.debug("The key '%s' contains '%s', "
                          "no need to remove %s in %s conf file.",
                          k, v, remove_key, conf_type)
                return

        conf_obj = remove_key_in_conf(remove_key, conf_type=conf_type,
                                      remote_params=remote_dargs)
    if session:
        session.close()
    return conf_obj
