import logging

from avocado.core import exceptions
from avocado.utils import process

from virttest import cpu
from virttest import utils_package


LOG = logging.getLogger('avocado.' + __name__)


def install_virt_pkgs(vm_session):
    """
    Install required virt packages for nested virt test

    :param vm_session: session to the vm
    :raises: exceptions.TestError if installation fails
    """
    pkg_names = ['libvirt', 'qemu-kvm']
    LOG.info("Virt packages will be installed")
    pkg_mgr = utils_package.package_manager(vm_session, pkg_names)
    if not pkg_mgr.install():
        raise exceptions.TestError("Package '%s' installation "
                                   "fails" % pkg_names)


def enable_nested_virt_on_host():
    """
    Enable nested virt on the host

    :raises: exceptions.TestError if nested virt is not set successfully
    :raises: exceptions.TestCancel if not Intel host
    """
    if not cpu.get_cpu_vendor().count('Intel'):
        raise exceptions.TestCancel("Only Intel machine is supported in "
                                    "this function so far.")
    cmd = 'modprobe -r kvm_intel; modprobe -r kvm; modprobe kvm nested=1; modprobe kvm_intel nested=1'
    process.run(cmd, verbose=True, ignore_status=False, shell=True)

    cmd = 'cat /sys/module/kvm_intel/parameters/nested'
    ret = process.run(cmd, verbose=True,
                      ignore_status=False,
                      shell=True).stdout_text.strip()
    if ret not in ['Y', '1']:
        raise exceptions.TestError("Checking nested virt environment "
                                   "with the command '{}' fails with "
                                   "the result '{}'".format(cmd, ret))


def update_vm_cpu(guest_xml, cpu_mode=None):
    """
    Update vm cpu xml for nested virt environment

    :param guest_xml: the vm xml
    :param cpu_mode: like 'host-model', 'host-passthrough'
    :return: the updated vm xml
    """
    # Update cpu mode if needed
    cur_vmcpuxml = guest_xml.cpu
    if cpu_mode:
        LOG.info("Update cpu mode from '{}' to '{}'".format(cur_vmcpuxml.mode, cpu_mode))
        cur_vmcpuxml.mode = cpu_mode if cur_vmcpuxml.mode != cpu_mode else cur_vmcpuxml.mode

    # If the cpu mode is host-passthrough, then there might no cpu feature in the vm xml
    try:
        vmx_index = cur_vmcpuxml.get_feature_index('vmx')
    except Exception as detail:
        LOG.warning(detail)
    else:
        cur_vmcpuxml.set_feature(vmx_index, name='vmx', policy='require')

    if cur_vmcpuxml.mode == 'host-passthrough':
        cur_vmcpuxml.migratable = 'off'

    guest_xml.cpu = cur_vmcpuxml
    guest_xml.sync()
    return guest_xml
