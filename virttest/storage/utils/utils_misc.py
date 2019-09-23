import os
import json

from gluster import gfapi

from avocado.utils import genio
from avocado.utils import process

STORAGE_POOL_ROOT_DIR = '/tmp/avocado'


def make_pool_base_dir(protocol):
    base_dir = os.path.join(STORAGE_POOL_ROOT_DIR, protocol)
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    elif not os.path.isdir(base_dir):
        raise TypeError("Storage pool file '%s' not a directory" % base_dir)
    return base_dir


def get_volume_capacity(uri):
    cmd = "qemu-img info {url} --output=json".format(url=uri)
    out = process.system_output(cmd, shell=True, ignore_status=False)
    out_json = json.loads(out)
    return out_json.get("virtual-size"), out_json.get("actual-size")


def wipe_volume(volume):
    cmd = "qemu-img create %s %s" % (volume.url, volume.size)
    return process.system(cmd, shell=True, ignore_status=False)


def create_volume(volume):
    if volume.protocol == "icssi":
        return
    options = volume.generate_qemu_img_options()
    cmd = "qemu-img create %s %s %s" % (options, volume.url, volume.size)
    process.system(cmd, shell=True, ignore_status=False)


def remove_volume(volume):
    if volume.pool.protocol == "iscsi":
        pass
    elif volume.pool.protocol == "ceph":
        # storage_volume.pool._volume.remove()
        pass
    os.remove(volume.entry_point)


def write_volume_file(volume):
    return genio.write_one_line(volume.entry_point, volume.url)


def list_files(root_dir):
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            yield os.path.join(root, f)
        for d in dirs:
            list_files(os.path.join(root, d))


def list_files_in_gluster_volume(volume, root_dir):
    if not isinstance(volume, gfapi.Volume):
        raise TypeError(
            "storage_volume '%s' is '%s', it's not a instance of '%s'" %
            (volume, type(volume), type(
                gfapi.Volume)))

    for root, dirs, files in volume.walk(root_dir):
        for f in files:
            yield os.path.join(root, f)
        for d in dirs:
            list_files_in_gluster_volume(volume, os.path.join(root, d))


def convert2bool(value):
    if value in ("yes", "on", "true"):
        return True
    elif value in ("no", "off", "false"):
        return False
    else:
        return bool(value)


def format_volume_to_qcow2(vol):
    cmd = "qemu-img create -f qcow2"
    if vol.backing is not None:
        cmd += " -b %s" % vol.backing.get_path()
        cmd += " -F %s" % vol.backing.fmt.type
    options = [
        "compat",
        "encryption",
        "cluster_size",
        "preallocation",
        "lazy_refcounts",
        "nocow"]
    for option in options:
        value = getattr(vol.fmt, option)
        if value is not None:
            options.append("%s=%s" % (option, value))
    str_options = ",".join(options)
    if str_options:
        cmd += " -o %s" % str_options
    cmd += " %s" % vol.get_path()
    cmd += " %s" % vol.fmt.size
    return process.system(cmd, shell=True, ignore_status=False)


def format_volume_to_raw(vol):
    cmd = "qemu-img create -f raw"
    if vol.fmt.preallocation:
        cmd += " -o preallocation=%s" % vol.fmt.preallocation
    cmd += " %s %s" % (vol.get_path(), vol.size)
    return process.system(cmd, shell=True, ignore_status=False)


def format_volume_to_luks(vol):
    cmd = "qemu-img create -f luks --object secret,data='%s',id=%s  -o key-secret=%s %s %s" % (
        vol.fmt.key_secret.data, vol.fmt.key_secret.id, vol.fmt.key_secret.id, vol.get_path(), vol.fmt.size)
    return process.system(cmd, shell=True, ignore_status=False)
