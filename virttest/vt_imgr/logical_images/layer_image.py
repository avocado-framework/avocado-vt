import logging
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy

from virttest.utils_misc import generate_random_string
from virttest.vt_resmgr import resmgr

LOG = logging.getLogger("avocado." + __name__)


class LayerImage(ABC):
    """
    Abstract base class for individual image objects within logical image hierarchies.

    A LayerImage represents a single layer in a logical image's topology, with each
    image backed by a storage volume resource managed by the unified resource system.
    Images are the building blocks that compose logical images, providing the actual
    disk image files and their associated metadata.

    Each image object encapsulates:
        - Volume Resource: Storage backing through the resource management system
        - Configuration: Derived from cartesian parameters (image_size, image_format, etc.)
    """

    IMAGE_FORMAT = None

    def __init__(self, config):
        self._config = config
        self.meta["uuid"] = uuid.uuid4().hex

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        # TODO: A new converter module will be introduced in future to convert
        #       cartesian params into internal python configuration.
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
            },
            "spec": {
                "backup": None,
                "format": cls.IMAGE_FORMAT,
                "size": image_params.get("image_size", "20G"),
                "volume": None,  # Volume uuid
            },
        }

    @classmethod
    def define_config(cls, image_name, image_params):
        """
        Define the image configuration by its cartesian params.
        Currently, use the existing image params, e.g. image_size
        """
        return cls._define_config_legacy(image_name, image_params)

    @abstractmethod
    def define_config_by_self(self):
        postfix = generate_random_string(8)

        config = deepcopy(self.config)
        config["meta"].update(
            {
                "uuid": None,
                "name": f"{self.name}_{postfix}",
            }
        )
        config["spec"].update(
            {
                "backup": None,
                # Let the caller determine how to create the volume
                "volume": None,
            }
        )

        return config

    @property
    def volume_uuid(self):
        return self.spec["volume"]

    @property
    def volume_access_node_names(self):
        """
        Return a list of node tag names where the volume can be accessed.
        """
        return resmgr.get_resource_binding_nodes(self.volume_uuid)

    @property
    def uuid(self):
        return self.meta["uuid"]

    @property
    def name(self):
        return self.meta["name"]

    @property
    def config(self):
        return self._config

    @property
    def spec(self):
        return self.config["spec"]

    @property
    def meta(self):
        return self.config["meta"]

    @property
    def volume_allocated(self):
        d = resmgr.get_resource_info(self.volume_uuid, "meta.allocated")
        return d["allocated"]

    def create_backup_image(self, arguments, node):
        LOG.debug(f"Create a backup layer image for {self.name}")

        # Use the local filesystem pool to store the backup
        volume_selector = "[{'key': 'type', 'operator': '==', 'values': 'filesystem'},"
        volume_selector += (
            "{'key': 'nodes', 'operator': 'contains', 'values': '%s'}]" % node.tag
        )
        volume_params = {
            "volume_pool_selectors": volume_selector,
        }
        pool_id = resmgr.select_pool("volume", volume_params)
        if not pool_id:
            raise RuntimeError(
                f"Cannot get a filesystem storage pool on node {node.tag}"
            )

        backup_image_config = self.define_config_by_self()
        backup_image_config["spec"]["volume"] = resmgr.create_resource_from_source(
            self.volume_uuid, pool_id
        )

        backup_image = self.__class__(backup_image_config)
        backup_image.bind_volume([node.tag])
        backup_image.allocate_volume(arguments, node)
        # Update the layer image's backup image name
        self.spec["backup"] = backup_image.name
        return backup_image

    def clone(self, arguments, node):
        LOG.debug(f"Clone the layer image based on {self.name}")

        arguments = (
            arguments.update({"node": node.tag}) if arguments else {"node": node.tag}
        )
        config = self.define_config_by_self()
        config["spec"].update(
            {
                # No backup for the new image
                "backup": None,
                # Clone the volume
                "volume": resmgr.clone_resource(self.volume_uuid, arguments),
            }
        )

        return self.__class__(config)

    def bind_volume(self, node_names=None):
        LOG.debug(f"Bind the volume of layer image {self.name} to {node_names}")
        return resmgr.bind_resource(self.volume_uuid, node_names)

    def unbind_volume(self, node_names=None):
        LOG.debug(f"Unbind the volume of layer image {self.name} from {node_names}")
        return resmgr.unbind_resource(self.volume_uuid, node_names)

    def allocate_volume(self, arguments, node):
        LOG.debug(f"Allocate the volume of layer image {self.name}")
        arguments = (
            arguments.update({"node": node.tag}) if arguments else {"node": node.tag}
        )
        resmgr.update_resource(self.volume_uuid, "allocate", arguments)

    def release_volume(self, arguments, node):
        LOG.debug(f"Release the volume of layer image {self.name}")
        arguments = (
            arguments.update({"node": node.tag}) if arguments else {"node": node.tag}
        )
        resmgr.update_resource(self.volume_uuid, "release", arguments)
