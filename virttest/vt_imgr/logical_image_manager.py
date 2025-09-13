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
    def __init__(self):
        self._images = dict()

    def startup(self):
        # TODO: Leave it empty for future extension
        pass

    def teardown(self):
        # TODO: Leave it empty for future extension
        pass

    def define_logical_image_config(self, image_name, params):
        """
        Define the logical image configuration by its cartesian params.

        :param image_name: The image name, defined by the param "images"
        :type image_name: string
        :param params: The params of the image_name, it should contain
                       all its lower-level images' params.
                       Note it's NOT a image-specific params like
                         params.object_params("sn")
                       Examples:
                       1. images_vm1 = "image1 sn"
                          image_chain_sn = "base sn"
                          image_name = "sn"
                          params = the_test_case_params.object_params('vm1')
                       2. images = "image1 stg"
                          image_name = "image1"
                          params = the_test_case_params
        :type params: Params
        :return: The logical image configuration
        :rtype: dict
        """
        image_params = params.object_params(image_name)
        image_type = image_params.get("image_type", "qemu")
        image_class = get_logical_image_class(image_type)

        LOG.debug(f"Define the logical image configuration of {image_name}")
        return image_class.define_config(image_name, params)

    def create_logical_image_object(self, image_config):
        """
        Create a top-level image object by its configuration without any
        storage allocation. All its lower-level images and their storage
        resource objects will be created.
        :param image_config: The image configuration, generated with function
                             define_logical_image_config
        :type image_config: dict
        :return: The logical image object uuid
        :rtype: string
        """
        LOG.debug(f"Create the logical image object of {image_config['meta']['name']}")
        image_type = image_config["meta"]["type"]
        image_class = get_logical_image_class(image_type)
        image = image_class(image_config)
        image.create_object()
        self._images[image.image_id] = image
        return image.image_id

    def destroy_logical_image_object(self, image_id):
        """
        Destroy a specified image object.

        :param image_id: The logical image object uuid
        :type image_id: string
        """
        image = self._images.pop(image_id)

        LOG.debug(f"Destroy the logical image object of {image.image_name}")
        image.destroy_object()

    def clone_logical_image(self, image_id):
        """
        Clone the logical image from an existing one.
        The cloned image has the same topology, the storage is allocated from the
        same storage pool too, the data of the image should also be copied.

        :param image_id: The logical image object uuid
        :type image_id: string
        :return: The cloned logical image object uuid
        :rtype: string
        """
        image = self._images.get(image_id)

        LOG.debug(f"Clone the logical image from {image.image_name}")
        clone_image = image.clone()
        self._images[clone_image.image_id] = clone_image
        return clone_image.image_id

    def update_logical_image(self, image_id, config):
        """
        Update a specified logical image object.

        :param image_id: The logical image object uuid
        :type image_id: string
        :param config: The command and its arguments: {command: arguments}
                       Supported commands for a qemu logical image object:
                         create: Create the image
                         destroy: Destroy the image
                         backup: Backup the data
                         restore: Restore the data
                         resize: qemu-img resize
                         map: qemu-img map
                         convert: qemu-img convert
                         commit: qemu-img commit
                         snapshot: qemu-img snapshot
                         rebase: qemu-img rebase
                         info: qemu-img info
                         check: qemu-img check
                         add: Add a lower-level image object
                         delete: Delete a lower-level image object
                         compare: Compare two qemu images
                      The arguments is a dict which contains all related
                      settings for a specific command
        :type config: dict
        """
        cmd, arguments = config.popitem()
        image = self._images.get(image_id)
        image_handler = image.get_image_handler(cmd)

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

        LOG.debug(f"Update the logical image {image.image_name}: cmd={cmd}, args={arguments}")
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
                          3. Get sn's volume configuration
                            request=spec.images.sn.spec.volume
        :type request: string
        :param verbose: True to print the volumes' configuration, while
                        False to print the volume's uuid
        :type verbose: boolean
        :return: The configuration
        :rtype: dict
        """
        image = self._images.get(image_id)

        LOG.debug(f"Get the configuration of the logical image {image.image_name}: request={request}")
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
        LOG.debug(f"Get the logical image object id: name={image_name}, owner={owner}")
        for image_id, image in self._images.items():
            if image_name == image.image_name:
                if owner:
                    if image.is_owned_by(owner):
                        return image_id
                else:
                    return image_id
        return None


imgr = _LogicalImageManager()
