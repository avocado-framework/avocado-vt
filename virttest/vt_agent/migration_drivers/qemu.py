import logging
import six
import time
import json

from managers import vmm
from managers import connect_mgr

# from virttest.vt_vmm.objects.migrate_qemu_capabilities import QEMU_MIGRATION_CAPABILITIES
# from virttest.vt_vmm.objects.migrate_qemu_parameters import QEMU_MIGRATION_PARAMETERS
from virttest.vt_vmm.objects import migrate_flags
from virttest.qemu_devices import qdevices
from virttest.vt_vmm import migrate_utils
from virttest import utils_misc

LOG = logging.getLogger("avocado.service." + __name__)

VMM = vmm.VirtualMachinesManager()

QEMU_MIGRATION_WAIT_COMPLETED_TIMEOUT = 3600


class QemuMigrationError(Exception):
    pass


class QemuMigrationTimeoutError(Exception):
    pass


def _prepare_storage_destination(instance_id):
    # TODO: Implement prepare storage destination for migration
    pass


def _get_supported_protocols():
    return ["tcp", "rdma", "x-rdma", "unix", "exec", "fd"]


def _is_support_protocol(protocol):
    return protocol in _get_supported_protocols()


def _prepare_incoming(uri_params):
    protocol = uri_params.get("protocol")
    address = uri_params.get("address")
    port = uri_params.get("port")

    if port is None:
        port = utils_misc.find_free_port(5200, 5899)

    if not _is_support_protocol(protocol):
        raise ValueError(f"No support {protocol}")

    uri = None
    if protocol in ("tcp", "rdma", "x-rdma"):
        # Work around default 0 as the address
        uri = f"{protocol}:0:{port}"
    elif protocol in ("unix",):
        uri = f"{protocol}:{address}"
    elif protocol in ("exec",):
        uri = f"{protocol}:{address}"
        raise NotImplementedError("Unsupported protocol exec")
    elif protocol in ("fd",):
        uri = f"{protocol}:{address}"

    incoming = dict()
    # Address where QEMU is supposed to listen
    incoming["address"] = address
    incoming["protocol"] = protocol
    incoming["port"] = port
    # Used when calling migrate-incoming QMP command
    incoming["uri"] = uri
    # # for fd:N URI
    # incoming["fd"] = fd

    return incoming


def _create_instance_process(instance_id, driver_kind, spec, migrate_incoming_uri):
    LOG.info(
        f"Creating the VM instance process with incoming URI: {migrate_incoming_uri}.")
    instance_info = VMM.build_instance(instance_id, driver_kind, spec, migrate_incoming_uri)
    VMM.register_instance(instance_id, instance_info)
    VMM.run_instance(instance_id)
    devices = VMM.get_instance(instance_id).get("devices")

    params = json.loads(spec)
    monitors = params.get("monitors")
    for monitor in monitors:
        name = monitor.get("id")
        protocol = monitor.get("type")
        for device in devices:
            if isinstance(device, qdevices.CharDevice):
                if name == device.get_qid():
                    client_params = device.params
                    break
        else:
            raise ValueError(f"Not found the qemu client params for {name}")
        connect = connect_mgr.create_connect(instance_id, "qemu", name,
                                             protocol, client_params)
        connect_id = utils_misc.generate_random_string(16)
        connect_mgr.register_connect(connect_id, connect)

    for monitor in connect_mgr.get_connects_by_instance(instance_id):
        # Issue qmp_capabilities negotiation
        monitor.cmd("qmp_capabilities")


def _query_capabilities(instance_id, virt_capabilities):
    # for capability in capabilities:
    #     if capability not in migrate_utils.get_qemu_migration_capability(capability):
    #         raise ValueError(f"No support capability: {capability}")

    cmd = "query-migrate-capabilities"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    current_capabilities = monitor.cmd(cmd)

    capabilities = dict()
    for virt_capability in virt_capabilities:
        qemu_capabilities = migrate_utils.get_qemu_migration_capability(virt_capability)
        for current_cap in current_capabilities:
            if current_cap["capability"] == qemu_capabilities:
                capabilities[virt_capability] = current_cap["state"]
    LOG.debug(f"The queried capabilities: {capabilities}")
    return capabilities


