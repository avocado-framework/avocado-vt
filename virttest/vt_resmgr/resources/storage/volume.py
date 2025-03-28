import copy
import os

from virttest.utils_numeric import normalize_data_size
from virttest.vt_cluster import cluster
from virttest import utils_misc

from ..resource import _Resource


class _Volume(_Resource):
    """
    Storage volumes are abstractions of physical partitions,
    LVM logical volumes, file-based disk images
    """
    _RESOURCE_TYPE = "volume"
    _VOLUME_TYPE = None

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        size = normalize_data_size(
            resource_params.get("image_size", "20G"), order_magnitude="B"
        )

        nodes = self._get_binding_nodes(resource.get("volume_pool_selectors", list()))
        config = super()._define_config_legacy(resource_name, resource_params)
        config["meta"].update(
            {
                "volume-type": cls._VOLUME_TYPE,
                "bindings": [{"node": n, "backing": None} for n in nodes],
            }
        )
        config["spec"].update(
            {
                "size": size,
                "allocation": None,
                "uri": None,
            }
        )

        return config


class _FileVolume(_Volume):
    """For file based volumes"""

    _VOLUME_TYPE = "file"

    def __init__(self, resource_config):
        super().__init__(resource_config)
        self._handlers.update(
            {
                "resize": self.resize,
            }
        )

    @classmethod
    def _define_config_legacy(cls, resource_name, resource_params):
        config = super()._define_config_legacy(resource_name, resource_params)

        image_name = resource_params.get("image_name", "image")
        if os.path.isabs(image_name):
            # FIXME: the image file may not come from this pool
            config["spec"]["uri"] = image_name
            config["spec"]["filename"] = os.path.basename(image_name)
        else:
            image_format = resource_params.get("image_format", "qcow2")
            config["spec"]["filename"] = "%s.%s" % (image_name, image_format)
            config["spec"]["uri"] = None

        return config

    def resize(self, arguments):
        """
        Resize the file based volume
        """
        new = int(normalize_data_size(arguments["size"], "B"))
        if new != self.resource_spec["size"]:
            node_name = self.resource_bindings[0]["node"]
            backing_id = self._get_backing(node_name)

            LOG.debug(f"Resize the volume {self.resource_id} from {node_name}")
            node = cluster.get_node(node_name)
            r, o = node.proxy.resource.update_resource_by_backing(
                backing_id, {"resize": arguments}
            )
            if r != 0:
                raise Exception(o["out"])
            self.resource_spec["size"] = new
        else:
            LOG.debug("No need to resize the volume as the size never changes")

    def allocate(self, arguments):
        node_name = self.resource_bindings[0]["node"]
        backing_id = self._get_backing(node_name)
        node = cluster.get_node(node_name)

        LOG.debug(f"Allocate the volume {self.resource_id} from {node_name}.")
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"allocate": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]

    def release(self, arguments):
        node_name = self.resource_bindings[0]["node"]
        backing_id = self._get_backing(node_name)
        node = cluster.get_node(node_name)

        LOG.debug(f"Release the volume {self.resource_id} from {node_name}")
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"release": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        self.resource_meta["allocated"] = False
        self.resource_spec["allocation"] = 0
        self.resource_spec["uri"] = None

    def clone(self):
        config = copy.deepcopy(self.resource_config)

        # Reset options
        filename = config["spec"]["filename"]
        resource_name = config["meta"]["name"]
        postfix = utils_misc.generate_random_string(8)
        config["spec"].update(
            {
                "uri": None,
                "filename": f"{filename}.clone_{postfix}",
                "allocation": 0,
            }
        )
        config["meta"].update(
            {
                "name": f"{resource_name}_clone_{postfix}",
                "pool": pool_id,
                "allocated": False,
            }
        )

        cloned_obj = self.__class__(config)
        cloned_obj.bind(dict())
        cloned_obj.allocate(dict())

        return cloned_obj

    def sync(self, arguments):
        LOG.debug(f"Sync up the configuration of volume {self.resource_id}")
        node_name = self.resource_bindings[0]["node"]
        backing_id = self._get_backing(node_name)
        node = cluster.get_node(node_name)
        r, o = node.proxy.resource.update_resource_by_backing(
            backing_id, {"sync": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        config = o["out"]
        self.resource_meta["allocated"] = config["meta"]["allocated"]
        self.resource_spec["uri"] = config["spec"]["uri"]
        self.resource_spec["allocation"] = config["spec"]["allocation"]


class _BlockVolume(_Volume):
    """For disk, lvm, iscsi based volumes"""

    _VOLUME_TYPE = "block"


class _NetworkVolume(_Volume):
    """For rbd, iscsi-direct based volumes"""

    _VOLUME_TYPE = "network"
