import collections
import json
import logging
import os
import re
import string

from virttest.utils_numeric import normalize_data_size
from virttest.vt_utils.image.qemu import get_image_opts

from avocado.utils import path as utils_path
from avocado.utils import process

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


def get_qemu_virt_image_json_repr(virt_image_opts):
    """Generate image json representation."""
    return "'json:%s'" % json.dumps(virt_image_opts)


def get_qemu_virt_image_opts_repr(virt_image_opts):
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
        ["%s=%s" % (attr, value) for attr, value in _dict_to_dot(virt_image_opts)]
    )


def parse_qemu_img_options(virt_image_spec):
    options = [
        "preallocation",
        "cluster_size",
        "lazy_refcounts",
        "compat",
        "extent_size_hint",
        "compression_type",
    ]
    opts = {k: v for k, v in virt_image_spec.items() if k in options and v is not None}

    # TODO: data_file, backing_file
    return opts


def get_qemu_virt_image_repr(virt_image_config, output=None):
    virt_image_spec = virt_image_config["spec"]

    mapping = {
        "uri": lambda i: virt_image_spec["volume"]["spec"]["uri"],
        "json": get_qemu_virt_image_json_repr,
        "opts": get_qemu_virt_image_opts_repr,
    }

    auth_opts, sec_opts, img_opts = get_image_opts(virt_image_config)
    func = mapping.get(output)
    if func is None:
        func = mapping["json"] if auth_opts or sec_opts else mapping["uri"]
    virt_image_repr = func(img_opts)

    objs = []
    if auth_opts:
        objs.append(get_qemu_img_object_repr(auth_opts))
    if sec_opts:
        objs.append(get_qemu_img_object_repr(sec_opts))
    objs_repr = " ".join(objs)

    opts_repr = ""
    options = parse_qemu_img_options(virt_image_spec)
    if auth_opts:
        # FIXME: cookie-secret
        if "file" in auth_opts:
            options["password-secret"] = auth_opts["name"]
        elif "dir" in auth_opts:
            options["tls-creds"] = auth_opts["name"]
        else:
            options["key-secret"] = auth_opts["name"]

    if sec_opts:
        virt_image_format = virt_image_spec["format"]
        if virt_image_format == "luks":
            key = "password-secret" if "file" in sec_opts else "key-secret"
        elif virt_image_format == "qcow2":
            key = "encrypt.key-secret"
            options.update({f"encrypt.{k}": v for k, v in sec_opts.items()})
        else:
            raise ValueError(
                f"Encryption of a {virt_image_format} image is not supported"
            )
        options[key] = sec_opts["name"]
    opts_repr = ",".join([f"{k}={v}" for k, v in options.items()])

    return objs_repr, opts_repr, virt_image_repr


