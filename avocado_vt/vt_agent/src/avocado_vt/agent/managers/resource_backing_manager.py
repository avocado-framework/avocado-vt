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
import os
import pickle

# pylint: disable=E0611
from avocado_vt.agent.core.data_dir import BACKING_MGR_ENV_FILENAME
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

from .resource_backings import get_pool_connection_class, get_resource_backing_class

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


class _ResourceBackingManager(object):
    """
    Manages resource backings and pool connections on worker nodes.

    The ResourceBackingManager serves as the central coordinator for all resource-related
    operations on worker nodes in the VT cluster. It maintains the lifecycle of resource
    backing objects (node-local implementations of resources) and pool connection objects
    (connections to local or shared resource pools).

    This manager operates on worker nodes and communicates with the central ResourceManager
    on the controller node through the cluster proxy system. It handles the worker-side aspects
    of the distributed resource management architecture.

    Key Responsibilities:
        - Pool connection management: establishing and maintaining connections to resource pools
        - Resource backing lifecycle: creating, managing, and destroying resource backings
        - State persistence: maintaining manager state across process boundaries
        - Service coordination: providing resource services to the cluster proxy

    Architecture Integration:
        Controller Node: ResourceManager coordinates cluster-wide resource state
        Worker Nodes: ResourceBackingManager handles node-local resource operations
        Communication: Cluster proxy enables controller-worker coordination

    State Persistence:
        The manager persists its state to BACKING_MGR_ENV_FILENAME to handle scenarios
        where the agent daemon is not running (e.g., when worker node is also controller node).
        State restoration occurs during initialization to maintain consistency.
    """

    def __init__(self):
        self._backings = dict()
        self._pool_connections = dict()

        # When the worker node is also the controller node, the agent daemon will
        # not be started, the process quits before the job process starts, so
        # the backing manager has to restore the configurations. Abort the
        # process whenever there is a loading failure
        try:
            if os.path.isfile(BACKING_MGR_ENV_FILENAME):
                self._load()
        except Exception as e:
            LOG.error("Failed to load the backing manager env file: %s", str(e))
            raise

    def _load(self):
        with open(BACKING_MGR_ENV_FILENAME, "rb") as f:
            self._dump_data = pickle.load(f)

    def _dump(self):
        with open(BACKING_MGR_ENV_FILENAME, "wb") as f:
            pickle.dump(self._dump_data, f)

    @property
    def _dump_data(self):
        return {
            "pool_connections": self._pool_connections,
        }

    @_dump_data.setter
    def _dump_data(self, data):
        self._pool_connections = data.get("pool_connections", dict())

    @property
    def backings(self):
        return self._backings

    @property
    def pool_connections(self):
        return self._pool_connections

    def startup(self):
        """
        Start the resource backing manager when starting the resmgr on controller
        """
        pass

    def teardown(self):
        """
        Stop the resource backing manager when stopping the resmgr on controller
        """
        if os.path.exists(BACKING_MGR_ENV_FILENAME):
            os.unlink(BACKING_MGR_ENV_FILENAME)
        self._dump_data = dict()

    def query_resource_backing(self, resource_id):
        """
        Get the resource backing uuid by its resource uuid.
        Used for other managers running on the worker node, e.g. vmm manager
        """
        for backing_uuid, backing_obj in self.backings.items():
            if backing_obj.resource_uuid == resource_id:
                return backing_uuid
        return None

    def get_resource_info_by_backing(self, backing_id, verbose=False):
        """
        Get the required resource information.
        Used for other managers running on the worker node, e.g. vmm manager.
        If verbose is true, all related information is returned, including
        the pool configuration.
        """
        backing = self.backings[backing_id]
        pool_conn = self.pool_connections[backing.resource_pool_uuid]
        if verbose:
            return backing.get_all_resource_info(pool_conn)
        else:
            return backing.sync_resource_info(pool_conn)

    def create_pool_connection(self, pool_config):
        """
        Open a connection to the resource pool from a worker node
        """
        r, o = 0, dict()
        try:
            pool_id = pool_config["meta"]["uuid"]
            pool_type = pool_config["meta"]["type"]
            pool_conn_class = get_pool_connection_class(pool_type)
            pool_conn = pool_conn_class(pool_config)
            ret = pool_conn.open()
            self.pool_connections[pool_id] = pool_conn
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)

        if r == 0:
            self._dump()

        return r, o

    def destroy_pool_connection(self, pool_id):
        """
        Close the connection to the resource pool from a worker node
        """
        r, o = 0, dict()
        try:
            pool_conn = self.pool_connections.pop(pool_id)
            ret = pool_conn.close()
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)

        if r == 0:
            self._dump()

        return r, o

    def create_backing_object(self, resource_backing_config):
        """
        Create the resource backing object. The resource can only be accessed
        by its backing object on a worker node.

        Note some attributes can only be set when creating the backing object,
        e.g. the volume's uri, so return the attributes in order to update the
        resource configuration on the controller node.
        """
        r, o = 0, dict()
        try:
            pool_id = resource_backing_config["meta"]["pool"]
            pool_conn = self.pool_connections[pool_id]
            res_type = resource_backing_config["meta"]["type"]
            backing_class = get_resource_backing_class(pool_conn.POOL_TYPE, res_type)
            backing = backing_class(resource_backing_config, pool_conn)
            self.backings[backing.uuid] = backing
            o["out"] = {"backing": backing.uuid}
            d = backing.sync_resource_info(pool_conn)
            if d:
                o["out"].update(d)
        except Exception as e:
            r, o["out"] = 1, str(e)

        return r, o

    def destroy_backing_object(self, backing_id):
        """
        Destroy the resource backing object.

        Note no need to check if the resource is released or not, because a
        resource can have one or several backings, the resource on the controller
        node can take care of this.
        """
        r, o = 0, dict()
        self.backings.pop(backing_id)
        return r, o

    def clone_resource_by_backing(self, backing_id, arguments):
        """
        Clone a new resource by the source resource's backing.
        """
        r, o = 0, dict()
        try:
            backing = self.backings[backing_id]
            source_backing = self.backings[arguments.pop("source")]
            pool_conn = self.pool_connections[backing.resource_pool_uuid]
            ret = backing.clone_resource(pool_conn, source_backing, arguments)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)

        return r, o

    def update_resource_by_backing(self, backing_id, command, arguments):
        """
        Update the resource by its backing object.
        """
        r, o = 0, dict()
        try:
            backing = self.backings[backing_id]
            pool_conn = self.pool_connections[backing.resource_pool_uuid]
            handler = backing.get_update_handler(command)
            ret = handler(pool_conn, arguments)
            if ret:
                o["out"] = ret
        except Exception as e:
            r, o["out"] = 1, str(e)

        return r, o


rb_mgr = _ResourceBackingManager()
