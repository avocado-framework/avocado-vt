import logging
import copy

from virttest.vt_cluster import cluster

from ..image import _Image
from .qemu_virt_image import get_virt_image_class


LOG = logging.getLogger("avocado." + __name__)


class _QemuImage(_Image):

    # The upper-level image type
    _IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        # Store images with the same order as tags defined in image_chain
        self._handlers = {
            "create": self.qemu_img_create,
            "destroy": self.qemu_img_destroy,
            "rebase": self.qemu_img_rebase,
            "commit": self.qemu_img_commit,
            "snapshot": self.qemu_img_snapshot,
            "add": self.add_virt_image,
            "remove": self.remove_virt_image,
            "info": self.qemu_img_info,
        }

    @classmethod
    def _define_virt_image_config(cls, image_name, image_params, node_tags):
        image_format = image_params.get("image_format", "qcow2")
        virt_image_class = get_virt_image_class(image_format)
        return virt_image_class.define_config(image_name, image_params, node_tags)

    @classmethod
    def _define_config_legacy(cls, image_name, params, node_tags):
        def _define_topo_chain_config():
            backing = None
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                virt_images[image_tag] = cls._define_virt_image_config(
                    image_tag, image_params, node_tags
                )
                if backing is not None:
                    virt_images[image_tag]["spec"]["backing"] = backing
                backing = image_tag

        def _define_topo_none_config():
            image_params = params.object_params(image_name)
            virt_images[image_name] = cls._define_virt_image_config(
                image_name, image_params, node_tags
            )

        config = super()._define_config_legacy(image_name, params, node_tags)
        virt_images = config["spec"]["virt-images"]

        image_chain = params.object_params(image_name).objects("image_chain")
        if image_chain:
            config["meta"]["topology"] = {"chain": image_chain}
            _define_topo_chain_config()
        else:
            config["meta"]["topology"] = {"none": [image_name]}
            _define_topo_none_config()

        return config

    @property
    def image_access_nodes(self):
        node_set = set()
        for virt_image in self.virt_images.values():
            node_set.update(virt_image.virt_image_access_nodes)
        return list(node_set)

    @property
    def virt_images(self):
        return self._virt_images

    @property
    def virt_image_names(self):
        if "none" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["none"]
        elif "chain" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["chain"]
        else:
            raise ValueError("Unknown topology %s" % self.image_meta["topology"])
        return names

    def get_image_update_config(self, node_tag):
        config = copy.deepcopy(self.image_config)
        spec = config["spec"]
        if tag in self.virt_image_names:
            virt_image_config = spec["virt-images"][tag]
            volume_config = virt_image_config["spec"]["volume"]
            bindings = volume_config["meta"].pop("bindings")
            volume_config["meta"]["backing"] = bindings[node_tag]
        return config

    def create_virt_image_object(self, virt_image_name):
        config = self.image_spec["virt-images"][virt_image_name]
        image_format = config["spec"]["format"]
        virt_image_class = get_virt_image_class(image_format)
        virt_image = virt_image_class(config)
        virt_image.create_object()
        return virt_image

    def create_object(self):
        """
        Create the qemu image object.
        All its lower-level virt image objects and their volume
        objects will be created
        """
        LOG.debug("Created the image object for qemu image %s",
                  self.image_meta["name"])
        for virt_image_name in self.virt_image_names:
            self.virt_images[virt_image_name] = self.create_virt_image_object(virt_image_name)

    def destroy_virt_image_object(self, virt_image_name):
        virt_image = self.virt_images.pop(virt_image_name)
        virt_image.destroy_object()

    def destroy_object(self):
        """
        Destroy the image object, all its lower-level image objects
        will be destroyed.
        """
        for virt_image_name in self.virt_image_names[::-1]:
            self.destroy_virt_image_object(virt_image_name)
        for virt_image_name in self.virt_images:
            self.destroy_virt_image_object(virt_image_name)

    def query(self, request):
        for virt_image in self.virt_images:
            virt_image.sync_volume(dict())

        config = self.image_config
        if request is not None:
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config


    def backup(self):
        pass

    def add_virt_image(self, arguments):
        """
        Add a lower-level virt image into the qemu image

        Create the virt image object
        Allocate the storage
        Use qemu-img to create the virt image
        Update the qemu image's topology
        """
        tag = arguments["target"]
        backing = arguments.get("source")
        image_params = arguments.pop('params')
        node_tags = self.image_access_nodes

        if backing in self.virt_image_names:
            idx = self.virt_image_names.index(backing)
            self.virt_image_names.insert(idx+1, tag)
            if "none" in self.image_meta["topology"]:
                LOG.info("topology: none->chain")
                self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop("none")
            self.image_spec["virt-images"][tag]["spec"]["backing"] = backing
        elif backing is not None:
            raise Exception(f"{backing} is not defined in the qemu image")

        self.image_spec["virt-images"][tag] = self._define_virt_image_config(
            tag, image_params, self.image_access_nodes
        )
        self.virt_images[tag] = self.create_virt_image_object(tag)
        return self.qemu_img_create(arguments)

    def remove_virt_image(self, arguments):
        """
        Remove the lower-level virt image

        Release the storage allocation
        Destroy the virt image object
        Update the qemu image's topology
        """
        tag = arguments.pop('target')
        if tag in self.virt_images:
            virt_image = self.virt_images[tag]
            virt_image.release_volume(arguments)
            virt_image.destroy_object()
            self.virt_images.pop(tag)
            if tag in self.virt_image_names:
                self.virt_image_names.remove(tag)
                if len(self.virt_image_names) < 2 and "none" not in self.image_meta["topology"]:
                    _, self.image_meta["topology"]["none"] = self.image_meta["topology"].popitem()
        else:
            LOG.warning(f"{tag} is not defined in the qemu image")
        return 0, dict()

    def qemu_img_create(self, arguments):
        """
        qemu-img create

        Allocate storage
        Create lower-level virt images with qemu-img
        """
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        tag = arguments.get("target", None)
        image_tags = [tag] if tag else self.virt_image_names

        LOG.info("Create the qemu image %s, targets: %s",
                 self.image_meta["name"], image_tags)

        for image_tag in image_tags:
            virt_image = self.virt_images[image_tag]
            virt_image.bind_volume(arguments)
            virt_image.allocate_volume(arguments)

        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"create": arguments})
        if r != 0:
            raise Exception(o["out"])

        return r, o

    def qemu_img_destroy(self, arguments):
        """
        Release the storage

        Note all the lower-level image objects and their volume objects
        will not be destroyed.
        """
        LOG.info("Destroy the qemu image %s", self.image_meta["name"])
        for image_tag in self.virt_image_names[::-1]:
            virt_image = self.virt_images[image_tag]
            virt_image.release_volume(arguments)
        return 0, dict()

    def qemu_img_rebase(self, arguments):
        backing = arguments.get("source")
        target = arguments.get("target")
        if backing not in self.virt_image_names:
            raise ValueError(f"{backing} is not defined in the qemu image")
        elif backing != self.virt_image_names[-1]:
            raise ValueError(f"{backing} is not the top virt image")

        if target not in self.virt_image_names:
            idx = self.virt_image_names.index(backing)
            self.virt_image_names.insert(idx+1, target)
            if "none" in self.image_meta["topology"]:
                LOG.info("topology: none->chain")
                self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop("none")

        LOG.info(f"Rebase lower-level image {target} onto {backing}")
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"rebase": arguments})
        if r != 0:
            raise Exception(o["out"])

        return r, o

    def qemu_img_commit(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"commit": arguments})
        if r != 0:
            raise Exception(o["out"])
        return r, o

    def qemu_img_snapshot(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"snapshot": arguments})
        if r != 0:
            raise Exception(o["out"])
        return r, o

    def qemu_img_info(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"info": arguments})
        if r != 0:
            raise Exception(o["out"])
        return r, o

    def qemu_img_check(self, arguments):
        node_tag = self.image_access_nodes[0]
        node = cluster.get_node_by_tag(node_tag)
        r, o = node.proxy.image.handle_image(self.image_config,
                                             {"check": arguments})
        if r != 0:
            raise Exception(o["out"])
        return r, o
