import logging

from managers import connect_mgr, vmm

from virttest import utils_misc
from virttest.qemu_devices import qdevices

VMM = vmm.VirtualMachinesManager()
LOG = logging.getLogger("avocado.service." + __name__)


def open_connect(instance_id, name, protocol, log_file=None):
    devices = VMM.get_instance(instance_id).get("devices")
    for device in devices:
        if isinstance(device, qdevices.CharDevice):
            if name in device.get_qid():  # FIXME:
                client_params = device.params
                break
    else:
        raise ValueError(f"Not found the qemu client params for {name}")
    connect = connect_mgr.create_connect(
        instance_id, "qemu", name, protocol, client_params, log_file
    )
    connect_id = utils_misc.generate_random_string(16)
    connect_mgr.register_connect(connect_id, connect)
    return connect_id


def is_connected(instance_id, name):
    connects = connect_mgr.get_connects_by_instance(instance_id)
    for connect in connects:
        if connect.name == name:
            return True
    return False


def close_connect(connect_id):
    connect = connect_mgr.get_connect(connect_id)
    return connect.close()


def execute_connect_data(
    connect_id, data, timeout=None, debug=False, fd=None, data_format=None
):
    connect = connect_mgr.get_connect(connect_id)
    LOG.info(
        f"<Instance: {connect.instance_id}; Monitor: {connect.name}> "
        f"Executing {connect.protocol} connect data: {data}"
    )
    return connect.execute_data(data, timeout, debug, fd, data_format)


def get_connect_events(connect_id):
    connect = connect_mgr.get_connect(connect_id)
    return connect.get_events()


def get_connect_event(connect_id, name):
    connect = connect_mgr.get_connect(connect_id)
    return connect.get_event(name)


def clear_connect_events(connect_id):
    connect = connect_mgr.get_connect(connect_id)
    return connect.clear_events()


def clear_connect_event(connect_id, name):
    connect = connect_mgr.get_connect(connect_id)
    return connect.clear_event(name)


def is_responsive(connect_id):
    connect = connect_mgr.get_connect(connect_id)
    return connect.is_responsive()


def get_monitor_log_files(monitor_id):
    monitor = connect_mgr.get_connect(monitor_id)
    return [log_file for log_file in monitor.open_log_files]
