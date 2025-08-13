import collections
import logging

LOG = logging.getLogger("avocado.service." + __name__)


def _get_dir_volume_opts(volume_config):
    return {
        "driver": "file",
        "filename": volume_config["spec"]["uri"],
    }


def _get_nfs_volume_opts(volume_config):
    return _get_dir_volume_opts(volume_config)


def _get_ceph_volume_opts(volume_config):
    volume_spec = volume_config["spec"]
    pool_config = volume_config["meta"]["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    volume_opts = {
        "driver": "rbd",
        "pool": pool_spec["pool"],
        "image": volume_spec["filename"],
    }

    if pool_spec.get("conf") is not None:
        volume_opts["conf"] = pool_spec["conf"]
    if pool_spec.get("namespace") is not None:
        volume_opts["namespace"] = pool_spec["namespace"]

    return volume_opts


def _get_iscsi_direct_volume_opts(volume_config):
    pool_config = volume_config["meta"]["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    # required options for iscsi
    volume_opts = {
        "driver": "iscsi",
        "transport": pool_spec["transport"],
        "portal": pool_spec["portal"],
        "target": pool_spec["target"],
    }

    # optional option
    if pool_spec["user"] is not None:
        volume_opts["user"] = pool_spec["user"]

    return volume_opts


def _get_nbd_volume_opts(volume_config):
    volume_meta = volume_config["meta"]
    volume_spec = volume_config["spec"]
    pool_config = volume_meta["pool"]
    pool_meta = pool_config["meta"]
    pool_spec = pool_config["spec"]

    volume_opts = {"driver": "nbd"}
    if pool_spec.get("host"):
        volume_opts.update(
            {
                "server.type": "inet",
                "server.host": pool_spec["host"],
                "server.port": volume_spec.get("port", 10809),
            }
        )
    elif pool_spec.get("path"):
        volume_opts.update(
            {
                "server.type": "unix",
                "server.path": pool_spec["path"],
            }
        )
    else:
        raise ValueError("Either 'host' or 'path' is required")

    if volume_spec.get("export"):
        volume_opts["export"] = volume_spec["export"]

    return volume_opts


def get_ceph_pool_access_opts(pool_config):
    auth = dict()
    return auth


def get_iscsi_direct_pool_access_opts(pool_config):
    auth = dict()
    return auth


def get_nbd_pool_access_opts(pool_config):
    auth = dict()
    return auth


def get_qemu_image_volume_access_auth_opts(pool_config):
    access_opts_getters = {
        "filesystem": lambda i: dict(),
        "nfs": lambda i: dict(),
        "ceph": get_ceph_pool_access_opts,
        "iscsi-direct": get_iscsi_direct_pool_access_opts,
        "nbd": get_nbd_pool_access_opts,
    }

    pool_type = pool_config["meta"]["type"]
    access_opts_getter = access_opts_getters[pool_type]

    return access_opts_getter(pool_config)


def get_volume_opts(volume_config):
    volume_opts_getters = {
        "filesystem": _get_dir_volume_opts,
        "nfs": _get_nfs_volume_opts,
        "ceph": _get_ceph_volume_opts,
        "iscsi-direct": _get_iscsi_direct_volume_opts,
        "nbd": _get_nbd_volume_opts,
    }

    pool_config = volume_config["meta"]["pool"]
    pool_type = pool_config["meta"]["type"]
    volume_opts_getter = volume_opts_getters[pool_type]

    return volume_opts_getter(volume_config)


def get_image_opts(image_config):
    """
    Get lower-level qemu virt image options

    Return a tuple of (access_auth_opts, encryption_opts, image_opts)
    """
    volume_config = image_config["spec"]["volume"]
    image_format = image_config["spec"]["format"]

    image_opts = collections.OrderedDict()
    image_opts["file"] = collections.OrderedDict()
    image_opts["driver"] = image_format
    image_opts["file"].update(get_volume_opts(volume_config))

    # lower-level virt image encryption options
    encryption_opts = image_config["spec"].get("encryption", dict())
    if image_format == "luks":
        key = "password-secret" if "file" in encryption_opts else "key-secret"
        image_opts[key] = encryption_opts["name"]
    elif image_format == "qcow2" and encryption_opts:
        encrypt_format = encryption_opts["encrypt"]["format"]
        if encrypt_format == "luks":
            image_opts["encrypt.key-secret"] = encryption_opts["name"]
            image_opts.update(
                {f"encrypt.{k}": v for k, v in encryption_opts["encrypt"]}
            )
        else:
            raise ValueError(f"Unknown encrypt format: {encrypt_format}")

    # volume pool access auth options
    pool_config = volume_config["meta"]["pool"]
    access_auth_opts = get_qemu_image_volume_access_auth_opts(pool_config)

    # TODO: Add filters here
    return access_auth_opts, encryption_opts, image_opts
