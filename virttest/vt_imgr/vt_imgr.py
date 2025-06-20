"""
The upper-level image manager.

from virttest.vt_imgr import vt_imgr

# Define the image configuration
image_config = vt_imgr.define_image_config(image_name, params)

# Create the upper-level image object
image_id = vt_imgr.create_image_object(image_config)

# Create the upper-level image
vt_imgr.handle_image(image_id, {"create":{}})

# Create only one lower-level image
vt_imgr.handle_image(image_id, {"create":{"target": "top"}})

# Destroy one lower-level image
vt_imgr.handle_image(image_id, {"destroy":{"target": "top"}})

# Get the configuration of the upper-level image
out = vt_imgr.get_image_info(image_id, request=None)
out:
{
   "meta": {
     "uuid": "uuid-sn"
     "name": "sn",
     "type": "qemu",
     "topology": {"chain": ["base", "sn"]}
   },
   "spec": {
     "virt-images": {
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

# Destroy the upper-level image
vt_imgr.handle_image(image_id, {"destroy":{}})

# Destroy the upper-level image object
vt_imgr.destroy_image_object(image_id)
"""

import logging

from virttest.vt_cluster import cluster

from .images import get_image_class

LOG = logging.getLogger("avocado." + __name__)


class _VTImageManager(object):
    def __init__(self):
        self._images = dict()

    def startup(self):
        LOG.info(f"Start the image manager")

    def teardown(self):
        LOG.info(f"Stop the image manager")

    def define_image_config(self, image_name, params):
        """
        Define the upper-level image(e.g. in the context of a VM, it's
        mapping to a VM's disk) configuration by its cartesian params.
        E.g. An upper-level qemu image has an lower-level image chain
            base ---> sn
              |        |
           resource resource
        :param image_name: The image tag defined in cartesian params,
                           e.g. for a qemu image, the tag should be the
                           top image("sn" in the example above) if the
                           "image_chain" is defined, usually it is
                           defined in the "images" param, e.g. "image1"
        :type image_name: string
        :param params: The params for all the lower-level images
                       Note it's *NOT* an image-specific params like
                         params.object_params("sn")
                       *BUT* the params for both "sn" and "base"
                       Examples:
                       1. images_vm1 = "image1 sn"
                          image_chain_sn = "base sn"
                          image_name = "sn"
                          params = the_case_params.object_params('vm1')
                       2. images = "image1 stg"
                          image_name = "image1"
                          params = the_case_params
        :type params: Params
        :return: The image configuration
        :rtype: dict
        """
        image_params = params.object_params(image_name)
        image_type = image_params.get("image_type", "qemu")
        image_class = get_image_class(image_type)

        LOG.debug(f"Define the {image_type} image configuration for {image_name}")
        return image_class.define_config(image_name, params)

    def create_image_object(self, image_config):
        """
        Create an upper-level image(e.g. in the context of a VM, it's
        mapping to a VM's disk) object by its configuration without
        any storage allocation. All its lower-level images and their
        mapping storage resource objects will be created.
        :param image_config: The image configuration.
                             Call define_image_config to get it.
        :type image_config: dict
        :return: The image object id
        :rtype: string
        """
        image_type = image_config["meta"]["type"]
        image_class = get_image_class(image_type)
        image = image_class(image_config)
        image.create_object()
        self._images[image.image_id] = image

        LOG.debug(f"Created the image object {image.image_id} for {image.image_name}")
        return image.image_id

    def destroy_image_object(self, image_id):
        """
        Destroy a specified image. All its storage allocation should
        be released.

        :param image_id: The image id
        :type image_id: string
        """
        LOG.debug(f"Destroy the image object {image_id}")
        image = self._images.pop(image_id)
        image.destroy_object()

    def handle_image(self, image_id, config):
        """
        Update a specified upper-level image

        config format:
          {command: arguments}

        Supported commands for a qemu image:
          create: Use qemu-img create the image
          destroy: Destroy the specified lower-level images
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
          backup: Backup a qemu image
          compare: Comare two qemu images
          config: Update the static configurations

        The arguments is a dict object which contains all related settings
        for a specific command
        :param image_id: The image id
        :type image_id: string
        """
        cmd, arguments = config.popitem()
        image = self._images.get(image_id)
        image_handler = image.get_image_handler(cmd)

        node_tags = arguments.pop("nodes", list())
        node_names = [cluster.get_node_by_tag(tag).name for tag in node_tags]
        if node_names:
            arguments["nodes"] = node_names

        LOG.debug(f"Handle the image object {image_id} with cmd {cmd}")
        return image_handler(arguments)

    def get_image_info(self, image_id, request=None):
        """
        Get the configuration of a specified upper-level image

        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.virt-images.<image_name>[.meta[.<key>]]]
                          spec[.virt-images.<image_name>[.spec[.<key>]]]
                        Examples:
                          1. Get the image's configuration
                            request=None
                          2. Get the lower-level images' configurations
                            request=spec.virt-images
                          3. Get sn's volume configuration
                            request=spec.virt-images.sn.spec.volume
        :type request: string
        :return: The configuration
        :rtype: dict
        """
        LOG.debug(
            f"Get the config of the image object {image_id} with request {request}"
        )
        image = self._images.get(image_id)
        if image is None:
            LOG.error(f"No such image in {self._images}")
        return image.get_info(request)

    def query_image(self, image_name, vm_name=None):
        """
        Get the image object id

        Note: The partition id is not required because only one
        partition is created when running a test case

        :param image_name: The image tag defined in 'images'
        :type image_name: string
        :param vm_name: The vm tag defined in 'vms'
        :type vm_name: string
        :return: The image object id
        :rtype: string
        """
        _ = []
        for image_id, image in self._images.items():
            if image_name == image.image_name:
                if vm_name:
                    if image.is_used_by(vm_name):
                        return image_id
                else:
                    return image_id
                _.append(image.image_name)
        else:
            LOG.error(f"Could not find image {image_name} in {_}")
        return None


vt_imgr = _VTImageManager()
