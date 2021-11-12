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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Module for providing the interface of cluster for virt test.
"""

import os
import pickle

from virttest import data_dir


class ClusterError(Exception):
    """The generic cluster error."""
    pass


class _Partition(object):
    """The representation of the partition of the cluster."""

    def __init__(self):
        self._nodes = set()

    def add_node(self, node):
        """
        Add the node into the partition.

        :param node: The node to be added.
        :type node: vt_cluster.node.Node
        """
        self._nodes.add(node)

    def del_node(self, node):
        """
        delete the node from the partition.

        :param node: The node to be deleted.
        :type node: vt_cluster.node.Node
        """
        self._nodes.remove(node)

    @property
    def nodes(self):
        return self._nodes


class _Cluster(object):
    """The representation of the cluster."""

    def __init__(self):
        self._filename = os.path.join(data_dir.get_base_backend_dir(),
                                      "cluster_env")
        if os.path.isfile(self._filename):
            data = self._data()
            self._logger_server_host = data.get("_logger_server_host")
            self._logger_server_port = data.get("_logger_server_port")
            self._partitions = data.get("_partitions")
            self._nodes = data.get("_nodes")
        else:
            self._logger_server_host = "localhost"
            self._logger_server_port = 9999
            self._partitions = []
            self._nodes = {}

    def _save(self):
        _data = {"data": self.__dict__}
        with open(self._filename, "wb") as f:
            pickle.dump(_data, f)

    def _data(self):
        with open(self._filename, "rb") as f:
            return pickle.load(f).get("data", {})

    def register_node(self, name, node):
        """
        Register the node into the cluster.

        :param name: the node name
        :type name: str
        :param node: the node object
        :type node: vt_node.Node
        """
        self._nodes[name] = node
        self._save()

    def unregister_node(self, name):
        """
        Unregister the node from the cluster.

        :param name: the node name
        """
        del self._nodes[name]
        self._save()

    def get_node(self, name):
        """
        Get the node from the cluster.

        :param name: the node name
        :type name: str
        :return: the node object
        :rtype: vt_node.Node
        """
        return self._nodes.get(name)

    def get_all_nodes(self):
        """
        Get the all nodes.

        :return: the list of all nodes
        :rtype: list
        """
        return [_ for _ in self._nodes.values()]

    def assign_logger_server_host(self, host="localhost"):
        """
        Assign the host for the master logger server.

        :param host: The host of server.
        :type host: str
        """
        self._logger_server_host = host
        self._save()

    @property
    def logger_server_host(self):
        return self._logger_server_host

    def assign_logger_server_port(self, port=9999):
        """
        Assign the port for the master logger server.

        :param port: The port of server.
        :type port: int
        """
        self._logger_server_port = port
        self._save()

    @property
    def logger_server_port(self):
        return self._logger_server_port

    @property
    def metadata_file(self):
        return os.path.join(
                data_dir.get_base_backend_dir(), "cluster_metadata.json")

    def create_partition(self):
        """
        Create a partition for the cluster.

        :return: The partition obj
        :rtype: _Partition
        """
        partition = _Partition()
        self._partitions.append(partition)
        self._save()
        return partition

    def clear_partition(self, partition):
        """
        Clear a partition from the cluster.

        :param partition: The partition to be cleared
        :type partition: _Partition
        """
        self._partitions.remove(partition)
        self._save()

    @property
    def free_nodes(self):
        nodes = set(self.get_all_nodes()[:])
        for partition in self._partitions:
            nodes = nodes - partition.nodes
        return list(nodes)


cluster = _Cluster()