def _create(image_config, arguments):
    def _dd(image_tag):
        qemu_img_cmd = ""
        virt_image_config = image_spec["virt-images"][image_tag]
        volume_config = virt_image_config["spec"]["volume"]

        if virt_image_config["spec"]["format"] == "raw":
            count = normalize_data_size(
                int(volume_config["spec"]["size"]), order_magnitude="M"
            )
            qemu_img_cmd = "dd if=/dev/zero of=%s count=%s bs=1M" % (
                volume_config["spec"]["path"],
                count,
            )

    def _qemu_img_create(virt_image_tag):
        qemu_img_cmd = ""
        virt_image_config = image_spec["virt-images"][virt_image_tag]
        virt_image_spec = virt_image_config["spec"]
        volume_config = virt_image_config["spec"]["volume"]

        # Prepare the secret data storage file
        encryption = virt_image_spec.get("encryption", {})
        if encryption.get("storage") == "file":
            # FIXME:
            os.makedirs(os.path.dirname(encryption["file"]), exist_ok=True)
            with open(encryption["file"], "w") as fd:
                fd.write(encryption["data"])

        cmd_dict = {
            "image_format": virt_image_spec["format"],
            "image_size": int(volume_config["spec"]["size"]),
        }

        secret_objects = list()
        base_tag = virt_image_spec.get("backing")
        if base_tag is not None:
            base_virt_image_config = image_spec["virt-images"][base_tag]
            objs_repr, _, cmd_dict["backing_file"] = get_qemu_virt_image_repr(
                base_virt_image_config, image_repr_format
            )
            if objs_repr:
                secret_objects.append(objs_repr)
            cmd_dict["backing_format"] = base_virt_image_config["spec"]["format"]

            # Add all backings' secret and access auth objects
            for tag in list(image_meta["topology"].values())[0]:
                if tag == base_tag:
                    break
                config = image_spec["virt-images"][tag]
                objs_repr, _, _ = get_qemu_virt_image_repr(config)
                if objs_repr:
                    secret_objects.append(objs_repr)

        objs_repr, options_repr, cmd_dict["image_filename"] = get_qemu_virt_image_repr(
            virt_image_config, "uri"
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
    image_meta = image_config["meta"]
    image_spec = image_config["spec"]

    tag = arguments.pop("target", None)
    virt_images = [tag] if tag else list(image_meta["topology"].values())[0]
    for tag in virt_images:
        _qemu_img_create(tag)


def _snapshot(image_config, arguments):
    pass


def _rebase(image_config, arguments):
    qemu_image_binary = arguments.pop("qemu_img_binary", QEMU_IMG_BINARY)
    image_repr_format = arguments.pop("repr", None)
    backing = arguments.pop("source")
    backing_config = image_config["spec"]["virt-images"][backing]
    target = arguments.pop("target")
    target_config = image_config["spec"]["virt-images"][target]

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
    obj_repr, options_repr, cmd_dict["image_filename"] = get_qemu_virt_image_repr(
        target_config, image_repr_format
    )
    if obj_repr or image_repr_format in ["opts", "json"]:
        secret_objects.append(obj_repr)
        cmd_dict.pop("image_format")
    if options_repr:
        cmd_dict["options"] = options_repr

    obj_repr, _, cmd_dict["backing_file"] = get_qemu_virt_image_repr(
        backing_config, None
    )
    if obj_repr:
        secret_objects.append(obj_repr)

    # Add all backings' secret and access auth objects
    for tag in list(image_config["meta"]["topology"].values())[0]:
        if tag == backing:
            break
        config = image_config["spec"]["virt-images"][tag]
        objs_repr, _, _ = get_qemu_virt_image_repr(config)
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
    target_config = image_config["spec"]["virt-images"][target]

    cmd_dict = {
        "quiet": arguments.pop("quiet", False),
        "image_format": target_config["spec"]["format"],
        "check_repair": arguments.pop("repair", None),
        "force_share": arguments.pop("force", False),
        "output_format": arguments.pop("output", "human"),
        "source_cache_mode": arguments.pop("source_cache_mode", None),
    }

    secret_objects = list()
    obj_repr, _, cmd_dict["image_filename"] = get_qemu_virt_image_repr(
        target_config, image_repr_format
    )
    if obj_repr:
        secret_objects.append(obj_repr)

    image_list = list(image_config["meta"]["topology"].values())[0]
    if target in image_list:
        # Add all backings' secret and access auth objects
        for tag in image_list:
            if tag == target:
                break
            config = image_config["spec"]["virt-images"][tag]
            objs_repr, _, _ = get_qemu_virt_image_repr(config)
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
    target_config = image_config["spec"]["virt-images"][target]

    cmd_dict = {
        "image_format": target_config["spec"]["format"],
        "backing_chain": arguments.pop("backing_chain", False),
        "force_share": arguments.pop("force", False),
        "output_format": arguments.pop("output", "human"),
    }

    secret_objects = list()
    obj_repr, _, cmd_dict["image_filename"] = get_qemu_virt_image_repr(
        target_config, image_repr_format
    )
    if obj_repr:
        secret_objects.append(obj_repr)

    image_list = list(image_config["meta"]["topology"].values())[0]
    if target in image_list:
        # Add all backings' secret and access auth objects
        for tag in image_list:
            if tag == target:
                break
            config = image_config["spec"]["virt-images"][tag]
            objs_repr, _, _ = get_qemu_virt_image_repr(config)
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
    "rebase": _rebase,
    "snapshot": _snapshot,
    "commit": _commit,
    "check": _check,
    "info": _info,
}


def get_qemu_image_handler(cmd):
    return _qemu_image_handlers.get(cmd)
