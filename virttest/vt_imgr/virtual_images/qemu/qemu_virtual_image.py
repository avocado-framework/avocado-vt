import copy
import logging

from virttest.utils_misc import generate_random_string
from virttest.vt_cluster import cluster
from virttest.vt_resmgr import resmgr

from ..virtual_image import _VirImage
from .images import get_qemu_image_class

LOG = logging.getLogger("avocado." + __name__)


class _QemuVirImage(_VirImage):

    # The upper-level image type
    _IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        # Store images with the same order as tags defined in image_chain
        self._handlers.update(
            {
                "create": self.create,
                "destroy": self.destroy,
                "rebase": self.qemu_img_rebase,
                "commit": self.qemu_img_commit,
                "snapshot": self.qemu_img_snapshot,
                "add": self.add_image_object,
                "remove": self.remove_image_object,
                "info": self.qemu_img_info,
                "check": self.qemu_img_check,
                "config": self.config,
            }
        )

    @classmethod
    def define_image_config(cls, image_name, image_params):
        image_format = image_params.get("image_format", "qcow2")
        image_class = get_qemu_image_class(image_format)
        return image_class.define_config(image_name, image_params)

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        def _define_topo_chain_config():
            backing = None
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                images[image_tag] = cls.define_image_config(image_tag, image_params)
                if backing is not None:
                    images[image_tag]["spec"]["backing"] = backing
                backing = image_tag

        def _define_topo_none_config():
            image_params = params.object_params(image_name)
            images[image_name] = cls.define_image_config(image_name, image_params)

        config = super()._define_config_legacy(image_name, params)
        images = config["spec"]["images"]

        # image_chain should be the upper-level image param
        image_chain = params.object_params(image_name).objects("image_chain")
        if image_chain:
            # config["meta"]["topology"] = {"type": "chain", "value": image_chain}
            config["meta"]["topology"] = {"chain": image_chain}
            _define_topo_chain_config()
        else:
            # config["meta"]["topology"] = {"type": "flat", "value": [image_name]}
            config["meta"]["topology"] = {"none": [image_name]}
            _define_topo_none_config()

        return config

    @property
    def image_access_nodes(self):
        """
        Get the nodes where all images can be accessed
        """
        node_set = set()
        for image in self.images.values():
            node_set.update(image.image_access_nodes)
        return list(node_set)

    @property
    def image_names(self):
        if "none" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["none"]
        elif "chain" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["chain"]
        else:
            raise ValueError("Unknown topology %s" % self.image_meta["topology"])
        return names

    def _create_image_object(self, image_name):
        config = self.image_spec["images"][image_name]
        image_format = config["spec"]["format"]
        image_class = get_qemu_image_class(image_format)
        image = image_class(config)
        image.create_object()
        return image

    def create_object(self):
        """
        Create the qemu image object.
        All its lower-level virt image objects and their volume
        objects will be created
        """
        LOG.debug("Created the image object for qemu image %s", self.image_meta["name"])
        for image_name in self.image_names:
            self.images[image_name] = self._create_image_object(image_name)

    def destroy_image_object(self, image_name):
        image = self.images.pop(image_name)
        image.destroy_object()

    def destroy_object(self):
        """
        Destroy the image object, all its lower-level image objects
        will be destroyed.
        """
        for image_name in self.image_names[::-1]:
            self.destroy_image_object(image_name)
        for image_name in self.images:
            self.destroy_image_object(image_name)

    def add_image_object(self, arguments):
        """
        Add a lower-level virt image into the qemu image

        Create the virt image object
        Update the qemu image's topology

        Note: If the virt image has a backing, then its backing must be
        the topest virt image, e.g. base <-- top, add top1, top1's backing
        must be top, setting top1's backing to base will lead to error.
        """
        target = arguments["target"]
        target_image_params = arguments["target_params"]
        backing_chain = arguments.get("backing_chain", False)
        node_names = arguments.get("nodes") or self.image_access_nodes

        if target in self.images:
            raise ValueError(f"{target} already existed")

        if not set(node_names).issubset(set(self.image_access_nodes)):
            raise ValueError(
                f"{node_names} should be a subset of {self.image_access_nodes}"
            )

        config = self.define_image_config(target, target_image_params)

        if backing_chain:
            config["spec"]["backing"] = self.image_names[-1]
            self.image_names.append(target)
            self.image_meta["name"] = target
            if "none" in self.image_meta["topology"]:
                self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop(
                    "none"
                )

            LOG.info(
                "Qemu image changed: name=%s, topology=%s",
                self.image_meta["name"],
                self.image_meta["topology"],
            )

        self.image_spec["images"][target] = config
        self.images[target] = self._create_image_object(target)

    def remove_image_object(self, arguments):
        """
        Remove the lower-level virt image

        Destroy the virt image object
        Update the qemu image's topology
        """
        target = arguments.pop("target")

        if target not in self.images:
            raise ValueError(f"{target} does not exist")

        if len(self.images) == 1:
            raise ValueError(
                f"Cannot remove {target} for a qemu image "
                "must have at least one lower-level image"
            )

        if target in self.image_names:
            if (
                "chain" in self.image_meta["topology"]
                and target != self.image_names[-1]
            ):
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be removed" % self.image_names
                )
            elif "none" in self.image_meta["topology"]:
                raise ValueError(
                    "Removing %s in topology(%s) can cause an "
                    "unknown state of the image" % (target, self.image_names)
                )

        image = self.images.pop(target)
        if image.volume_allocated:
            raise RuntimeError(f"The resource of {target} isn't released yet")

        image.destroy_object()

        if target in self.image_names:
            self.image_names.remove(target)
            self.image_meta["name"] = self.image_names[-1]

            if len(self.image_names) < 2:
                self.image_meta["topology"]["none"] = self.image_meta["topology"].pop(
                    "chain"
                )

            LOG.info(
                "Qemu image changed: name=%s, topology=%s",
                self.image_meta["name"],
                self.image_meta["topology"],
            )

    def clone(self):
        LOG.debug(f"Clone the image from qemu image {self.image_name}")

        config = {
            "meta": copy.deepcopy(self.image_meta),
            "spec": {
                "images": {},
            },
        }

        # Change the image name
        postfix = generate_random_string(8)
        cloned_image_name = f"{config['meta']['name']}_{postfix}"
        config["meta"]["name"] = cloned_image_name

        # Clone each qemu image object
        images = dict()
        for image_name in self.image_names:
            image = self.images[image_name]
            cloned_image = image.create_object_from_self()
            cloned_image.bind_volume({"nodes": image.image_access_nodes})
            cloned_image.allocate_volume(dict())
            images[image_name] = cloned_image
            config["spec"]["images"][image_name] = cloned_image.image_config

        # Add each image object for management
        obj = self.__class__(config)
        for image_name in self.image_names:
            obj.images[image_name] = images[image_name]

        # Update the topology for images
        if "chain" in obj.image_meta["topology"]:
            node_name = obj.image_access_nodes[0]
            node = cluster.get_node(node_name)

            for i in range(1, len(obj.image_names)):
                arguments = {
                    "source": obj.image_names[i - 1],
                    "target": obj.image_names[i],
                }
                r, o = node.proxy.image.update_image(
                    obj.get_image_info(verbose=True), {"rebase": arguments}
                )
                if r != 0:
                    raise Exception(o["out"])
        return obj

    def create(self, arguments):
        """
        Create the qemu image
        """
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        target = arguments.get("target")
        if target in self.image_names:
            if target != self.image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be created" % self.image_names
                )

        image_tags = [target] if target else self.image_names
        LOG.info(
            "Create the qemu image %s, targets: %s", self.image_meta["name"], image_tags
        )

        for image_tag in image_tags:
            image = self.images[image_tag]
            image.create(arguments)

        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"create": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def destroy(self, arguments):
        """
        Release the storage

        Note all the lower-level image objects and their volume objects
        will not be destroyed.
        """
        target = arguments.pop("target", None)
        if target in self.image_names:
            if target != self.image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be destroyed" % self.image_names
                )

        image_tags = [target] if target else list(self.images.keys())
        LOG.info(
            "Destroy the qemu image %s, targets: %s",
            self.image_meta["name"],
            image_tags,
        )

        for image_tag in image_tags:
            self.images[image_tag].destroy(arguments)

    def backup(self):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        # Use the local filesystem pool to store the backup
        pool_id = None
        for pool_id in resmgr.pools:
            pool_config = resmgr.get_pool_info(pool_id, "meta")
            pool_meta = pool_config["meta"]
            if pool_meta["type"] == "filesystem" and node_name in pool_meta["access"]["nodes"]:
                break

        for image_name in self.image_names:
            image = self.images[image_name]
            backup_image = image.create_object_from_self(pool_id)
            backup_image.bind_volume({"nodes": [node_name]})
            backup_image.allocate_volume(dict())
            image.image_spec["backup"] = backup_image.image_name
            self.images[backup_image.image_name] = backup_image

        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"backup": {}}
        )
        if r != 0:
            raise Exception(o["out"])

    def restore(self):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"restore": {}}
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_rebase(self, arguments):
        """
        Rebase target to the top of the qemu image
        """
        target = arguments.get("target")
        backing = self.image_names[-1]
        arguments["source"] = backing

        LOG.info(f"Rebase lower-level image {target} onto {backing}")
        add_args = {
            "target": arguments["target"],
            "target_params": arguments.pop("target_params"),
            "nodes": arguments.pop("nodes", None),
        }
        self.add_image_object(add_args)

        create_args = {
            "target": target,
        }
        self.create(create_args)

        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"rebase": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        self.image_meta["name"] = target
        self.image_names.append(target)
        if "none" in self.image_meta["topology"]:
            self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop(
                "none"
            )
        config = self.image_spec["images"][target]
        config["spec"]["backing"] = backing

        LOG.info(
            "Qemu image changed: name=%s, topology=%s",
            self.image_meta["name"],
            self.image_meta["topology"],
        )

    def qemu_img_commit(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"commit": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_snapshot(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"snapshot": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_info(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"info": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]

    def qemu_img_check(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_image(
            self.get_image_info(verbose=True), {"check": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]
