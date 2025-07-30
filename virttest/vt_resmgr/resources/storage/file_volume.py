import copy
import logging
import os

from virttest import utils_misc
from virttest.utils_numeric import normalize_data_size
from virttest.vt_cluster import cluster

from .volume import _Volume

LOG = logging.getLogger("avocado." + __name__)


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
            config["spec"]["filename"] = os.path.basename(image_name)
            config["spec"]["uri"] = image_name
        else:
            image_format = resource_params.get("image_format", "qcow2")
            config["spec"]["filename"] = f"{image_name}.{image_format}"
            config["spec"]["uri"] = None

        return config

    def create_object_by_self(self, pool_id, access_nodes):
        postfix = utils_misc.generate_random_string(8)
        volume_obj = super().create_object_by_self(pool_id, access_nodes)
        volume_obj.resource_spec.update(
            {
                "allocation": None,
                "filename": f"{self.resource_spec['filename']}_{postfix}",
                "uri": None,
            }
        )
        return volume_obj

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

    def clone(self, arguments):
        config = copy.deepcopy(self.resource_config)

        # Reset options of the cloned resource in a specific resource because
        # only this type of resource knows what options need to be reset
        postfix = utils_misc.generate_random_string(8)
        filename = config["spec"]["filename"]
        resource_name = config["meta"]["name"]
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
                "allocated": False,
                "bindings": [
                    {"node": n, "backing": None} for n in self.resource_binding_nodes
                ],
            }
        )

        cloned_obj = self.__class__(config)
        cloned_obj.create_object()
        cloned_obj.bind(dict())
        args = {
            "how": arguments.get("how", "copy") if arguments else "copy",
            "source": self.resource_spec["uri"],
        }
        cloned_obj.allocate(args)

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
