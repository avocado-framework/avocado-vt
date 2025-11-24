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

"""
Resource Service Module for VT Agent Worker Nodes.

This module provides the service interface for resource management operations on
worker nodes in the avocado-vt distributed testing environment. It serves as the
RPC endpoint that the master node calls to coordinate resource operations across
the cluster.

The service acts as a thin wrapper around the ResourceBackingManager, exposing
resource management capabilities through standardized function calls that can be
invoked remotely via the cluster proxy system. This enables the master node's
ResourceManager to coordinate distributed resource operations while maintaining
clean separation between cluster coordination and node-local implementation.

Service Architecture:
    Master Node (ResourceManager) → Cluster Proxy → Worker Node (Resource Service) → ResourceBackingManager

Key Operations:
    Pool Management: Creating and destroying connections to resource pools
    Backing Management: Creating, destroying, and operating on resource backings
    Resource Operations: Allocation, release, cloning, and synchronization commands

All functions follow a consistent return pattern:
    Success: (0, {"out": result_data})
    Failure: (1, {"out": error_message})

This standardized interface enables reliable error handling and result processing
across the distributed cluster environment.
"""

# pylint: disable=E0611
from avocado_vt.agent.managers import rb_mgr


def start_resource_backing_service():
    """
    Start the resource service by starting the resource backing manager.
    """
    return rb_mgr.startup()


def stop_resource_backing_service():
    """
    Stop the resource service by stopping the resource backing manager.
    """
    return rb_mgr.teardown()


def create_pool_connection(pool_config):
    """
    Create the connection to a resource pool from a worker node.

    :param pool_config: The required resource pool configuration
    :type pool_config: dict
    :return: Succeeded: 0, {confs to be updated on master node}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    return rb_mgr.create_pool_connection(pool_config)


def destroy_pool_connection(pool_id):
    """
    Destroy the connection to a specified resource pool from a worker node.

    :param pool_id: The resource pool uuid
    :type pool_id: string
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    return rb_mgr.destroy_pool_connection(pool_id)


def create_resource_backing(backing_config):
    """
    Create a resource backing object on the worker node, which is bound
    to one resource only

    :param backing_config: The required resource configuration to create a
                           backing object, depending on the resource type
    :type backing_config: dict
    :return: Succeeded: 0, {"out": resource backing uuid}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    return rb_mgr.create_backing_object(backing_config)


def destroy_resource_backing(backing_id):
    """
    Destroy a resource backing object.

    :param backing_id: The resource backing uuid
    :type backing_id: string
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    return rb_mgr.destroy_backing_object(backing_id)


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
    return rb_mgr.clone_resource_by_backing(backing_id, arguments)


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
    return rb_mgr.update_resource_by_backing(backing_id, command, arguments)
