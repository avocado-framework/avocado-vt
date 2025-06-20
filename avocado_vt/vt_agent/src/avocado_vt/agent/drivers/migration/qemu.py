# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>
import copy
import json
import logging
import os
import time

import six
from avocado_vt.agent.core import data_dir
from avocado_vt.agent.managers import connect_mgr, vmm
from virttest import utils_misc
from virttest.qemu_devices import qdevices
from virttest.vt_vmm.objects import migrate_flags
from virttest.vt_vmm.utils import migrate_utils

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
        if not address:
            address = os.path.join(
                data_dir.get_tmp_dir(),
                "migration-unix-%s" % utils_misc.generate_random_string(8),
            )
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


def _create_instance_process(instance_id, backend, spec, migrate_incoming):
    LOG.info(
        f"Creating the VM instance process with incoming: {migrate_incoming}."
    )
    instance_info = VMM.build_instance(
        instance_id, backend, spec, migrate_incoming
    )
    if instance_id not in VMM.instances:
        VMM.register_instance(instance_id, instance_info)
    else:
        VMM.update_instance(instance_id, instance_info)
    VMM.run_instance(instance_id)
    devices = VMM.get_instance_info(instance_id).devices

    # Create a QMP monitor for the instance of the migration process
    # params = json.loads(spec)
    params = copy.deepcopy(spec)
    monitors = params.get("monitors")
    for monitor in monitors:
        name = monitor.get("id")
        backend_id = monitor.get("backend").get("id")
        protocol = monitor.get("type")
        for device in devices:
            if isinstance(device, qdevices.CharDevice):
                if backend_id == device.get_qid():
                    client_params = device.params
                    break
        else:
            raise ValueError(f"Not found the qemu client params for {backend_id}")
        instance_pid = VMM.get_instance_pid(instance_id)
        connect = connect_mgr.create_connect(
            instance_id, instance_pid, "qemu", name, protocol, client_params
        )
        connect_id = utils_misc.generate_random_string(16)
        connect_mgr.register_connect(connect_id, connect)

    for monitor in connect_mgr.get_connects_by_instance(instance_id):
        # Issue qmp_capabilities negotiation
        # monitor.cmd("qmp_capabilities")
        pass  # FIXME: the client.QMPMonitor has been issue the negotiation


def _query_capabilities(instance_id, virt_capabilities):
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


def prepare_migrate_instance(instance_id, backend, spec, mig_params):
    uri_params = mig_params.get("uri")
    mig_flags = mig_params.get("flags")
    migrate_incoming = _prepare_incoming(uri_params)
    capabilities = mig_params.get("capabilities", {})
    parameters = mig_params.get("parameters", {})

    _prepare_storage_destination(instance_id)
    _create_instance_process(instance_id, backend, spec, migrate_incoming)
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


def _wait_for_migration_completion(
    instance_id, no_wait_complete=False, timeout=QEMU_MIGRATION_WAIT_COMPLETED_TIMEOUT
):
    LOG.info(f"Waiting for migration to complete within {timeout} sec")
    end_time = time.time() + float(timeout)
    info = dict()
    while time.time() < end_time:
        time.sleep(2)
        ret, info = _migration_finished(instance_id)
        if ret:
            return True, info
    return False, info


def _migrate_nbd_copy_cancel(instance_id, disks):
    LOG.info("Cancelling drive mirrors")
    cmd = "block-job-cancel"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    for disk in disks:
        args = {"device": disk}
        monitor.cmd(cmd, args)


def _migrate_cancel(instance_id):
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd("migrate_cancel")


