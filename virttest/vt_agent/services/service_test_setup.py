import os

from virttest.utils_misc import *
from avocado.utils.process import *

from avocado.utils import process

from virttest import utils_misc
from virttest import env_process


def get_kvm_version(enable_kvm=True):
    if os.path.exists("/dev/kvm"):
        return os.uname()[2]
    else:
        if enable_kvm:
            return None


def get_kvm_userspace_version(params):
    kvm_userspace_ver_cmd = params.get("kvm_userspace_ver_cmd", "")
    if kvm_userspace_ver_cmd:
        try:
            kvm_userspace_version = process.run(
                kvm_userspace_ver_cmd, shell=True).stdout_text.strip()
        except process.CmdError:
            kvm_userspace_version = "Unknown"
    else:
        qemu_path = utils_misc.get_qemu_binary(params)
        kvm_userspace_version = env_process._get_qemu_version(qemu_path)
        qemu_dst_path = utils_misc.get_qemu_dst_binary(params)
        if qemu_dst_path and qemu_dst_path != qemu_path:
            kvm_userspace_version = env_process._get_qemu_version(qemu_dst_path)
    return kvm_userspace_version


def process_command(params, bindir, command, command_noncritical):
    # Export environment vars
    for k in params:
        os.putenv("KVM_TEST_%s" % k, str(params[k]))
    # Execute commands
    try:
        process.system("cd %s; %s" % (bindir, command), shell=True)
    except process.CmdError as e:
        if command_noncritical:
            return str(e)
        else:
            return False
    return True