def _query_parameters(instance_id, virt_parameters):
    # for parameter in parameters:
    #     if parameter not in QEMU_MIGRATION_PARAMETERS:
    #         raise ValueError(f"No support parameter: {parameter}")

    cmd = "query-migrate-parameters"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    current_parameters = monitor.cmd(cmd)

    parameters = dict()
    for virt_parameter in virt_parameters:
        qemu_parameter = migrate_utils.get_qemu_migration_parameter(virt_parameter)
        parameters[virt_parameter] = current_parameters.get(qemu_parameter)
    LOG.debug(f"The queried parameters: {parameters}")
    return parameters


def _apply_migration_capabilities(instance_id, virt_capabilities):
    capabilities = []
    for virt_capability, state in virt_capabilities.items():
        qemu_capability = migrate_utils.get_qemu_migration_capability(virt_capability)
        capabilities.append({"capability": qemu_capability, "state": state})

    cmd = "migrate-set-capabilities"
    args = {"capabilities": capabilities}
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd(cmd, args)


def _apply_migration_parameters(instance_id, virt_parameters):
    parameters = {}
    for virt_parameter, value in virt_parameters.items():
        qemu_parameter = migrate_utils.get_qemu_migration_parameter(virt_parameter)
        parameters[qemu_parameter] = value

    cmd = "migrate-set-parameters"
    for parameter, value in parameters.items():
        args = {parameter: value}
        monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
        monitor.cmd(cmd, args)


def _start_nbd_server(instance_id):
    pass

def _stop_nbd_server(instance_id):
    pass


def _run_migration_incoming(instance_id, incoming):
    cmd = "migrate-incoming"
    uri = incoming.get("uri")

    protocol = incoming.get("protocol")
    if protocol == "tcp":
        _uri = uri.split(":")
        _uri = ":[::]:".join((_uri[0], _uri[-1]))
    else:
        _uri = uri
    args = {"uri": _uri}
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd(cmd, args)


def _reset_migration(instance_id):
    pass


def migrate_instance_prepare(instance_id, driver_kind, spec, mig_params):
    uri_params = mig_params.get("uri")
    mig_flags = mig_params.get("flags")
    migrate_incoming = _prepare_incoming(uri_params)
    capabilities = mig_params.get("capabilities", {})
    parameters = mig_params.get("parameters", {})

    _prepare_storage_destination(instance_id)
    _create_instance_process(instance_id, driver_kind, spec, migrate_incoming)
    orig_caps = _query_capabilities(instance_id, capabilities.keys())
    orig_params = _query_parameters(instance_id, parameters.keys())

    try:
        _apply_migration_capabilities(instance_id, capabilities)
        _apply_migration_parameters(instance_id, parameters)
        if migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags:
            _start_nbd_server(instance_id)
        _run_migration_incoming(instance_id, migrate_incoming)
    except Exception as e:
        # Rest the migration capabilities and parameters
        _apply_migration_capabilities(instance_id, orig_caps)
        _apply_migration_parameters(instance_id, orig_params)
        VMM.stop_instance(instance_id)
        raise e

    return migrate_incoming


def _migrate_nbd_storage(instance_id):
    pass


def _start_migration(instance_id, uri_params):
    protocol = uri_params.get("protocol")
    address = uri_params.get("address")
    port = uri_params.get("port")
    if protocol in ("tcp", "rdma", "x-rdma"):
        uri = f"{protocol}:{address}:{port}"
    elif protocol == "unix":
        uri = f"{protocol}:{address}"
    elif protocol == "exec":
        uri = f"{protocol}:{address}"
    elif protocol == "fd":
        uri = f"{protocol}:{address}"
    else:
        raise ValueError(f"No support protocol: {protocol}")

    cmd = "migrate"
    args = {"uri": uri}
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd(cmd, args)


def _is_mig_status(out, expected):
    if isinstance(out, six.string_types):  # HMP
        pattern = "Migration status: %s" % expected
        return pattern in out
    else:  # QMP
        return out.get("status") == expected


