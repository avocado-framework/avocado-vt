"""
Shared code for tests that need to control libvirt on remote
"""

import logging

from avocado.core import exceptions

from virttest import remote

from virttest.utils_test import libvirt


def update_remote_file(params, value,
                       file_path='/etc/libvirt/libvirtd.conf',
                       restart_libvirt=True):
    """
    Update file on remote and restart libvirtd if needed

    :param param: Test run params
    :param value: The value to update
    :param file_path: The path of the file
    :param restart_libvirt: True to restart libvirtd
    :return: remote.RemoteFile object

    """
    try:
        tmp_value = eval(value)
        logging.debug("Update file {} with: {}".format(file_path, value))
        remote_ip = params.get("server_ip", params.get("remote_ip"))
        remote_pwd = params.get("server_pwd", params.get("remote_pwd"))
        remote_user = params.get("server_user", params.get("remote_user"))

        remote_file_obj = remote.RemoteFile(address=remote_ip, client='scp',
                                            username=remote_user,
                                            password=remote_pwd,
                                            port='22', remote_path=file_path)
        remote_file_obj.sub_else_add(tmp_value)
        if restart_libvirt:
            libvirt.remotely_control_libvirtd(remote_ip, remote_user,
                                              remote_pwd, action='restart',
                                              status_error='no')
        return remote_file_obj
    except Exception as err:
        raise exceptions.TestFail("Unable to update {}: {}"
                                  .format(file_path, err))
