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

from abc import ABC, abstractmethod


class ResourcePoolConnection(ABC):
    """
    Abstract base class for managing resource pool connections from worker nodes.

    This class defines the interface for establishing and maintaining connections
    between worker nodes and resource pools. Each pool type requires a specific
    connection mechanism - for example, NFS pools require mounting the NFS share.

    The connection lifecycle is managed by the ResourceBackingManager and follows
    the pattern: initialize → open → maintain → close. Implementations must be
    idempotent and handle connection state transitions gracefully.

    Attributes:
        POOL_TYPE (str): Unique identifier for the pool type this connection handles
        _pool_id (str): UUID of the pool this connection manages

    Abstract Methods:
        open(): Establish the physical connection to the pool
        close(): Terminate the connection and cleanup resources
        connected: Property indicating current connection status
    """

    POOL_TYPE = None

    def __init__(self, pool_config):
        self._pool_id = pool_config["meta"]["uuid"]
        self._pool_config = pool_config

    @property
    def pool_config(self):
        return self._pool_config

    @abstractmethod
    def open(self):
        """
        Open the connection to the pool from a worker node
        """
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """
        Close the connection to the pool from a worker node
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def connected(self):
        """
        Check if the pool is connected to a worker node
        """
        raise NotImplementedError
