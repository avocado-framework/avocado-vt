import logging

from vt_agent.managers import vmm

from . import qemu
from . import libvirt


LOG = logging.getLogger("avocado.service." + __name__)

mig_drivers = {
    "qemu": qemu,
    "libvirt": libvirt,
}


VMM = vmm.VirtualMachinesManager()


def get_migration_driver(driver_kind):
    # LOG.info("All instances: %s", VMM.instances)
    # instance_info = VMM.get_instance(instance_id)
    # driver_kind = instance_info["driver_kind"]
    if driver_kind in mig_drivers:
        return mig_drivers[driver_kind]
    else:
        raise ValueError("Unsupported driver kind: %s" % driver_kind)


# def handle_request(instance_id, request):
#     instance_info = vmm.get_instance(instance_id)
#     action = request["action"]
#     params = request.get("params", {})
#     driver_kind = instance_info["driver_kind"]
#     if driver_kind in drivers:
#         driver = drivers[driver_kind]
#         if action not in dir(driver):
#             raise ValueError("Unsupported action: %s" % action)
#         if params:
#             return getattr(driver, action)(instance_id, **params)
#         else:
#             return getattr(driver, action)(instance_id)
#     else:
#         raise ValueError("Unsupported driver kind: %s" % driver_kind)
