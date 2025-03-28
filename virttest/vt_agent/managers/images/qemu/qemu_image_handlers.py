import copy
import collections
import json
import logging
import os
import re
import shutil
import string

from avocado.utils import path as utils_path
from avocado.utils import process

from virttest.utils_numeric import normalize_data_size
from virttest.vt_utils.image.qemu import get_image_opts

LOG = logging.getLogger("avocado.service." + __name__)


class _ParameterAssembler(string.Formatter):
    """
    Command line parameter assembler.

    This will automatically prepend parameter if corresponding value is passed
    to the format string.
    """

    sentinal = object()

    def __init__(self, cmd_params=None):
        string.Formatter.__init__(self)
        self.cmd_params = cmd_params or {}

    def format(self, format_string, *args, **kwargs):
        """Remove redundant whitespaces and return format string."""
        ret = string.Formatter.format(self, format_string, *args, **kwargs)
        return re.sub(" +", " ", ret)

    def get_value(self, key, args, kwargs):
        try:
            val = string.Formatter.get_value(self, key, args, kwargs)
        except KeyError:
            if key in self.cmd_params:
                val = None
            else:
                raise
        return (self.cmd_params.get(key, self.sentinal), val)

    def convert_field(self, value, conversion):
        """
        Do conversion on the resulting object.

        supported conversions:
            'b': keep the parameter only if bool(value) is True.
            'v': keep both the parameter and its corresponding value,
                 the default mode.
        """
        if value[0] is self.sentinal:
            return string.Formatter.convert_field(self, value[1], conversion)
        if conversion is None:
            conversion = "v"
        if conversion == "v":
            return "" if value[1] is None else " ".join(value)
        if conversion == "b":
            return value[0] if bool(value[1]) else ""
        raise ValueError("Unknown conversion specifier {}".format(conversion))


QEMU_IMG_BINARY = utils_path.find_command("qemu-img")
qemu_img_parameters = {
    "image_format": "-f",
    "backing_file": "-b",
    "backing_format": "-F",
    "unsafe": "-u",
    "quiet": "-q",
    "options": "-o",
    "secret_object": "",
    "tls_creds_object": "",
    "image_opts": "--image-opts",
    "check_repair": "-r",
    "output_format": "--output",
    "force_share": "-U",
    "resize_preallocation": "--preallocation",
    "resize_shrink": "--shrink",
    "convert_compressed": "-c",
    "cache_mode": "-t",
    "source_cache_mode": "-T",
    "target_image_format": "-O",
    "convert_sparse_size": "-S",
    "rate_limit": "-r",
    "convert_target_is_zero": "--target-is-zero",
    "convert_backing_file": "-B",
    "commit_drop": "-d",
    "compare_strict_mode": "-s",
    "compare_second_image_format": "-F",
    "backing_chain": "--backing-chain",
}
cmd_formatter = _ParameterAssembler(qemu_img_parameters)


def get_qemu_img_object_repr(sec_opts, obj_type="secret"):
    mapping = {
        "secret": "--object secret,id={name}",
        "cookie": "--object secret,id={name}",
        "tls-creds-x509": "--object tls-creds-x509,id={name},endpoint=client,dir={dir}",
    }

    obj_str = mapping.get(obj_type)
    if obj_str is None:
        raise ValueError(f"Unknown object type {obj_type}")

    if "format" in sec_opts:
        obj_str += ",format={format}"
    if "file" in sec_opts:
        obj_str += ",file={file}"
    elif obj_type != "tls-creds-x509":
        obj_str += ",data={data}"

    return obj_str.format(**sec_opts)


def get_qemu_image_json_repr(image_opts):
    """Generate image json representation."""
    return "'json:%s'" % json.dumps(image_opts)


def get_qemu_image_opts_repr(image_opts):
    """Generate image-opts."""

    def _dict_to_dot(dct):
        """Convert dictionary to dot representation."""
        flat = []
        prefix = []
        stack = [dct.items()]
        while stack:
            it = stack[-1]
            try:
                key, value = next(it)
            except StopIteration:
                if prefix:
                    prefix.pop()
                stack.pop()
                continue
            if isinstance(value, collections.Mapping):
                prefix.append(key)
                stack.append(value.items())
            else:
                flat.append((".".join(prefix + [key]), value))
        return flat

    return ",".join(
        ["%s=%s" % (attr, value) for attr, value in _dict_to_dot(image_opts)]
    )