def _is_mig_none(out):
    return _is_mig_status(out, "none")


def _is_mig_succeeded(out):
    return _is_mig_status(out, "completed")


def _is_mig_failed(out):
    return _is_mig_status(out, "failed")


def _is_mig_cancelled(out):
    return _is_mig_status(out, "cancelled")


def _is_mig_pre_switchover(out):
    return _is_mig_status(out, "pre-switchover")


def _query_migrate(instance_id):
    cmd = "query-migrate"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    return monitor.cmd(cmd)


def _migrate_continue(instance_id, state):
    args = {"state": state}
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd("migrate-continue", args)


def _migration_finished(instance_id):
    mig_info = _query_migrate(instance_id)
    if _is_mig_pre_switchover(mig_info):
        _migrate_continue(instance_id, "pre-switchover")
        return False, mig_info
    ret = (
            _is_mig_none(mig_info)
            or _is_mig_succeeded(mig_info)
            or _is_mig_failed(mig_info)
            or _is_mig_cancelled(mig_info)
    )
    return ret, mig_info


def _wait_for_migration_completion(instance_id, wait_flags, timeout):
    LOG.info(f"Waiting for migration to complete within {timeout} sec")
    end_time = time.time() + float(timeout)
    info = dict()
    while time.time() < end_time:
        ret, info = _migration_finished(instance_id)
        # FIXME: Serialize the dict contents to workaroud
        #  the OverflowError: int exceeds XML-RPC limits
        info = json.dumps(info)
        if ret:
            return True, info
        time.sleep(2)
    return False, info


def _migrate_nbd_copy_cancel(instance_id, disks):
    LOG.info("Cancelling drive mirrors")
    cmd = "block-job-cancel"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    for disk in disks:
        args = {"device": disk}
        monitor.cmd(cmd, args)


def migrate_instance_perform(instance_id, mig_params,
                             timeout=QEMU_MIGRATION_WAIT_COMPLETED_TIMEOUT):
    """
    Perform the migration of the instance.

    :param instance_id: ID of the instance to be migrated
    :param mig_params: Migration parameters
    :param timeout: Timeout for migration completion in seconds
    :return: None
    """
    mig_flags = mig_params.get("flags")
    uri_params = mig_params.get("uri")
    capabilities = mig_params.get("capabilities", {})
    parameters = mig_params.get("parameters", {})
    wait_flags = mig_params.get("wait_flags")
    mig_disks = mig_params.get("migrate_disks")
    storage_migration = migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags

    orig_caps = _query_capabilities(instance_id, capabilities.keys())
    orig_params = _query_parameters(instance_id, parameters.keys())

    try:
        _apply_migration_capabilities(instance_id, capabilities)
        _apply_migration_parameters(instance_id, parameters)
        if storage_migration:
            _migrate_nbd_storage(instance_id)
        _start_migration(instance_id, uri_params)
        ret, migration_info = _wait_for_migration_completion(
            instance_id, wait_flags, timeout)
        if not ret:
            raise TimeoutError("Migration did not complete within the specified timeout")
        LOG.info("Migration is completed")

        if storage_migration:
            _migrate_nbd_copy_cancel(instance_id, mig_disks)

    except Exception as e:
        # Rest the migration capabilities and parameters
        LOG.error("Failed to migrate instance: %s", e)
        _apply_migration_capabilities(instance_id, orig_caps)
        _apply_migration_parameters(instance_id, orig_params)
        VMM.stop_instance(instance_id)
        raise e

    return ret, migration_info


