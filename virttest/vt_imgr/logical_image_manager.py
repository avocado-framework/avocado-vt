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

from virttest.vt_cluster import cluster

from .logical_images import get_logical_image_class

LOG = logging.getLogger("avocado." + __name__)


class _LogicalImageManager(object):
    """
    The LogicalImageManager coordinates complex image topologies where images can have
    multiple layers (base images, snapshots) and manages their underlying storage
    resources through the unified resource management system. It provides high-level
    operations for image lifecycle management while delegating storage allocation to
    the resource manager.

    Key Responsibilities:
        Image Hierarchy: Managing relationships between images
        Storage Coordination: Interfacing with the resource manager for volume allocation
        Lifecycle Operations: Creating, cloning, updating, and destroying image objects

    Architecture Integration:
        LogicalImageManager → LogicalImage objects → Image objects -> Volume resources → backings
    """

    def __init__(self):
        self._images = dict()

    def startup(self):
        # TODO: Leave it empty for future extension
        pass

    def teardown(self):
        # TODO: Leave it empty for future extension
        pass

    def _define_logical_image_config(self, image_name, params):
        """
        Define the logical image configuration by its cartesian params.
        """
        image_params = params.object_params(image_name)
        image_type = image_params.get("image_type", "qemu")
        image_class = get_logical_image_class(image_type)
        return image_class.define_config(image_name, params)

    def create_logical_image_from_params(self, image_name, params):
        """
        Create a logical(upper-level) image object by its cartesian params.
        All its lower-level image objects will be created;
        All the lower-level images' volume objects will be created;
        All the volumes' backing objects will be created;
        The storage will not be allocated;

        :param image_name: The image name, defined by the param "images"
        :type image_name: string
        :param params: The params of the image_name.
                       Note it should contain all its lower-level images'
                       params instead of an image-specific params like:
                         params.object_params("snapshot")
                       Examples:
                       1. images_vm1 = "image1 snapshot"
                          image_chain_snapshot = "base snapshot"
                          image_name = "snapshot"
                          params = the_test_case_params.object_params('vm1')
                       2. images = "image1 stg"
                          image_name = "image1"
                          params = the_test_case_params
        :type params: Params
        :return: The logical image object uuid
        :rtype: string
        """
        LOG.info(f"Create the logical image object of {image_name}")
        image_config = self._define_logical_image_config(image_name, params)
        image_type = image_config["meta"]["type"]
        image_class = get_logical_image_class(image_type)
        image = image_class(image_config)
        image.create_object()
        self._images[image.image_id] = image
        return image.image_id

    def destroy_logical_image(self, image_id):
        """
        Destroy a specified logical image object.

        :param image_id: The logical image object uuid
        :type image_id: string
        """
        image = self._images.pop(image_id)

        LOG.info(f"Destroy the logical image object of {image.image_name}")
        image.destroy_object()

    def clone_logical_image(self, source_image_id, arguments=None):
        """
        Clone the logical image from an existing one.
        The cloned image has the same topology, the storage is allocated from the
        same storage pool too, the data of the image should also be the same.

        :param source_image_id: The source logical image object uuid
        :type source_image_id: string
        :param arguments: The arguments of the clone
        :type arguments: dict
        :return: The cloned logical image object uuid
        :rtype: string
        """
        image = self._images.get(source_image_id)

        LOG.info(f"Clone the logical image from {image.image_name}")
        clone_image = image.clone(arguments)
        self._images[clone_image.image_id] = clone_image
        return clone_image.image_id

    def update_logical_image(self, image_id, command, arguments=None):
        """
        Update a specified logical image object.

        :param image_id: The logical image object uuid
        :type image_id: string
        :param command: The command name.
                        The supported commands for all kinds of logical images:
                create: Create the image
               destroy: Destroy the image
                backup: Backup the data
               restore: Restore the data
                resize: qemu-img resize

                        The supported commands for the qemu logical images:
                rebase: qemu-img rebase
                  info: qemu-img info
                 check: qemu-img check
                   add: Add a lower-level image object
                delete: Delete a lower-level image object
        :param arguments: A specific command's arguments.
        :type arguments: dict
        """
        image = self._images.get(image_id)
        image_handler = image.get_image_handler(command)

        # "nodes" should be the names defined in the cartesian param "nodes"
        node_tags = arguments.pop("nodes", list())
        node_names = list()
        for tag in node_tags:
            name = cluster.get_node_by_tag(tag)
            if name:
                node_names.append(name)
            else:
                raise ValueError(f"Failed to get node name for node {tag}")

        if node_names:
            arguments["nodes"] = node_names

        LOG.info(
            f"Update the logical image {image.image_name}: cmd={command}, args={arguments}"
        )
        return image_handler(arguments)

    def get_logical_image_info(self, image_id, request=None, verbose=False):
        """
        Get the configuration of a specified top-level image

        :param image_id: The logical image object uuid
        :type image_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.images.<image_name>[.meta[.<key>]]]
                          spec[.images.<image_name>[.spec[.<key>]]]
                        Examples:
                          1. Get the image's configuration
                            request=None
                          2. Get the lower-level images' configurations
                            request=spec.images
                          3. Get base's volume configuration
                            request=spec.images.base.spec.volume
        :type request: string
        :param verbose: True to print the volumes' configuration, while
                        False to print the volume's uuid
        :type verbose: boolean
        :return: The configuration
        :rtype: dict
        """
        image = self._images.get(image_id)

        LOG.info(
            f"Get the configuration of the logical image {image.image_name}: request={request}"
        )
        return image.get_info(request, verbose)

    def query_logical_image(self, image_name, owner=None):
        """
        Get the logical image object id

        Note: The partition id is not required because only one
        partition is created when running a test case

        :param image_name: The image name defined in 'images'
        :type image_name: string
        :param owner: The owner could be a vm name defined in param 'vms',
                      i.e. the image is used by the vm
        :type owner: string
        :return: The logical image object uuid
        :rtype: string
        """
        LOG.info(f"Get the logical image object uuid: name={image_name}, owner={owner}")
        for image_id, image in self._images.items():
            if image_name == image.image_name:
                if owner:
                    if image.is_owned_by(owner):
                        return image_id
                else:
                    return image_id
        return None


imgr = _LogicalImageManager()