def parse_qemu_img_options(image_spec):
    options = [
        "preallocation",
        "cluster_size",
        "lazy_refcounts",
        "compat",
        "extent_size_hint",
        "compression_type",
    ]
    opts = {k: v for k, v in image_spec.items() if k in options and v is not None}

    # TODO: data_file, backing_file
    return opts


def get_qemu_image_repr(image_config, output=None):
    image_spec = image_config["spec"]

    mapping = {
        "uri": lambda i: image_spec["volume"]["spec"]["uri"],
        "json": get_qemu_image_json_repr,
        "opts": get_qemu_image_opts_repr,
    }

    auth_opts, sec_opts, img_opts = get_image_opts(image_config)
    func = mapping.get(output)
    if func is None:
        func = mapping["json"] if auth_opts or sec_opts else mapping["uri"]
    image_repr = func(img_opts)

    objs = []
    if auth_opts:
        objs.append(get_qemu_img_object_repr(auth_opts))
    if sec_opts:
        objs.append(get_qemu_img_object_repr(sec_opts))
    objs_repr = " ".join(objs)

    opts_repr = ""
    options = parse_qemu_img_options(image_spec)
    if auth_opts:
        # FIXME: cookie-secret
        if "file" in auth_opts:
            options["password-secret"] = auth_opts["name"]
        elif "dir" in auth_opts:
            options["tls-creds"] = auth_opts["name"]
        else:
            options["key-secret"] = auth_opts["name"]

    if sec_opts:
        image_format = image_spec["format"]
        if image_format == "luks":
            key = "password-secret" if "file" in sec_opts else "key-secret"
        elif image_format == "qcow2":
            key = "encrypt.key-secret"
            options.update({f"encrypt.{k}": v for k, v in sec_opts.items()})
        else:
            raise ValueError(f"Encryption of a {image_format} image is not supported")
        options[key] = sec_opts["name"]
    opts_repr = ",".join([f"{k}={v}" for k, v in options.items()])

    return objs_repr, opts_repr, image_repr


def _clone(logical_image_config):
    logical_image_meta = logical_image_config["meta"]
    logical_image_spec = logical_image_config["spec"]
    tag = arguments.pop("target", None)
    image_names = [tag] if tag else logical_image_meta["topology"]["value"]

    for image_name in image_names:
        image_config = logical_image_spec["images"][image_name]
        backup_image_name = image_config["spec"]["backup"]
        _dump_data(logical_image_config, image_name, backup_image_name)


