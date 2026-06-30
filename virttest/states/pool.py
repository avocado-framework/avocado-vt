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
# Copyright 2013-2026 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

"""
Module for the QCOW2 pool state management backend.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import os
import time
from typing import Any
import logging as log

import shutil
import contextlib
import fcntl
import errno
import json

from aexpect import remote, ops_linux as ops
from aexpect.client import RemoteSession
from avocado.utils import crypto
from virttest.utils_params import Params

from virttest.qemu_storage import QemuImg

from .setup import StateBackend

logging = log.getLogger("avocado.job." + __name__)


#: skip waiting on locks if we only read from the pool for all processes
#: WARNING: use it only if you know what you are doing
SKIP_LOCKS = False


class TransferOps:
    """A small namespace for pool transfer operations of multiple types."""

    _session_cache = {}

    @classmethod
    def get_session(cls, host: str, params: Params) -> RemoteSession:
        """
        Get a possibly reused session to the remote location.

        :param host: remote host name for the remote location
        :param params: configuration parameters
        :returns: a new session or previously cached session
        """
        session = cls._session_cache.get(host)
        if not session:
            session = remote.remote_login(
                params["nets_shell_client"],
                params["nets_shell_host"],
                params["nets_shell_port"],
                params["nets_username"],
                params["nets_password"],
                params["nets_shell_prompt"],
            )
            cls._session_cache[host] = session
        return session

    @classmethod
    def list_paths(cls, pool_path: str, params: Params) -> list[str]:
        """
        List all states in a path from the pool.

        :param pool_path: pool path to list pool states from
        :param params: configuration parameters
        """
        hosts, path = pool_path.split(":")
        if hosts != "":
            return cls.list_remote(pool_path, params)
        elif ";" in path:
            return cls.list_link(path.replace(";", ""), params)
        else:
            return cls.list_local(path, params)

    @classmethod
    def compare(cls, cache_path: str, pool_path: str, params: Params) -> bool:
        """
        Compare cache and pool external state version.

        :param cache_path: cache path to compare with
        :param pool_path: pool path to compare with
        :param params: configuration parameters
        """
        hosts, path = pool_path.split(":")
        if hosts != "":
            return cls.compare_remote(cache_path, pool_path, params)
        elif ";" in path:
            return cls.compare_link(cache_path, path.replace(";", ""), params)
        else:
            return cls.compare_local(cache_path, path, params)

    @classmethod
    def download(cls, cache_path: str, pool_path: str, params: Params) -> None:
        """
        Download a path from the pool depending on the pool location.

        :param cache_path: cache path to download to
        :param pool_path: pool path to download from
        :param params: configuration parameters
        """
        hosts, path = pool_path.split(":")
        if hosts != "":
            cls.download_remote(cache_path, pool_path, params)
        elif ";" in path:
            cls.download_link(cache_path, path.replace(";", ""), params)
        else:
            cls.download_local(cache_path, path, params)

    @classmethod
    def upload(cls, cache_path: str, pool_path: str, params: Params) -> None:
        """
        Upload a path to the pool depending on the pool location.

        :param cache_path: cache path to upload from
        :param pool_path: pool path to upload to
        :param params: configuration parameters
        """
        hosts, path = pool_path.split(":")
        if hosts != "":
            cls.upload_remote(cache_path, pool_path, params)
        elif ";" in path:
            cls.upload_link(cache_path, path.replace(";", ""), params)
        else:
            cls.upload_local(cache_path, path, params)

    @classmethod
    def delete(cls, pool_path: str, params: Params) -> None:
        """
        Delete a path in the pool depending on the pool location.

        :param pool_path: path in the pool to delete
        :param params: configuration parameters
        """
        hosts, path = pool_path.split(":")
        if hosts != "":
            cls.delete_remote(pool_path, params)
        elif ";" in path:
            cls.delete_link(path.replace(";", ""), params)
        else:
            cls.delete_local(path, params)

    @staticmethod
    def list_local(pool_path: str, params: Params) -> list[str]:
        """
        List all states in a path from the pool.

        All arguments are identical to the main entry method.
        """
        if not os.path.exists(pool_path):
            return []
        return os.listdir(pool_path)

    @staticmethod
    def compare_local(cache_path: str, pool_path: str, params: Params) -> bool:
        """
        Compare cache and pool external state version.

        All arguments are identical to the main entry method.
        """
        if os.path.exists(cache_path):
            local_hash = crypto.hash_file(cache_path, 1048576, "md5")
        else:
            local_hash = ""
        if os.path.exists(pool_path):
            remote_hash = crypto.hash_file(pool_path, 1048576, "md5")
        else:
            remote_hash = ""

        return local_hash == remote_hash

    @staticmethod
    def download_local(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Download a path from the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        update_timeout = params.get_numeric("update_pool_timeout", 300)
        with image_lock(pool_path, update_timeout) as lock:
            if TransferOps.compare_local(cache_path, pool_path, params):
                logging.info(f"Skip download of an already available {cache_path}")
                return
            shutil.copy(pool_path, cache_path)

    @staticmethod
    def upload_local(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Upload a path to the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        update_timeout = params.get_numeric("update_pool_timeout", 300)
        with image_lock(pool_path, update_timeout) as lock:
            if TransferOps.compare_local(cache_path, pool_path, params):
                logging.info(f"Skip upload of an already available {cache_path}")
                return
            os.makedirs(os.path.dirname(pool_path), exist_ok=True)
            shutil.copy(cache_path, pool_path)

    @staticmethod
    def delete_local(pool_path: str, params: Params) -> None:
        """
        Delete a path in the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        update_timeout = params.get_numeric("update_pool_timeout", 300)
        with image_lock(pool_path, update_timeout) as lock:
            os.unlink(pool_path)

    @staticmethod
    def list_remote(pool_path: str, params: Params) -> list[str]:
        """
        List all states in a path from the pool.

        All arguments are identical to the main entry method.
        """
        host, path = pool_path.split(":")
        session = TransferOps.get_session(host, params)
        status, output = session.cmd_status_output(f"ls {path}")
        if status != 0:
            logging.debug(f"Path {path} not found: {output}")
            return []
        return output.split()

    @staticmethod
    def compare_remote(cache_path: str, pool_path: str, params: Params) -> bool:
        """
        Compare cache and pool external state version.

        All arguments are identical to the main entry method.
        """
        if os.path.exists(cache_path):
            local_hash = crypto.hash_file(cache_path, 1048576, "md5")
        else:
            local_hash = ""
        host, path = pool_path.split(":")

        session = TransferOps.get_session(host, params)
        remote_hash = ops.hash_file(session, path, "1M", "md5")

        return local_hash == remote_hash

    @staticmethod
    def download_remote(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Download a path from the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        # TODO: no support for remote lock files yet
        host, path = pool_path.split(":")

        if TransferOps.compare_remote(cache_path, pool_path, params):
            logging.info(
                f"Skip download of an already available and valid {cache_path}"
            )
            return
        if os.path.exists(cache_path):
            logging.info(f"Force download of an already available {cache_path}")

        remote.copy_files_from(
            params["nets_shell_host"],
            params["nets_file_transfer_client"],
            params["nets_username"],
            params["nets_password"],
            params["nets_file_transfer_port"],
            path,
            cache_path,
            timeout=params.get_numeric("update_pool_timeout", 300),
        )

    @staticmethod
    def upload_remote(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Upload a path to the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        # TODO: need to create remote directory if not available
        # TODO: no support for remote lock files yet
        host, path = pool_path.split(":")

        if TransferOps.compare_remote(cache_path, pool_path, params):
            logging.info(f"Skip upload of an already available {pool_path}")
            return
        logging.info(f"Will possibly force upload to {pool_path}")

        remote.copy_files_to(
            params["nets_shell_host"],
            params["nets_file_transfer_client"],
            params["nets_username"],
            params["nets_password"],
            params["nets_file_transfer_port"],
            cache_path,
            path,
            timeout=params.get_numeric("update_pool_timeout", 300),
        )

    @staticmethod
    def delete_remote(pool_path: str, params: Params) -> None:
        """
        Delete a path in the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        host, path = pool_path.split(":")
        session = remote.remote_login(
            params["nets_shell_client"],
            params["nets_shell_host"],
            params["nets_shell_port"],
            params["nets_username"],
            params["nets_password"],
            params["nets_shell_prompt"],
        )
        session.cmd(f"rm {path}")

    @staticmethod
    def compare_link(cache_path: str, pool_path: str, params: Params) -> bool:
        """
        Compare cache and pool external state version.

        All arguments are identical to the main entry method.

        ..todo:: True symlink support is available only for simple backing chains -
            we cannot have the same get_location for an entire chain here since some
            backing files are links and not the originals.
        """
        if os.path.islink(cache_path):
            return os.path.realpath(cache_path) == pool_path
        else:
            return TransferOps.compare_local(cache_path, pool_path, params)

    @staticmethod
    def list_link(pool_path: str, params: Params) -> list[str]:
        """
        List all states in a path from the pool.

        All arguments are identical to the main entry method.
        """
        return TransferOps.list_local(pool_path, params)

    @staticmethod
    def download_link(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Download a path from the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        update_timeout = params.get_numeric("update_pool_timeout", 300)
        with image_lock(pool_path, update_timeout) as lock:
            if TransferOps.compare_link(cache_path, pool_path, params):
                logging.info(f"Skip link of an already available {cache_path}")
                return
            # actual data must be kept safe
            if not os.path.islink(cache_path) and os.path.exists(cache_path):
                raise RuntimeError(
                    f"Cannot link to {pool_path}, {cache_path} data exists"
                )
            # clean up dead links
            if os.path.islink(cache_path) and not os.path.exists(cache_path):
                logging.warning(f"Dead link {cache_path} image detected")
            # possibly reset the symlink pointer
            if os.path.islink(cache_path):
                os.unlink(cache_path)
            os.symlink(pool_path, cache_path)

    @staticmethod
    def upload_link(cache_path: str, pool_path: str, params: Params) -> None:
        """
        Upload a path to the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        if os.path.islink(cache_path):
            raise ValueError("Cannot upload a symlink to its destination")
        else:
            TransferOps.upload_local(cache_path, pool_path, params)

    @staticmethod
    def delete_link(pool_path: str, params: Params) -> None:
        """
        Delete a path in the pool depending on the pool location.

        All arguments are identical to the main entry method.
        """
        TransferOps.delete_local(pool_path, params)


class QCOW2ImageTransfer(StateBackend):
    """Backend manipulating root or external states from a shared pool of QCOW2 images."""

    ops = TransferOps

    @staticmethod
    def get_image_path(params: Params) -> str:
        """
        Get the absolute path to a QCOW2 image.

        :param params: configuration parameters
        :returns: absolute path to the QCOW2 image
        """
        vm_name, image_name = params["vms"], params["images"]
        vm_dir = os.path.join(params["vms_base_dir"], vm_name)

        image_path, image_format = params["image_name"], params.get("image_format")
        if image_format is None:
            raise ValueError(
                f"Unspecified image format for {image_name} - " "must be qcow2 or raw"
            )
        if image_format not in ["raw", "qcow2"]:
            raise ValueError(
                f"Incompatible image format {image_format} for"
                f" {image_name} - must be qcow2 or raw"
            )
        if not os.path.isabs(image_path):
            image_path = os.path.join(vm_dir, image_path)
        image_format = "" if image_format == "raw" else "." + image_format
        image_path = image_path + image_format
        return image_path

    @classmethod
    def check_root(cls, params: Params, object: Any = None) -> bool:
        """
        Check whether a root state or essentially the object exists.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        image_name = params["image_name"]
        target_image = cls.get_image_path(params)
        shared_pool = ":" + params["shared_pool"]
        image_base_name = os.path.join(vm_name, os.path.basename(target_image))

        logging.debug(
            f"Checking for shared {vm_name}/{image_name} existence"
            f" in the shared pool {shared_pool}"
        )
        src_image_name = os.path.join(shared_pool, image_base_name)
        # it is possible that the the root state is partially provided
        pool_images = cls.ops.list_paths(os.path.join(shared_pool, vm_name), params)
        if image_name + ".qcow2" in pool_images:
            logging.info("The shared %s image exists", src_image_name)
            return True
        else:
            logging.info("The shared %s image doesn't exist", src_image_name)
            return False

    @classmethod
    def get_root(cls, params: Params, object: Any = None) -> None:
        """
        Get a root state or essentially due to pre-existence do nothing.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        image_name = params["image_name"]
        target_image = cls.get_image_path(params)
        shared_pool = ":" + params["shared_pool"]
        image_base_names = os.path.join(vm_name, os.path.basename(target_image))

        logging.info(
            f"Downloading shared {vm_name}/{image_name} "
            f"from the shared pool {shared_pool}"
        )
        src_image_name = os.path.join(shared_pool, image_base_names)
        cls.ops.download(target_image, src_image_name, params)

    @classmethod
    def set_root(cls, params: Params, object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        All arguments match the base class.
        """
        vm_name = params["vms"]
        image_name = params["image_name"]
        target_image = cls.get_image_path(params)
        shared_pool = ":" + params["shared_pool"]
        image_base_names = os.path.join(vm_name, os.path.basename(target_image))

        logging.info(
            f"Uploading shared {vm_name}/{image_name} "
            f"to the shared pool {shared_pool}"
        )
        dst_image_name = os.path.join(shared_pool, image_base_names)
        cls.ops.upload(target_image, dst_image_name, params)

    @classmethod
    def unset_root(cls, params: Params, object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        All arguments match the base class and in addition:
        """
        vm_name = params["vms"]
        image_name = params["image_name"]
        target_image = cls.get_image_path(params)
        shared_pool = ":" + params["shared_pool"]
        image_base_names = os.path.join(vm_name, os.path.basename(target_image))

        logging.info(
            f"Removing shared {vm_name}/{image_name} "
            f"from the shared pool {shared_pool}"
        )
        dst_image_name = os.path.join(shared_pool, image_base_names)
        cls.ops.delete(dst_image_name, params)

    @classmethod
    def get_dependency(cls, state: str, params: Params) -> str:
        """
        Return a backing state that the current state depends on.

        :param state: state name to retrieve the backing dependency of

        The rest of the arguments match the signature of the other methods here.
        """
        vm_id, image_name = params["object_id"], params["images"]
        vm_dir = os.path.join(params["swarm_pool"], vm_id)
        params["image_chain"] = f"snapshot {image_name}"
        params["image_name_snapshot"] = os.path.join(image_name, state)
        params["image_format_snapshot"] = "qcow2"
        # TODO: we might want to return the complete backing chain but in some
        # cases parts of it are stored in a remote location
        # params["backing_chain"] = "yes"
        qemu_img = QemuImg(params.object_params("snapshot"), vm_dir, "snapshot")
        image_info = qemu_img.info(force_share=True, output="json")
        image_file = json.loads(image_info).get("backing-filename", "")
        return os.path.basename(image_file.replace(".qcow2", ""))

    @classmethod
    def compare_chain(
        cls, state: str, cache_dir: str, pool_dir: str, params: Params
    ) -> bool:
        """
        Compare checksums for all dependencies states backing a given state.

        :param state: state name
        :param cache_dir: root cache directory to compare from/to
        :param pool_dir: root pool directory to compare from/to
        :param params: configuration parameters
        """
        vm_id = params["object_id"]

        logging.debug(f"Comparing backing chain for {state}")
        next_state = state
        while next_state != "":
            for image_name in params.objects("images"):
                image_params = params.object_params(image_name)
                cache_path = os.path.join(
                    cache_dir, vm_id, image_name, next_state + ".qcow2"
                )
                pool_path = os.path.join(
                    pool_dir, vm_id, image_name, next_state + ".qcow2"
                )
                if not cls.ops.compare(cache_path, pool_path, image_params):
                    logging.warning(
                        f"The image {image_name} has different {next_state} between cache {cache_path} and pool {pool_path}"
                    )
                    return False
            if next_state == state and params["object_type"] in ["vms", "nets/vms"]:
                cache_path = os.path.join(cache_dir, vm_id, next_state + ".state")
                pool_path = os.path.join(pool_dir, vm_id, next_state + ".state")
                if not cls.ops.compare(cache_path, pool_path, params):
                    logging.warning(
                        f"The vm {vm_id} has different {next_state} between cache {cache_path} and pool {pool_path}"
                    )
                    return False
            # comparison of state chain is not yet complete if the state has backing dependencies
            next_state = cls.get_dependency(next_state, params)

        logging.debug(
            f"The backing chain for {state} is identical between cache {cache_dir} and pool {pool_dir}"
        )
        return True

    @classmethod
    def transfer_chain(
        cls,
        state: str,
        cache_dir: str,
        pool_dir: str,
        params: Params,
        down: bool = True,
    ) -> None:
        """
        Repeat pool operation an all dependencies states backing a given state.

        :param state: state name
        :param cache_dir: root cache directory to transfer from/to
        :param pool_dir: root pool directory to transfer from/to
        :param params: configuration parameters
        :param down: whether the chain is downloaded or uploaded
        """
        transfer_operation = cls.ops.download if down else cls.ops.upload
        vm_id = params["object_id"]

        logging.debug(f"Transferring backing chain for {state}")
        next_state = state
        while next_state != "":
            for image_name in params.objects("images"):
                image_params = params.object_params(image_name)
                cache_path = os.path.join(
                    cache_dir, vm_id, image_name, next_state + ".qcow2"
                )
                pool_path = os.path.join(
                    pool_dir, vm_id, image_name, next_state + ".qcow2"
                )
                # if only vm state is not available this would indicate image corruption
                transfer_operation(cache_path, pool_path, image_params)
            if next_state == state and params["object_type"] in ["vms", "nets/vms"]:
                cache_path = os.path.join(cache_dir, vm_id, next_state + ".state")
                pool_path = os.path.join(pool_dir, vm_id, next_state + ".state")
                transfer_operation(cache_path, pool_path, params)
            # transfer of state chain is not yet complete if the state has backing dependencies
            next_state = cls.get_dependency(next_state, params)

        logging.debug(
            f"The backing chain for {state} is fully transferred to cache {cache_dir} from pool {pool_dir}"
        )

    @classmethod
    def show(cls, params: Params, object: Any = None) -> list[str]:
        """
        Return a list of available states of a specific type.

        All arguments match the base class.
        """
        vm_id, vm_name = params["object_id"], params["vms"]
        state_tag = f"{vm_name}"
        format = ".state"
        if params["object_type"] in ["images", "nets/vms/images"]:
            image_name = params["images"]
            state_tag += f"/{image_name}"
            format = ".qcow2"

        pool_dir = params["show_location"]
        path = os.path.join(pool_dir, state_tag.replace(vm_name, vm_id))
        logging.debug(
            f"Showing shared {state_tag} states " f"in the pool location {pool_dir}"
        )

        states = cls.ops.list_paths(path, params)
        states = [p.replace(format, "") for p in states]
        return states

    @classmethod
    def get(cls, params: Params, object: Any = None) -> None:
        """
        Get a state transferring its entire chain of dependencies.

        All arguments match the base class.
        """
        cache_dir = params["swarm_pool"]
        pool_dir = params["get_location"]

        vm_name = params["vms"]
        state_tag = f"{vm_name}"
        format = "state"
        if params["object_type"] in ["images", "nets/vms/images"]:
            image_name = params["images"]
            state_tag += f"/{image_name}"
            format = "qcow2"
        state = params["get_state"]
        logging.info(
            f"Downloading shared {state_tag} state {state} "
            f"from the shared pool {pool_dir} to {cache_dir}"
        )

        cls.transfer_chain(state, cache_dir, pool_dir, params, down=True)

    @classmethod
    def set(cls, params: Params, object: Any = None) -> None:
        """
        Set a state transferring its entire chain of dependencies.

        All arguments match the base class.
        """
        cache_dir = params["swarm_pool"]
        pool_dir = params["set_location"]

        vm_name = params["vms"]
        state_tag = f"{vm_name}"
        if params["object_type"] in ["images", "nets/vms/images"]:
            image_name = params["images"]
            state_tag += f"/{image_name}"
        state = params["set_state"]
        logging.info(
            f"Uploading shared {state_tag} state {state} "
            f"to the shared pool {pool_dir} from {cache_dir}"
        )

        cls.transfer_chain(state, cache_dir, pool_dir, params, down=False)

    @classmethod
    def unset(cls, params: Params, object: Any = None) -> None:
        """
        Unset a state preserving its entire chain of dependencies.

        All arguments match the base class and in addition:
        """
        pool_dir = params["unset_location"]

        vm_id, vm_name = params["object_id"], params["vms"]
        state_tag = f"{vm_name}"
        if params["object_type"] in ["images", "nets/vms/images"]:
            image_name = params["images"]
            state_tag += f"/{image_name}"
        state = params["unset_state"]
        logging.info(
            f"Removing shared {state_tag} state {state} "
            f"from the shared pool {pool_dir}"
        )

        for image_name in params.objects("images"):
            image_params = params.object_params(image_name)
            pool_path = os.path.join(pool_dir, vm_id, image_name, state + ".qcow2")
            cls.ops.delete(pool_path, image_params)
        if params["object_type"] in ["vms", "nets/vms"]:
            pool_path = os.path.join(pool_dir, vm_id, state + ".state")
            cls.ops.delete(pool_path, params)


class RootSourcedStateBackend(StateBackend):
    """Backend manipulating root states from a possibly shared source."""

    transport = QCOW2ImageTransfer

    @classmethod
    def check_root(
        cls, params: Params, object: Any = None
    ) -> list["TestObject"] | bool:
        """
        Check whether a root state or essentially the object exists.

        All arguments match the base class.
        """
        local_root_exists = cls._check_root(params, object)
        if params["pool_scope"] == "own":
            return local_root_exists
        pool_root_exists = cls.transport.check_root(params, object)
        # TODO: boot state has to be deprecated and it cannot be handled remotely
        return local_root_exists or (
            pool_root_exists and params["object_type"] not in ["vms", "nets/vms"]
        )

    @classmethod
    def get_root(cls, params: Params, object: Any = None) -> None:
        """
        Get a root state or essentially due to pre-existence do nothing.

        All arguments match the base class.
        """
        if "own" not in params["pool_scope"]:
            cls.transport.get_root(params, object)
            return
        elif params["pool_scope"] == "own":
            cls._get_root(params, object)
            return

        local_root_exists = cls._check_root(params, object)
        pool_root_exists = cls.transport.check_root(params, object)

        if pool_root_exists:
            if local_root_exists:
                cache_valid = True
                vm_name = params["vms"]
                for image_name in params.objects("images"):
                    image_params = params.object_params(image_name)
                    image_filename = image_params["image_name"]
                    cache_path = os.path.join(
                        image_params["vms_base_dir"], vm_name, image_filename + ".qcow2"
                    )
                    pool_path = os.path.join(
                        image_params.get("shared_pool", ""),
                        vm_name,
                        image_filename + ".qcow2",
                    )
                    if not cls.transport.ops.compare(
                        cache_path, ":" + pool_path, image_params
                    ):
                        logging.warning(
                            f"The image {image_name} is different between cache {cache_path} and pool {pool_path}"
                        )
                        cache_valid = False
                        break
            else:
                cache_valid = False
            if not cache_valid:
                cls.transport.get_root(params, object)
        cls._get_root(params, object)

    @classmethod
    def set_root(cls, params: Params, object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        All arguments match the base class.
        """
        # local and pool root setting are mutually exclusive as we usually want
        # to set the pool root from an existing local root with some states on it
        if params["pool_scope"] == "own":
            cls._set_root(params, object)
        elif params["pool_scope"] == "shared":
            local_root_exists = cls._check_root(params, object)
            if not local_root_exists:
                raise RuntimeError("Updating state pool requires local root states")
            cls.transport.set_root(params, object)
        else:
            raise RuntimeError(f"Invalid pool scope {params['pool_scope']}")

    @classmethod
    def unset_root(cls, params: Params, object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        All arguments match the base class and in addition:
        """
        # local and pool root setting are mutually exclusive as we usually want
        # to set the pool root from an existing local root with some states on it
        if params["pool_scope"] == "own":
            cls._unset_root(params, object)
        elif params["pool_scope"] == "shared":
            cls.transport.unset_root(params, object)
        else:
            raise RuntimeError(f"Invalid pool scope {params['pool_scope']}")


class SourcedStateBackend(StateBackend):
    """Backend manipulating states from a possibly shared source."""

    transport = QCOW2ImageTransfer

    @classmethod
    def get_sources(cls, do: str, params: Params) -> list[str]:
        """
        Get the currently permitted pool and state reuse scope.

        :param do: state operation to consider the location for
        :param params: parameters for the current state manipulation
        """

        def proximity(source: str) -> int:
            score = 0
            source_net, source_path = source.split(":")
            source_params = params.object_params(source_net) if source_net else params
            if params["nets_gateway"] == source_params["nets_gateway"]:
                score += 1000
            if params["nets_host"] == source_params["nets_host"]:
                score += 100
            if params["swarm_pool"] == source_path:
                score += 10
            else:
                score += 1
            return score

        return sorted(params.objects(f"{do}_location"), key=proximity, reverse=True)

    @classmethod
    def get_source_scope(
        cls, source_path: str, source_params: Params, own_params: Params
    ) -> str:
        """
        Get the currently permitted pool and state reuse scope.

        :param source_path: source identifier inclusive of all scopes
        :param own_params: parameters for the current state manipulation
        """
        if own_params["nets_gateway"] != source_params["nets_gateway"]:
            return "cluster"
        elif own_params["nets_host"] != source_params["nets_host"]:
            return "swarm"
        elif own_params["shared_pool"].lstrip(":") == source_path:
            return "shared"
        elif own_params["swarm_pool"] == source_path:
            return "own"
        else:
            return "shared"

    @classmethod
    def show(cls, params: Params, object: Any = None) -> list[str]:
        """
        Return a list of available states of a specific type.

        All arguments match the base class.
        """
        sources = cls.get_sources("show", params)
        scopes = params.get_list("pool_scope")
        if "own" in scopes:
            cache_states = cls._show(params, object)
        else:
            cache_states = []

        pool_states = set()
        for source in sources:
            logging.debug(f"Next show source to consider is {source}")
            source_net, source_path = source.split(":")
            source_params = (
                params.object_params(source_net) if source_net else params.copy()
            )
            source_params["show_location"] = source

            # filtering stage where we may disallow certain data transport
            source_scope = cls.get_source_scope(source_path, source_params, params)
            if source_scope == "own" or source_scope not in scopes:
                continue
            logging.debug(f"Choosing {source} as the show source to use")

            mirror_states = cls.transport.show(source_params, object)
            pool_states = (
                set(mirror_states)
                if not pool_states
                else pool_states.intersection(mirror_states)
            )

        return list(set(cache_states).union(pool_states))

    @classmethod
    def get(cls, params: Params, object: Any = None) -> None:
        """
        Get a state from the best possible mirror in a certain restricted scope.

        All arguments match the base class.
        """
        sources = cls.get_sources("get", params)
        scopes = params.get_list("pool_scope")

        # get from best available source (assuming from best to worst until filters permit it, then breaking)
        for source in sources:
            logging.debug(f"Next get source to consider is {source}")
            source_net, source_path = source.split(":")
            source_params = (
                params.object_params(source_net) if source_net else params.copy()
            )
            source_params["get_location"] = source

            # filtering stage where we may disallow certain data transport
            source_scope = cls.get_source_scope(source_path, source_params, params)
            if source_scope == "own" or source_scope not in scopes:
                continue
            logging.debug(f"Choosing {source} as the get source to use")

            source_params["show_location"] = source
            local_state_exists = params["get_state"] in cls._show(params, object)
            pool_state_exists = params["get_state"] in cls.transport.show(
                source_params, object
            )

            if pool_state_exists:
                if local_state_exists:
                    cache_valid = cls.transport.compare_chain(
                        params["get_state"],
                        params["swarm_pool"],
                        source_params["get_location"],
                        source_params,
                    )
                else:
                    cache_valid = False
                if not cache_valid:
                    cls.transport.get(source_params, object)
            break

        if "own" in scopes:
            cls._get(params, object)

    @classmethod
    def set(cls, params: Params, object: Any = None) -> None:
        """
        Set a state to all mirrors in a certain restricted scope.

        All arguments match the base class.
        """
        sources = cls.get_sources("set", params)
        scopes = params.get_list("pool_scope")
        if "own" in scopes:
            cls._set(params, object)
        else:
            local_state_exists = params["set_state"] in cls._show(params, object)
            if not local_state_exists:
                raise RuntimeError("Updating state pool requires local states")

        # set from best available source (assuming from best to worst until filters permit it, then breaking)
        for source in sources:
            logging.debug(f"Next set source to consider is {source}")
            source_net, source_path = source.split(":")
            source_params = (
                params.object_params(source_net) if source_net else params.copy()
            )
            source_params["set_location"] = source

            # filtering stage where we may disallow certain data transport
            source_scope = cls.get_source_scope(source_path, source_params, params)
            if source_scope == "own" or source_scope not in scopes:
                continue
            logging.debug(f"Choosing {source} as the set source to use")

            cls.transport.set(source_params, object)

    @classmethod
    def unset(cls, params: Params, object: Any = None) -> None:
        """
        Unset a state to all mirrors in a certain restricted scope.

        All arguments match the base class and in addition:
        """
        sources = cls.get_sources("unset", params)
        scopes = params.get_list("pool_scope")
        if "own" in scopes:
            cls._unset(params, object)

        # unset from best available source (assuming from best to worst until filters permit it, then breaking)
        for source in sources:
            logging.debug(f"Next unset source to consider is {source}")
            source_net, source_path = source.split(":")
            source_params = (
                params.object_params(source_net) if source_net else params.copy()
            )
            source_params["unset_location"] = source

            # filtering stage where we may disallow certain data transport
            source_scope = cls.get_source_scope(source_path, source_params, params)
            if source_scope == "own" or source_scope not in scopes:
                continue
            logging.debug(f"Choosing {source} as the unset source to use")

            cls.transport.unset(source_params, object)


@contextlib.contextmanager
def image_lock(resource_path: str, timeout: int = 300) -> None:
    """
    Wait for a lock to free image for state pool operations.

    :param resource_path: path to the potentially locked resource
    :param timeout: timeout to wait before erroring out (default 5 mins)
    """
    if SKIP_LOCKS:
        yield None
        return
    lockfile = resource_path + ".lock"
    os.makedirs(os.path.dirname(lockfile), exist_ok=True)
    with open(lockfile, "wb") as fd:
        for _ in range(timeout):
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError as error:
                # block here but still support a finite timeout
                if error.errno != errno.EACCES and error.errno != errno.EAGAIN:
                    raise
            else:
                break
            logging.debug("Waiting for image to become available")
            time.sleep(1)
        else:
            raise RuntimeError(
                f"Waiting to acquire {lockfile} took more than "
                f"the allowed {timeout} seconds"
            )
        try:
            yield fd
        finally:
            fcntl.lockf(fd, fcntl.LOCK_UN)