def perform_migrate_instance(
    instance_id, mig_params, timeout=QEMU_MIGRATION_WAIT_COMPLETED_TIMEOUT
):
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
    no_wait_complete = mig_params.get("no_wait_complete", False)
    mig_disks = mig_params.get("migrate_disks")
    storage_migration = migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags

    orig_caps = _query_capabilities(instance_id, capabilities.keys())
    orig_params = _query_parameters(instance_id, parameters.keys())

    migration_info = {}
    ret = None

    try:
        _apply_migration_capabilities(instance_id, capabilities)
        _apply_migration_parameters(instance_id, parameters)
        if storage_migration:
            _migrate_nbd_storage(instance_id)
        _start_migration(instance_id, uri_params)
        ret, migration_info = _wait_for_migration_completion(
            instance_id, no_wait_complete, timeout
        )
        if not ret:
            raise QemuMigrationTimeoutError(
                "Migration did not complete within the specified timeout"
            )

        if _is_mig_succeeded(migration_info):
            LOG.info("Migration completed successfully")
        elif _is_mig_failed(migration_info):
            raise QemuMigrationError("Migration failed")
        else:
            raise QemuMigrationError(
                f"Migration ended with unknown status: {migration_info}"
            )

        if storage_migration:
            _migrate_nbd_copy_cancel(instance_id, mig_disks)

    except Exception as e:
        # Rest the migration capabilities and parameters
        LOG.error("Failed to migrate instance: %s", e)
        _apply_migration_capabilities(instance_id, orig_caps)
        _apply_migration_parameters(instance_id, orig_params)
        # No stop the instance if the migration is cancelled
        if "cancelled" not in migration_info.get("status"):
            VMM.stop_instance(instance_id)
            raise e

    # FIXME: Serialize the dict contents to workaround
    #  the OverflowError: int exceeds XML-RPC limits
    migration_info = json.dumps(migration_info)

    return ret, migration_info


def query_migrate_instance(instance_id):
    """
    Query the migration status of the instance.

    :param instance_id: ID of the instance to be queried
    :return: Migration status
    """
    mig_data_file = os.path.join(data_dir.get_tmp_dir(), "mig_data")
    try:
        with open(mig_data_file, "r") as f:
            data = json.load(f)
            if instance_id in data:
                ret, info = data[instance_id]
                return ret, json.dumps(info)
    except:
        return None, "{}"


def finish_migrate_instance(instance_id, mig_ret, mig_params):
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
        # close the qmp monitor of the instance of the migration process
        for connect in connect_mgr.get_connects_by_instance(instance_id):
            connect.close()
            connect_mgr._connects.clear()  # workaround to clear all connects
        inmig_ret = True

    # FIXME: Serialize the dict contents to workaroud
    #  the OverflowError: int exceeds XML-RPC limits
    mig_info = json.dumps(mig_info)
    return inmig_ret, mig_info


def confirm_migrate_instance(instance_id, inmig_ret, mig_params):
    mig_flags = mig_params.get("flags")
    cmd = "query-status"
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    instance_status = monitor.cmd(cmd)["status"]
    if inmig_ret:
        if "postmigrate" in instance_status:
            VMM.stop_instance(instance_id)
            # close the qmp monitor of the instance of the migration process
            for connect in connect_mgr.get_connects_by_instance(instance_id):
                connect.close()
                connect_mgr._connects.clear()  # workaround to clear all connects
            VMM.cleanup_instance(instance_id)

    else:

        if migrate_flags.VIR_MIGRATE_NON_SHARED_DISK in mig_flags:
            mig_disks = mig_params.get("migrate_disks")
            _migrate_nbd_copy_cancel(instance_id, mig_disks)
        if VMM.is_instance_paused(instance_id):
            VMM.continue_instance(instance_id)

def cancel_migrate_instance(instance_id, timeout=60):
    monitor = connect_mgr.get_connects_by_instance(instance_id)[0]
    monitor.cmd("migrate_cancel")

    err = ""
    end_time = time.time() + float(timeout)
    while time.time() < end_time:
        try:
            status = monitor.cmd("query-migrate")
        except Exception as e:
            err = str(e)
            continue
        if _is_mig_succeeded(status):
            LOG.error("Failed to cancel as the migration succeeded")
            return False
        elif _is_mig_failed(status):
            LOG.error("Failed to cancel as the migration failed")
            return False
        if _is_mig_cancelled(status):
            return True
    LOG.error(f"Timeout for canceling migration within {timeout} seconds: {err}")
    return False


def resume_migrate_instance(instance_id, mig_params):
    pass
