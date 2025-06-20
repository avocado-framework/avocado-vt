import logging

from virttest.vt_resmgr import resmgr

from ...virt_image import _VirtImage

LOG = logging.getLogger("avocado." + __name__)


class _QemuVirtImage(_VirtImage):
    """
    A virt image has one storage resource(volume), take qemu virt image
    as an example, the cartesian params beginning with 'image_', e.g.
    'image_size' describe this object
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name, image_params)
        config["spec"].update(
            {
                "backing": None,
                "volume": resmgr.define_resource_config(
                    image_name, "volume", image_params
                ),
            }
        )

        return config

    def info(self):
        pass

    def keep(self):
        pass

    def create_object(self):
        LOG.debug(f"Create the virt image object for '{self.virt_image_name}'")
        volume_config = self.virt_image_spec["volume"]
        volume_id = resmgr.create_resource_object(volume_config)
        resmgr.update_resource(volume_id, {"bind": dict()})

    def destroy_object(self):
        LOG.debug(f"Destroy the virt image object for '{self.virt_image_name}'")
        resmgr.update_resource(self.volume_id, {"unbind": dict()})
        resmgr.destroy_resource_object(self.volume_id)

    def sync_volume(self, arguments):
        LOG.debug(f"Sync up the volume conf for '{self.virt_image_name}'")
        resmgr.update_resource(self.volume_id, {"sync": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for '{self.virt_image_name}'")
        resmgr.update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for '{self.virt_image_name}'")
        resmgr.update_resource(self.volume_id, {"release": arguments})
