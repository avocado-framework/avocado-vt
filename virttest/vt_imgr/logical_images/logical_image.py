import copy
import uuid
from abc import ABC, abstractmethod


class LogicalImage(ABC):
    """
    Abstract base class for logical images in the avocado-vt image management system.

    A logical image represents a complete disk image structure that maps to a VM's
    virtual disk. Logical images can have complex hierarchical topologies composed
    of multiple layer images, e.g. the backing chains for the qemu logical image,
    enabling advanced features like snapshots semantics.

    The Qemu Image Hierarchy Example:
        base_image ---> snapshot_1 ---> snapshot_2 (logical image name)

    In this chain, 'snapshot_2' is the logical image name(what the VM sees), while
    'base_image' and 'snapshot_1' are its backing images providing the foundation
    data layers. Each layer can be stored on different storage pools and accessed
    through the unified resource management system.
    """

    # The supported image types: qemu
    IMAGE_TYPE = None

    def __init__(self, image_config):
        self._config = image_config
        self.meta["uuid"] = uuid.uuid4().hex
        self._layer_images = dict()  # {image name: image object}
        self._handlers = {
            "create": self.create,
            "destroy": self.destroy,
            "backup": self.backup,
            "restore": self.restore,
        }

    @property
    def topo_layer_image_names(self):
        """
        Return a list of layer image names in the topology.

        Note self.layer_images can have more layer images than the count of
        image names in the topology when a layer image has a backup.
        """
        return self.meta["topology"]["value"]

    @property
    def layer_images(self):
        """
        Returns all the layer images associated with this logical image.
        """
        return self._layer_images

    @property
    def config(self):
        return self._config

    @property
    def meta(self):
        return self.config["meta"]

    @property
    def spec(self):
        return self.config["spec"]

    @property
    def uuid(self):
        return self.meta["uuid"]

    @property
    def name(self):
        return self.meta["name"]

    @property
    def node_affinity(self):
        """
        Returns a list of node names where the logical images can be handled.
        Note the node names are defined in the cartesian param 'nodes'.
        """
        nodes = set()
        for image in self.layer_images.values():
            nodes = (
                set(image.volume_access_node_names)
                if not nodes
                else nodes.intersection(image.volume_access_node_names)
            )
        return list(nodes)

    def set_node_affinity(self, node_names=None):
        for image in self.layer_images.values():
            image.bind_volume(node_names)

    def unset_node_affinity(self, node_names=None):
        for image in self.layer_images.values():
            image.unbind_volume(node_names)

    def is_owned_by(self, owner):
        return owner == self.meta["owner"]

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        """
        Define the logical image configuration in the old way
        TODO: Introduce a converter to convert the cartesian params
              to the internal python configuration
        """
        return {
            "meta": {
                "uuid": None,
                "name": image_name,
                "type": cls.IMAGE_TYPE,
                "owner": params.object_params(image_name).get("image_owner"),
                "topology": {"type": None, "value": None},
            },
            "spec": {
                "images": dict(),
            },
        }

    @classmethod
    def define_config(cls, image_name, params):
        """
        Define the logical image configuration by its cartesian params
        """
        return cls._define_config_legacy(image_name, params)

    def customized_config(self):
        return self.config

    @abstractmethod
    def create_layer_images(self):
        """
        Create the layer image objects of the logical image.
        It depends on the specific type of the logical image.
        """
        raise NotImplementedError

    def destroy_layer_images(self):
        """
        Destroy the layer image objects of the logical image.
        It depends on the specific type of the logical image.
        """
        for image in self.layer_images.values():
            if image.volume_allocated:
                raise RuntimeError(
                    f"Cannot destroy layer image {image.name} when its volume is allocated."
                )
        self.layer_images.clear()

    @abstractmethod
    def create(self, arguments, node):
        """
        Create the logical image on a specified node with the topology.
        Create all layer images if not arguments.get("target").
        Create the specified layer image arguments["target"] only if "target" is set.
        Allocate its layer images' volumes.
        Build the layer image topology.
        """
        raise NotImplementedError

    @abstractmethod
    def destroy(self, arguments, node):
        raise NotImplementedError

    @abstractmethod
    def clone(self, arguments, node):
        """
        Clone the logical image on a specified node.
            The layer image and its volume are cloned.
            The topology of the layer images is cloned;
            The data is cloned;
        """
        raise NotImplementedError

    @abstractmethod
    def backup(self, arguments, node):
        """
        Backup the data of the logical image on a specified node.
        In order to do so, create a local filesystem volume to hold
        the data of each layer image on the specified node.

        All backup storage is allocated on the specified node.
        Backup all layer images if not arguments.get("target").
        Backup the specified layer image arguments["target"] only if "target" is set.
        """
        raise NotImplementedError

    @abstractmethod
    def restore(self, arguments, node):
        """
        Restore the data of the logical image.

        All backup data is store on the same local storage pool on the specified node.
        Restore all layer images if not arguments.get("target").
        Restore the specified layer image arguments["target"] only if "target" is set.
        """
        raise NotImplementedError

    def get_info(self, request=None):
        config = copy.deepcopy(self.config)

        if request is not None:
            item = None
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(
                        f"Cannot get the logical image configuration with request: {request}"
                    )
            else:
                config = {item: config}

        return config

    def get_image_handler(self, cmd):
        return self._handlers.get(cmd)
