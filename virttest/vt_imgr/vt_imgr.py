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

# Query the configuration of the upper-level image
out = vt_imgr.query_image(image_id, request=None)
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

from .images import get_image_class
from virttest.vt_cluster import cluster

LOG = logging.getLogger("avocado." + __name__)


# TODO:
# Add drivers for diff handlers
# Add access permission for images
# serialize
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
        LOG.debug(f"Define the image configuration for {image_name}")
        image_params = params.object_params(image_name)
        image_type = image_params.get("image_type", "qemu")
        image_class = get_image_class(image_type)
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
        LOG.debug("Create the image object %s for %s",
                  image.image_id, image_config["meta"]["name"])
        return image.image_id

    def destroy_image_object(self, image_id):
        """
        Destroy a specified image. All its storage allocation should
        be released.

        :param image_id: The image id
        :type image_id: string
        """
        LOG.debug(f"Destroy the image object {image_id}")
        image = self._images.get(image_id)
        image.destroy_object()
        del(self._images[image_id])


    def handle_image(self, image_id, config):
        """
        Update a specified upper-level image

        config format:
          {command: arguments}

        Supported commands for a qemu image:
          create: qemu-img create
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

          Note: Not all images support the above operations
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

        LOG.debug(f"Handle the image {image_id} with {cmd}")
        return image_handler(arguments)

    def query_image(self, image_id, request=None):
        """
        Query the configuration of a specified upper-level image

        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.virt-images.<image_name>[.meta[.<key>]]]
                          spec[.virt-images.<image_name>[.spec[.<key>]]]
                        Examples:
                          1. Query the image's configuration
                            request=None
                          2. Query the lower-level images' configurations
                            request=spec.virt-images
                          3. Query sn's volume configuration
                            request=spec.virt-images.sn.spec.volume
        :type request: string
        :return: The configuration
        :rtype: dict
        """
        LOG.debug(f"Query the image {image_id} with {request}")
        image = self._images.get(image_id)
        return image.query(request)

    def get_image_by_tag(self, image_tag):
        """
        Get the image uuid with the image tag.
        For the qemu image, the image tag is defined in the param 'images'
        """
        # FIXME: we cannot get the image by its tag name
        for image in self._images.values():
            if image_tag in image.image_spec["virt-images"]:
                return image.image_id
        return None

    def get_image(self, image_name, vm_name=None, partition_id=None):
        pass


vt_imgr = _VTImageManager()
