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
Node properties management for virt test clusters.

This module provides functionality to collect, save, and manage metadata from all
nodes in a virt test cluster. It handles the persistence of node-specific information
including hostname, CPU vendor ID, CPU model name, and other hardware or software
configurations.

The module offers three main operations:
- save_properties(): Collects and saves node metadata to a JSON file
- load_properties(): Loads previously saved node metadata from file
- remove_properties(): Removes the metadata file

The metadata is stored in JSON format and can be used by other parts of the test
framework to make decisions based on node capabilities and characteristics.
"""

import json
import logging
import os

from . import cluster

LOG = logging.getLogger("avocado." + __name__)


def save_properties():
    """Save node properties to the metadata file."""
    if os.path.exists(cluster.metadata_file):
        os.remove(cluster.metadata_file)

    props = {}
    for node in cluster.get_all_nodes():
        props[node.name] = {}
        props[node.name]["hostname"] = node.proxy.host.platform.get_hostname()
        props[node.name]["cpu_vendor_id"] = node.proxy.host.cpu.get_cpu_vendor_id()
        props[node.name]["cpu_model_name"] = node.proxy.host.cpu.get_cpu_model_name()
        # TODO: Support more other properties of the nodes

    with open(cluster.metadata_file, "w") as metadata_file:
        json.dump(props, metadata_file)


def load_properties():
    """
    Load node properties from the metadata file.

    :return: Dictionary containing node properties, or empty dict if file doesn't exist
    :rtype: dict
    """
    if not os.path.exists(cluster.metadata_file):
        LOG.warning(f"Metadata file {cluster.metadata_file} does not exist")
        return {}

    try:
        with open(cluster.metadata_file, "r") as metadata_file:
            props = json.load(metadata_file)
            return props
    except json.JSONDecodeError as e:
        LOG.error(f"Failed to parse metadata file {cluster.metadata_file}: {e}")
        return {}
    except Exception as e:
        LOG.error(f"Failed to load properties from {cluster.metadata_file}: {e}")
        return {}


def remove_properties():
    """Remove the metadata file."""
    try:
        os.remove(cluster.metadata_file)
    except OSError as e:
        LOG.warning(f"Could not remove metadata file {cluster.metadata_file}: {e}")
