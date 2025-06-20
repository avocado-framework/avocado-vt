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
Cluster management interface for virtualization testing.

This module provides a comprehensive framework for managing cluster nodes
in virtualization testing environments. It handles node registration, partition
management, and cluster state persistence to support distributed virtualization
test scenarios.

Key Components:
    - ClusterError: Base exception for cluster-related operations
    - _Partition: Logical grouping of nodes and resource pools
    - _Cluster: Main cluster management class with state persistence
    - cluster: Global cluster instance for application use

The cluster state is automatically persisted to disk and restored on
initialization, enabling consistent cluster management across test runs.
"""

import logging
import os
import pickle
import uuid

from virttest import data_dir

LOG = logging.getLogger("avocado." + __name__)


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
        :raises ValueError: If the node is not in this partition
        """
        if node not in self._nodes:
            raise ValueError(f"Node {node} is not in this partition")
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

    This class handles the state of the cluster, including its nodes, and
    partitions. It persists this state to a file.
    """

    def __init__(self):
        self._filename = os.path.join(data_dir.get_base_backend_dir(), "cluster_env")
        self._empty_data = {
            "partitions": [],
            "nodes": {},
        }
        try:
            if os.path.isfile(self._filename):
                self._data = self._load()
            else:
                self._data = self._empty_data.copy()
        except Exception as e:
            LOG.warning(
                f"Failed to load cluster state: {e}. Starting with empty state."
            )
            self._data = self._empty_data.copy()

    def _save(self):
        """
        Persist the current cluster state to disk using pickle serialization.
        """
        with open(self._filename, "wb") as f:
            pickle.dump(self._data, f, protocol=0)

    def _load(self):
        """
        Load cluster state from the persistent storage file.

        :return: The deserialized cluster data dictionary containing
                 partitions and nodes.
        :rtype: dict
        """
        with open(self._filename, "rb") as f:
            return pickle.load(f)

    @property
    def idle_nodes(self):
        """
        Get all nodes that are not currently assigned to any partition.

        Idle nodes are available for assignment to new partitions or
        for other cluster operations.

        :return: A list of unassigned node objects.
        :rtype: list[virttest.vt_cluster.node.Node]
        """
        assigned_nodes = set()
        for partition in self._data["partitions"]:
            assigned_nodes.update(partition.nodes)

        return [
            node for node in self._data["nodes"].values() if node not in assigned_nodes
        ]

    @property
    def partitions(self):
        """
        Get all partitions currently defined in the cluster.

        :return: A list of all partition objects in the cluster.
        :rtype: list[_Partition]
        """
        return self._data["partitions"]

    @property
    def metadata_file(self):
        """
        Get the path to the cluster metadata JSON file.

        :return: The full path to the metadata file.
        :rtype: str
        """
        return os.path.join(data_dir.get_base_backend_dir(), "cluster_metadata.json")

    def cleanup_env(self):
        """
        Reset the cluster to its initial empty state.

        This method clears all partitions and nodes from memory and
        removes the persistent storage file if it exists. Use this to
        completely reset the cluster environment.
        """
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

        Also removes the node from any partitions it belongs to.
        If the node is not found, a warning is logged.

        :param name: The name of the node to unregister.
        :type name: str
        """
        if name in self._data["nodes"]:
            node = self._data["nodes"][name]

            for partition in self._data["partitions"]:
                if node in partition.nodes:
                    partition.del_node(node)

            del self._data["nodes"][name]
            self._save()
        else:
            LOG.warning(f"Attempted to unregister non-existent node: {name}")

    def get_node_by_tag(self, tag):
        """
        Get a node from the cluster by its assigned tag.

        :param tag: The tag of the node to retrieve.
        :type tag: str
        :return: The node object if found, otherwise None.
        :rtype: virttest.vt_cluster.node.Node | None
        """
        for node in self.get_all_nodes():
            if node.tag == tag:
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
        return list(self._data["nodes"].values())

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

    def remove_partition(self, partition):
        """
        Remove a partition from the cluster.

        :param partition: The partition object to remove.
        :type partition: _Partition
        """
        if partition not in self._data["partitions"]:
            partition_uuid = partition.uuid if hasattr(partition, "uuid") else "unknown"
            LOG.warning(f"Attempted to remove non-existent partition: {partition_uuid}")
            return

        try:
            nodes_to_remove = list(partition.nodes)
            for node in nodes_to_remove:
                partition.del_node(node)

            self._data["partitions"].remove(partition)
            self._save()
        except Exception as e:
            LOG.error(f"Failed to remove partition {partition.uuid}: {e}")
            raise ClusterError(f"Failed to remove partition: {e}")


cluster = _Cluster()
