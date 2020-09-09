
"""
Virsh net* command related utility functions
"""

from avocado.core import exceptions

from virttest import virsh
from virttest import remote
from virttest.utils_test import libvirt


def create_or_del_network(net_dict, is_del=False, remote_args=None):
    """
    Create or delete network on local or remote

    :param net_dict: Dictionary with the network parameters
    :param is_del: Whether the networks should be deleted
    :param remote_args: The parameters for remote
    """

    remote_virsh_session = None
    if remote_args:
        remote_virsh_session = virsh.VirshPersistent(**remote_args)

    if not is_del:
        net_dev = libvirt.create_net_xml(net_dict.get("net_name"), net_dict)

        if not remote_virsh_session:
            if net_dev.get_active():
                net_dev.undefine()
            net_dev.define()
            net_dev.start()
        else:
            remote_ip = remote_args.get("remote_ip")
            remote_user = remote_args.get("remote_user")
            remote_pwd = remote_args.get("remote_pwd")
            if not all([remote_ip, remote_user, remote_pwd]):
                raise exceptions.TestError("remote_[ip|user|pwd] are necessary!")
            remote.scp_to_remote(remote_ip, '22', remote_user, remote_pwd,
                                 net_dev.xml, net_dev.xml, limit="",
                                 log_filename=None, timeout=600,
                                 interface=None)
            remote_virsh_session.net_define(net_dev.xml, debug=True)
            remote_virsh_session.net_start(net_dict.get("net_name"),
                                           debug=True)
            remote.run_remote_cmd("rm -rf %s" % net_dev.xml, remote_args)
    else:
        virsh_session = virsh
        if remote_virsh_session:
            virsh_session = remote_virsh_session
        if net_dict.get("net_name") in virsh_session.net_state_dict():
            virsh_session.net_destroy(net_dict.get("net_name"),
                                      debug=True, ignore_status=True)
            virsh_session.net_undefine(net_dict.get("net_name"),
                                       debug=True, ignore_status=True)
    if remote_virsh_session:
        remote_virsh_session.close_session()