def migrate_instance_finish(instance_id, mig_ret, mig_params):
    """
    Finish the migration of the instance.

    :param instance_id: ID of the instance to be migrated
    :param mig_ret: Result of migration
    :param mig_params: Migration parameters
    :return: None
    """
    mig_flags = mig_params.get("flags")
    inmig_ret = False
    mig_info = dict()
    if not mig_ret:
        if VMM.is_instance_running(instance_id):
            mig_info = _query_migrate(instance_id)
            if migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags:
                _stop_nbd_server(instance_id)
            VMM.stop_instance(instance_id)
    else:
        mig_info = _query_migrate(instance_id)
        if VMM.is_instance_paused(instance_id):
            VMM.continue_instance(instance_id)
        # close the instance monitor
        for connect in connect_mgr.get_connects_by_instance(instance_id):
            connect.close()
            connect_mgr._connects.clear() # workaround to clear all connects
        inmig_ret = True

    # FIXME: Serialize the dict contents to workaroud
    #  the OverflowError: int exceeds XML-RPC limits
    mig_info = json.dumps(mig_info)
    return inmig_ret, mig_info


def migrate_instance_confirm(instance_id, inmig_ret, mig_params):
    mig_flags = mig_params.get("flags")
    cmd = "query-status"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    instance_status = monitor.cmd(cmd)["status"]
    if inmig_ret:
        if "postmigrate" in instance_status:
            VMM.stop_instance(instance_id)
    else:

        if migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags:
            mig_disks = mig_params.get("migrate_disks")
            _migrate_nbd_copy_cancel(instance_id, mig_disks)
        if VMM.is_instance_paused(instance_id):
            VMM.continue_instance(instance_id)


def migrate_instance_cancel(instance_id, mig_params):
    pass


def migrate_instance_resume(instance_id, mig_params):
    pass

# def query_capabilities(instance_id, capabilities: list):
#     """
#
#
#     :param instance_id:
#     :param capabilities: list
#     :return: The queried capabilities
#     """
#     for capability in capabilities:
#         if capability not in QEMU_MIGRATION_CAPABILITIES:
#             raise ValueError("Unknown migration capability: %s" % capability)
#
#     monitor = connect.get_connects_by_instance(instance_id)[0]
#     instance_info = vmm.get_instance(instance_id)
#     qemu_version = instance_info.get("qemu_version")
#
#     cmd = "query-migrate-capabilities"
#     output = monitor.cmd(cmd, args=None, timeout=60, debug=True, fd=None)
#
#     all_capabilities = dict()
#     for capability in capabilities:
#         qemu_caps = QEMU_MIGRATION_CAPABILITIES.get(capability)
#         for qemu_cap in qemu_caps:
#             if qemu_version in qemu_cap["version"]:
#                 qemu_capability = qemu_cap["name"]
#                 break
#         else:
#             raise ValueError("Unknown qemu migration capability: %s" % capability)
#
#         for _ in output:
#             if qemu_capability in _.get("capabilities"):
#                 all_capabilities[capability] = _
#     LOG.debug("The qemu migration capabilities: %s" % all_capabilities)
#     return all_capabilities
#
#
# def get_parameter(instance_id, parameters):
#     for parameter in parameters:
#         if parameter not in QEMU_MIGRATION_PARAMETERS:
#             raise ValueError("Unknown migration parameter: %s" % parameter)
#
#     monitor = connect.get_connects_by_instance(instance_id)[0]
#     instance_info = vmm.get_instance(instance_id)
#     qemu_version = instance_info.get("qemu_version")
#
#     cmd = "query-migrate-parameters"
#     output = monitor.cmd(cmd, args=None, timeout=60, debug=True, fd=None)
#
#     all_parameters = dict()
#     for parameter in parameters:
#         qemu_params = QEMU_MIGRATION_PARAMETERS.get(parameter)
#         for qemu_param in qemu_params:
#             if qemu_version in qemu_param["version"]:
#                 qemu_parameter = qemu_param["name"]
#                 break
#         else:
#             raise ValueError("Unknown qemu migration parameter: %s" % parameter)
#
#         for key, val in output.items():
#             if qemu_parameter == key:
#                 all_parameters[parameter] = {key: val}
#     LOG.debug("The qemu migration parameters: %s" % all_parameters)
#     return all_parameters
#
#
# def set_capabilities(instance_id, capabilities: dict):
#     for capability in capabilities:
#         if capability not in QEMU_MIGRATION_CAPABILITIES:
#             raise ValueError("Unknown migration capability: %s" % capability)
