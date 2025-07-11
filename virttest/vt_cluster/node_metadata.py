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
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Module for providing the interface of cluster for virt test.
"""

import json
import logging
import os

from . import cluster

LOG = logging.getLogger("avocado." + __name__)


def dump_metadata_file(nodes_metadata):
    """Dump the metadata into the file."""
    with open(cluster.metadata_file, "w") as metadata_file:
        json.dump(nodes_metadata, metadata_file)


def load_metadata_file():
    """Load the metadata from the file."""
    try:
        with open(cluster.metadata_file, "r") as metadata_file:
            return json.load(metadata_file)
    except Exception:
        return {}


def load_metadata():
    """Load the metadata of the nodes."""
    if os.path.exists(cluster.metadata_file):
        os.remove(cluster.metadata_file)

    _meta = {}
    for node in cluster.get_all_nodes():
        LOG.debug(f"{node}: Loading the node metadata")
        _meta[node.name] = {}
        _meta[node.name]["hostname"] = node.hostname
        _meta[node.name]["address"] = node.address

        # just an example for getting the metadata
        _meta[node.name]["cpu_vendor_id"] = node.proxy.unittest.cpu.get_vendor_id()

    dump_metadata_file(_meta)


def unload_metadata():
    """Unload the metadata of the nodes"""
    try:
        os.remove(cluster.metadata_file)
    except OSError:
        pass
