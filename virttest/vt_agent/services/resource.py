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
# Authors: Zhenchao Liu <zhencliu@redhat.com>

import logging

from managers import resbkmgr

LOG = logging.getLogger("avocado.service." + __name__)


def startup_resbkmgr():
    """
    Start the resource backing manager.
    """
    LOG.info(f"Startup the resource backing manager")
    return resbkmgr.startup()


def teardown_resbkmgr():
    """
    Stop the resource backing manager.
    """
    LOG.info(f"Teardown the resource backing manager")
    return resbkmgr.teardown()


def connect_pool(pool_id, pool_config):
    """
    Connect to a specified resource pool from a worker node.

    :param pool_id: The resource pool uuid
    :type pool_id: string
    :param pool_config: The resource pool configuration
    :type pool_config: dict
    :return: Succeeded: 0, {confs to be updated on master node}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Open the connection to pool {pool_config['meta']['name']}: uuid={pool_id}")
    return resbkmgr.create_pool_connection(pool_id, pool_config)


def disconnect_pool(pool_id):
    """
    Disconnect a specified resource pool from a worker node.

    :param pool_id: The resource pool uuid
    :type pool_id: string
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Close the connection to pool: uuid={pool_id}")
    return resbkmgr.destroy_pool_connection(pool_id)


def create_backing_object(backing_config):
    """
    Create a resource backing object on the worker node, which is bound
    to one resource only

    :param backing_config: The required resource configuration to create a
                           backing object, depending on the resource types
    :type backing_config: dict
    :return: Succeeded: 0, {"out": resource backing uuid}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(
        "Create the backing object of the resource: uuid=%s", backing_config["meta"]["uuid"]
    )
    return resbkmgr.create_backing_object(backing_config)


def destroy_backing_object(backing_id):
    """
    Destroy the backing object.

    :param backing_id: The resource backing uuid
    :type backing_id: string
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Destroy the backing object: uuid={backing_id}")
    return resbkmgr.destroy_backing_object(backing_id)


def clone_resource_by_backing(backing_id, arguments=None):
    """
    Clone a resource by a specified backing.

    :param backing_id: The resource backing uuid
    :type backing_id: string
    :param arguments: The arguments of the command
    :type arguments: dict
    :return: Succeeded: 0, {"out": {The cloned resource configurations}}
             Failed: 1, {"out": "error message"}
    :rtype: tuple
    """
    LOG.info(f"Clone a new resource: source resource backing uuid={backing_id}, args={arguments}")
    return resbkmgr.clone_resource_by_backing(backing_id, arguments)


def update_resource_by_backing(backing_id, command, arguments=None):
    """
    Update a resource by a specified backing

    :param backing_id: The resource backing uuid
    :type backing_id: string
    :param command: The command to execute on a worker node
    :type command: string
    :param arguments: The arguments of the command
    :type arguments: dict
    :return: Succeeded: 0, {"out": Depends on the command}
             Failed: 1, {"out": "error message"}
    :rtype: tuple
    """
    LOG.info(f"Update the resource by its backing: uuid={backing_id}, cmd={command}, args={arguments}")
    return resbkmgr.update_resource_by_backing(backing_id, command, arguments)
