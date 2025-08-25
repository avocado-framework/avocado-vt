from virttest.vt_vmm.objects.migrate_qemu_capabilities import QEMU_MIGRATION_CAPABILITIES
from virttest.vt_vmm.objects.migrate_qemu_parameters import QEMU_MIGRATION_PARAMETERS


def get_qemu_migration_capability(virt_capability):
    if virt_capability in QEMU_MIGRATION_CAPABILITIES:
        return QEMU_MIGRATION_CAPABILITIES[virt_capability]
    else:
        raise ValueError(f"Unsupported type for virt capability {virt_capability}")


def get_virt_migration_capability(qemu_capability):
    for virt_capability, qemu_capabilities in QEMU_MIGRATION_CAPABILITIES.items():
        if qemu_capability in qemu_capabilities:
            return virt_capability
    else:
        raise ValueError(f"Unsupported type for qemu migration capability {qemu_capability}")


def get_qemu_migration_parameter(virt_parameter):
    if virt_parameter in QEMU_MIGRATION_PARAMETERS:
        return QEMU_MIGRATION_PARAMETERS[virt_parameter]
    else:
        raise ValueError(f"Unsupported type for virt parameter {virt_parameter}")


def get_virt_migration_parameter(qemu_parameter):
    for virt_paramter, qemu_parameters in QEMU_MIGRATION_PARAMETERS.items():
        if qemu_parameter in qemu_parameters:
            return virt_paramter
    else:
        raise ValueError(f"Unsupported type for qemu migration parameter {virt_paramter}")
