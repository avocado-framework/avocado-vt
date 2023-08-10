from enum import Enum, auto

from avocado.utils import cpu

from . import Capabilities


class _CPUCapsFlags(Enum):
    """
    Enumerate the flags of host cpu capabilities.

    The following are CPU security capabilities
      SEV: sev flag is enabled by AMD cpu
      SEV_ES: sev_es flag is enabled by AMD cpu
      SEV_SNP: sev_snp flag is enabled by AMD cpu
      TDX: tdx flag is enabled by intel cpu
    """

    SEV = auto()
    SEV_ES = auto()
    SEV_SNP = auto()
    TDX = auto()


# The host cpu capabilities
_cpu_caps = Capabilities()
_cpu_caps._load_cpu_caps()


def _load_cvm_caps_amd():
    """AMD SEV/ES/SNP"""
    if cpu.cpu_has_flags('sev_snp'):
        _cpu_caps.set_flag(_CPUCapsFlags.SEV_SNP)
    if cpu.cpu_has_flags('sev_es'):
        _cpu_caps.set_flag(_CPUCapsFlags.SEV_ES)
    if cpu.cpu_has_flags('sev'):
        _cpu_caps.set_flag(_CPUCapsFlags.SEV)


def _load_cvm_caps_intel():
    """Intel TDX"""
    if cpu.cpu_has_flags('tdx'):
        _cpu_caps.set_flag(_CPUCapsFlags.TDX)


def _load_cvm_caps():
    """
    set cpu flags from /proc/cpuinfo to see if the
    cvm related flags(e.g. sev or tdx) are enabled
      For AMD SEV/ES/SNP, enable them in BIOS
    """
    vendor = cpu.set_vendor()
    if vendor == 'amd':
        _load_cvm_caps_amd()
    elif vendor == 'intel':
        _load_cvm_caps_intel()


def _load_cpu_caps():
    _load_cvm_caps()


def is_cpu_sev_enabled():
    return _CPUCapsFlags.SEV in _cpu_caps


def is_cpu_sev_es_enabled():
    return _CPUCapsFlags.SEV_ES in _cpu_caps


def is_cpu_sev_snp_enabled():
    return _CPUCapsFlags.SEV_SNP in _cpu_caps


def is_cpu_tdx_enabled():
    return _CPUCapsFlags.TDX in _cpu_caps


def get_cpu_cvm_flags():
    if is_cpu_tdx_enabled():
        return ['tdx']
    elif is_cpu_sev_snp_enabled():
        return ['sev', 'sev-es', 'snp']
    elif is_cpu_sev_es_enabled():
        return ['sev', 'sev-es']
    elif is_cpu_sev_enabled():
        return ['sev']
    return None
