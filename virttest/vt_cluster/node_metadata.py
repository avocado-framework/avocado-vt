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
This module handles the collection and management of metadata from all nodes
in a virt test cluster. It provides functions to load metadata from nodes,
dump it to a file for persistence, and load it back from the file. This
allows other parts of the test framework to easily access node-specific
information like CPU model, hostname, and other hardware or software
configurations.
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
    except (IOError, ValueError):
        return {}


def load_metadata():
    """Load the metadata of the nodes."""
    if os.path.exists(cluster.metadata_file):
        os.remove(cluster.metadata_file)

    _meta = {}
    for node in cluster.get_all_nodes():
        _meta[node.name] = {}
        _meta[node.name]["hostname"] = node.hostname
        _meta[node.name]["address"] = node.address

        # FIXME: An example for loading the cpu's metadata
        _meta[node.name]["cpu_vendor_id"] = node.proxy.cpu.get_cpu_vendor_id()
        _meta[node.name]["cpu_model_name"] = node.proxy.cpu.get_cpu_model_name()

        # TODO: Load more others metadata of the nodes

    dump_metadata_file(_meta)


def unload_metadata():
    """Unload the metadata of the nodes"""
    try:
        os.remove(cluster.metadata_file)
    except OSError:
        pass
