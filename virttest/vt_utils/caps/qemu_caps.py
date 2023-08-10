from enum import Enum, auto
import re

from avocado.utils import cpu
from avocado.utils import process

from virttest.utils_misc import get_qemu_binary
from . import Capabilities


class _QemuCapsFlags(Enum):
    """ Enumerate the flags of VM capabilities. """

    BLOCKDEV = _auto_value()
    SMP_DIES = _auto_value()
    SMP_CLUSTERS = _auto_value()
    INCOMING_DEFER = _auto_value()
    MIGRATION_PARAMS = _auto_value()

    # The following are cvm capabilities of qemu objects
    OBJECT_SEV_GUEST = _auto_value()
    OBJECT_SNP_GUEST = _auto_value()
    OBJECT_TDX_GUEST = _auto_value()


# The qemu capabilities
_qemu_caps = Capabilities()
_qemu_binary = get_qemu_binary(params={})  # TODO
_qemu_caps._load_qemu_caps()


def _exec_qemu(options, tmo=10):
    cmd = "%s %s 2>&1" % (_qemu_binary, options)
    return process.run(cmd, timeout=tmo, ignore_status=True,
                       shell=True, verbose=False).stdout_text


def _has_object(obj, object_help):
    return bool(re.search(r'^\s*%s\n' % obj, object_help, re.M))


def _load_cvm_obj_caps_amd(object_help):
    if _has_object('sev-guest', object_help):
        _qemu_caps.set(_QemuCapsFlags.OBJECT_SEV_GUEST)
    if _has_object('sev-snp-guest', object_help):
        _qemu_caps.set(_QemuCapsFlags.OBJECT_SNP_GUEST)


def _load_cvm_obj_caps_intel(object_help):
    if _has_object('tdx-guest', object_help):
        _qemu_caps.set(_QemuCapsFlags.OBJECT_TDX_GUEST)


def _load_cvm_obj_caps(object_help):
    vendor = cpu.get_vendor()
    if vendor == 'amd':
        _load_cvm_obj_caps_amd(object_help)
    elif vendor == 'intel':
        _load_cvm_obj_caps_intel(object_help)


def _load_qemu_caps():
    object_help = _exec_qemu("-object \?")
    _load_cvm_obj_caps(object_help)


def is_qemu_sev_enabled():
    return _QemuCapsFlags.OBJECT_SEV_GUEST in _qemu_caps


def is_qemu_sev_es_enabled():
    return is_qemu_sev_enabled()


def is_qemu_sev_snp_enabled():
    return _QemuCapsFlags.OBJECT_SNP_GUEST in _qemu_caps


def is_qemu_tdx_enabled():
    return _QemuCapsFlags.OBJECT_TDX_GUEST in _qemu_caps


def get_qemu_cvm_flags():
    return []
