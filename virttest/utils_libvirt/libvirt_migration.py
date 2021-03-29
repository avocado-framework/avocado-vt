"""
libvirt related migration functions
"""
import os
import logging

from virttest import defaults
from virttest import libvirt_vm
from virttest import remote
from virttest.utils_test import libvirt


def update_virsh_migrate_extra_opts(params):
    """
    Update extra options for virsh migrate command

    :param params: the parameters used
    :return: the updated extra options
    """
    extra_opts = params.get("virsh_migrate_extra")
    postcopy_options = params.get("postcopy_options")
    if postcopy_options:
        extra_opts = "%s %s" % (extra_opts, postcopy_options)
    return extra_opts


def update_virsh_migrate_extra_args(params):
    """
    Update extra arguments for the function executed during migration

    :param params: the parameters used
    :return: the updated extra arguments
    """
    func_params_exists = "yes" == params.get("action_during_mig_params_exists",
                                             "no")

    extra_args = {}
    if func_params_exists:
        if params.get("action_during_mig_params"):
            extra_args.update({'func_params': eval(
                params.get("action_during_mig_params"))})
        else:
            extra_args.update({'func_params': params})

    extra_args.update({'status_error': params.get("status_error", "no")})
    extra_args.update({'err_msg': params.get("err_msg")})
    return extra_args


def update_nfs_disk_params(params):
    """
    Update nfs disk's params

    :param params: the parameters used
    :return: the updated params
    """
    storage_type = params.get("storage_type")
    if storage_type == "nfs":
        # Params for NFS shared storage
        shared_storage = params.get("migrate_shared_storage", "")
        if shared_storage == "":
            default_guest_asset = defaults.get_default_guest_os_info()['asset']
            default_guest_asset = "%s.qcow2" % default_guest_asset
            shared_storage = os.path.join(params.get("nfs_mount_dir"),
                                          default_guest_asset)
            logging.debug("shared_storage:%s", shared_storage)

        # Params to update disk using shared storage
        params["disk_type"] = "file"
        params["disk_source_protocol"] = "netfs"
        params["mnt_path_name"] = params.get("nfs_mount_dir")
    return params


def update_params(params):
    """
    Update the parameters for migraion tests

    :param params: the parameters used
    :return: the updated params
    """
    params["server_ip"] = params.get("remote_ip")
    params["server_user"] = params.get("remote_user", "root")
    params["server_pwd"] = params.get("remote_pwd")
    params["client_ip"] = params.get("local_ip")
    params["client_pwd"] = params.get("local_pwd")
    params["virsh_migrate_desturi"] = libvirt_vm.complete_uri(
                                       params.get("migrate_dest_host"))
    params["virsh_migrate_connect_uri"] = libvirt_vm.complete_uri(
        params.get("migrate_source_host"))
    params = update_nfs_disk_params(params)

    return params
