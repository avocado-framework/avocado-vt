import logging

from ...managers import vmm

VMM = vmm.VirtualMachinesManager()

LOG = logging.getLogger('avocado.service.' + __name__)


def build_instance(instance_id, instance_driver, instance_spec):
    if instance_id in VMM.instances:
        raise vmm.VMMError(f"The instance {instance_id} was registered.")

    LOG.info(f"Build the instance {instance_id} by {instance_spec}")

    instance_info = VMM.build_instance(instance_driver, instance_spec)
    VMM.register_instance(instance_id, instance_info)


def run_instance(instance_id):
    VMM.run_instance(instance_id)


def stop_instance(instance_id):
    VMM.stop_instance(instance_id)


def get_instance_status(instance_id):
    return VMM.get_instance_status(instance_id)


def get_instance_pid(instance_id):
    return VMM.get_instance_pid(instance_id)


def get_instance_monitors(instance_id):
    return []

