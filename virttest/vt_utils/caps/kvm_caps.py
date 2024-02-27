from enum import Enum, auto

from avocado.utils import cpu

from . import Capabilities


SYS_MODULE_PATH = '/sys/module'
KVM_AMD_MODULE_PATH = f'{SYS_MODULE_PATH}/kvm_amd'
KVM_INTEL_MODULE_PATH = f'{SYS_MODULE_PATH}/kvm_intel'


class _KVMCapsFlags(Enum):
    """
    Enumerate the flags of KVM module capabilities
    """

    # The following are cvm capabilities of kvm module
    SEV = auto()
    SEV_ES = auto()
    SEV_SNP = auto()
    TDX = auto()


# The kvm module capabilities
_kvm_caps = Capabilities()
_kvm_caps._load_kvm_caps()


# FIXME: these functions may be utils
def _is_kvm_sev_enabled():
    """
    Check if the AMD SEV is enabled by kvm module.
    """
    if not os.path.exists('/dev/sev'):
        return False

    try:
        with open(f'{KVM_AMD_MODULE_PATH}/parameters/sev', 'r') as fd:
            sev_value = fd.read().strip()
    except Exception:
        return False

    return sev_value in ['y', 'Y', '1']


def _is_kvm_sev_es_enabled():
    """
    Check if the AMD SEV-ES is enabled by kvm module.
    """
    try:
        with open(f'{KVM_AMD_MODULE_PATH}/parameters/sev_es', 'r') as fd:
            es_value = fd.read().strip()
    except Exception:
        return False

    return es_value in ['y', 'Y', '1']


def _is_kvm_sev_snp_enabled():
    """
    Check if the AMD SEV-SNP is enabled by kvm module.
    """
    try:
        with open(f'{KVM_AMD_MODULE_PATH}/parameters/sev_snp', 'r') as fd:
            snp_value = fd.read().strip()
    except Exception:
        return False

    return snp_value in ['y', 'Y', '1']


def _is_kvm_tdx_enabled():
    """
    Check if the Intel TDX is enabled by kvm module.
    """
    try:
        with open(f'{KVM_INTEL_MODULE_PATH}/parameters/tdx', 'r') as fd:
            tdx_value = fd.read().strip()
    except Exception:
        return False

    return tdx_value in ['y', 'Y', '1']


def _load_cvm_caps_amd():
    """
    AMD SEV

    Note that sev_snp depends on sev_es, sev_es depends on sev,
    i.e. sev_snp cannot be enabled if either sev_es or sev is disabled.
    """
    if _is_kvm_sev_snp_enabled():
        _kvm_caps.set_flag(_KVMCapsFlags.SEV_SNP)
    if _is_kvm_sev_es_enabled():
        _kvm_caps.set_flag(_KVMCapsFlags.SEV_ES)
    if _is_kvm_sev_enabled():
        _kvm_caps.set_flag(_KVMCapsFlags.SEV)


def _load_cvm_caps_intel():
    """Intel TDX"""
    if _is_kvm_tdx_enabled():
        _kvm_caps.set_flag(_KVMCapsFlags.TDX)


def _load_cvm_caps():
    """
    The kvm module secure guest capabilities
    """
    vendor = cpu.set_vendor()
    if vendor == 'amd':
        _load_cvm_caps_amd()
    elif vendor == 'intel':
        _load_cvm_caps_intel()


def _load_kvm_caps():
    _load_cvm_caps()


def is_kvm_sev_enabled():
    return _KVMCapsFlags.SEV in _kvm_caps


def is_kvm_sev_es_enabled():
    return _KVMCapsFlags.SEV_ES in _kvm_caps


def is_kvm_sev_snp_enabled():
    return _KVMCapsFlags.SEV_SNP in _kvm_caps


def is_kvm_tdx_enabled():
    return _KVMCapsFlags.TDX in _kvm_caps

def get_kvm_cvm_flags():
    return []