def _create(logical_image_config, arguments):
    def _dd(image_tag):
        qemu_img_cmd = ""
        image_config = logical_image_spec["images"][image_tag]
        volume_config = image_config["spec"]["volume"]

        if image_config["spec"]["format"] == "raw":
            count = normalize_data_size(
                int(volume_config["spec"]["size"]), order_magnitude="M"
            )
            qemu_img_cmd = "dd if=/dev/zero of=%s count=%s bs=1M" % (
                volume_config["spec"]["path"],
                count,
            )

    def _qemu_img_create(image_tag):
        image_config = logical_image_spec["images"][image_tag]
        image_spec = image_config["spec"]
        volume_config = image_spec["volume"]

        # FIXME: Create the file on worker
        encryption = image_spec.get("encryption", {})
        if encryption.get("storage") == "file":
            # FIXME:
            os.makedirs(os.path.dirname(encryption["file"]), exist_ok=True)
            with open(encryption["file"], "w") as fd:
                fd.write(encryption["data"])

        cmd_dict = {
            "image_format": image_spec["format"],
            "image_size": int(volume_config["spec"]["size"]),
        }

        secret_objects = list()
        base_tag = image_spec.get("backing")
        if base_tag is not None:
            base_image_config = logical_image_spec["images"][base_tag]
            objs_repr, _, cmd_dict["backing_file"] = get_qemu_image_repr(
                base_image_config, image_repr_format
            )
            if objs_repr:
                secret_objects.append(objs_repr)
            cmd_dict["backing_format"] = base_image_config["spec"]["format"]

            # Add all backings' secret and access auth objects
            for tag in image_names:
                if tag == base_tag:
                    break
                config = logical_image_spec["images"][tag]
                objs_repr, _, _ = get_qemu_image_repr(config)
                if objs_repr:
                    secret_objects.append(objs_repr)

        objs_repr, options_repr, cmd_dict["image_filename"] = get_qemu_image_repr(
            image_config, "uri"
        )
        if objs_repr:
            secret_objects.append(objs_repr)
        if options_repr:
            cmd_dict["options"] = options_repr

        cmd_dict["secret_object"] = " ".join(secret_objects)

        qemu_img_cmd = (
            qemu_image_binary + " " + cmd_formatter.format(create_cmd, **cmd_dict)
        )

        LOG.info(f"Create image with command: {qemu_img_cmd}")
        process.run(qemu_img_cmd, shell=True, verbose=False, ignore_status=False)

    create_cmd = (
        "create {secret_object} {image_format} "
        "{backing_file} {backing_format} {unsafe!b} {options} "
        "{image_filename} {image_size}"
    )

    qemu_image_binary = arguments.pop("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.pop("repr", None)
    logical_image_meta = logical_image_config["meta"]
    logical_image_spec = logical_image_config["spec"]

    tag = arguments.pop("target", None)
    image_names = [tag] if tag else logical_image_meta["topology"]["value"]
    for image_name in image_names:
        _qemu_img_create(image_name)


def _dd(logical_image_config, source_image_name, target_image_name, bs=None, count=None, skip=None, rawcopy=False):
    """
    Qemu image dd wrapper, like dd command, clone the image.
    Please use convert to convert one format of image to another.
    :param output: of=output
    :param bs: bs=bs, the block size in bytes
    :param count: count=count, count of blocks copied
    :param skip: skip=skip, count of blocks skipped
    :param rawcopy: True to do a raw copy no matter if the image is
                    in raw format or not
    :return: process.CmdResult object containing the result of the
             command
    """
    logical_image_meta = logical_image_config["meta"]
    logical_image_spec = logical_image_config["spec"]
    source_image_config = logical_image_spec["images"][source_image_name]
    target_image_config = logical_image_spec["images"][target_image_name]

    dd_cmd = (
        "dd {secret_object} {tls_creds_object} {image_format} "
        "{target_image_format} {block_size} {count} {skip} "
        "if={image_filename} of={target_image_filename}"
    )

    cmd_dict = {
        "image_format": source_image_config["spec"]["format"],
        "target_image_format": target_image_config["spec"]["format"],
        "block_size": f"bs={bs}" if bs is not None else "",
        "count": f"count={count}" if count is not None else "",
        "skip": f"skip={skip}" if skip is not None else "",
    }

    # TODO: use raw copy(-f raw -O raw) and ignore image secret and format
    # for qemu-img dd cannot support setting secret for the target image
    auth_opts, sec_opts, img_opts = get_image_opts(source_image_config)
    raw_copy = True if rawcopy or sec_opts else False
    if raw_copy:
        cmd_dict["image_format"] = cmd_dict["target_image_format"] = "raw"
        source_image_config["spec"]["format"] = "raw"
        target_image_config["spec"]["format"] = "raw"
        source_image_config["spec"].pop("encryption")
        target_image_config["spec"].pop("encryption")

    out_format = "json" if auth_opts else "uri"
    objs_repr, options_repr, cmd_dict["image_filename"] = get_qemu_image_repr(
        source_image_config, out_format
    )

    # target image supports uri only
    _, _, cmd_dict["target_image_filename"] = get_qemu_image_repr(
        target_image_config, "uri"
    )

    secret_objects = list()
    if objs_repr:
        secret_objects.append(objs_repr)

    base_tag = source_image_config["spec"].get("backing")
    image_names = logical_image_meta["topology"]["value"]
    if base_tag is not None:
        # Add all backings' secret objects
        for tag in image_names:
            config = logical_image_spec["images"][tag]
            objs_repr, _, _ = get_qemu_image_repr(config)
            if objs_repr:
                secret_objects.append(objs_repr)
            if tag == base_tag:
                break

    if secret_objects:
        cmd_dict["secret_object"] = " ".join(secret_objects)

    dd_cmd = (
        QEMU_IMG_BINARY + " " + cmd_formatter.format(dd_cmd, **cmd_dict)
    )
    process.run(dd_cmd, shell=True, verbose=False, ignore_status=False)


def _dump_data(logical_image_config, source_image_name, target_image_name):
    source_image_config = logical_image_config["spec"]["images"][source_image_name]
    target_image_config = logical_image_config["spec"]["images"][target_image_name]
    source_volume_config = source_image_config["spec"]["volume"]
    target_volume_config = target_image_config["spec"]["volume"]

    if source_volume_config["meta"]["volume-type"] == "file":
        # Copy the file for a file-based volume
        shutil.copyfile(source_volume_config["spec"]["uri"],
                        target_volume_config["spec"]["uri"])
    else:
        # Use qemu-img dd to dump data for other types of volumes
        _dd(logical_image_config, source_image_name, target_image_name)


def _backup(logical_image_config, arguments):
    logical_image_meta = logical_image_config["meta"]
    logical_image_spec = logical_image_config["spec"]
    tag = arguments.pop("target", None)
    image_names = [tag] if tag else logical_image_meta["topology"]["value"]

    for image_name in image_names:
        image_config = logical_image_spec["images"][image_name]
        backup_image_name = image_config["spec"]["backup"]
        _dump_data(logical_image_config, image_name, backup_image_name)


def _restore(logical_image_config, arguments):
    logical_image_meta = logical_image_config["meta"]
    logical_image_spec = logical_image_config["spec"]
    tag = arguments.pop("target", None)
    image_names = [tag] if tag else logical_image_meta["topology"]["value"]

    for image_name in image_names:
        image_config = logical_image_spec["images"][image_name]
        backup_image_name = image_config["spec"]["backup"]
        _dump_data(logical_image_config, backup_image_name, image_name)


def _snapshot(image_config, arguments):
    pass


def _rebase(image_config, arguments):
    qemu_image_binary = arguments.pop("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.pop("repr", None)
    backing = arguments.pop("source")
    backing_config = image_config["spec"]["images"][backing]
    target = arguments.pop("target")
    target_config = image_config["spec"]["images"][target]

    rebase_cmd = (
        "rebase {secret_object} {image_format} {cache_mode} "
        "{source_cache_mode} {unsafe!b} {options} "
        "{backing_file} {backing_format} {image_filename}"
    )

    cmd_dict = {
        "image_format": target_config["spec"]["format"],
        "cache_mode": arguments.pop("cache_mode", None),
        "source_cache_mode": arguments.pop("source_cache_mode", None),
        "unsafe": arguments.pop("unsafe", False),
        "backing_format": backing_config["spec"]["format"],
    }

    secret_objects = list()
    obj_repr, options_repr, cmd_dict["image_filename"] = get_qemu_image_repr(
        target_config, image_repr_format
    )
    if obj_repr or image_repr_format in ["opts", "json"]:
        secret_objects.append(obj_repr)
        cmd_dict.pop("image_format")
    if options_repr:
        cmd_dict["options"] = options_repr

    obj_repr, _, cmd_dict["backing_file"] = get_qemu_image_repr(backing_config, None)
    if obj_repr:
        secret_objects.append(obj_repr)

    # Add all backings' secret and access auth objects
    for tag in image_config["meta"]["topology"]["value"]:
        if tag == backing:
            break
        config = image_config["spec"]["images"][tag]
        objs_repr, _, _ = get_qemu_image_repr(config)
        if objs_repr:
            secret_objects.append(objs_repr)

    cmd_dict["secret_object"] = " ".join(secret_objects)

    qemu_img_cmd = (
        qemu_image_binary + " " + cmd_formatter.format(rebase_cmd, **cmd_dict)
    )

    LOG.info(f"Rebase {target} onto {backing} by command: {qemu_img_cmd}")
    process.run(qemu_img_cmd, shell=True, verbose=False, ignore_status=False)


def _commit(image_config, arguments):
    pass


def _check(image_config, arguments):
    check_cmd = (
        "check {secret_object} {quiet!b} {image_format} "
        "{check_repair} {force_share!b} {output_format} "
        "{source_cache_mode} {image_opts} {image_filename}"
    )

    qemu_image_binary = arguments.pop("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.pop("repr", None)
    target = arguments.pop("target", image_config["meta"]["name"])
    target_config = image_config["spec"]["images"][target]

    cmd_dict = {
        "quiet": arguments.pop("quiet", False),
        "image_format": target_config["spec"]["format"],
        "check_repair": arguments.pop("repair", None),
        "force_share": arguments.pop("force", False),
        "output_format": arguments.pop("output", "human"),
        "source_cache_mode": arguments.pop("source_cache_mode", None),
    }

    secret_objects = list()
    obj_repr, _, cmd_dict["image_filename"] = get_qemu_image_repr(
        target_config, image_repr_format
    )
    if obj_repr:
        secret_objects.append(obj_repr)

    image_list = image_config["meta"]["topology"]["value"]
    if target in image_list:
        # Add all backings' secret and access auth objects
        for tag in image_list:
            if tag == target:
                break
            config = image_config["spec"]["images"][tag]
            objs_repr, _, _ = get_qemu_image_repr(config)
            if objs_repr:
                secret_objects.append(objs_repr)
    cmd_dict["secret_object"] = " ".join(secret_objects)

    if obj_repr or image_repr_format in ["opts", "json"]:
        cmd_dict.pop("image_format")
    if image_repr_format == "opts":
        cmd_dict["image_opts"] = cmd_dict.pop("image_filename")

    qemu_img_cmd = qemu_image_binary + " " + cmd_formatter.format(check_cmd, **cmd_dict)

    LOG.info(f"Check {target} with command: {qemu_img_cmd}")
    cmd_result = process.run(
        qemu_img_cmd, shell=True, verbose=True, ignore_status=False
    )
    return cmd_result.stdout_text


def _info(image_config, arguments):
    info_cmd = (
        "info {secret_object} {image_format} {backing_chain!b} "
        "{force_share!b} {output_format} {image_opts} {image_filename}"
    )

    qemu_image_binary = arguments.pop("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.pop("repr", None)
    target = arguments.pop("target", image_config["meta"]["name"])
    target_config = image_config["spec"]["images"][target]

    cmd_dict = {
        "image_format": target_config["spec"]["format"],
        "backing_chain": arguments.pop("backing_chain", False),
        "force_share": arguments.pop("force", False),
        "output_format": arguments.pop("output", "human"),
    }

    secret_objects = list()
    obj_repr, _, cmd_dict["image_filename"] = get_qemu_image_repr(
        target_config, image_repr_format
    )
    if obj_repr:
        secret_objects.append(obj_repr)

    image_list = image_config["meta"]["topology"]["value"]
    if target in image_list:
        # Add all backings' secret and access auth objects
        for tag in image_list:
            if tag == target:
                break
            config = image_config["spec"]["images"][tag]
            objs_repr, _, _ = get_qemu_image_repr(config)
            if objs_repr:
                secret_objects.append(objs_repr)
    cmd_dict["secret_object"] = " ".join(secret_objects)

    if obj_repr or image_repr_format in ["opts", "json"]:
        cmd_dict.pop("image_format")

    if image_repr_format == "opts":
        cmd_dict["image_opts"] = cmd_dict.pop("image_filename")

    qemu_img_cmd = qemu_image_binary + " " + cmd_formatter.format(info_cmd, **cmd_dict)

    LOG.info(f"Query info for {target} with command: {qemu_img_cmd}")
    cmd_result = process.run(
        qemu_img_cmd, shell=True, verbose=True, ignore_status=False
    )
    return cmd_result.stdout_text


_qemu_image_handlers = {
    "create": _create,
    "clone": _clone,
    "backup": _backup,
    "restore": _restore,
    "rebase": _rebase,
    "snapshot": _snapshot,
    "commit": _commit,
    "check": _check,
    "info": _info,
}


def get_qemu_image_handler(cmd):
    return _qemu_image_handlers.get(cmd)
