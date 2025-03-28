"""
The virtual image(top-level) manager.

from virttest.vt_imgr import imgr

# Define the image configuration
image_config = imgr.define_logical_image_config(image_name, params)

# Create the top-level image object
image_id = imgr.create_logical_image_object(image_config)

# Create the top-level image
imgr.update_logical_image(image_id, {"create":{}})

# Create only one lower-level image
imgr.update_logical_image(image_id, {"create":{"target": "top"}})

# Destroy one lower-level image
imgr.update_logical_image(image_id, {"destroy":{"target": "top"}})

# Get the configuration of the top-level image
out = imgr.get_logical_image_info(image_id, request=None)
out:
{
   "meta": {
     "uuid": "uuid-sn"
     "name": "sn",
     "type": "qemu",
     "topology": {"type": "chain", "value": ["base", "sn"]}
   },
   "spec": {
     "images": {
       "base": {
         "meta": {},
         "spec": {
           "format": "raw",
           "volume": {"meta": {}, "spec": {}}}
       },
       "sn": {
         "meta": {},
         "spec": {
           "format": "qcow2",
           "volume": {"meta": {}, "spec": {}}}
         }
      }
  }
}

# Destroy the top-level image
imgr.update_logical_image(image_id, {"destroy":{}})

# Destroy the top-level image object
imgr.destroy_logical_image_object(image_id)
"""

import logging

from virttest.vt_cluster import cluster

from .logical_images import get_logical_image_class

LOG = logging.getLogger("avocado." + __name__)


class _LogicalImageManager(object):
    def __init__(self):
        self._images = dict()

    def startup(self):
        LOG.info(f"Start the image manager")

    def teardown(self):
        LOG.info(f"Stop the image manager")

    def define_logical_image_config(self, image_name, params):
        """
        Define the top-level image configuration by its cartesian params

        :param image_name: The image tag, defined by the param "images"
        :type image_name: string
        :param params: The params of the image_name, it contains all its
                       lower-level images' params.
                       Note it's NOT a lower-level image-specific params like
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
        :return: The image configuration
        :rtype: dict
        """
        image_params = params.object_params(image_name)
        # TODO: logical_image_type is a top-level image param
        image_type = image_params.get("logical_image_type", "qemu")
        image_class = get_logical_image_class(image_type)

        LOG.debug(f"Define the {image_type} logical image configuration for {image_name}")
        return image_class.define_config(image_name, params)

    def create_logical_image_object(self, image_config):
        """
        Create an top-level image object by its configuration without any
        storage allocation. All its lower-level images and their storage
        resource objects will be created.
        :param image_config: The image configuration, generated with function
                             define_logical_image_config
        :type image_config: dict
        :return: The image object id
        :rtype: string
        """
        LOG.debug(f"Create the logical image object for ${image_config['meta']['name']}")
        image_type = image_config["meta"]["type"]
        image_class = get_logical_image_class(image_type)
        image = image_class(image_config)
        image.create_object()
        self._images[image.image_id] = image

        return image.image_id

    def destroy_logical_image_object(self, image_id):
        """
        Destroy a specified image object.

        :param image_id: The image id
        :type image_id: string
        """
        LOG.debug(f"Destroy the logical image object {image_id}")
        image = self._images.pop(image_id)
        image.destroy_object()

    def clone_logical_image(self, image_id):
        """
        Clone the image

        :param image_id: The image id
        :type image_id: string
        :return: The cloned image uuid
        :rtype: string
        """
        LOG.debug(f"Clone the logical image object {image_id}")
        image = self._images.get(image_id)
        clone_image = image.clone()
        self._images[clone_image.image_id] = clone_image
        return clone_image.image_id

    def update_logical_image(self, image_id, config):
        """
        Update a specified top-level image

        config format:
          {command: arguments}

        Supported commands for a qemu image:
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
          compare: Comare two qemu images

        The arguments is a dict object which contains all related settings
        for a specific command
        :param image_id: The image id
        :type image_id: string
        """
        cmd, arguments = config.popitem()
        image = self._images.get(image_id)
        image_handler = image.get_image_handler(cmd)

        # nodes should be the node names defined in cluster.json
        node_tags = arguments.pop("nodes", list())
        node_names = [cluster.get_node_by_tag(tag).name for tag in node_tags]
        if node_names:
            arguments["nodes"] = node_names

        LOG.debug(f"Update the logical image object {image_id} with cmd {cmd}")
        return image_handler(arguments)

    def get_logical_image_info(self, image_id, request=None, verbose=False):
        """
        Get the configuration of a specified top-level image

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
        LOG.debug(
            f"Get the configuration of logical image {image_id} with request {request}"
        )
        image = self._images.get(image_id)
        config = image.get_info(verbose)

        if request is not None:
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config

    def query_logical_image(self, image_name, vm_name=None):
        """
        Get the logical image object id

        Note: The partition id is not required because only one
        partition is created when running a test case

        :param image_name: The image name defined in 'images'
        :type image_name: string
        :param vm_name: The vm name defined in 'vms', if it's specified,
                        it means the image is used by the vm
        :type vm_name: string
        :return: The image object id
        :rtype: string
        """
        LOG.debug(
            f"Get the logical image object id of {image_name} owned by {vm_name}"
        )
        for image_id, image in self._images.items():
            if image_name == image.image_name:
                if vm_name:
                    if image.is_owned_by(vm_name):
                        return image_id
                else:
                    return image_id
        return None


imgr = _LogicalImageManager()
