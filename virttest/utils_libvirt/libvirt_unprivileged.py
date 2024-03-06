import logging

import aexpect

from virttest import libvirt_vm, remote, utils_params

LOG = logging.getLogger("avocado." + __name__)


def get_unprivileged_vm(vm_name, user, passwd, **args):
    """
    To get the instance of the given unprivileged vm.

    :param vm_name: name of the unprileged vm
    :param user: name of the unprivileged user
    :param passwd: password of the unprivileged user
    :param args: other arguments
    :return: instance of the unprivileged vm
    """

    host_session = aexpect.ShellSession("su")
    remote.VMManager.set_ssh_auth(host_session, "localhost", user, passwd)
    host_session.close()

    params = utils_params.Params()
    params["connect_uri"] = f"qemu+ssh://{user}@localhost/session"
    params["serials"] = args.get("serials", "serial0")
    params["status_test_command"] = args.get("status_test_command", "echo $?")
    params.update(args)
    root_dir = args.get("root_dir", f"/home/{user}/")
    addr_cache = args.get("address_cache", {})
    uvm = libvirt_vm.VM(vm_name, params, root_dir, addr_cache)

    return uvm
