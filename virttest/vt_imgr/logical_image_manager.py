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

    def _get_logical_image_access_node(self, image_id, node_tag=None):
        image = self._images.get(image_id)
        if node_tag:
            node = cluster.get_node_by_tag(node_tag)
            if not node:
                raise ValueError(f"Cannot get the node object with {node_tag}")
            if node.name not in image.node_affinity:
                raise ValueError(f"Cannot access {image.name} from node {node_tag}")
        else:
            node = cluster.get_node_by_tag(image.node_affinity[0])
        return node

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
        Create a logical image object by its cartesian params.
        All its layer image objects will be created;
        All the layer images' volume objects will be created;
        All the volumes' backing objects will be created;
        The storage will not be allocated;

        :param image_name: The image name, defined by the param "images"
        :type image_name: string
        :param params: The params of the image_name.
                       Note it should contain all its layer images'
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
        image.create_layer_images()
        self._images[image.uuid] = image
        return image.uuid

    def destroy_logical_image(self, image_id):
        """
        Destroy a specified logical image object.
        The logical image object will be destroyed only after calling the destroy
        command: update_logical_image(image_id, "destroy").

        :param image_id: The logical image object uuid
        :type image_id: string
        """
        image = self._images.pop(image_id)

        LOG.info(f"Destroy the logical image object of {image.name}")
        image.destroy_layer_images()

    def set_logical_image_node_affinity(self, image_id, node_names=None):
        """
        Set the specified worker nodes where the logical image can be handled.
        When creating a logical image, the users should always know where to
        handle it, e.g. in a live migration test, there should be at least two
        worker nodes where the logical image can be handled.

        :param image_id: The logical image object uuid.
        :type image_id: string
        :param node_names: The node names defined in the param 'nodes', if it's
                           not set, for the volume of each layer image, set its
                           backing nodes to the ones both in the partition and
                           in the volume pool's accessible nodes. For the logical
                           image, the nodes should be the intersection of all its
                           layer images' volume backing nodes.
        :type node_names: list
        """
        image = self._images.get(image_id)

        LOG.info(f"Set the logical image node affinity: {node_names}")
        image.set_node_affinity(node_names)

    def unset_logical_image_node_affinity(self, image_id, node_names=None):
        """
        Unset the specified worker nodes where the logical image can be handled.

        :param image_id: The logical image object uuid.
        :type image_id: string
        :param node_names: The node names defined in the param 'nodes', if it's
                           not set, for the volume of each layer image, unset
                           all of its backing nodes.
        :type node_names: list
        """
        image = self._images.get(image_id)

        LOG.info(f"Unset the logical image node affinity: {node_names}")
        image.unset_node_affinity(node_names)

    def clone_logical_image(self, source_image_id, arguments=None):
        """
        Clone the logical image from an existing one.
        The cloned logical image has the same topology, the storage is allocated
        from the same storage, the data of the image should also be the same.

        :param source_image_id: The source logical image object uuid.
        :type source_image_id: string
        :param arguments: The arguments of the clone on how to clone the image.
                          The supported arguments for all commands:
                  'node': The node name, defined in 'nodes', i.e. the clone
                          will be run on the node. If it's not set, choose the
                          first node in its affinity node list.

        :type arguments: dict
        :return: The cloned logical image object uuid
        :rtype: string
        """
        arguments = dict() if not arguments else arguments
        node_tag = arguments.pop("node", None)
        node = self._get_logical_image_access_node(source_image_id, node_tag)
        source_image = self._images.get(source_image_id)

        LOG.info(f"Clone the logical image based on {source_image.name}")
        clone_image = source_image.clone(arguments, node)
        self._images[clone_image.uuid] = clone_image
        return clone_image.uuid

    def update_logical_image(self, source_image_id, command, arguments=None):
        """
        Update a specified logical image.

        :param source_image_id: The logical image object uuid.
        :type source_image_id: string
        :param command: The command name.
                        The supported commands for all kinds of logical images:
                create: Create the image:
                        The layer images' storage will be allocated;
                        The layer images will be created;
                        The layer images' hierarchy will be created;
               destroy: Destroy the image:
                        The storage will be released;
                        The layer images will be destroyed;
                        The layer image objects will not be destroyed;
                backup: Backup the image data.
               restore: Restore the image data.

                        The supported commands for the qemu logical images:
                rebase: qemu-img rebase
                  info: qemu-img info
                 check: qemu-img check
                   add: Add a layer image object
                delete: Delete a layer image object
        :param arguments: A specific command's arguments.
                          The supported arguments for all commands:
                  'node': The node name, defined in 'nodes', i.e. the command
                          will be run on the node. If it's not set, choose the
                          first node where all its layer images can be accessed.
        :type arguments: dict
        """
        arguments = dict() if not arguments else arguments
        node_tag = arguments.pop("node", None)
        node = self._get_logical_image_access_node(source_image_id, node_tag)
        image = self._images.get(source_image_id)
        LOG.info(
            f"Update the logical image {image.name} with: cmd={command}, args={arguments}"
        )
        image_handler = image.get_image_handler(command)
        return image_handler(arguments, node)

    def get_logical_image_info(self, image_id, request=None):
        """
        Get the configuration of a specified logical image.

        :param image_id: The logical image object uuid.
        :type image_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Examples:
                          1. Get the image's configuration
                            request=None
                          2. Get the layer images' configurations
                            request=spec.images
                          3. Get the layer image base's volume uuid
                            request=spec.images.base.spec.volume
        :type request: string
        :return: The configuration
        :rtype: dict
        """
        image = self._images.get(image_id)

        LOG.info(
            f"Get the configuration of the logical image {image.name}: request={request}"
        )
        return image.get_info(request)

    def query_logical_image(self, image_name, vm_name=None):
        """
        Get the logical image object uuid.

        Note: The partition id is not required because only one
        partition is created when running a specific test case

        :param image_name: The image name defined in the cartesian param 'images'
        :type image_name: string
        :param vm_name: The vm name defined in cartesian param 'vms', e.g.
                          vms = vm1 vm2
                          images = image1
                        for both vm1 and vm2, the logical image name should be
                        the same, so the vm name is required to query the image.
        :type vm_name: string
        :return: The logical image object uuid
        :rtype: string
        """
        LOG.info(f"Get the logical image uuid with: name={image_name}, vm={vm_name}")
        for image_id, image in self._images.items():
            if image_name == image.name:
                if vm_name:
                    if image.is_owned_by(vm_name):
                        return image_id
                else:
                    return image_id
        return None


imgr = _LogicalImageManager()
