import logging

from managers import vmm
from vt_agent import migration_drivers

LOG = logging.getLogger("avocado.service." + __name__)

VMM = vmm.VirtualMachinesManager()


def handle_request(instance_id, request):
    LOG.info(f"Handling request of migration for instance {instance_id}: {request}")
    return migration_drivers.handle_request(instance_id, request)

    #
    # if action == "start":
    #     VMM.start_instance(instance_id)
    # elif action == "stop":
    #     VMM.stop_instance(instance_id)
    # elif action == "pause":
    #     VMM.pause_instance(instance_id)
    # elif action == "resume":
    #     VMM.resume_instance(instance_id)
    # elif action == "migrate_to":
    #     VMM.migrate_instance_to(instance_id, params)
    # elif action == "get_state":
    #     return VMM.get_instance_state(instance_id)
    # else:
    #     LOG.error(f"Invalid action {action} for instance {instance_id}")

# def get_capability(instance_id, capability):
#     LOG.info(f"Get the capability {capability} of instance {instance_id}")
#     mig_drv = migration_drivers.get_driver(instance_id)
#     return mig_drv.get_capability(capability)
#
#
# def set_capability(instance_id, capability, value):
#     LOG.info(f"Set the capability {capability} to {value} for instance {instance_id}")
#     mig_drv = migration_drivers.get_driver(instance_id)
#     mig_drv.set_capability(capability, value)
#
#
# def get_parameter(instance_id, parameter):
#     LOG.info(f"Get the parameter {parameter} of instance {instance_id}")
#     mig_drv = migration_drivers.get_driver(instance_id)
#     return mig_drv.get_parameter(parameter)
#
#
# def set_parameter(instance_id, parameter, value):
#     LOG.info(f"Set the parameter {parameter} to {value} for instance {instance_id}")
#     mig_drv = migration_drivers.get_driver(instance_id)
#     mig_drv.set_parameter(parameter)
#
#
# def migrate_incoming(instance_id, uri):
#     LOG.info(f"Migrate incoming from {uri} for instance {instance_id}")
#     mig_drv = migration_drivers.get_driver(instance_id)
#     mig_drv.migrate_incoming(uri)
#
#
# def migrate(instance_id, uri, **kwargs):
#     LOG.info(f"Migrate incoming from {uri} for instance")