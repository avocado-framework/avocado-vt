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
    Manage the pool connection from a worker node.
    The way to connect a pool to a worker node depends on the type of the
    pool, e.g. a nfs pool is connected to a worker node by mounting the nfs.
    """
    POOL_TYPE = None

    def __init__(self, pool_config):
        self._pool_id = pool_config["meta"]["uuid"]

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
