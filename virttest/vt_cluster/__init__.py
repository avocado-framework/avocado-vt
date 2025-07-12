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

"""
Module for providing the interface of cluster for virt test.
"""

import os
import pickle
import uuid

from virttest import data_dir


class ClusterError(Exception):
    """Base exception for cluster-related errors."""

    pass


class _Partition(object):
    """
    Represents a partition within the cluster.

    A partition is a logical grouping of nodes and their associated resource pools.
    It is identified by a unique UUID.
    """

    def __init__(self):
        self._uuid = uuid.uuid4().hex
        self._pools = dict()
        self._nodes = set()

    @property
    def pools(self):
        """
        Get the resource pools associated with this partition.

        :return: A dictionary of resource pools.
        :rtype: dict
        """
        return self._pools

    @property
    def uuid(self):
        """
        Get the unique identifier (UUID) of this partition.

        :return: The UUID string.
        :rtype: str
        """
        return self._uuid

    def add_node(self, node):
        """
        Add a node to this partition.

        :param node: The node object to add.
        :type node: virttest.vt_cluster.node.Node
        """
        self._nodes.add(node)

    def del_node(self, node):
        """
        Remove a node from this partition.

        :param node: The node object to remove.
        :type node: virttest.vt_cluster.node.Node
        """
        self._nodes.remove(node)

    @property
    def nodes(self):
        """
        Get the set of nodes belonging to this partition.

        :return: A set of node objects.
        :rtype: set[virttest.vt_cluster.node.Node]
        """
        return self._nodes


class _Cluster(object):
    """
    Manages the overall cluster environment.

    This class handles the state of the cluster, including its nodes,
    partitions, and logger configuration. It persists this state to a file.
    """

    def __init__(self):
        self._filename = os.path.join(data_dir.get_base_backend_dir(), "cluster_env")
        self._empty_data = {
            "logger_server_host": "",
            "logger_server_port": 0,
            "partitions": [],
            "nodes": {},
        }
        if os.path.isfile(self._filename):
            self._data = self._load()
        else:
            self._data = self._empty_data

    def _save(self):
        with open(self._filename, "wb") as f:
            pickle.dump(self._data, f, protocol=0)

    def _load(self):
        with open(self._filename, "rb") as f:
            return pickle.load(f)

    def cleanup_env(self):
        self._data = self._empty_data
        if os.path.isfile(self._filename):
            os.unlink(self._filename)

    def register_node(self, name, node):
        """
        Register a node with the cluster.

        :param name: A unique name or identifier for the node.
        :type name: str
        :param node: The node object to register.
        :type node: virttest.vt_cluster.node.Node
        """
        self._data["nodes"][name] = node
        self._save()

    def unregister_node(self, name):
        """
        Unregister a node from the cluster by its name.

        If the node is not found, a warning is logged.

        :param name: The name of the node to unregister.
        :type name: str
        """
        if name in self._data["nodes"]:
            del self._data["nodes"][name]
            self._save()

    def get_node_by_tag(self, name):
        """
        Get a node from the cluster by its assigned tag.

        :param name: The tag of the node to retrieve.
        :type name: str
        :return: The node object if found, otherwise None.
        :rtype: virttest.vt_cluster.node.Node | None
        """
        for node in self.get_all_nodes():
            if node.tag == name:
                return node
        return None

    def get_node(self, name):
        """
        Get a node from the cluster by its registration name.

        :param name: The registration name of the node.
        :type name: str
        :return: The node object if found, otherwise None.
        :rtype: virttest.vt_cluster.node.Node | None
        """
        return self._data["nodes"].get(name)

    def get_all_nodes(self):
        """
        Get a list of all currently registered nodes in the cluster.

        :return: A list of node objects.
        :rtype: list[virttest.vt_cluster.node.Node]
        """
        return [_ for _ in self._data["nodes"].values()]

    def assign_logger_server_host(self, host="localhost"):
        """
        Set the hostname or IP address for the master logger server.

        :param host: The hostname or IP address. Defaults to "localhost".
        :type host: str
        """
        self._data["logger_server_host"] = host
        self._save()

    @property
    def logger_server_host(self):
        """
        Get the currently configured logger server host.

        :return: The logger server hostname or IP address.
        :rtype: str
        """
        return self._data["logger_server_host"]

    def assign_logger_server_port(self, port=9999):
        """
        Set the port number for the master logger server.

        :param port: The port number. Defaults to 9999.
        :type port: int
        """
        self._data["logger_server_port"] = port
        self._save()

    @property
    def logger_server_port(self):
        """
        Get the currently configured logger server port.

        :return: The logger server port number.
        :rtype: int
        """
        return self._data["logger_server_port"]

    @property
    def metadata_file(self):
        """
        Get the path to the cluster metadata JSON file.

        :return: The full path to the metadata file.
        :rtype: str
        """
        return os.path.join(data_dir.get_base_backend_dir(), "cluster_metadata.json")

    def create_partition(self):
        """
        Create a new, empty partition within the cluster.

        :return: The newly created partition object.
        :rtype: _Partition
        """
        partition = _Partition()
        self._data["partitions"].append(partition)
        self._save()
        return partition

    def clear_partition(self, partition):
        """
        Remove a partition from the cluster.

        If the specified partition is not found, a warning is logged.

        :param partition: The partition object to remove.
        :type partition: _Partition
        """
        try:
            self._data["partitions"].remove(partition)
            self._save()
        except ValueError:
            pass

    @property
    def free_nodes(self):
        nodes = set(self.get_all_nodes()[:])
        for partition in self._data["partitions"]:
            nodes = nodes - partition.nodes
        return list(nodes)

    @property
    def partition(self):
        """
        When the job starts a new process to run a case, the cluster object
        will be re-constructed as a new one, it reads the dumped file to get
        back all the information. Note the cluster here is a 'slice' because
        this object only serves the current test case, when the process(test
        case) is finished, the slice cluster is gone. So there is only one
        partition object added in self._data["partition"]
        """
        return self._data["partitions"][0]


cluster = _Cluster()
