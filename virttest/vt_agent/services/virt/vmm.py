import logging
import re

from managers import vmm
from vt_agent import migration_drivers

VMM = vmm.VirtualMachinesManager()

LOG = logging.getLogger("avocado.service." + __name__)


def build_instance(instance_id, instance_driver, instance_spec, migrate_inc_uri=None):
    if instance_id in VMM.instances:
        raise vmm.VMMError(f"The instance {instance_id} was registered.")

    LOG.info(f"Build the instance '{instance_id}'")
    instance_info = VMM.build_instance(instance_id, instance_driver,
                                       instance_spec, migrate_inc_uri)
    VMM.register_instance(instance_id, instance_info)


def run_instance(instance_id):
    LOG.info(f"Run the instance '{instance_id}'")
    VMM.run_instance(instance_id)


def stop_instance(instance_id, graceful=True, timeout=120, shutdown_cmd=None,
                  username=None, password=None, prompt=None):
    LOG.info(f"Stop the instance '{instance_id}'")
    prompt = re.compile(prompt)
    VMM.stop_instance(instance_id, graceful, timeout,
                      shutdown_cmd, username, password, prompt)


def pause_instance(instance_id):
    LOG.info(f"Pause the instance '{instance_id}'")
    VMM.pause_instance(instance_id)


def continue_instance(instance_id):
    LOG.info(f"Continue the instance '{instance_id}'")
    VMM.continue_instance(instance_id)


def get_instance_consoles(instance_id, console_type):
    return VMM.get_instance_consoles(instance_id, console_type)


def get_instance_process(instance_id, name):
    if VMM.get_instance(instance_id):
        return VMM.get_instance_process_info(instance_id, name)
    return None


def get_instance_type(instance_id):
    return VMM.get_instance(instance_id).get("driver_kind")


def cleanup_instance(instance_id, free_mac_addresses=True):
    VMM.cleanup_instance(instance_id, free_mac_addresses)
    VMM.unregister_instance(instance_id)


def get_instance_pid(instance_id):
    return VMM.get_instance_pid(instance_id)


def attach_instance_device(instance_id, device_spec):
    pass


def detach_instance_device(instance_id, device_spec):
    pass


def migrate_instance_prepare(instance_id, driver_kind, spec, mig_params):
    LOG.info(f"Prepare the migration of the instance({instance_id})")
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_prepare(instance_id, driver_kind,
                                            spec, mig_params)


def migrate_instance_perform(instance_id, mig_params):
    LOG.info(f"Perform the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_perform(instance_id, mig_params)


def migrate_instance_finish(instance_id, mig_ret, mig_params):
    LOG.info(f"Finish the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_finish(instance_id, mig_ret, mig_params)


def migrate_instance_confirm(instance_id, inmig_ret, mig_params):
    LOG.info(f"Confirm the migration of the instance({instance_id})")
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_confirm(instance_id, inmig_ret, mig_params)


def migrate_instance_cancel(instance_id, mig_params):
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_cancel(instance_id, mig_params)


def migrate_instance_resume(instance_id, mig_params):
    instance_info = VMM.get_instance(instance_id)
    driver_kind = instance_info["driver_kind"]
    mig_drv = migration_drivers.get_migration_driver(driver_kind)
    return mig_drv.migrate_instance_resume(instance_id, mig_params)


