import logging
from abc import abstractmethod

from ...virt_image import _VirtImage
from virttest.vt_resmgr import (
    define_resource_config,
    create_resource_object,
    destroy_resource_object,
    update_resource,
)


LOG = logging.getLogger("avocado." + __name__)


class _QemuVirtImage(_VirtImage):
    """
    A virt image has one storage resource(volume), take qemu virt image
    as an example, the cartesian params beginning with 'image_', e.g.
    'image_size' describe this object
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params, node_tags):
        config = super()._define_config_legacy(image_name,
                                               image_params,
                                               node_tags)
        create = None
        if image_params.get_boolean("force_create_image"):
            create = "force"
        elif image_params.get_boolean("create_image"):
            create = "graceful"
        remove = image_params.get_boolean("remove_image", True)
        config["meta"].update({
            "create": create,
            "remove": remove,
        })

        config["spec"].update({
            "backing": None,
            "volume": define_resource_config("volume",
                                             image_params,
                                             node_tags),
        })

        return config

    def info(self):
        pass

    def keep(self):
        pass

    def create_object(self):
        LOG.debug(f"Create the virt image object for '{self.virt_image_name}'")
        volume_config = self.virt_image_spec["volume"]
        create_resource_object(volume_config)
        self.bind_volume(dict())

    def destroy_object(self):
        LOG.debug(f"Destroy the virt image object for '{self.virt_image_name}'")
        self.unbind_volume(dict())
        destroy_resource_object(self.volume_id)

    def sync_volume(self, arguments):
        LOG.debug(f"Sync-up the volume conf for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"sync": arguments})

    def bind_volume(self, arguments):
        LOG.debug(f"Bind the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"bind": arguments})

    def unbind_volume(self, arguments):
        LOG.debug(f"Unbind the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"unbind": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for '{self.virt_image_name}'")
        update_resource(self.volume_id, {"release": arguments})

    @property
    def volume_allocated(self):
        conf = query_resource(self.volume_id, request="meta.allocated")
        return conf["allocated"]
