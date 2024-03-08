import logging
from abc import abstractmethod

from ...virt_image import _VirtImage
from virttest.vt_resmgr import (
    define_resource_config,
    create_resource_object,
    destroy_resource_object,
    update_resource,
    query_resource,
)


LOG = logging.getLogger("avocado." + __name__)


class _QemuVirtImage(_VirtImage):
    """
    A virt image has one storage resource(volume), take qemu virt image
    as an example, the cartesian params beginning with 'image_', e.g.
    'image_size' describe this object
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name,
                                               image_params)
        config["spec"].update({
            "backing": None,
            "volume": define_resource_config(image_name,
                                             "volume",
                                             image_params),
        })

        return config

    def info(self):
        pass

    def keep(self):
        pass

    def create_object(self):
        LOG.debug(f"Create the virt image object for '{self.virt_image_name}'")
        volume_config = self.virt_image_spec["volume"]
        volume_id = create_resource_object(volume_config)
        update_resource(volume_id, {"bind": dict()})

    def destroy_object(self):
        LOG.debug(f"Destroy the virt image object for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"unbind": dict()})
        destroy_resource_object(self.volume_id)

    def sync_volume(self, arguments):
        LOG.debug(f"Sync up the volume conf for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"sync": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"release": arguments})
